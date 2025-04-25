"""
Main Routes for Automation Hub
Handles dashboard and status endpoints
"""
import logging
from flask import Blueprint, render_template, jsonify
from models import WhatsAppTask

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Create main blueprint
main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Main dashboard page for the automation hub"""
    # Get active WhatsApp tasks
    whatsapp_tasks = WhatsAppTask.query.filter(
        WhatsAppTask.status.in_(['created', 'running'])
    ).order_by(WhatsAppTask.created_at.desc()).limit(5).all()
    
    return render_template('index.html', 
                          whatsapp_tasks=whatsapp_tasks)

@main_bp.route('/status')
def status():
    """Get status of all services"""
    return jsonify({
        "whatsapp": {
            "active": True,
            "activeTaskCount": WhatsAppTask.query.filter(
                WhatsAppTask.status.in_(['created', 'running'])
            ).count()
        },
        "facebook": {
            "active": True
        },
        "instagram": {
            "active": True
        }
    })