"""
Main Routes for Automation Hub
Handles dashboard and status endpoints
"""
import logging
from flask import Blueprint, render_template, jsonify, request, session, redirect, url_for
from models import WhatsAppTask, FacebookBatch, InstagramBatch
from utils import get_personalized_greeting

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Create main blueprint
main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Main dashboard page for the automation hub"""
    # No longer fetching active WhatsApp tasks as per user request
    # Users should go to batch manager page for this information
    
    # Get personalized greeting
    username = session.get('username', None)
    greeting = get_personalized_greeting(username)
    
    return render_template('index.html',
                          greeting=greeting,
                          username=username)

@main_bp.route('/set_username', methods=['POST'])
def set_username():
    """Set the username in the session"""
    username = request.form.get('username', '').strip()
    if username:
        session['username'] = username
    return redirect(url_for('main.index'))

@main_bp.route('/batch-manager')
def batch_manager():
    """Batch Manager page for all platforms"""
    # Get personalized greeting
    username = session.get('username', None)
    greeting = get_personalized_greeting(username)
    
    # Fetch WhatsApp tasks from database
    whatsapp_tasks = WhatsAppTask.query.order_by(WhatsAppTask.created_at.desc()).all()
    
    # Fetch Instagram batches from database
    instagram_batches = InstagramBatch.query.order_by(InstagramBatch.created_at.desc()).all()
    
    # Fetch Facebook batches from database
    facebook_batches = FacebookBatch.query.order_by(FacebookBatch.created_at.desc()).all()
    
    return render_template('batch_manager.html',
                         greeting=greeting,
                         username=username,
                         whatsapp_tasks=whatsapp_tasks,
                         instagram_batches=instagram_batches,
                         facebook_batches=facebook_batches)

@main_bp.route('/status')
def status():
    """Get status of all services"""
    # Get counts for each platform
    instagram_count = InstagramBatch.query.filter(
        InstagramBatch.status.in_(['running'])
    ).count()
    
    facebook_count = FacebookBatch.query.filter(
        FacebookBatch.status.in_(['running'])
    ).count()
    
    whatsapp_count = WhatsAppTask.query.filter(
        WhatsAppTask.status.in_(['created', 'running'])
    ).count()
    
    return jsonify({
        "whatsapp": {
            "active": True,
            "activeTaskCount": whatsapp_count
        },
        "facebook": {
            "active": True,
            "activeBatchCount": facebook_count
        },
        "instagram": {
            "active": True,
            "activeBatchCount": instagram_count
        }
    })