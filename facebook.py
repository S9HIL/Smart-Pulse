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
        # Get the token type selection
        token_type = request.form.get('token_type', 'single')
        
        # Handle different token input methods
        if token_type == 'single':
            access_token = request.form.get('access_token')
            if not access_token:
                return jsonify({
                    "success": False,
                    "message": "Facebook access token is required"
                })
        else:  # token_type == 'file'
            tokens_file = request.files.get('tokens_file')
            if not tokens_file:
                return jsonify({
                    "success": False,
                    "message": "Tokens file is required"
                })
            # Read the first token from the file
            try:
                token_content = tokens_file.read().decode('utf-8').strip()
                tokens = token_content.splitlines()
                if not tokens:
                    return jsonify({
                        "success": False,
                        "message": "The token file is empty"
                    })
                access_token = tokens[0].strip()  # Use the first token for now
            except Exception as e:
                return jsonify({
                    "success": False,
                    "message": f"Error reading token file: {str(e)}"
                })
        
        # Get other form data
        conversation_id = request.form.get('conversation_id')
        haters_name = request.form.get('haters_name')
        message_text = request.form.get('message_text', '')
        message_file = request.files.get('message_file')
        speed = int(request.form.get('speed', 5))
        
        if not conversation_id:
            return jsonify({
                "success": False,
                "message": "Conversation ID is required"
            })
            
        # Process message content
        messages = []
        
        if message_file:
            try:
                file_content = message_file.read().decode('utf-8')
                messages = [line.strip() for line in file_content.split('\n') if line.strip()]
            except Exception as e:
                logger.error(f"Error reading message file: {str(e)}")
                return jsonify({
                    "success": False,
                    "message": f"Error reading message file: {str(e)}"
                })
        elif message_text:
            messages = [line.strip() for line in message_text.split('\n') if line.strip()]
            
        if not messages:
            return jsonify({
                "success": False,
                "message": "No messages provided. Please enter message text or upload a file."
            })
        
        # Generate batch ID
        batch_id = str(uuid.uuid4())
        
        # Initialize logs for this batch
        logs[batch_id] = []
        
        # Try to get account name
        account_name = None
        try:
            account_name = get_account_name(access_token)
        except Exception as e:
            logger.warning(f"Could not get account name: {str(e)}")
        
        # Create batch record in database
        batch = FacebookBatch(
            id=batch_id,
            access_token=access_token,
            account_name=account_name,
            conversation_id=conversation_id,
            haters_name=haters_name,
            status="running",
            speed=speed
        )
        db.session.add(batch)
        
        # Add messages to database
        for message in messages:
            msg = FacebookMessage(
                batch_id=batch_id,
                message=message,
                status="pending",
                status_class="text-secondary"
            )
            db.session.add(msg)
            
        db.session.commit()
        
        # Create event to signal stop
        stop_flags[batch_id] = threading.Event()
        
        # Handle token list for file upload mode
        token_list = []
        if token_type == 'file' and 'tokens_file' in request.files:
            # Reopen the file since we already read it once
            tokens_file = request.files.get('tokens_file')
            tokens_file.seek(0)
            token_content = tokens_file.read().decode('utf-8').strip()
            token_list = [token.strip() for token in token_content.splitlines() if token.strip()]
        else:
            token_list = [access_token]
            
        # Start sending messages in background thread
        thread = threading.Thread(
            target=send_messages_from_file,
            args=(conversation_id, token_list, messages, haters_name, speed, batch_id)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            "success": True,
            "message": "Message sending started",
            "batch_id": batch_id,
            "links": {
                "messages": url_for('facebook.messages_page', batch_id=batch_id)
            }
        })
        
    except Exception as e:
        logger.error(f"Error starting Facebook messages: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"An error occurred: {str(e)}"
        })

@facebook_bp.route('/stop/<batch_id>', methods=['POST'])
def stop_sending(batch_id):
    """Stop sending messages for a batch"""
    if batch_id in stop_flags:
        stop_flags[batch_id].set()
        
        # Update batch status in database
        batch = FacebookBatch.query.get(batch_id)
        if batch:
            batch.status = "stopped"
            db.session.commit()
            
        return jsonify({"success": True, "status": "stopped"})
    
    return jsonify({"success": False, "status": "batch ID not found"}), 404

@facebook_bp.route('/messages/<batch_id>')
def messages_page(batch_id):
    """View messages for a specific batch"""
    # Get batch from database
    batch = FacebookBatch.query.get(batch_id)
    if not batch:
        return render_template('facebook/messages.html', error="Invalid Batch ID")
        
    return render_template('facebook/messages.html', batch=batch)

@facebook_bp.route('/logs/<batch_id>')
def get_logs(batch_id):
    """Get logs for a specific batch"""
    try:
        # Get messages from database
        messages = FacebookMessage.query.filter_by(batch_id=batch_id).order_by(FacebookMessage.timestamp).all()
        
        # Get batch info
        batch = FacebookBatch.query.get(batch_id)
        if not batch:
            return jsonify({
                "success": False,
                "message": "Batch not found"
            })
            
        return jsonify({
            "success": True,
            "messages": [msg.to_dict() for msg in messages],
            "batch": batch.to_dict()
        })
    except Exception as e:
        logger.error(f"Error getting logs for batch {batch_id}: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Error getting logs: {str(e)}"
        })

@facebook_bp.route('/stop-status/<batch_id>')
def stop_status(batch_id):
    """Get stop status for a batch"""
    is_stopped = False
    
    if batch_id in stop_flags:
        is_stopped = stop_flags[batch_id].is_set()
    
    # Also check database status
    batch = FacebookBatch.query.get(batch_id)
    status = "unknown"
    if batch:
        status = batch.status
        # If status is stopped or completed in DB, consider it stopped
        if status in ["stopped", "completed", "failed"]:
            is_stopped = True
    
    return jsonify({
        "success": True,
        "is_stopped": is_stopped,
        "status": status
    })

