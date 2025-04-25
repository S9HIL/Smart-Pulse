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
instagram_bp = Blueprint('instagram', __name__, template_folder='../templates/instagram')

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
        batch_id = generate_batch_id()
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
            # Quick check if client is still logged in
            client.user_info_by_username(batch_info['username'])
        except Exception as e:
            logger.error(f"Client session expired: {str(e)}")
            return jsonify({
                "success": False,
                "message": "Instagram session expired. Please start a new batch."
            }), 400
        
        # Get unsent messages
        batch_data = user_batches.get(batch_id, [])
        unsent_messages = []
        
        if len(batch_data) > 0:
            # Find messages that weren't sent yet
            prefix = batch_info.get('message_prefix', '')
            
            # Get all sent messages to avoid duplicates
            sent_messages = [msg.get('message', '') for msg in batch_data 
                            if 'status_class' in msg and msg['status_class'] == 'message-success']
            
            # Extract the message content without prefix
            sent_content = []
            for msg in sent_messages:
                if prefix and msg.startswith(prefix):
                    sent_content.append(msg[len(prefix):])
                else:
                    sent_content.append(msg)
                    
            # Load the full message list from the original batch
            all_messages = batch_info.get('all_messages', [])
            
            # Find messages not yet sent
            for msg in all_messages:
                if msg not in sent_content:
                    unsent_messages.append(msg)
        
        if not unsent_messages:
            return jsonify({
                "success": False, 
                "message": "No unsent messages found in this batch."
            }), 400
        
        # Add restart message to log
        user_batches[batch_id].append({
            "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "message": f"Message sending restarted with {len(unsent_messages)} remaining messages",
            "status": "Restarted",
            "status_class": "message-restarted"
        })
        
        # Start message sending again
        start_message_sending(
            batch_id=batch_id,
            client=client,
            username=batch_info['username'],
            password=batch_info.get('password', ''),
            target=batch_info['target'],
            target_type=batch_info['target_type'],
            message_prefix=batch_info.get('message_prefix', ''),
            messages=unsent_messages,
            delay_time=batch_info.get('delay_time', 5)
        )
        
        logger.info(f"Message sending process restarted for batch: {batch_id}")
        
        return jsonify({
            "success": True, 
            "message": f"Message sending restarted for batch {batch_id}"
        })
        
    return jsonify({
        "success": False, 
        "message": "Batch ID not found"
    }), 404

@instagram_bp.route('/api/batch/<batch_id>/delete', methods=['POST'])
def delete_batch(batch_id):
    """Delete a batch completely"""
    from app import db
    from models import InstagramSession
    
    success_memory = False
    success_db = False
    
    # Clean up in-memory data
    if batch_id in active_batches:
        # Stop the batch if it's running
        if batch_id in stop_flags:
            stop_flags[batch_id] = True
            
        # Clean up client
        if batch_id in clients:
            try:
                if clients[batch_id]:
                    clients[batch_id].logout()
            except Exception as e:
                logger.error(f"Error logging out client: {str(e)}")
            finally:
                clients[batch_id] = None
                
        # Remove all batch data
        if batch_id in user_batches:
            del user_batches[batch_id]
        if batch_id in stop_flags:
            del stop_flags[batch_id]
        if batch_id in clients:
            del clients[batch_id]
        
        # Finally remove from active batches
        del active_batches[batch_id]
        success_memory = True
    
    # Also clean up from database
    try:
        session = InstagramSession.query.filter_by(batch_id=batch_id).first()
        if session:
            db.session.delete(session)
            db.session.commit()
            logger.info(f"Deleted Instagram batch {batch_id} from database")
            success_db = True
    except Exception as e:
        logger.error(f"Error deleting Instagram batch {batch_id} from database: {str(e)}")
    
    if success_memory or success_db:
        return jsonify({
            "success": True,
            "message": f"Batch {batch_id} deleted successfully"
        })
    
    return jsonify({
        "success": False,
        "message": "Batch ID not found"
    }), 404

# Helper Functions
def generate_batch_id():
    """Generate a unique batch ID"""
    return f'IG_{int(time.time())}_{uuid.uuid4().hex[:6]}'

