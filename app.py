import os
import logging
from flask import Flask
from facebook import facebook_bp
from instagram import instagram_bp
from routes import main_bp
from whatsapp_bridge import whatsapp_bp

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "automation_hub_secret_key")

# Register blueprints
app.register_blueprint(main_bp)
app.register_blueprint(facebook_bp, url_prefix='/facebook')
app.register_blueprint(instagram_bp, url_prefix='/instagram')
app.register_blueprint(whatsapp_bp, url_prefix='/whatsapp')

# Log startup info
logger.info("Automation Hub started")
