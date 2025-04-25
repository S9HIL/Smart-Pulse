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
from flask import Blueprint, request, render_template, jsonify, redirect, url_for, session
from instagrapi import Client
from instagrapi.exceptions import LoginRequired, ClientError, ClientLoginRequired

from app import db
from models import InstagramBatch, InstagramMessage

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

def generate_batch_id():
    """Generate a unique batch ID"""
    return str(uuid.uuid4())

@instagram_bp.route('/')
def index():
    """Instagram automation main page"""
    return render_template('instagram/index.html')

@instagram_bp.route('/dashboard')
def dashboard():
    """Instagram dashboard page"""
    return render_template('instagram/dashboard.html')

@instagram_bp.route('/api/batches')
def list_batches():
    """API endpoint to list all Instagram batches"""
    try:
        # Get all batches from database
        batches = InstagramBatch.query.order_by(InstagramBatch.created_at.desc()).all()
        return jsonify({
            "success": True,
            "batches": [batch.to_dict() for batch in batches]
        })
    except Exception as e:
        logger.error(f"Error listing batches: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Error listing batches: {str(e)}"
        })

@instagram_bp.route('/send-message', methods=['POST'])
def send_message():
    """Start sending Instagram messages"""
    try:
        # Extract form data
        username = request.form.get('username')
        password = request.form.get('password')
        target = request.form.get('target')
        target_type = request.form.get('target_type')  # 'user' or 'group'
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
        
        # Create database batch record
        new_batch = InstagramBatch(
            id=batch_id,
            username=username,
            target=target,
            target_type=target_type,
            status='running',
            message_prefix=message_prefix,
            delay_time=delay_time
        )
        
        # Store batch messages
        for message_text in messages:
            message = InstagramMessage(
                batch_id=batch_id,
                message=message_text,
                status='pending',
                status_class='message-pending'
            )
            db.session.add(message)
        
        # Save batch and messages to database
        db.session.add(new_batch)
        db.session.commit()
        
        # Set up control flags
        stop_flags[batch_id] = False
        
        # Start message sending in background
        thread = threading.Thread(
            target=start_message_sending,
            args=(batch_id, username, password, target, target_type, message_prefix, messages, delay_time)
        )
        thread.daemon = True
        thread.start()
        
        # Return immediate success response with batch ID
        return jsonify({
            "success": True,
            "message": "Message sending started",
            "batch_id": batch_id
        })
    
    except Exception as e:
        logger.error(f"Error in send_message: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"An error occurred: {str(e)}"
        })

@instagram_bp.route('/stop/<batch_id>', methods=['POST'])
def stop_sending(batch_id):
    """Stop sending messages for a batch"""
    try:
        # Set stop flag
        stop_flags[batch_id] = True
        
        # Update batch status in database
        batch = InstagramBatch.query.get(batch_id)
        if batch:
            batch.status = 'stopped'
            db.session.commit()
            
            return jsonify({
                "success": True,
                "message": f"Stopped message sending for batch {batch_id}"
            })
        else:
            return jsonify({
                "success": False,
                "message": f"Batch {batch_id} not found"
            })
    except Exception as e:
        logger.error(f"Error stopping batch {batch_id}: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Error stopping batch: {str(e)}"
        })

@instagram_bp.route('/batch/<batch_id>')
@instagram_bp.route('/messages/<batch_id>')  # Adding a second route for compatibility
def messages_page(batch_id):
    """View messages for a specific batch"""
    try:
        # Get batch from database
        batch = InstagramBatch.query.get(batch_id)
        if not batch:
            logger.warning(f"Batch not found: {batch_id}")
            return render_template('instagram/messages.html', error=f"Batch ID {batch_id} not found")
        
        logger.info(f"Viewing batch: {batch_id}")
        return render_template('instagram/messages.html', batch=batch)
    except Exception as e:
        logger.error(f"Error viewing batch {batch_id}: {str(e)}")
        return render_template('instagram/messages.html', error=f"Error loading batch: {str(e)}")

