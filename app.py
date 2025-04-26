import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Define the base class for SQLAlchemy models
class Base(DeclarativeBase):
    pass

# Create SQLAlchemy instance
db = SQLAlchemy(model_class=Base)

# Create Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "automation_hub_secret_key")

# Configure database
# Debug log for DATABASE_URL
database_url = os.environ.get("DATABASE_URL", "sqlite:///automation_hub.db")
logger.debug(f"Using database URL: {database_url}")

# Handle special case for postgres:// URLs
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
    logger.debug(f"Replaced postgres:// with postgresql:// in URL")

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialize database
db.init_app(app)

# Register blueprints - will be imported after db is initialized
with app.app_context():
    from facebook import facebook_bp
    from instagram import instagram_bp
    from routes import main_bp
    from whatsapp_bridge import whatsapp_bp
    
    # Register blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(facebook_bp, url_prefix='/facebook')
    app.register_blueprint(instagram_bp, url_prefix='/instagram')
    app.register_blueprint(whatsapp_bp, url_prefix='/whatsapp')
    
    # Import models to ensure they're registered with SQLAlchemy
    import models
    
    # Create all tables
    db.create_all()
    
    # Add context processor for current time in India
    from routes import get_current_indian_time
    
    @app.context_processor
    def inject_time():
        return {'curr_time': get_current_indian_time()}
    
    # Log startup info
    logger.info("Automation Hub started")