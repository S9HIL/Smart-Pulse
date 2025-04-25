"""
Instagram Automation Blueprint
Handles Instagram direct messaging automation
"""

import os
import logging
import uuid
import time
import threading
import json
from datetime import datetime
from flask import Blueprint, request, render_template, jsonify, redirect, url_for
from instagrapi import Client
from instagrapi.exceptions import LoginRequired, ClientError, ClientLoginRequired

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create blueprint
instagram_bp = Blueprint('instagram', __name__, template_folder='templates')

# Global variables
user_batches = {}  # Store batch information
stop_flags = {}    # Control message sending
clients = {}       # Store Instagram client instances
active_batches = {}  # Track active batches

@instagram_bp.route('/')
def index():
    """Instagram automation main page"""
    return render_template('instagram/index.html')

@instagram_bp.route('/api/batches')
def get_batches():
    """Get all active message batches"""
    batches_list = []
    
    for batch_id, batch_info in active_batches.items():
        batches_list.append({
            'batch_id': batch_id,
            'target': batch_info.get('target', 'Unknown'),
            'target_type': batch_info.get('target_type', 'Unknown'),
            'status': 'Running' if not stop_flags.get(batch_id, True) else 'Stopped',
            'created_at': batch_info.get('created_at', 'Unknown'),
            'message_count': len(user_batches.get(batch_id, [])),
            'username': batch_info.get('username', 'Unknown')
        })
    
    return jsonify({"success": True, "batches": batches_list})

@instagram_bp.route('/api/send_message', methods=['POST'])
def send_message():
    """Start sending Instagram messages"""
    try:
        # Extract form data
        username = request.form.get('username')
        password = request.form.get('password')
        target = request.form.get('target')
        target_type = request.form.get('target_type')  # 'inbox' or 'group'
        message_prefix = request.form.get('message_prefix', '')
        delay_time = int(request.form.get('delay_time', 5))
        messages_text = request.form.get('messages', '')
        
        # Basic validation
        if not all([username, password, target, target_type]):
            return jsonify({"success": False, "message": "Missing required fields. Please fill in all required fields."})
        
        # Process messages from text field or file
        messages = []
        
        # Check for message file first
        message_file = request.files.get('message_file')
        if message_file:
            try:
                messages = message_file.read().decode('utf-8').splitlines()
                messages = [msg.strip() for msg in messages if msg.strip()]
            except Exception as e:
                logger.error(f"Error processing message file: {str(e)}")
                return jsonify({"success": False, "message": f"Error processing message file: {str(e)}"})
        # If no file or empty file, try messages text field
        elif messages_text:
            messages = [msg.strip() for msg in messages_text.strip().split('\n') if msg.strip()]
        
        if not messages:
            return jsonify({"success": False, "message": "No messages found. Please provide messages either in the text area or upload a file."})
            
        # Generate batch ID
        batch_id = str(uuid.uuid4())
        user_batches[batch_id] = []
        stop_flags[batch_id] = False
        
        # Create and login Instagram client
        client = Client()
        try:
            logger.info(f"Attempting to login with username: {username}")
            
            # Set client settings for better reliability
            client.delay_range = [1, 3]
            client.request_timeout = 30
            
            # Try to authenticate with a delay and proper error handling
            max_retries = 3
            retry_count = 0
            login_success = False
            
            while retry_count < max_retries and not login_success:
                try:
                    client.login(username, password)
                    login_success = True
                    logger.info(f"Successfully logged in as {username}")
                except ClientLoginRequired as e:
                    logger.error(f"Instagram login error (attempt {retry_count+1}): {str(e)}")
                    retry_count += 1
                    if retry_count < max_retries:
                        logger.info(f"Waiting 3 seconds before retry...")
                        time.sleep(3)
                except Exception as e:
                    logger.error(f"Unexpected error during login: {str(e)}")
                    raise
            
            if not login_success:
                return jsonify({
                    "success": False,
                    "message": "Failed to login after multiple attempts. Please check your credentials and try again."
                })
                
            clients[batch_id] = client
            
            # Store active batch info
            active_batches[batch_id] = {
                'username': username,
                'target': target,
                'target_type': target_type,
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'delay_time': delay_time,
                'message_prefix': message_prefix
            }
            
            # Validate target based on type
            if target_type == 'inbox':
                try:
                    user_id = client.user_id_from_username(target)
                    active_batches[batch_id]['target_id'] = user_id
                except Exception as e:
                    logger.error(f"Error finding user {target}: {str(e)}")
                    return jsonify({
                        "success": False,
                        "message": f"Target username '{target}' not found"
                    })
            elif target_type == 'group':
                try:
                    # For group chat, target should be thread_id
                    # Check if it's numeric
                    if not target.isdigit():
                        return jsonify({
                            "success": False,
                            "message": "Group chat ID should be numeric"
                        })
                    active_batches[batch_id]['target_id'] = target
                except Exception as e:
                    logger.error(f"Error with group ID {target}: {str(e)}")
                    return jsonify({
                        "success": False,
                        "message": f"Invalid group chat ID: {str(e)}"
                    })
            else:
                return jsonify({
                    "success": False,
                    "message": "Invalid target type. Choose either 'inbox' or 'group'"
                })
                
            # Start message sending process
            start_message_sending(
                batch_id=batch_id,
                client=client,
                username=username,
                password=password,
                target=target,
                target_type=target_type,
                message_prefix=message_prefix,
                messages=messages,
                delay_time=delay_time
            )
            
            # Return a JSON response with the batch_id
            # The frontend will handle the redirect
            return jsonify({
                "success": True,
                "message": "Message sending started successfully",
                "batch_id": batch_id
            })
            
        except (LoginRequired, ClientLoginRequired) as e:
            logger.error(f"Instagram login required: {str(e)}")
            return jsonify({
                "success": False,
                "message": "Instagram login required. Your session may have expired."
            })
        except Exception as e:
            logger.error(f"Instagram login failed: {str(e)}")
            return jsonify({
                "success": False,
                "message": f"Login failed: {str(e)}"
            })
    except Exception as e:
        logger.error(f"Error in send_message: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"An error occurred: {str(e)}"
        })

