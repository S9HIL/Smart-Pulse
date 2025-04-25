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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create blueprint
facebook_bp = Blueprint('facebook', __name__, template_folder='templates')

# Global variables
stop_flags = {}
logs = {}

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
        
        # Start message sending in background
        threading.Thread(
            target=send_messages_from_file, 
            args=(convo_id, tokens, messages, haters_name, speed, batch_id)
        ).start()

        return jsonify({
            "success": True,
            "status": "started",
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
        return jsonify({"success": True, "status": "stopped"})
    return jsonify({"success": False, "status": "batch ID not found"}), 404

@facebook_bp.route('/messages/<batch_id>')
def messages_page(batch_id):
    """View messages for a specific batch"""
    if batch_id in stop_flags:
        return render_template('facebook/messages.html', batch_id=batch_id)
    return render_template('facebook/messages.html', batch_id=batch_id, error="Invalid Batch ID")

@facebook_bp.route('/logs/<batch_id>')
def get_logs(batch_id):
    """Get logs for a specific batch"""
    if batch_id in logs:
        return jsonify(logs[batch_id])
    return jsonify({"success": False, "status": "no logs available for this batch ID"}), 404

@facebook_bp.route('/stop-status/<batch_id>')
def stop_status(batch_id):
    """Get stop status for a batch"""
    if batch_id in stop_flags:
        return jsonify({
            "success": True,
            "status": "active" if not stop_flags[batch_id].is_set() else "stopped"
        })
    return jsonify({"success": False, "status": "batch ID not found"}), 404

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
                    
                    # Send message
                    response = requests.post(url, json=parameters, headers=headers)
                    success = response.ok
                    
                    # Log message
                    log_message = {
                        "convoId": convo_id,
                        "time": time.strftime('%Y-%m-%d %H:%M:%S'),
                        "accountName": account_name,
                        "status": "Success" if success else "Failed",
                        "message": f'{haters_name} {message}'
                    }
                    logs.setdefault(batch_id, []).append(log_message)
                    
                    logger.info(f"[{'Success' if success else 'Failed'}] Facebook message to conversation {convo_id}: {haters_name} {message}")
                    
                    # Wait before sending next message
                    time.sleep(speed)
            except Exception as e:
                logger.error(f"Error in message loop: {str(e)}")
                time.sleep(30)  # Wait longer on error
    except Exception as e:
        logger.error(f"Error in send_messages_from_file: {str(e)}")
    finally:
        # Add stopped status message
        logs.setdefault(batch_id, []).append({
            "convoId": convo_id,
            "time": time.strftime('%Y-%m-%d %H:%M:%S'),
            "accountName": "System",
            "status": "Stopped",
            "message": "Message sending stopped."
        })
        logger.info(f"Facebook message sending stopped for batch: {batch_id}")
