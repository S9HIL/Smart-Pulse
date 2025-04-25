"""
Main Routes for Automation Hub
Handles dashboard and status endpoints
"""
import logging
from flask import Blueprint, render_template, jsonify, request, session, redirect, url_for
from models import WhatsAppTask
from utils import get_personalized_greeting

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
    
    # Get personalized greeting
    username = session.get('username', None)
    greeting = get_personalized_greeting(username)
    
    return render_template('index.html',
                          whatsapp_tasks=whatsapp_tasks,
                          greeting=greeting,
                          username=username)

@main_bp.route('/set_username', methods=['POST'])
def set_username():
    """Set the username in the session"""
    username = request.form.get('username', '').strip()
    if username:
        session['username'] = username
    return redirect(url_for('main.index'))

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