def send_instagram_message(client, target, target_type, message):
    """Send a message to Instagram user or group"""
    max_retries = 3
    retry_count = 0
    error_message = None
    
    while retry_count < max_retries:
        try:
            if target_type == 'inbox':
                # Direct message to a user
                user_id = client.user_id_from_username(target)
                thread = client.direct_send(message, [user_id])
                return True, thread
            elif target_type == 'group':
                # Send to a group chat
                thread_id = target
                client.direct_send(message, thread_ids=[thread_id])
                return True, thread_id
            else:
                logger.error(f"Unknown target type: {target_type}")
                return False, None
        except LoginRequired as e:
            # Session expired, need to relogin
            logger.error(f"Session expired during message send (attempt {retry_count+1}): {str(e)}")
            error_message = f"Session expired: {str(e)}"
            # Try to re-login if we have credentials
            try:
                if hasattr(client, '_username') and hasattr(client, '_password'):
                    logger.info("Attempting to relogin automatically...")
                    client.login(client._username, client._password)
                    logger.info("Successfully relogged in")
                else:
                    logger.error("Can't relogin: credentials not stored")
                    # Can't relogin without credentials
                    return False, error_message
            except Exception as login_error:
                logger.error(f"Relogin failed: {str(login_error)}")
                return False, f"Relogin failed: {str(login_error)}"
        except Exception as e:
            error_message = str(e)
            logger.error(f"Error sending Instagram message (attempt {retry_count+1}): {error_message}")
            
        # Increment retry counter and wait before retrying
        retry_count += 1
        if retry_count < max_retries:
            wait_time = retry_count * 2  # Progressive backoff: 2s, 4s, etc.
            logger.info(f"Waiting {wait_time} seconds before retry...")
            time.sleep(wait_time)
    
    # If we get here, all retries failed
    return False, error_message or "Failed to send message after multiple attempts"

def start_message_sending(batch_id, client, username, password, target, target_type, message_prefix, messages, delay_time):
    """Start message sending in a background thread"""
    # Store the full list of messages
    if batch_id in active_batches:
        active_batches[batch_id]['all_messages'] = messages.copy()
        
    # Start the background thread
    threading.Thread(
        target=send_messages_loop,
        args=(batch_id, client, username, password, target, target_type, message_prefix, messages, delay_time),
        daemon=True
    ).start()

def send_messages_loop(batch_id, client, username, password, target, target_type, message_prefix, messages, delay_time):
    """Send messages in a loop"""
    logger.info(f"Starting message loop for batch {batch_id} to {target_type} {target}")
    
    # Initialize message count in active_batches if not already there
    if batch_id in active_batches:
        active_batches[batch_id]['sent_count'] = 0
    
    try:
        for message in messages:
            # Check if we need to stop
            if stop_flags.get(batch_id, True):
                logger.info(f"Message sending stopped for batch {batch_id}")
                break
                
            # Create the complete message with prefix
            full_message = f"{message_prefix}{message}" if message_prefix else message
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Try to send the message
            success, thread_info = send_instagram_message(client, target, target_type, full_message)
            status_msg = "Success" if success else "Failed"
            
            logger.info(f"[{status_msg}] Message to {target_type} {target}: {full_message[:30]}...")
            
            # Record the message
            message_record = {
                "time": current_time,
                "target": target,
                "target_type": target_type,
                "message": full_message,
                "status_class": "message-success" if success else "message-failure",
                "thread_info": str(thread_info) if thread_info else None
            }
            
            # Append to message history
            if batch_id in user_batches:
                user_batches[batch_id].append(message_record)
            else:
                user_batches[batch_id] = [message_record]
            
            # Increment the sent message count if successful
            if success and batch_id in active_batches:
                if 'sent_count' not in active_batches[batch_id]:
                    active_batches[batch_id]['sent_count'] = 0
                active_batches[batch_id]['sent_count'] += 1
                
            # Wait before sending next message
            if not stop_flags.get(batch_id, True):
                time.sleep(delay_time)
    except Exception as e:
        logger.error(f"Error in message loop: {str(e)}")
        
        # Record the error
        if batch_id in user_batches:
            user_batches[batch_id].append({
                "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "message": f"Error: {str(e)}",
                "status": "Error",
                "status_class": "message-error"
            })
    finally:
        # Mark process as completed
        if batch_id in user_batches:
            user_batches[batch_id].append({
                "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "message": "Message sending process completed",
                "status": "Completed",
                "status_class": "message-stopped"
            })
            
        # Set stop flag
        stop_flags[batch_id] = True
        logger.info(f"Message sending completed for batch: {batch_id}")