@facebook_bp.route('/api/batches')
def list_batches():
    """API endpoint to list all Facebook batches"""
    try:
        batches = FacebookBatch.query.order_by(FacebookBatch.created_at.desc()).all()
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

@facebook_bp.route('/api/batch/<batch_id>', methods=['DELETE'])
def delete_batch(batch_id):
    """Delete a batch and all its messages"""
    try:
        # Set stop flag if batch is running
        if batch_id in stop_flags:
            stop_flags[batch_id].set()
            
        # Delete messages
        FacebookMessage.query.filter_by(batch_id=batch_id).delete()
        
        # Delete batch
        batch = FacebookBatch.query.get(batch_id)
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

def get_account_name(access_token):
    """Get Facebook account name from access token"""
    url = f"https://graph.facebook.com/v15.0/me?access_token={access_token}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return data.get('name')
    return None

def send_messages_from_file(convo_id, tokens, messages, haters_name, speed, batch_id):
    """Send messages from file in background thread"""
    from app import app
    
    logger.info(f"Starting Facebook message sending for batch {batch_id}")
    
    # Get the stop event
    stop_event = stop_flags.get(batch_id)
    if not stop_event:
        logger.error(f"No stop event found for batch {batch_id}")
        return
    
    try:
        # Update database status
        with app.app_context():
            batch = FacebookBatch.query.get(batch_id)
            if not batch:
                logger.error(f"Batch {batch_id} not found in database")
                return
            
            # Log start
            log_message(batch_id, "Starting message sending process", "info")
        
        # Facebook API URL
        fb_api_url = "https://graph.facebook.com/v15.0/"
        
        # Loop through messages
        total_messages = len(messages)
        current_token_index = 0
        
        for idx, message in enumerate(messages, 1):
            # Check if stop was requested
            if stop_event.is_set():
                with app.app_context():
                    log_message(batch_id, "Message sending stopped by user", "info")
                    batch = FacebookBatch.query.get(batch_id)
                    if batch:
                        batch.status = "stopped"
                        db.session.commit()
                return
            
            # Format message with haters name if provided
            formatted_message = message
            if haters_name:
                formatted_message = message.replace("%name%", haters_name)
            
            # Get current token
            token = tokens[current_token_index]
            
            # Log the message being sent
            with app.app_context():
                log_message(batch_id, f"Sending message {idx}/{total_messages}: {formatted_message[:40]}...", "pending")
            
            try:
                # Send message
                response = requests.post(
                    f"{fb_api_url}{convo_id}/messages",
                    params={"access_token": token},
                    data={"message": formatted_message}
                )
                
                # Check response
                if response.status_code == 200:
                    with app.app_context():
                        log_message(batch_id, f"Message {idx}/{total_messages} sent successfully", "success")
                else:
                    # Try to parse error
                    error_msg = "Unknown error"
                    try:
                        error_data = response.json()
                        error_msg = error_data.get('error', {}).get('message', 'Unknown error')
                    except:
                        error_msg = f"HTTP Error {response.status_code}"
                    
                    with app.app_context():
                        log_message(batch_id, f"Failed to send message {idx}/{total_messages}", "failed", error_msg)
                        
                        # Rotate token if access error
                        if "access token" in error_msg.lower():
                            current_token_index = (current_token_index + 1) % len(tokens)
                            log_message(batch_id, f"Switching to next access token", "info")
            
            except Exception as e:
                with app.app_context():
                    log_message(batch_id, f"Error sending message {idx}/{total_messages}", "failed", str(e))
            
            # Delay before next message
            if idx < total_messages and not stop_event.is_set():
                time.sleep(speed)
        
        # If we get here without stopping, mark as completed
        if not stop_event.is_set():
            with app.app_context():
                log_message(batch_id, "All messages sent successfully", "success")
                batch = FacebookBatch.query.get(batch_id)
                if batch:
                    batch.status = "completed"
                    db.session.commit()
            
    except Exception as e:
        logger.error(f"Error in message sending process: {str(e)}")
        with app.app_context():
            log_message(batch_id, "Error in message sending process", "failed", str(e))
            
            # Update batch status
            try:
                batch = FacebookBatch.query.get(batch_id)
                if batch:
                    batch.status = "failed"
                    db.session.commit()
            except Exception as inner_e:
                logger.error(f"Error updating batch status: {str(inner_e)}")

def log_message(batch_id, message, status="info", error=None):
    """Log a message to both console and database"""
    # Map status to CSS class
    status_class_map = {
        "info": "text-info",
        "pending": "text-secondary",
        "success": "text-success",
        "failed": "text-danger"
    }
    status_class = status_class_map.get(status, "text-secondary")
    
    # Log to console
    if status == "failed":
        logger.error(f"Batch {batch_id}: {message} - {error}")
    else:
        logger.info(f"Batch {batch_id}: {message}")
    
    # Store in database
    try:
        new_message = FacebookMessage(
            batch_id=batch_id,
            message=message,
            status=status,
            status_class=status_class,
            error=error,
            timestamp=datetime.utcnow()
        )
        db.session.add(new_message)
        db.session.commit()
    except Exception as e:
        logger.error(f"Error logging to database: {str(e)}")
        
    # Also store in runtime logs
    if batch_id in logs:
        logs[batch_id].append({
            "message": message,
            "status": status,
            "error": error,
            "timestamp": datetime.utcnow().isoformat()
        })