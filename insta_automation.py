"""
Instagram Automation Module for Sʌʜɩɭ Pʀʌjʌpʌtɩ Hub
Handles Instagram direct messaging automation using the provided automation class
"""

import logging
import time
import json
import threading
from datetime import datetime
from instagrapi import Client
from instagrapi.exceptions import LoginRequired, ClientError, ChallengeRequired
from instagrapi.mixins.challenge import ChallengeChoice
from app import db
from models import InstagramBatch, InstagramMessage

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Global variables to handle challenge verification
verification_code = {}
verification_lock = threading.Lock()

class InstagramAutomation:
    """Class to handle Instagram automation using Instagrapi."""
    
    def __init__(self, username, password):
        """Initialize Instagram automation client.
        
        Args:
            username (str): Instagram username
            password (str): Instagram password
        """
        self.username = username
        self.password = password
        self.client = Client()
        self.logged_in = False
        self.challenge_info = None
        
        # Set custom challenge resolver
        self.client.challenge_code_handler = self.custom_challenge_code_handler
    
    def custom_challenge_code_handler(self, username, choice):
        """Custom handler for Instagram security challenges.
        
        This will store the challenge info and wait for the code to be provided
        by the user through the web interface.
        
        Args:
            username (str): Instagram username
            choice (ChallengeChoice): Type of challenge (EMAIL, SMS, etc.)
            
        Returns:
            str: Verification code provided by user
        """
        logger.info(f"Challenge required for {username} via {choice}")
        
        # Store challenge info for the UI
        self.challenge_info = {
            "username": username,
            "choice_type": str(choice),
            "status": "pending"
        }
        
        # Wait for verification code from web interface
        # This will be a blocking operation, but we'll handle it with timeouts
        max_wait = 300  # 5 minutes
        wait_interval = 2
        waited = 0
        
        while waited < max_wait:
            with verification_lock:
                if username in verification_code:
                    code = verification_code.pop(username)
                    logger.info(f"Using verification code for {username}")
                    self.challenge_info["status"] = "resolved"
                    return code
            
            time.sleep(wait_interval)
            waited += wait_interval
        
        logger.error(f"Timed out waiting for verification code for {username}")
        self.challenge_info["status"] = "timeout"
        return "000000"  # Return invalid code to fail gracefully
    
    def get_challenge_info(self):
        """Get current challenge information.
        
        Returns:
            dict: Challenge information or None if no challenge
        """
        return self.challenge_info
        
    def submit_verification_code(self, code):
        """Submit verification code received from the user.
        
        Args:
            code (str): Verification code
            
        Returns:
            bool: True if code accepted, False otherwise
        """
        if not self.challenge_info:
            return False
            
        with verification_lock:
            verification_code[self.challenge_info["username"]] = code
        
        return True
    
    def login(self):
        """Log in to Instagram.
        
        Returns:
            dict or None: User info if login successful, None otherwise
        """
        try:
            # Reset challenge info
            self.challenge_info = None
            
            # Try to login
            user_info = self.client.login(self.username, self.password)
            self.logged_in = True
            logger.info(f"Successfully logged in as {self.username}")
            return user_info
        except ChallengeRequired as e:
            logger.warning(f"Challenge required during login: {str(e)}")
            # Challenge will be handled by our custom handler
            # Return special indicator that challenge is in progress
            return {"status": "challenge_required", "challenge_info": self.challenge_info}
        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
            return None
    
    def _check_login(self):
        """Check if logged in, try to relogin if not.
        
        Returns:
            bool: True if logged in successfully, False otherwise
        """
        if not self.logged_in:
            try:
                self.login()
                return self.logged_in
            except Exception as e:
                logger.error(f"Error during login check: {str(e)}")
                return False
        return True
    
    def get_user_id(self, username):
        """Get user ID from username.
        
        Args:
            username (str): Instagram username
        
        Returns:
            str or None: User ID if found, None otherwise
        """
        if not self._check_login():
            return None
        
        try:
            user = self.client.user_info_by_username(username)
            return user.pk
        except Exception as e:
            logger.error(f"Error getting user ID for {username}: {str(e)}")
            return None
    
    def send_direct_message(self, username, message):
        """Send a direct message to a user.
        
        Args:
            username (str): Instagram username
            message (str): Message to send
        
        Returns:
            bool: True if message sent successfully, False otherwise
        """
        if not self._check_login():
            return False
        
        try:
            # Try to get user ID from username
            user_id = self.get_user_id(username)
            if not user_id:
                logger.error(f"Could not find user ID for {username}")
                return False
            
            # Send the message
            result = self.client.direct_send(message, [user_id])
            logger.info(f"Message sent to {username}: {message[:20]}...")
            return True
        except Exception as e:
            logger.error(f"Error sending DM to {username}: {str(e)}")
            return False
    
    def send_group_message(self, group_id, message):
        """Send a message to a group chat.
        
        Args:
            group_id (str): Instagram group thread ID
            message (str): Message to send
        
        Returns:
            bool: True if message sent successfully, False otherwise
        """
        if not self._check_login():
            return False
        
        try:
            # Send message to the thread
            result = self.client.direct_send(message, thread_ids=[group_id])
            logger.info(f"Message sent to group {group_id}: {message[:20]}...")
            return True
        except Exception as e:
            logger.error(f"Error sending message to group {group_id}: {str(e)}")
            return False
    
    def get_group_info(self, group_id):
        """Get information about a group chat.
        
        Args:
            group_id (str): Instagram group thread ID
        
        Returns:
            dict or None: Group info if successful, None otherwise
        """
        if not self._check_login():
            return None
        
        try:
            thread_info = self.client.direct_thread(group_id)
            return {
                'id': thread_info.thread_id,
                'title': thread_info.thread_title,
                'users': [user.username for user in thread_info.users],
                'is_group': thread_info.is_group
            }
        except Exception as e:
            logger.error(f"Error getting group info: {str(e)}")
            return None


