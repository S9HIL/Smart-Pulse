"""
Main Routes for Automation Hub
Handles dashboard and status endpoints
"""
import logging
import datetime
import pytz
from flask import Blueprint, render_template, jsonify, request, session, redirect, url_for, flash
from flask_login import login_required, current_user
from models import WhatsAppTask, FacebookBatch, InstagramBatch, WhatsAppMessage, FacebookMessage, InstagramMessage, db
from utils import get_personalized_greeting
import traceback

# Get current Indian time
def get_current_indian_time():
    """Get current time in India (IST)"""
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.datetime.now(ist)
    return now.strftime('%H:%M:%S %p')

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Create main blueprint
main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Main dashboard page for the automation hub"""
    # Get current hour to determine time of day
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.datetime.now(ist)
    hour = now.hour
    
    # Determine time of day
    if 5 <= hour < 12:
        time_of_day = "Morning"
    elif 12 <= hour < 17:
        time_of_day = "Afternoon"
    elif 17 <= hour < 21:
        time_of_day = "Evening"
    else:
        time_of_day = "Night"
    
    return render_template('index.html', time_of_day=time_of_day)

@main_bp.route('/set_username', methods=['POST'])
def set_username():
    """Set the username in the session"""
    username = request.form.get('username', '').strip()
    if username:
        # Store username directly in a cookie instead of using session
        response = redirect(url_for('main.index'))
        response.set_cookie('username', username, max_age=86400*30)  # 30 days
        return response
    return redirect(url_for('main.index'))

@main_bp.route('/batch-manager')
@login_required
def batch_manager():
    """Batch Manager page for all platforms"""
    # Check if user is approved
    if not current_user.is_approved:
        flash('Your account is pending approval.', 'warning')
        return redirect(url_for('auth.pending_approval'))
    
    return render_template('batch_manager.html')

@main_bp.route('/delete-batch', methods=['POST'])
@login_required
def delete_batch():
    """Delete a batch from any platform"""
    # Check if user is approved
    if not current_user.is_approved:
        return jsonify({
            'success': False,
            'message': 'Your account is pending approval.'
        })
    try:
        batch_id = request.json.get('batch_id')
        platform = request.json.get('platform')
        
        if not batch_id or not platform:
            return jsonify({
                'success': False,
                'message': 'Missing batch_id or platform parameter'
            })
            
        logger.debug(f"Deleting {platform} batch: {batch_id}")
        
        # Handle deletion based on platform
        if platform == 'whatsapp':
            # First delete all messages
            messages = WhatsAppMessage.query.filter_by(task_id=batch_id).all()
            for message in messages:
                db.session.delete(message)
            
            # Then delete the task
            task = WhatsAppTask.query.get(batch_id)
            if task:
                db.session.delete(task)
                db.session.commit()
                return jsonify({'success': True, 'message': 'WhatsApp task deleted successfully'})
            else:
                return jsonify({'success': False, 'message': 'WhatsApp task not found'})
                
        elif platform == 'instagram':
            # First delete all messages
            messages = InstagramMessage.query.filter_by(batch_id=batch_id).all()
            for message in messages:
                db.session.delete(message)
            
            # Then delete the batch
            batch = InstagramBatch.query.get(batch_id)
            if batch:
                db.session.delete(batch)
                db.session.commit()
                return jsonify({'success': True, 'message': 'Instagram batch deleted successfully'})
            else:
                return jsonify({'success': False, 'message': 'Instagram batch not found'})
                
        elif platform == 'facebook':
            # First delete all messages
            messages = FacebookMessage.query.filter_by(batch_id=batch_id).all()
            for message in messages:
                db.session.delete(message)
            
            # Then delete the batch
            batch = FacebookBatch.query.get(batch_id)
            if batch:
                db.session.delete(batch)
                db.session.commit()
                return jsonify({'success': True, 'message': 'Facebook batch deleted successfully'})
            else:
                return jsonify({'success': False, 'message': 'Facebook batch not found'})
        
        else:
            return jsonify({'success': False, 'message': f'Unknown platform: {platform}'})
            
    except Exception as e:
        logger.error(f"Error deleting batch: {str(e)}")
        logger.error(traceback.format_exc())
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f"Error deleting batch: {str(e)}"
        })

@main_bp.route('/status')
@login_required
def status():
    """Get status of all services"""
    # Check if user is approved
    if not current_user.is_approved:
        return jsonify({
            'success': False,
            'message': 'Your account is pending approval.'
        })
    try:
        # Count tasks by platform and status
        whatsapp_stats = {
            'total': WhatsAppTask.query.count(),
            'running': WhatsAppTask.query.filter_by(status='running').count(),
            'completed': WhatsAppTask.query.filter_by(status='completed').count(),
            'stopped': WhatsAppTask.query.filter_by(status='stopped').count(),
            'failed': WhatsAppTask.query.filter_by(status='failed').count()
        }
        
        instagram_stats = {
            'total': InstagramBatch.query.count(),
            'running': InstagramBatch.query.filter_by(status='running').count(),
            'completed': InstagramBatch.query.filter_by(status='completed').count(),
            'stopped': InstagramBatch.query.filter_by(status='stopped').count(),
            'failed': InstagramBatch.query.filter_by(status='failed').count()
        }
        
        facebook_stats = {
            'total': FacebookBatch.query.count(),
            'running': FacebookBatch.query.filter_by(status='running').count(),
            'completed': FacebookBatch.query.filter_by(status='completed').count(),
            'stopped': FacebookBatch.query.filter_by(status='stopped').count(),
            'failed': FacebookBatch.query.filter_by(status='failed').count()
        }
        
        # Get the latest tasks for each platform
        latest_whatsapp = WhatsAppTask.query.order_by(WhatsAppTask.created_at.desc()).limit(5).all()
        latest_instagram = InstagramBatch.query.order_by(InstagramBatch.created_at.desc()).limit(5).all()
        latest_facebook = FacebookBatch.query.order_by(FacebookBatch.created_at.desc()).limit(5).all()
        
        return jsonify({
            'success': True,
            'platforms': {
                'whatsapp': {
                    'stats': whatsapp_stats,
                    'latest': [task.to_dict() for task in latest_whatsapp]
                },
                'instagram': {
                    'stats': instagram_stats,
                    'latest': [batch.to_dict() for batch in latest_instagram]
                },
                'facebook': {
                    'stats': facebook_stats,
                    'latest': [batch.to_dict() for batch in latest_facebook]
                }
            }
        })
    
    except Exception as e:
        logger.error(f"Error getting platform status: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error getting status: {str(e)}"
        })