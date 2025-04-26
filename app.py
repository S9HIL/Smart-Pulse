import os
import logging
from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
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
app = Flask("SMART-PULSE")

# Set a secure secret key - use a string directly to ensure consistency 
app.config["SECRET_KEY"] = "smart_pulse_secret_key_by_sahil_prajapati_2025_supersecure"
app.secret_key = app.config["SECRET_KEY"]  # Also set directly on app for compatibility

# Configure database
# Debug log for DATABASE_URL
database_url = 'postgresql://koyeb-adm:npg_ZCUA5mS8uOFw@ep-orange-lab-a2otm96c.eu-central-1.pg.koyeb.app/koyebdb'
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

# Initialize database and migrations
db.init_app(app)
from flask_migrate import Migrate
migrate = Migrate(app, db)

# Initialize login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'warning'

@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(int(user_id))

# Register blueprints - will be imported after db is initialized
with app.app_context():
    from facebook import facebook_bp
    from instagram import instagram_bp
    from routes import main_bp
    from whatsapp_bridge import whatsapp_bp
    from auth import auth_bp
    
    # Register blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(facebook_bp, url_prefix='/facebook')
    app.register_blueprint(instagram_bp, url_prefix='/instagram')
    app.register_blueprint(whatsapp_bp, url_prefix='/whatsapp')
    
    # Import models to ensure they're registered with SQLAlchemy
    import models
    
    # Don't recreate tables on existing database
    # db.create_all()
    
    # Add context processor for current time in India
    from routes import get_current_indian_time
    
    @app.context_processor
    def inject_time():
        return {'curr_time': get_current_indian_time()}
    
    # Global before_request handler to enforce authentication
    @app.before_request
    def check_authentication():
        from flask import request, redirect, url_for, current_app
        from flask_login import current_user
        
        # List of routes that don't require authentication
        public_routes = [
            'static',            # Static files
            'auth.login',        # Login page
            'auth.register',     # Register page
            'auth.pending_approval',  # Pending approval page
            'main.index',        # Home page (will handle auth in the view)
        ]
        
        # Check if the endpoint is specified and needs protection
        if request.endpoint and not any(request.endpoint == route or request.endpoint.startswith(route + '.') for route in public_routes):
            # If user is not authenticated, redirect to login
            if not current_user.is_authenticated:
                return redirect(url_for('main.index'))
                
            # If user is authenticated but not approved, redirect to pending approval
            if not current_user.is_approved:
                return redirect(url_for('auth.pending_approval'))
    
    # Log startup info
    logger.info("Automation Hub started")