# Helper functions for integration with the main app

def log_message(batch_id, message, status="info", error=None):
    """Log a message to both the database and console.
    
    Args:
        batch_id (str): Batch ID for this message
        message (str): Message content
        status (str): Status type (info, success, failed, pending)
        error (str, optional): Error message if status is failed
    """
    status_class_map = {
        "info": "message-info",
        "success": "message-success",
        "failed": "message-failed",
        "pending": "message-pending"
    }
    
    status_class = status_class_map.get(status.lower(), "message-info")
    
    # Log to console
    if status.lower() == "failed":
        logger.error(f"Batch {batch_id}: {message} - {error}")
    else:
        logger.info(f"Batch {batch_id}: {message}")
    
    # Log to database
    try:
        msg = InstagramMessage(
            batch_id=batch_id,
            message=message,
            status=status.capitalize(),
            status_class=status_class,
            error=error
        )
        db.session.add(msg)
        db.session.commit()
    except Exception as e:
        logger.error(f"Error logging message to database: {str(e)}")


def update_batch_status(batch_id, status):
    """Update the status of a batch in the database.
    
    Args:
        batch_id (str): Batch ID to update
        status (str): New status (running, stopped, completed, failed)
    """
    try:
        batch = InstagramBatch.query.get(batch_id)
        if batch:
            batch.status = status
            batch.updated_at = datetime.now()
            db.session.commit()
    except Exception as e:
        logger.error(f"Error updating batch status: {str(e)}")