@instagram_bp.route('/api/messages/<batch_id>')
def get_logs(batch_id):
    """Get logs for a specific batch"""
    try:
        # Get messages from database
        messages = InstagramMessage.query.filter_by(batch_id=batch_id).order_by(InstagramMessage.timestamp.desc()).all()
        
        # Get batch info
        batch = InstagramBatch.query.get(batch_id)
        
        return jsonify({
            "success": True,
            "messages": [msg.to_dict() for msg in messages],
            "status": batch.status if batch else "unknown"
        })
    except Exception as e:
        logger.error(f"Error getting logs for batch {batch_id}: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Error getting logs: {str(e)}"
        })

@instagram_bp.route('/api/status/<batch_id>')
def stop_status(batch_id):
    """Get stop status for a batch"""
    try:
        is_stopped = stop_flags.get(batch_id, False)
        batch = InstagramBatch.query.get(batch_id)
        
        return jsonify({
            "success": True,
            "is_stopped": is_stopped,
            "status": batch.status if batch else "unknown"
        })
    except Exception as e:
        logger.error(f"Error getting stop status for batch {batch_id}: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Error getting stop status: {str(e)}"
        })

@instagram_bp.route('/api/batch/<batch_id>', methods=['DELETE'])
def delete_batch(batch_id):
    """Delete a batch and all its messages"""
    try:
        # Set stop flag if batch is running
        if batch_id in stop_flags:
            stop_flags[batch_id] = True
        
        # Delete messages
        InstagramMessage.query.filter_by(batch_id=batch_id).delete()
        
        # Delete batch
        batch = InstagramBatch.query.get(batch_id)
        if batch:
            db.session.delete(batch)
            db.session.commit()
            
            return jsonify({
                "success": True,
                "message": f"Batch {batch_id} deleted successfully"
            })
        else:
            return jsonify({
                "success": False,
                "message": f"Batch {batch_id} not found"
            })
    except Exception as e:
        logger.error(f"Error deleting batch {batch_id}: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Error deleting batch: {str(e)}"
        })

def send_instagram_message(client, target, target_type, message):
    """Send a message to Instagram user or group"""
    max_retries = 3
    retry_count = 0
    error_message = None
    
    while retry_count < max_retries:
        try:
            if target_type == 'user':
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
                return False, f"Unknown target type: {target_type}"
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
                    break
            except Exception as re_err:
                logger.error(f"Relogin failed: {str(re_err)}")
                break
        except Exception as e:
            logger.error(f"Error sending message (attempt {retry_count+1}): {str(e)}")
            error_message = str(e)
        
        retry_count += 1
        if retry_count < max_retries:
            time.sleep(2)  # Wait before retry
    
    return False, error_message

def log_message(batch_id, message, status="info", error=None):
    """Log a message to both the database and console.
    
    Args:
        batch_id (str): Batch ID for this message
        message (str): Message content
        status (str): Status type (info, success, failed, pending)
        error (str, optional): Error message if status is failed
    """
    # Map status to CSS class
    status_class_map = {
        'info': 'text-info',
        'success': 'text-success',
        'failed': 'text-danger',
        'pending': 'text-secondary'
    }
    
    status_class = status_class_map.get(status, 'text-secondary')
    
    # Log to console
    if status == 'failed':
        logger.error(f"Batch {batch_id}: {message} - {error}")
    elif status == 'info':
        logger.info(f"Batch {batch_id}: {message}")
    elif status == 'success':
        logger.info(f"Batch {batch_id}: {message}")
    
    # Store in database
    try:
        new_message = InstagramMessage(
            batch_id=batch_id,
            message=message,
            status=status,
            status_class=status_class,
            error=error
        )
        db.session.add(new_message)
        db.session.commit()
    except Exception as e:
        logger.error(f"Error logging message to database: {str(e)}")

def update_batch_status(batch_id, status):
    """Update the status of a batch in the database.
    
    Args:
        batch_id (str): Batch ID to update
        status (str): New status (running, stopped, completed, failed)
    """
    try:
        batch = InstagramBatch.query.get(batch_id)
        if batch:
            batch.status = status
            batch.updated_at = datetime.utcnow()
            db.session.commit()
    except Exception as e:
        logger.error(f"Error updating batch status: {str(e)}")

