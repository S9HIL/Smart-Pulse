"""
Facebook Automation Blueprint
Handles Facebook messaging automation
"""

import os
import logging
import time
import uuid
import threading
import requests
from flask import Blueprint, request, render_template, jsonify, redirect, url_for
from app import db
from models import FacebookBatch, FacebookMessage
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create blueprint
facebook_bp = Blueprint('facebook', __name__, template_folder='templates')

# Global variables
stop_flags = {}  # Runtime stop flags
logs = {}        # Runtime message logs

@facebook_bp.route('/')
def index():
    """Facebook automation main page"""
    return render_template('facebook/index.html')

@facebook_bp.route('/send_messages', methods=['POST'])
def send_messages():
    """Start sending Facebook messages"""
    try:
        # Get form data
        tokens = request.files['accessToken'].read().decode().splitlines()
        convo_id = request.form['threadId']
        text_file = request.files['txtFile']
        messages = text_file.read().decode().splitlines()
        haters_name = request.form['kidx']
        speed = int(request.form['time'])
        
        # Validate inputs
        if not tokens:
            return jsonify({
                "success": False,
                "message": "No access tokens provided"
            })
        
        if not convo_id:
            return jsonify({
                "success": False,
                "message": "Thread ID is required"
            })
            
        if not messages:
            return jsonify({
                "success": False,
                "message": "No messages provided"
            })

        # Generate batch ID
        batch_id = str(uuid.uuid4())
        stop_flags[batch_id] = threading.Event()
        
        # Try to get account name for the record
        account_name = None
        if tokens:
            account_name = get_account_name(tokens[0].strip())
            
        # Create batch in database
        batch = FacebookBatch(
            id=batch_id,
            access_token=tokens[0].strip() if tokens else None,  # Store first token only
            account_name=account_name,
            conversation_id=convo_id,
            haters_name=haters_name,
            speed=speed,
            status='running'
        )
        db.session.add(batch)
        
        # Add initial message in database
        init_message = FacebookMessage(
            batch_id=batch_id,
            message="Message sending process initialized",
            status="Info",
            status_class="text-info"
        )
        db.session.add(init_message)
        db.session.commit()
        
        # Start message sending in background
        threading.Thread(
            target=send_messages_from_file, 
            args=(convo_id, tokens, messages, haters_name, speed, batch_id)
        ).start()

        # Return redirect URL instead of JSON
        message_url = url_for('facebook.messages_page', batch_id=batch_id)
        return redirect(message_url)
    except Exception as e:
        logger.error(f"Error starting Facebook messages: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"An error occurred: {str(e)}"
        })

@facebook_bp.route('/stop/<batch_id>', methods=['POST'])
def stop_sending(batch_id):
    """Stop sending messages for a batch"""
    # Check database first
    batch = FacebookBatch.query.get(batch_id)
    
    if batch:
        # Update database status
        batch.status = 'stopped'
        db.session.commit()
        
        # Add status message to database
        status_message = FacebookMessage(
            batch_id=batch_id,
            message="Message sending stopped by user",
            status="Stopped",
            status_class="text-warning"
        )
        db.session.add(status_message)
        db.session.commit()
        
        # Also set runtime stop flag if it exists
        if batch_id in stop_flags:
            stop_flags[batch_id].set()
            
        return jsonify({"success": True, "status": "stopped"})
    # For backward compatibility, check runtime flags
    elif batch_id in stop_flags:
        stop_flags[batch_id].set()
        return jsonify({"success": True, "status": "stopped"})
    
    return jsonify({"success": False, "status": "batch ID not found"}), 404

@facebook_bp.route('/messages/<batch_id>')
def messages_page(batch_id):
    """View messages for a specific batch"""
    # Check database first
    batch = FacebookBatch.query.get(batch_id)
    
    if batch:
        return render_template('facebook/messages.html', batch_id=batch_id)
    # For backward compatibility, check runtime flags
    elif batch_id in stop_flags:
        return render_template('facebook/messages.html', batch_id=batch_id)
        
    return render_template('facebook/messages.html', batch_id=batch_id, error="Invalid Batch ID")

