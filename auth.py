"""
Authentication Blueprint
Handles user authentication, registration, and user management
"""
import logging
from datetime import datetime
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import User, UserApproval, db

# Configure logger
logger = logging.getLogger(__name__)

# Create blueprint
auth_bp = Blueprint('auth', __name__)

# Routes
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login page"""
    # If user is already logged in, redirect to dashboard
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = 'remember' in request.form
        
        # Validate input
        if not email or not password:
            flash('Email and password are required.', 'danger')
            return redirect(url_for('main.index'))
        
        # Find user
        user = User.query.filter_by(email=email).first()
        
        # Check if user exists and password is correct
        if user and user.check_password(password):
            # Check if user is banned
            if user.is_banned:
                flash('Your account has been banned. Please contact an administrator.', 'danger')
                return redirect(url_for('main.index'))
            
            # Login user
            login_user(user, remember=remember)
            
            # Update last login time
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            # Check approval status for non-admin users
            if not user.is_admin and not user.is_approved:
                flash('Your account is pending approval by an administrator.', 'warning')
                # Redirect to pending approval page
                return redirect(url_for('auth.pending_approval'))
            
            # Redirect to requested page or dashboard
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            return redirect(url_for('main.index'))
        else:
            flash('Invalid email or password.', 'danger')
            return redirect(url_for('main.index'))
    
    # Redirect GET requests to the main index page which shows the login form for unauthenticated users
    return redirect(url_for('main.index'))

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """User registration page"""
    # If user is already logged in, redirect to dashboard
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validate input
        if not username or not email or not password or not confirm_password:
            flash('All fields are required.', 'danger')
            return redirect(url_for('main.index'))
        
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('main.index'))
        
        # Check if username or email already exists
        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing_user:
            if existing_user.username == username:
                flash('Username already exists.', 'danger')
            else:
                flash('Email already registered.', 'danger')
            return redirect(url_for('main.index'))
        
        # Create new user
        new_user = User(username=username, email=email)
        new_user.set_password(password)
        
        # Check if this is the first user (make them admin)
        is_first_user = User.query.count() == 0
        
        # Set admin status for first user or if it's the owner email
        if is_first_user or email.lower() == "sp7441043@gmail.com":
            new_user.is_admin = True
            new_user.is_approved = True
            flash('Admin account created successfully!', 'success')
        else:
            # Create approval request
            approval_request = UserApproval(
                user=new_user,
                status='pending',
                notes=f"New registration on {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            db.session.add(approval_request)
            flash('Account created successfully! Please wait for admin approval.', 'success')
        
        # Save to database
        db.session.add(new_user)
        db.session.commit()
        
        # Login new admin users automatically
        if new_user.is_admin:
            login_user(new_user)
            return redirect(url_for('main.index'))
        else:
            return redirect(url_for('main.index'))
    
    # Redirect GET requests to the main index page which shows the registration form when clicked
    return redirect(url_for('main.index'))

@auth_bp.route('/logout')
@login_required
def logout():
    """User logout"""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('main.index'))

@auth_bp.route('/pending-approval')
@login_required
def pending_approval():
    """Pending approval page for users waiting for admin approval"""
    if current_user.is_approved:
        return redirect(url_for('main.index'))
    
    # Find user's approval request
    approval = UserApproval.query.filter_by(user_id=current_user.id).order_by(UserApproval.request_date.desc()).first()
    
    return render_template('auth/pending_approval.html', approval=approval)

@auth_bp.route('/profile')
@login_required
def profile():
    """User profile page"""
    return render_template('auth/profile.html')

@auth_bp.route('/change-password', methods=['POST'])
@login_required
def change_password():
    """Change user password"""
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    # Validate input
    if not current_password or not new_password or not confirm_password:
        flash('All fields are required.', 'danger')
        return redirect(url_for('auth.profile'))
    
    if new_password != confirm_password:
        flash('New passwords do not match.', 'danger')
        return redirect(url_for('auth.profile'))
    
    # Check current password
    if not current_user.check_password(current_password):
        flash('Current password is incorrect.', 'danger')
        return redirect(url_for('auth.profile'))
    
    # Update password
    current_user.set_password(new_password)
    db.session.commit()
    
    flash('Password updated successfully.', 'success')
    return redirect(url_for('auth.profile'))

# Admin routes
@auth_bp.route('/admin/users')
@login_required
def admin_users():
    """Admin user management page"""
    if not current_user.is_admin:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('main.index'))
    
    # Get all users
    users = User.query.all()
    
    # Get all pending approval requests
    pending_approvals = UserApproval.query.filter_by(status='pending').order_by(UserApproval.request_date.asc()).all()
    
    return render_template('auth/admin_users.html', users=users, pending_approvals=pending_approvals)

@auth_bp.route('/admin/approve/<int:user_id>', methods=['POST'])
@login_required
def approve_user(user_id):
    """Approve a user"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Permission denied'})
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found'})
    
    # Update user approval status
    user.is_approved = True
    
    # Update approval request
    approval = UserApproval.query.filter_by(user_id=user_id, status='pending').first()
    if approval:
        approval.status = 'approved'
        approval.approval_date = datetime.utcnow()
        approval.approved_by = current_user.id
        approval.notes = f"{approval.notes}\nApproved by {current_user.username} on {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"
    
    db.session.commit()
    
    return jsonify({
        'success': True, 
        'message': f'User {user.username} has been approved'
    })

