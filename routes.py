import logging
from flask import Blueprint, render_template, jsonify, redirect, url_for
from facebook import facebook_bp
from instagram import instagram_bp
from whatsapp_bridge import whatsapp_bp, whatsapp_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create blueprint
main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Main dashboard page for the automation hub"""
    return render_template('dashboard.html')

@main_bp.route('/status')
def status():
    """Get status of all services"""
    try:
        # Check WhatsApp status
        whatsapp_status = {
            'running': whatsapp_service.is_running(),
            'status': whatsapp_service.status,
            'phone': whatsapp_service.connected_phone
        }
        
        return jsonify({
            'success': True,
            'services': {
                'whatsapp': whatsapp_status,
                'facebook': {'available': True},
                'instagram': {'available': True}
            }
        })
    except Exception as e:
        logger.error(f"Error getting status: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error getting status: {str(e)}"
        })
