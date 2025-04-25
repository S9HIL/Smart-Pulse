"""
WhatsApp Automation Blueprint
Handles WhatsApp messaging automation
"""
import logging
import time
import uuid
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request, redirect, url_for
from app import db
from models import WhatsAppTask, WhatsAppMessage
from utils import WhatsAppService

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Create blueprint
whatsapp_bp = Blueprint('whatsapp', __name__, template_folder='templates')

# Initialize WhatsApp service but don't start it automatically
whatsapp_service = WhatsAppService("whatsapp_service.js")

# Start the service when the blueprint is registered
@whatsapp_bp.record_once
def on_register(state):
    # Ensure WhatsApp service is running
    if not whatsapp_service.is_running():
        logger.info("Starting WhatsApp service from blueprint registration")
        whatsapp_service.start()

@whatsapp_bp.route('/')
def index():
    """WhatsApp automation main page"""
    # Get active tasks from database
    tasks = WhatsAppTask.query.order_by(WhatsAppTask.created_at.desc()).limit(10).all()
    
    return render_template('whatsapp/index.html', 
                          tasks=tasks, 
                          service_running=whatsapp_service.is_running(),
                          status=whatsapp_service.status,
                          phone_number=whatsapp_service.phone_number)

@whatsapp_bp.route('/dashboard')
def dashboard():
    """WhatsApp task dashboard"""
    # Get active tasks from database
    tasks = WhatsAppTask.query.order_by(WhatsAppTask.created_at.desc()).all()
    
    return render_template('whatsapp/dashboard.html', tasks=tasks)

@whatsapp_bp.route('/connect', methods=['POST'])
def connect():
    """Connect to WhatsApp"""
    try:
        phone_number = request.form.get('phone_number')
        use_pairing_code = request.form.get('use_pairing_code', 'false').lower() == 'true'
        pairing_code = request.form.get('pairing_code')
        
        # If using pairing code, make sure it's provided
        if use_pairing_code and not pairing_code:
            return jsonify({
                "success": False,
                "message": "Pairing code is required when use_pairing_code is true"
            })
        
        # Send connect command with appropriate parameters
        whatsapp_service.send_command('connect', {
            'phoneNumber': phone_number,
            'usePairingCode': use_pairing_code,
            'pairingCode': pairing_code
        })
        
        return jsonify({
            "success": True,
            "message": "Connection initiated"
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
        # Send disconnect command
        whatsapp_service.send_command('logout')
        
        return jsonify({
            "success": True,
            "message": "Disconnection initiated"
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
    return jsonify({
        "success": True,
        "isRunning": whatsapp_service.is_running(),
        "status": whatsapp_service.status,
        "phoneNumber": whatsapp_service.phone_number,
        "hasPairingCode": whatsapp_service.pairing_code is not None,
        "error": whatsapp_service.last_error
    })

# QR code functionality removed as per requirements

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
        message_prefix = request.form.get('message_prefix', '')
        
        # Process message file if provided
        messages = []
        if message_file:
            message_content = message_file.read().decode('utf-8')
            messages = [msg.strip() for msg in message_content.splitlines() if msg.strip()]
        elif message_text:
            messages = [msg.strip() for msg in message_text.split('\n') if msg.strip()]
        
        # Apply message prefix if provided
        if message_prefix:
            messages = [f"{message_prefix}{msg}" for msg in messages]
            
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
            
        # Generate task ID
        task_id = str(uuid.uuid4())
        
        # Create database task entry
        task = WhatsAppTask(
            id=task_id,
            phone_number=whatsapp_service.phone_number,
            status='created',
            total_recipients=len(recipient_list),
            total_messages=len(messages),
            delay=delay
        )
        db.session.add(task)
        
        # Create message entries
        for recipient in recipient_list:
            for message in messages:
                msg = WhatsAppMessage(
                    task_id=task_id,
                    recipient=recipient,
                    message=message,
                    status='pending'
                )
                db.session.add(msg)
        
        # Commit to database
        db.session.commit()
        
        # Send command to start messages
        whatsapp_service.send_command('send_messages', {
            'taskId': task_id,
            'recipients': recipient_list,
            'messages': messages,
            'delay': delay
        })
        
        # Update task status
        task.status = 'running'
        db.session.commit()
        
        return jsonify({
            "success": True,
            "task_id": task_id,
            "message": "Message sending started"
        })
        
    except Exception as e:
        logger.error(f"Error starting WhatsApp messages: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"An error occurred: {str(e)}"
        })

@whatsapp_bp.route('/stop_task/<task_id>', methods=['POST'])
def stop_task(task_id):
    """Stop a message sending task"""
    try:
        # Get task from database
        task = WhatsAppTask.query.get(task_id)
        if not task:
            return jsonify({
                "success": False,
                "message": "Task ID not found"
            })
            
        # Send command to stop task
        whatsapp_service.send_command('stop_task', {'taskId': task_id})
        
        # Update task status
        task.status = 'stopped'
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Task stopped successfully"
        })
        
    except Exception as e:
        logger.error(f"Error stopping task {task_id}: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"An error occurred: {str(e)}"
        })

