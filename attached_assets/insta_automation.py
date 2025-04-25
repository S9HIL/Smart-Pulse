import logging
import time
import json
import threading
from instagrapi import Client
from instagrapi.exceptions import LoginRequired, ClientError, ChallengeRequired
from instagrapi.mixins.challenge import ChallengeChoice

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
    
    def prevent_group_name_change(self, group_id, original_name=None):
        """Monitor and prevent group name changes.
        
        Args:
            group_id (str): Instagram group thread ID
            original_name (str, optional): Original group name to maintain
        
        Returns:
            bool: True if prevention enabled, False otherwise
        """
        if not self._check_login():
            return False
        
        try:
            # Get thread info
            thread_info = self.client.direct_thread(group_id)
            
            # If original_name not provided, use current name
            if not original_name:
                original_name = thread_info.thread_title
            
            # If name differs from original, change it back
            if thread_info.thread_title != original_name:
                self.client.direct_thread_update_title(group_id, original_name)
                logger.info(f"Reset group name to {original_name}")
            
            return True
        except Exception as e:
            logger.error(f"Error in group name change prevention: {str(e)}")
            return False
    
    def prevent_group_avatar_change(self, group_id):
        """Monitor and prevent group avatar changes.
        
        Args:
            group_id (str): Instagram group thread ID
        
        Returns:
            bool: True if prevention enabled, False otherwise
        """
        if not self._check_login():
            return False
        
        try:
            # This functionality would require monitoring changes
            # and restoring the original avatar, which is beyond
            # the scope of the basic API functionality.
            # Placeholder for future implementation.
            logger.warning("Group avatar change prevention not fully implemented")
            return True
        except Exception as e:
            logger.error(f"Error in group avatar change prevention: {str(e)}")
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
