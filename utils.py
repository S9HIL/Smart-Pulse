import logging
import json
import subprocess
import threading
import os
import signal
import time
import platform

logger = logging.getLogger(__name__)

def get_time_based_greeting():
    """
    Generate a time-based greeting message using Indian Standard Time (IST).
    Returns a string greeting based on the current time of day in India.
    """
    import datetime
    import pytz
    
    # Get current time in UTC
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    
    # Convert to Indian Standard Time (IST)
    ist_timezone = pytz.timezone('Asia/Kolkata')
    ist_time = utc_now.astimezone(ist_timezone)
    current_hour = ist_time.hour
    
    if 5 <= current_hour < 12:
        return f"Good Morning (IST: {ist_time.strftime('%H:%M')})"
    elif 12 <= current_hour < 17:
        return f"Good Afternoon (IST: {ist_time.strftime('%H:%M')})"
    elif 17 <= current_hour < 21:
        return f"Good Evening (IST: {ist_time.strftime('%H:%M')})"
    else:
        return f"Good Night (IST: {ist_time.strftime('%H:%M')})"

def get_personalized_greeting(username=None):
    """
    Generate a personalized greeting with time of day.
    
    Args:
        username (str, optional): User's name for personalization.
        
    Returns:
        str: A personalized greeting string
    """
    greeting = get_time_based_greeting()
    
    if username:
        return f"{greeting}, {username}!"
    else:
        return f"{greeting}!"


class WhatsAppService:
    """WhatsApp service manager that handles communication with Node.js WhatsApp service"""
    
    # Status properties
    status = "disconnected"
    phone_number = None
    pairing_code = None
    qr_code = None
    last_error = None
    messages = []
    
    def __init__(self, service_path):
        self.service_path = service_path
        self.process = None
        self.status = "stopped"
        self.messages = []
        self._stdout_thread = None
        self._stderr_thread = None
        self.connected_phone = None
        self.qr_code = None
        self.pairing_code = None
        self.last_error = None
        
    def start(self):
        """Start the WhatsApp service process"""
        # Check if file exists before trying to start
        if not os.path.isfile(self.service_path):
            logger.error(f"WhatsApp service not found at path: {self.service_path}")
            self.status = "disconnected"
            self.last_error = f"WhatsApp service file not found: {self.service_path}"
            return False
            
        if self.process and self.process.poll() is None:
            logger.info("WhatsApp service is already running")
            return True
            
        try:
            # Determine the Node.js path based on platform
            node_executable = "node"
            
            # Start the process
            logger.info(f"Starting WhatsApp service: {self.service_path}")
            self.process = subprocess.Popen(
                [node_executable, self.service_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=os.environ.copy()
            )
            
            # Start threads to read output
            self._stdout_thread = threading.Thread(target=self._read_stdout)
            self._stderr_thread = threading.Thread(target=self._read_stderr)
            self._stdout_thread.daemon = True
            self._stderr_thread.daemon = True
            self._stdout_thread.start()
            self._stderr_thread.start()
            
            self.status = "starting"
            logger.info("WhatsApp service started")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start WhatsApp service: {str(e)}")
            self.last_error = str(e)
            self.status = "disconnected"
            return False
            
    def stop(self):
        """Stop the WhatsApp service process"""
        if not self.process:
            logger.info("No WhatsApp service process to stop")
            return
            
        try:
            logger.info("Stopping WhatsApp service")
            
            # Send terminate signal
            if platform.system() == "Windows":
                self.process.terminate()
            else:
                os.kill(self.process.pid, signal.SIGTERM)
                
            # Wait for process to terminate
            self.process.wait(timeout=5)
            logger.info("WhatsApp service stopped")
            
        except subprocess.TimeoutExpired:
            logger.warning("WhatsApp service did not terminate gracefully, forcing kill")
            
            if platform.system() == "Windows":
                self.process.kill()
            else:
                os.kill(self.process.pid, signal.SIGKILL)
                
        except Exception as e:
            logger.error(f"Error stopping WhatsApp service: {str(e)}")
            
        finally:
            self.process = None
            self.status = "stopped"
            self.connected_phone = None
            self.qr_code = None
            self.pairing_code = None
            
    def restart(self):
        """Restart the WhatsApp service"""
        self.stop()
        time.sleep(2)  # Wait a bit before restarting
        self.start()
        
    def is_running(self):
        """Check if the WhatsApp service is running"""
        if self.process:
            return self.process.poll() is None
        return False
        
    def _read_stdout(self):
        """Read and process stdout from the WhatsApp service"""
        if not self.process or not self.process.stdout:
            logger.error("No process or stdout to read from")
            return
            
        for line in iter(self.process.stdout.readline, ''):
            if not line:
                break
                
            line = line.strip()
            logger.debug(f"WhatsApp stdout: {line}")
            
            try:
                # Check if line is JSON
                if line.startswith('{') and line.endswith('}'):
                    data = json.loads(line)
                    
                    # Process different message types
                    if 'type' in data:
                        if data['type'] == 'qr_code':
                            self.qr_code = data.get('qrData')
                            
                        elif data['type'] == 'pairing_code':
                            self.pairing_code = data.get('code')
                            
                        elif data['type'] == 'connection_update':
                            self.status = data.get('status', 'unknown')
                            self.connected_phone = data.get('phoneNumber')
                            self.phone_number = data.get('phoneNumber')
                            
                        elif data['type'] == 'message_log':
                            # Store message logs
                            log_entry = {
                                'timestamp': data.get('timestamp', time.strftime('%Y-%m-%d %H:%M:%S')),
                                'status': data.get('status', 'unknown'),
                                'message': data.get('message', ''),
                                'target': data.get('target', '')
                            }
                            self.messages.append(log_entry)
            except json.JSONDecodeError:
                pass  # Not a JSON line, ignore
                
        logger.info("WhatsApp stdout reader thread stopped")
        
    def _read_stderr(self):
        """Read stderr from the WhatsApp service"""
        if not self.process or not self.process.stderr:
            logger.error("No process or stderr to read from")
            return
            
        for line in iter(self.process.stderr.readline, ''):
            if not line:
                break
                
            line = line.strip()
            logger.error(f"WhatsApp stderr: {line}")
            self.last_error = line
            
        logger.info("WhatsApp stderr reader thread stopped")
        
    def send_command(self, command, data=None):
        """Send a command to the WhatsApp service using stdin"""
        if not self.is_running() or not self.process or not self.process.stdin:
            logger.error("Cannot send command - WhatsApp service is not running or stdin is not available")
            return False
            
        try:
            cmd_data = {
                'command': command
            }
            
            if data:
                cmd_data.update(data)
                
            # Write command to stdin
            cmd_json = json.dumps(cmd_data) + "\n"
            self.process.stdin.write(cmd_json)
            self.process.stdin.flush()
            return True
            
        except Exception as e:
            logger.error(f"Error sending command to WhatsApp service: {str(e)}")
            return False