@auth_bp.route('/admin/reject/<int:user_id>', methods=['POST'])
@login_required
def reject_user(user_id):
    """Reject a user approval request"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Permission denied'})
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found'})
    
    # Update approval request
    approval = UserApproval.query.filter_by(user_id=user_id, status='pending').first()
    if approval:
        approval.status = 'rejected'
        approval.approval_date = datetime.utcnow()
        approval.approved_by = current_user.id
        approval.notes = f"{approval.notes}\nRejected by {current_user.username} on {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"
    
    db.session.commit()
    
    return jsonify({
        'success': True, 
        'message': f'User {user.username} approval has been rejected'
    })

@auth_bp.route('/admin/ban/<int:user_id>', methods=['POST'])
@login_required
def ban_user(user_id):
    """Ban a user"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Permission denied'})
    
    # Make sure it's not the owner account
    owner = User.query.filter_by(email="sp7441043@gmail.com").first()
    if owner and owner.id == user_id:
        return jsonify({'success': False, 'message': 'Cannot ban the owner account'})
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found'})
    
    # Ban user
    user.is_banned = True
    user.is_approved = False
    
    # Add ban note
    note = request.json.get('note', '')
    approval = UserApproval(
        user_id=user_id,
        approved_by=current_user.id,
        status='banned',
        approval_date=datetime.utcnow(),
        notes=f"Banned by {current_user.username} on {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}\nReason: {note}"
    )
    db.session.add(approval)
    db.session.commit()
    
    return jsonify({
        'success': True, 
        'message': f'User {user.username} has been banned'
    })

@auth_bp.route('/admin/unban/<int:user_id>', methods=['POST'])
@login_required
def unban_user(user_id):
    """Unban a user"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Permission denied'})
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found'})
    
    # Unban user
    user.is_banned = False
    
    # Add unban note
    approval = UserApproval(
        user_id=user_id,
        approved_by=current_user.id,
        status='unbanned',
        approval_date=datetime.utcnow(),
        notes=f"Unbanned by {current_user.username} on {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    db.session.add(approval)
    db.session.commit()
    
    return jsonify({
        'success': True, 
        'message': f'User {user.username} has been unbanned'
    })

@auth_bp.route('/admin/delete/<int:user_id>', methods=['DELETE'])
@login_required
def delete_user(user_id):
    """Delete a user"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Permission denied'})
    
    # Make sure it's not the owner account
    owner = User.query.filter_by(email="sp7441043@gmail.com").first()
    if owner and owner.id == user_id:
        return jsonify({'success': False, 'message': 'Cannot delete the owner account'})
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found'})
    
    # Delete user and all associated data
    try:
        username = user.username
        db.session.delete(user)
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'User {username} has been deleted'
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting user {user_id}: {str(e)}")
        return jsonify({
            'success': False, 
            'message': f'Error deleting user: {str(e)}'
        })