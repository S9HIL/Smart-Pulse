import os
import logging
import threading
import time
import uuid
import json
import base64
import subprocess
from flask import Blueprint, request, render_template, jsonify, redirect, url_for
from config import WHATSAPP_SERVICE_PATH
from utils import WhatsAppService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create blueprint
whatsapp_bp = Blueprint('whatsapp', __name__, template_folder='templates')

# Initialize WhatsApp service
whatsapp_service = WhatsAppService(WHATSAPP_SERVICE_PATH)

# Global variables
batch_tasks = {}
service_status = "stopped"

@whatsapp_bp.route('/')
def index():
    """WhatsApp automation main page"""
    return render_template('whatsapp/index.html')

@whatsapp_bp.route('/connect', methods=['POST'])
def connect():
    """Connect to WhatsApp"""
    try:
        # Start WhatsApp service if not already running
        if not whatsapp_service.is_running():
            started = whatsapp_service.start()
            
            # If service didn't start successfully
            if not started:
                return jsonify({
                    "success": False,
                    "message": f"Failed to start WhatsApp service: {whatsapp_service.last_error}"
                })
            
        # Wait for service to initialize
        time.sleep(1)
        
        # Check if service is still running
        if not whatsapp_service.is_running():
            return jsonify({
                "success": False,
                "message": f"WhatsApp service started but then stopped: {whatsapp_service.last_error}"
            })
            
        return jsonify({
            "success": True,
            "status": whatsapp_service.status,
            "phoneNumber": whatsapp_service.connected_phone
        })
        
    except Exception as e:
        logger.error(f"Error connecting to WhatsApp: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"An error occurred: {str(e)}"
        })

@whatsapp_bp.route('/disconnect', methods=['POST'])
def disconnect():
    """Disconnect from WhatsApp"""
    try:
        whatsapp_service.stop()
        return jsonify({
            "success": True,
            "message": "Disconnected from WhatsApp"
        })
    except Exception as e:
        logger.error(f"Error disconnecting from WhatsApp: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"An error occurred: {str(e)}"
        })

@whatsapp_bp.route('/status')
def status():
    """Get WhatsApp connection status"""
    # Make sure there's a valid status even if service isn't running
    if not whatsapp_service.is_running():
        status_value = "disconnected"
    else:
        status_value = whatsapp_service.status or "disconnected"
        
    return jsonify({
        "success": True,
        "running": whatsapp_service.is_running(),
        "status": status_value,
        "phoneNumber": whatsapp_service.connected_phone,
        "hasQR": whatsapp_service.qr_code is not None,
        "hasPairingCode": whatsapp_service.pairing_code is not None,
        "error": whatsapp_service.last_error
    })

@whatsapp_bp.route('/qr_code')
def get_qr_code():
    """Get QR code for WhatsApp connection"""
    if whatsapp_service.qr_code:
        return jsonify({
            "success": True,
            "qrCode": whatsapp_service.qr_code
        })
    else:
        return jsonify({
            "success": False,
            "message": "No QR code available"
        })

@whatsapp_bp.route('/pairing_code', methods=['POST'])
def request_pairing_code():
    """Request a pairing code for WhatsApp connection"""
    try:
        phone_number = request.form.get('phone_number')
        if not phone_number:
            return jsonify({
                "success": False,
                "message": "Phone number is required"
            })
            
        # Send command to request pairing code
        whatsapp_service.send_command('request_pairing_code', {'phoneNumber': phone_number})
        
        # Wait for pairing code
        max_retries = 20
        for i in range(max_retries):
            if whatsapp_service.pairing_code:
                return jsonify({
                    "success": True,
                    "pairingCode": whatsapp_service.pairing_code
                })
            time.sleep(1)
            
        return jsonify({
            "success": False,
            "message": "Failed to get pairing code within timeout period"
        })
        
    except Exception as e:
        logger.error(f"Error requesting pairing code: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"An error occurred: {str(e)}"
        })

