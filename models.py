from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from app import db

class WhatsAppTask(db.Model):
    """Model for WhatsApp message sending tasks"""
    id = db.Column(db.String(64), primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    phone_number = db.Column(db.String(20), nullable=True)
    status = db.Column(db.String(20), default='created')  # created, running, completed, stopped, failed
    total_recipients = db.Column(db.Integer, default=0)
    total_messages = db.Column(db.Integer, default=0)
    sent_count = db.Column(db.Integer, default=0)
    failed_count = db.Column(db.Integer, default=0)
    delay = db.Column(db.Integer, default=10)  # delay in seconds between messages
    
    def __repr__(self):
        return f'<WhatsAppTask {self.id}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'phone_number': self.phone_number,
            'status': self.status,
            'total_recipients': self.total_recipients,
            'total_messages': self.total_messages,
            'sent_count': self.sent_count,
            'failed_count': self.failed_count,
            'delay': self.delay,
            'progress': self.progress
        }
    
    @property
    def progress(self):
        """Calculate the task's progress as a percentage"""
        if self.total_recipients * self.total_messages == 0:
            return 0
        return round((self.sent_count + self.failed_count) / (self.total_recipients * self.total_messages) * 100)

class WhatsAppMessage(db.Model):
    """Model for individual WhatsApp messages"""
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.String(64), db.ForeignKey('whats_app_task.id'), nullable=False)
    recipient = db.Column(db.String(64), nullable=False)
    message = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='pending')  # pending, sent, failed
    sent_at = db.Column(db.DateTime, nullable=True)
    error = db.Column(db.Text, nullable=True)
    
    task = db.relationship('WhatsAppTask', backref=db.backref('messages', lazy=True))
    
    def __repr__(self):
        return f'<WhatsAppMessage {self.id}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'task_id': self.task_id,
            'recipient': self.recipient,
            'message': self.message,
            'status': self.status,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'error': self.error
        }

class InstagramBatch(db.Model):
    """Model for Instagram messaging batches"""
    id = db.Column(db.String(64), primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    username = db.Column(db.String(100), nullable=False)
    target = db.Column(db.String(100), nullable=False)
    target_type = db.Column(db.String(20), nullable=False)  # 'user' or 'group'
    status = db.Column(db.String(20), default='running')  # running, stopped, completed, failed 
    message_prefix = db.Column(db.Text, nullable=True)
    delay_time = db.Column(db.Integer, default=5)
    
    def __repr__(self):
        return f'<InstagramBatch {self.id}>'
    
    def to_dict(self):
        return {
            'batch_id': self.id,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None,
            'username': self.username,
            'target': self.target,
            'target_type': self.target_type,
            'status': self.status,
            'message_prefix': self.message_prefix,
            'delay_time': self.delay_time,
            'message_count': len(self.messages) if hasattr(self, 'messages') else 0
        }

class InstagramMessage(db.Model):
    """Model for Instagram messages within a batch"""
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.String(64), db.ForeignKey('instagram_batch.id'), nullable=False)
    message = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='pending')  # pending, sent, failed, info
    status_class = db.Column(db.String(30), default='message-pending')  # CSS class
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    error = db.Column(db.Text, nullable=True)
    
    batch = db.relationship('InstagramBatch', backref=db.backref('messages', lazy=True))
    
    def __repr__(self):
        return f'<InstagramMessage {self.id}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'batch_id': self.batch_id,
            'message': self.message,
            'status': self.status,
            'status_class': self.status_class,
            'time': self.timestamp.strftime('%Y-%m-%d %H:%M:%S') if self.timestamp else None,
            'error': self.error
        }

class FacebookBatch(db.Model):
    """Model for Facebook messaging batches"""
    id = db.Column(db.String(64), primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    access_token = db.Column(db.String(255), nullable=True)
    account_name = db.Column(db.String(100), nullable=True)
    conversation_id = db.Column(db.String(100), nullable=False)
    haters_name = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(20), default='running')  # running, stopped, completed, failed
    speed = db.Column(db.Integer, default=5)  # delay in seconds
    
    def __repr__(self):
        return f'<FacebookBatch {self.id}>'
    
    def to_dict(self):
        return {
            'batch_id': self.id,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None,
            'account_name': self.account_name,
            'conversation_id': self.conversation_id,
            'haters_name': self.haters_name,
            'status': self.status,
            'speed': self.speed,
            'message_count': len(self.messages) if hasattr(self, 'messages') else 0
        }

class FacebookMessage(db.Model):
    """Model for Facebook messages within a batch"""
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.String(64), db.ForeignKey('facebook_batch.id'), nullable=False)
    message = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='pending')  # pending, sent, failed, info
    status_class = db.Column(db.String(30), default='text-secondary')  # CSS class
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    error = db.Column(db.Text, nullable=True)
    
    batch = db.relationship('FacebookBatch', backref=db.backref('messages', lazy=True))
    
    def __repr__(self):
        return f'<FacebookMessage {self.id}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'batch_id': self.batch_id,
            'message': self.message,
            'status': self.status,
            'status_class': self.status_class,
            'time': self.timestamp.strftime('%Y-%m-%d %H:%M:%S') if self.timestamp else None,
            'error': self.error
        }