def start_message_sending(batch_id, username, password, target, target_type, message_prefix, messages, delay_time):
    """Start the message sending process in a background thread.
    
    Args:
        batch_id (str): Batch ID for this message batch
        username (str): Instagram username
        password (str): Instagram password
        target (str): Target username or group ID
        target_type (str): Type of target (user or group)
        message_prefix (str): Text to add before each message
        messages (list): List of messages to send
        delay_time (int): Delay between messages in seconds
    """
    from app import app
    
    try:
        # Mark as active
        active_batches[batch_id] = True
        
        # Log start with application context
        with app.app_context():
            log_message(batch_id, f"Starting Instagram message sending to {target}")
            log_message(batch_id, f"Logging in as {username}...")
        
        # Initialize Instagram client
        client = Client()
        # Store credentials for potential relogin
        client._username = username
        client._password = password
        
        # Try to login
        try:
            client.login(username, password)
            with app.app_context():
                log_message(batch_id, f"Successfully logged in as {username}", "success")
        except Exception as e:
            with app.app_context():
                log_message(batch_id, f"Login failed: {str(e)}", "failed", str(e))
                update_batch_status(batch_id, "failed")
            active_batches.pop(batch_id, None)
            return
        
        # Store client
        clients[batch_id] = client
        
        # Initial verification of target
        if target_type == 'user':
            try:
                user_id = client.user_id_from_username(target)
                with app.app_context():
                    log_message(batch_id, f"Found user {target} (ID: {user_id})", "success")
            except Exception as e:
                with app.app_context():
                    log_message(batch_id, f"Target user {target} not found", "failed", str(e))
                    update_batch_status(batch_id, "failed")
                active_batches.pop(batch_id, None)
                return
        
        # Send messages one by one
        total_messages = len(messages)
        with app.app_context():
            log_message(batch_id, f"Starting to send {total_messages} messages with {delay_time}s delay")
        
        for idx, message_text in enumerate(messages, 1):
            # Check if stop flag is set
            if stop_flags.get(batch_id, False):
                with app.app_context():
                    log_message(batch_id, "Message sending stopped by user", "info")
                    update_batch_status(batch_id, "stopped")
                break
            
            # Prepare full message with prefix if needed
            full_message = f"{message_prefix}\n{message_text}" if message_prefix else message_text
            
            # Log the message being sent
            with app.app_context():
                log_message(batch_id, f"Sending message {idx}/{total_messages}: {full_message[:50]}...", "pending")
            
            # Send the message
            success, result = send_instagram_message(client, target, target_type, full_message)
            
            if success:
                with app.app_context():
                    log_message(batch_id, f"Message {idx}/{total_messages} sent successfully", "success")
            else:
                error_msg = result if result else "Unknown error"
                with app.app_context():
                    log_message(batch_id, f"Failed to send message {idx}/{total_messages}", "failed", error_msg)
                    
                    # If we've had too many failures, break
                    if idx >= 3 and idx / total_messages < 0.2:
                        log_message(batch_id, "Too many failures, stopping process", "failed")
                        update_batch_status(batch_id, "failed")
                        break
            
            # Delay before next message
            if idx < total_messages and not stop_flags.get(batch_id, False):
                time.sleep(delay_time)
        
        # Log completion if not stopped
        if not stop_flags.get(batch_id, False):
            with app.app_context():
                log_message(batch_id, "Message sending completed", "success")
                update_batch_status(batch_id, "completed")
        
        # Always logout when done
        try:
            client.logout()
            with app.app_context():
                log_message(batch_id, "Logged out of Instagram", "info")
        except Exception as e:
            with app.app_context():
                log_message(batch_id, "Error during logout", "failed", str(e))
    
    except Exception as e:
        logger.error(f"Error in message sending thread: {str(e)}")
        with app.app_context():
            log_message(batch_id, "Error in message sending process", "failed", str(e))
            update_batch_status(batch_id, "failed")
    
    finally:
        # Clean up
        clients.pop(batch_id, None)
        active_batches.pop(batch_id, None)