@whatsapp_bp.route('/send_messages', methods=['POST'])
def send_messages():
    """Start sending WhatsApp messages"""
    try:
        # Get form data
        recipients = request.form.get('recipients', '')
        message_text = request.form.get('message', '')
        message_file = request.files.get('message_file')
        delay = int(request.form.get('delay', 5))
        
        # Process message file if provided
        messages = []
        if message_file:
            message_content = message_file.read().decode('utf-8')
            messages = [msg.strip() for msg in message_content.splitlines() if msg.strip()]
        elif message_text:
            messages = [msg.strip() for msg in message_text.split('\n') if msg.strip()]
            
        # Process recipients
        recipient_list = [r.strip() for r in recipients.split(',') if r.strip()]
        
        # Validate inputs
        if not recipient_list:
            return jsonify({
                "success": False,
                "message": "No recipients provided"
            })
            
        if not messages:
            return jsonify({
                "success": False,
                "message": "No messages provided"
            })
            
        if not whatsapp_service.is_running() or whatsapp_service.status != "connected":
            return jsonify({
                "success": False,
                "message": "WhatsApp is not connected. Please connect first."
            })
            
        # Generate batch ID
        batch_id = str(uuid.uuid4())
        
        # Store batch task
        batch_tasks[batch_id] = {
            'id': batch_id,
            'recipients': recipient_list,
            'messages': messages,
            'delay': delay,
            'status': 'starting',
            'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'logs': []
        }
        
        # Send command to start messages
        whatsapp_service.send_command('send_messages', {
            'batchId': batch_id,
            'recipients': recipient_list,
            'messages': messages,
            'delay': delay
        })
        
        return jsonify({
            "success": True,
            "batch_id": batch_id,
            "message": "Message sending started"
        })
        
    except Exception as e:
        logger.error(f"Error starting WhatsApp messages: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"An error occurred: {str(e)}"
        })

@whatsapp_bp.route('/stop_batch/<batch_id>', methods=['POST'])
def stop_batch(batch_id):
    """Stop a batch of messages"""
    try:
        if batch_id not in batch_tasks:
            return jsonify({
                "success": False,
                "message": "Batch ID not found"
            })
            
        # Send command to stop batch
        whatsapp_service.send_command('stop_batch', {'batchId': batch_id})
        
        # Update batch status
        batch_tasks[batch_id]['status'] = 'stopped'
        
        return jsonify({
            "success": True,
            "message": "Batch stopped successfully"
        })
        
    except Exception as e:
        logger.error(f"Error stopping batch {batch_id}: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"An error occurred: {str(e)}"
        })

@whatsapp_bp.route('/batch_logs/<batch_id>')
def batch_logs(batch_id):
    """Get logs for a batch"""
    if batch_id not in batch_tasks:
        return jsonify({
            "success": False,
            "message": "Batch ID not found"
        })
        
    batch = batch_tasks[batch_id]
    
    # Get relevant logs from WhatsApp service messages
    logs = [msg for msg in whatsapp_service.messages if msg.get('batchId') == batch_id]
    
    return jsonify({
        "success": True,
        "batch": {
            "id": batch_id,
            "status": batch['status'],
            "created_at": batch['created_at'],
            "recipients": batch['recipients'],
            "message_count": len(batch['messages'])
        },
        "logs": logs
    })

@whatsapp_bp.route('/messages/<batch_id>')
def view_messages(batch_id):
    """View messages for a specific batch"""
    if batch_id not in batch_tasks:
        return render_template('whatsapp/messages.html', 
                              messages=[], 
                              batch_id=batch_id, 
                              error="Batch ID not found")
    
    batch = batch_tasks[batch_id]
    
    # Get relevant logs
    logs = [msg for msg in whatsapp_service.messages if msg.get('batchId') == batch_id]
    
    return render_template('whatsapp/messages.html', 
                          batch=batch, 
                          logs=logs, 
                          batch_id=batch_id)