def start_message_sending(batch_id, username, password, target, target_type, message_prefix, messages, delay_time):
    """Start the message sending process in a background thread.
    
    Args:
        batch_id (str): Batch ID for this message batch
        username (str): Instagram username
        password (str): Instagram password
        target (str): Target username or group ID
        target_type (str): Type of target (user or group)
        message_prefix (str): Text to add before each message
        messages (list): List of messages to send
        delay_time (int): Delay between messages in seconds
    """
    # Log initial message
    log_message(batch_id, "Starting Instagram automation...", "info")
    
    # Initialize the automation client
    client = InstagramAutomation(username, password)
    
    # Log login attempt
    log_message(batch_id, "Attempting to log in to Instagram...", "info")
    
    # Try to login
    login_result = client.login()
    
    if not login_result:
        log_message(batch_id, "Failed to log in to Instagram", "failed", "Authentication failed")
        update_batch_status(batch_id, "failed")
        
        # Auto-delete failed login batches
        try:
            batch = InstagramBatch.query.get(batch_id)
            if batch:
                db.session.delete(batch)
                db.session.commit()
                logger.info(f"Automatically deleted failed login batch {batch_id}")
        except Exception as e:
            logger.error(f"Error auto-deleting failed batch: {str(e)}")
            
        return False
    
    if isinstance(login_result, dict) and login_result.get("status") == "challenge_required":
        log_message(batch_id, "Instagram security challenge required!", "info")
        challenge_info = login_result.get("challenge_info", {})
        challenge_type = challenge_info.get("choice_type", "unknown")
        
        log_message(
            batch_id, 
            f"Please check your {challenge_type} for a security code and enter it on the website", 
            "pending"
        )
        
        # Note: The challenge handling would be managed via the web interface
        # The automation class will wait for the code submission
        
        # This process would block the thread until the code is provided
        # We'll continue here assuming the code will be provided or timeout
        
        # Wait for a moment to check if the challenge is resolved
        time.sleep(10)
        
        if not client.logged_in:
            log_message(batch_id, "Failed to complete security challenge", "failed", "Challenge not completed")
            update_batch_status(batch_id, "failed")
            
            # Auto-delete failed challenge batches
            try:
                batch = InstagramBatch.query.get(batch_id)
                if batch:
                    db.session.delete(batch)
                    db.session.commit()
                    logger.info(f"Automatically deleted failed challenge batch {batch_id}")
            except Exception as e:
                logger.error(f"Error auto-deleting failed challenge batch: {str(e)}")
                
            return False
    
    # Successfully logged in
    log_message(batch_id, f"Successfully logged in as {username}", "success")
    
    # Identify the target type and send messages
    target_name = target
    is_group = target_type.lower() == "group"
    
    # Get information about the target
    if is_group:
        log_message(batch_id, f"Targeting group with ID: {target}", "info")
        group_info = client.get_group_info(target)
        if group_info:
            target_name = group_info.get('title', target)
            log_message(batch_id, f"Resolved group name: {target_name}", "info")
    else:
        log_message(batch_id, f"Targeting user: {target}", "info")
        user_id = client.get_user_id(target)
        if not user_id:
            log_message(batch_id, f"Could not find user with username {target}", "failed", "User not found")
            update_batch_status(batch_id, "failed")
            
            # Auto-delete batches with user not found
            try:
                batch = InstagramBatch.query.get(batch_id)
                if batch:
                    db.session.delete(batch)
                    db.session.commit()
                    logger.info(f"Automatically deleted batch {batch_id} due to user not found")
            except Exception as e:
                logger.error(f"Error auto-deleting batch with missing user: {str(e)}")
                
            return False
    
    # Start sending messages
    log_message(batch_id, f"Starting to send {len(messages)} messages to {target_name} with {delay_time}s delay", "info")
    
    # Track the batch status in the database
    update_batch_status(batch_id, "running")
    
    # Send messages with delay
    sent_count = 0
    failed_count = 0
    
    for i, message in enumerate(messages):
        try:
            # Check if the batch has been stopped
            batch = InstagramBatch.query.get(batch_id)
            if not batch or batch.status != "running":
                log_message(batch_id, "Message sending stopped by user", "info")
                break
            
            # Add prefix if provided
            full_message = message
            if message_prefix:
                full_message = f"{message_prefix}{message}"
            
            # Log as pending
            log_message(
                batch_id, 
                f"Sending message ({i+1}/{len(messages)}): {full_message[:50]}{'...' if len(full_message) > 50 else ''}", 
                "pending"
            )
            
            # Send based on target type
            success = False
            if is_group:
                success = client.send_group_message(target, full_message)
            else:
                success = client.send_direct_message(target, full_message)
            
            # Update counters and log result
            if success:
                sent_count += 1
                log_message(
                    batch_id, 
                    f"Message sent ({i+1}/{len(messages)}): {full_message[:50]}{'...' if len(full_message) > 50 else ''}", 
                    "success"
                )
            else:
                failed_count += 1
                log_message(
                    batch_id, 
                    f"Failed to send message ({i+1}/{len(messages)})", 
                    "failed", 
                    f"Error sending message: {full_message[:50]}{'...' if len(full_message) > 50 else ''}"
                )
            
            # Add delay between messages
            if i < len(messages) - 1:  # No need to wait after the last message
                log_message(batch_id, f"Waiting {delay_time} seconds before next message...", "info")
                time.sleep(delay_time)
                
        except Exception as e:
            failed_count += 1
            error_msg = str(e)
            logger.error(f"Error sending message: {error_msg}")
            log_message(batch_id, f"Error sending message ({i+1}/{len(messages)})", "failed", error_msg)
            
            # Wait a bit longer after an error
            time.sleep(delay_time * 2)
    
    # Log completion
    if sent_count == len(messages):
        log_message(batch_id, f"All {sent_count} messages sent successfully! ✅", "success")
        update_batch_status(batch_id, "completed")
    elif sent_count > 0:
        log_message(
            batch_id, 
            f"Completed with {sent_count} messages sent and {failed_count} failed", 
            "success" if sent_count > failed_count else "failed"
        )
        update_batch_status(batch_id, "completed" if sent_count > failed_count else "failed")
    else:
        log_message(batch_id, "Failed to send any messages", "failed", "All messages failed to send")
        update_batch_status(batch_id, "failed")
    
    return True