@whatsapp_bp.route('/restart_task/<task_id>', methods=['POST'])
def restart_task(task_id):
    """Restart a stopped message sending task"""
    try:
        # Get task from database
        task = WhatsAppTask.query.get(task_id)
        if not task:
            return jsonify({
                "success": False,
                "message": "Task ID not found"
            })
        
        if task.status not in ['stopped', 'failed']:
            return jsonify({
                "success": False,
                "message": "Only stopped or failed tasks can be restarted"
            })
        
        # Get messages that were not sent
        pending_messages = WhatsAppMessage.query.filter_by(
            task_id=task_id, 
            status='pending'
        ).all()
        
        if not pending_messages:
            return jsonify({
                "success": False,
                "message": "No pending messages to restart"
            })
        
        # Get unique recipients and messages
        recipients = list(set([msg.recipient for msg in pending_messages]))
        messages = list(set([msg.message for msg in pending_messages]))
        
        # Send command to restart task
        whatsapp_service.send_command('restart_task', {
            'taskId': task_id,
            'recipients': recipients,
            'messages': messages,
            'delay': task.delay
        })
        
        # Update task status
        task.status = 'running'
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Task restarted successfully"
        })
        
    except Exception as e:
        logger.error(f"Error restarting task {task_id}: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"An error occurred: {str(e)}"
        })

@whatsapp_bp.route('/task/<task_id>')
def view_task(task_id):
    """View details for a specific task"""
    # Get task from database
    task = WhatsAppTask.query.get(task_id)
    if not task:
        return render_template('whatsapp/task.html', 
                              error="Task not found", 
                              task_id=task_id)
    
    # Get messages for this task
    messages = WhatsAppMessage.query.filter_by(task_id=task_id).all()
    
    # Group messages by status
    pending = [m for m in messages if m.status == 'pending']
    sent = [m for m in messages if m.status == 'sent']
    failed = [m for m in messages if m.status == 'failed']
    
    return render_template('whatsapp/task.html', 
                          task=task, 
                          messages=messages,
                          pending=pending,
                          sent=sent,
                          failed=failed)

@whatsapp_bp.route('/tasks')
def list_tasks():
    """List all WhatsApp message tasks"""
    # Get all tasks from database
    tasks = WhatsAppTask.query.order_by(WhatsAppTask.created_at.desc()).all()
    
    return render_template('whatsapp/tasks.html', tasks=tasks)

@whatsapp_bp.route('/task_status/<task_id>')
def task_status(task_id):
    """Get status for a specific task"""
    # Get task from database
    task = WhatsAppTask.query.get(task_id)
    if not task:
        return jsonify({
            "success": False,
            "message": "Task not found"
        })
    
    # Get message counts
    pending_count = WhatsAppMessage.query.filter_by(task_id=task_id, status='pending').count()
    sent_count = WhatsAppMessage.query.filter_by(task_id=task_id, status='sent').count()
    failed_count = WhatsAppMessage.query.filter_by(task_id=task_id, status='failed').count()
    
    return jsonify({
        "success": True,
        "task": task.to_dict(),
        "counts": {
            "pending": pending_count,
            "sent": sent_count,
            "failed": failed_count
        }
    })