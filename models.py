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