@instagram_bp.route('/dashboard')
def dashboard():
    """Instagram automation dashboard"""
    return render_template('instagram/dashboard.html')

@instagram_bp.route('/messages/<batch_id>')
def view_messages(batch_id):
    """View messages for a specific batch"""
    if batch_id not in user_batches:
        return render_template('instagram/message_output.html', 
                             messages=[], 
                             batch_id=batch_id, 
                             error="Batch ID not found")
    
    messages = user_batches.get(batch_id, [])
    is_stopped = stop_flags.get(batch_id, True)
    batch_info = active_batches.get(batch_id, {})
    
    return render_template('instagram/message_output.html', 
                          messages=messages, 
                          batch_id=batch_id, 
                          is_stopped=is_stopped,
                          batch_info=batch_info)

@instagram_bp.route('/api/batch/<batch_id>')
def get_batch_info(batch_id):
    """Get information about a specific batch"""
    if batch_id not in active_batches:
        return jsonify({
            "success": False,
            "message": "Batch not found"
        }), 404
    
    batch_info = active_batches[batch_id]
    messages = user_batches.get(batch_id, [])
    is_stopped = stop_flags.get(batch_id, True)
    
    # Count successful messages
    success_count = batch_info.get('sent_count', 0)
    if success_count == 0:
        # Count from messages as fallback
        success_count = len([msg for msg in messages if msg.get('status_class') == 'message-success'])
    
    return jsonify({
        "success": True,
        "batch_id": batch_id,
        "info": {
            "target": batch_info.get('target', 'Unknown'),
            "target_type": batch_info.get('target_type', 'Unknown'),
            "status": "Stopped" if is_stopped else "Running",
            "created_at": batch_info.get('created_at', 'Unknown'),
            "username": batch_info.get('username', 'Unknown'),
            "message_count": success_count,
            "message_prefix": batch_info.get('message_prefix', ''),
            "delay_time": batch_info.get('delay_time', 5)
        }
    })

@instagram_bp.route('/api/batch/<batch_id>/messages')
def get_batch_messages(batch_id):
    """Get messages for a specific batch"""
    if batch_id not in user_batches:
        return jsonify({
            "success": False,
            "message": "Batch not found"
        }), 404
    
    messages = user_batches.get(batch_id, [])
    # Filter sensitive info like passwords
    safe_messages = []
    for msg in messages:
        safe_msg = msg.copy()
        if 'password' in safe_msg:
            del safe_msg['password']
        safe_messages.append(safe_msg)
    
    return jsonify({
        "success": True,
        "batch_id": batch_id,
        "messages": safe_messages
    })

@instagram_bp.route('/api/batch/<batch_id>/stop', methods=['POST'])
def stop_message_sending(batch_id):
    """Stop message sending for a batch"""
    if batch_id in stop_flags:
        stop_flags[batch_id] = True
        
        # Add a status message
        if batch_id in user_batches:
            user_batches[batch_id].append({
                "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "message": "Message sending stopped by user",
                "status": "Stopped",
                "status_class": "message-stopped"
            })
            
        return jsonify({
            "success": True, 
            "message": "Message sending process stopped"
        })
    
    return jsonify({
        "success": False, 
        "message": "Invalid Batch ID"
    }), 404