@facebook_bp.route('/logs/<batch_id>')
def get_logs(batch_id):
    """Get logs for a specific batch"""
    # First check database
    batch_messages = FacebookMessage.query.filter_by(batch_id=batch_id).order_by(FacebookMessage.timestamp).all()
    
    if batch_messages:
        # Convert to format expected by frontend
        db_logs = []
        for msg in batch_messages:
            db_logs.append({
                "convoId": batch_id,
                "time": msg.timestamp.strftime('%Y-%m-%d %H:%M:%S') if msg.timestamp else time.strftime('%Y-%m-%d %H:%M:%S'),
                "accountName": "System",  # Default
                "status": msg.status,
                "message": msg.message
            })
        return jsonify(db_logs)
    
    # If not in database, check runtime logs
    elif batch_id in logs:
        return jsonify(logs[batch_id])
        
    return jsonify({"success": False, "status": "no logs available for this batch ID"}), 404

@facebook_bp.route('/stop-status/<batch_id>')
def stop_status(batch_id):
    """Get stop status for a batch"""
    # First check database
    batch = FacebookBatch.query.get(batch_id)
    
    if batch:
        is_stopped = batch.status == 'stopped'
        
        # Also check runtime flag if it exists
        if batch_id in stop_flags:
            is_stopped = is_stopped or stop_flags[batch_id].is_set()
            
            # Sync database and runtime flags
            if is_stopped and batch.status != 'stopped':
                batch.status = 'stopped'
                db.session.commit()
            elif not is_stopped and batch.status == 'stopped':
                stop_flags[batch_id].set()  # Make runtime flags match database
                is_stopped = True
                
        return jsonify({
            "success": True,
            "status": "stopped" if is_stopped else "active"
        })
    
    # For backward compatibility, check runtime flags
    elif batch_id in stop_flags:
        return jsonify({
            "success": True,
            "status": "active" if not stop_flags[batch_id].is_set() else "stopped"
        })
        
    return jsonify({"success": False, "status": "batch ID not found"}), 404

@facebook_bp.route('/api/batches')
def list_batches():
    """API endpoint to list all Facebook batches"""
    # Get batches from database
    batches = FacebookBatch.query.order_by(FacebookBatch.created_at.desc()).all()
    
    # Convert to list of dictionaries
    batch_list = []
    for batch in batches:
        # Get status from database and runtime flags
        is_stopped = batch.status == 'stopped'
        if batch.id in stop_flags:
            is_stopped = is_stopped or stop_flags[batch.id].is_set()
        
        batch_data = batch.to_dict()
        batch_data['status'] = 'stopped' if is_stopped else 'running'
        batch_list.append(batch_data)
        
    return jsonify({
        "success": True,
        "batches": batch_list
    })
    
@facebook_bp.route('/delete/<batch_id>', methods=['POST'])
def delete_batch(batch_id):
    """Delete a batch and all its messages"""
    try:
        # Check if batch exists
        batch = FacebookBatch.query.get(batch_id)
        if not batch:
            return jsonify({
                "success": False,
                "message": "Batch not found"
            }), 404
        
        # First stop the batch if it's running
        if batch.status == 'running' and batch_id in stop_flags:
            stop_flags[batch_id].set()
        
        # Delete messages associated with the batch
        FacebookMessage.query.filter_by(batch_id=batch_id).delete()
        
        # Delete the batch
        db.session.delete(batch)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Batch and all associated messages deleted successfully"
        })
        
    except Exception as e:
        logger.error(f"Error deleting batch {batch_id}: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Error deleting batch: {str(e)}"
        }), 500

# Helper Functions
def get_account_name(access_token):
    """Get Facebook account name from access token"""
    url = "https://graph.facebook.com/v17.0/me"
    params = {'access_token': access_token}
    try:
        response = requests.get(url, params=params)
        if response.ok:
            data = response.json()
            return data.get('name', 'Unknown')
        else:
            return 'Unknown'
    except Exception as e:
        logger.error(f"Error getting account name: {str(e)}")
        return 'Unknown'