@instagram_bp.route('/api/batch/<batch_id>/restart', methods=['POST'])
def restart_message_sending(batch_id):
    """Restart message sending for a batch"""
    if batch_id in clients and batch_id in active_batches:
        if not clients[batch_id]:
            return jsonify({
                "success": False, 
                "message": "Session expired. Please start a new batch."
            }), 400
            
        stop_flags[batch_id] = False
        client = clients[batch_id]
        batch_info = active_batches[batch_id]
        
        # Check if client is still connected
        try:
            # Test client connection
            try:
                client.get_timeline_feed()
            except (LoginRequired, ClientLoginRequired):
                # Re-login if needed
                client.login(batch_info.get('username'), batch_info.get('password'))
            
            # Start message sending again
            messages = [msg.get('original_message') for msg in user_batches.get(batch_id, []) 
                       if msg.get('original_message') and msg.get('status') != 'Sent']
            
            if not messages:
                return jsonify({
                    "success": False, 
                    "message": "No remaining messages to send"
                })
                
            # Add status message
            user_batches[batch_id].append({
                "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "message": "Message sending restarted",
                "status": "Info",
                "status_class": "message-info"
            })
            
            # Restart sending in background
            threading.Thread(
                target=send_messages_thread,
                args=(
                    batch_id,
                    client,
                    batch_info.get('target'),
                    batch_info.get('target_type'),
                    batch_info.get('message_prefix', ''),
                    messages,
                    batch_info.get('delay_time', 5)
                )
            ).start()
            
            return jsonify({
                "success": True, 
                "message": "Message sending restarted successfully"
            })
        except Exception as e:
            logger.error(f"Error restarting message sending: {str(e)}")
            return jsonify({
                "success": False, 
                "message": f"Error restarting: {str(e)}"
            })
    
    return jsonify({
        "success": False, 
        "message": "Invalid Batch ID or session expired"
    }), 404

# Helper functions
def start_message_sending(batch_id, client, username, password, target, target_type, message_prefix, messages, delay_time):
    """Start message sending process in a background thread"""
    logger.info(f"Starting Instagram message sending for batch: {batch_id}")
    
    # Store initial status message
    user_batches[batch_id].append({
        "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "username": username,
        "target": target,
        "message": "Starting message sending process",
        "status": "Info",
        "status_class": "message-info"
    })
    
    # Start sending thread
    threading.Thread(
        target=send_messages_thread,
        args=(batch_id, client, target, target_type, message_prefix, messages, delay_time)
    ).start()

def send_messages_thread(batch_id, client, target, target_type, message_prefix, messages, delay_time):
    """Send messages in a background thread"""
    try:
        logger.info(f"Message sending thread started for batch {batch_id}")
        
        # Get target ID
        target_id = None
        thread_id = None
        
        try:
            if target_type == 'inbox':
                target_id = client.user_id_from_username(target)
            else:  # group
                thread_id = target  # For group, target is the thread_id
        except Exception as e:
            error_msg = f"Error getting target ID: {str(e)}"
            logger.error(error_msg)
            user_batches[batch_id].append({
                "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "message": error_msg,
                "status": "Error",
                "status_class": "message-error"
            })
            return
        
        # Send messages
        for i, message in enumerate(messages):
            # Check if stopped
            if stop_flags.get(batch_id, True):
                logger.info(f"Message sending stopped for batch {batch_id}")
                break
                
            try:
                # Prepare message
                full_message = f"{message_prefix} {message}" if message_prefix else message
                
                # Send message
                if target_type == 'inbox':
                    result = client.direct_send(full_message, [target_id])
                else:  # group
                    result = client.direct_send(full_message, thread_ids=[thread_id])
                
                # Log success
                logger.info(f"Message sent to {target}: {full_message}")
                user_batches[batch_id].append({
                    "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    "message": full_message,
                    "target": target,
                    "status": "Sent",
                    "status_class": "message-success",
                    "original_message": message
                })
                
                # Update sent count in batch info
                if batch_id in active_batches:
                    active_batches[batch_id]['sent_count'] = active_batches[batch_id].get('sent_count', 0) + 1
                
                # Delay between messages
                time.sleep(delay_time)
                
            except Exception as e:
                error_msg = f"Error sending message: {str(e)}"
                logger.error(error_msg)
                user_batches[batch_id].append({
                    "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    "message": full_message,
                    "error": str(e),
                    "status": "Failed",
                    "status_class": "message-error",
                    "original_message": message
                })
                
                # If client error, wait longer
                if isinstance(e, ClientError):
                    logger.info("Client error, waiting 30 seconds before next attempt")
                    time.sleep(30)
                else:
                    time.sleep(delay_time * 2)  # Double delay on error
                    
        # Mark as completed
        logger.info(f"Message sending completed for batch {batch_id}")
        user_batches[batch_id].append({
            "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "message": "Message sending process completed",
            "status": "Completed",
            "status_class": "message-info"
        })
        
        # Update status
        stop_flags[batch_id] = True
        
    except Exception as e:
        logger.error(f"Error in message sending thread: {str(e)}")
        user_batches[batch_id].append({
            "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "message": f"Error in message sending thread: {str(e)}",
            "status": "Error",
            "status_class": "message-error"
        })
        
        # Update status
        stop_flags[batch_id] = True