def send_messages_from_file(convo_id, tokens, messages, haters_name, speed, batch_id):
    """Send messages from file in background thread"""
    headers = {
        'Connection': 'keep-alive',
        'Cache-Control': 'max-age=0',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': 'Mozilla/5.0 (Linux; Android 8.0.0; Samsung Galaxy S9 Build/OPR6.170623.017; wv) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.125 Mobile Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate',
        'Accept-Language': 'en-US,en;q=0.9,fr;q=0.8',
        'referer': 'www.google.com'
    }

    num_messages = len(messages)
    num_tokens = len(tokens)
    max_tokens = min(num_tokens, num_messages)
    
    try:
        logger.info(f"Starting Facebook message sending for batch {batch_id}")
        
        # Get batch from database
        batch = FacebookBatch.query.get(batch_id)
        
        while not stop_flags.get(batch_id, threading.Event()).is_set():
            try:
                for message_index in range(num_messages):
                    if stop_flags.get(batch_id, threading.Event()).is_set():
                        break
                        
                    # Get token and message
                    token_index = message_index % max_tokens
                    access_token = tokens[token_index].strip()
                    message = messages[message_index].strip()
                    
                    # Get account name
                    account_name = get_account_name(access_token)
                    
                    # Prepare request
                    url = f"https://graph.facebook.com/v17.0/t_{convo_id}/"
                    parameters = {'access_token': access_token, 'message': f'{haters_name} {message}'}
                    
                    # Format the full message
                    full_message = f'{haters_name} {message}'
                    
                    # Create pending message in database first
                    pending_msg = FacebookMessage(
                        batch_id=batch_id,
                        message=full_message,
                        status="Pending",
                        status_class="text-secondary"
                    )
                    
                    try:
                        db.session.add(pending_msg)
                        db.session.commit()
                        pending_id = pending_msg.id  # Store ID for later update
                    except Exception as db_err:
                        logger.error(f"Error storing pending message in database: {str(db_err)}")
                        pending_id = None  # Handle case where DB insert fails
                    
                    # Send message with retry mechanism
                    success = False
                    error_message = None
                    retry_count = 0
                    max_retries = 3
                    
                    while not success and retry_count < max_retries:
                        try:
                            # Send message to Facebook
                            response = requests.post(url, json=parameters, headers=headers, timeout=30)
                            
                            # Check for success
                            if response.ok:
                                success = True
                                response_data = response.json()
                                # Facebook returns message_id on success
                                if 'id' in response_data:
                                    logger.info(f"Message sent successfully with ID: {response_data['id']}")
                            else:
                                error_message = f"API Error: {response.status_code} - {response.text}"
                                logger.warning(f"Facebook API error (attempt {retry_count+1}): {error_message}")
                                retry_count += 1
                                time.sleep(2)  # Short delay before retry
                        except requests.exceptions.RequestException as req_err:
                            error_message = f"Request error: {str(req_err)}"
                            logger.warning(f"Network error (attempt {retry_count+1}): {error_message}")
                            retry_count += 1
                            time.sleep(5)  # Longer delay on network errors
                    
                    # Update the message status in database
                    if pending_id:
                        try:
                            # Find the pending message
                            pending_msg = FacebookMessage.query.get(pending_id)
                            if pending_msg:
                                pending_msg.status = "Success" if success else "Failed"
                                pending_msg.status_class = "text-success" if success else "text-danger"
                                if not success and error_message:
                                    pending_msg.error = error_message
                                db.session.commit()
                            else:
                                # If message not found, create a new one
                                db_message = FacebookMessage(
                                    batch_id=batch_id,
                                    message=full_message,
                                    status="Success" if success else "Failed",
                                    status_class="text-success" if success else "text-danger",
                                    error=error_message if not success else None
                                )
                                db.session.add(db_message)
                                db.session.commit()
                        except Exception as db_err:
                            logger.error(f"Error updating message status in database: {str(db_err)}")
                    
                    # Also store in memory for backward compatibility
                    log_message = {
                        "convoId": convo_id,
                        "time": time.strftime('%Y-%m-%d %H:%M:%S'),
                        "accountName": account_name,
                        "status": "Success" if success else "Failed",
                        "message": full_message
                    }
                    logs.setdefault(batch_id, []).append(log_message)
                    
                    logger.info(f"[{'Success' if success else 'Failed'}] Facebook message to conversation {convo_id}: {full_message}")
                    
                    # Wait before sending next message
                    time.sleep(speed)
            except Exception as e:
                logger.error(f"Error in message loop: {str(e)}")
                time.sleep(30)  # Wait longer on error
    except Exception as e:
        logger.error(f"Error in send_messages_from_file: {str(e)}")
    finally:
        # Add stopped status message to database
        try:
            status_message = FacebookMessage(
                batch_id=batch_id,
                message="Message sending stopped.",
                status="Stopped",
                status_class="text-warning"
            )
            db.session.add(status_message)
            
            # Also update batch status
            if batch:
                batch.status = 'stopped'
            db.session.commit()
        except Exception as db_err:
            logger.error(f"Error storing final status in database: {str(db_err)}")
        
        # Also store in memory for backward compatibility
        logs.setdefault(batch_id, []).append({
            "convoId": convo_id,
            "time": time.strftime('%Y-%m-%d %H:%M:%S'),
            "accountName": "System",
            "status": "Stopped",
            "message": "Message sending stopped."
        })
        logger.info(f"Facebook message sending stopped for batch: {batch_id}")
