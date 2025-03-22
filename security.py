import os
import pyotp
import jwt
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, session, current_app
from werkzeug.security import generate_password_hash, check_password_hash
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from cryptography.fernet import Fernet

# Configuration
JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'your-secret-key')  # À changer en production
FERNET_KEY = Fernet.generate_key()
cipher_suite = Fernet(FERNET_KEY)

# Email configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USERNAME = os.environ.get('SMTP_USERNAME', '')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')

class Security:
    def __init__(self, app=None):
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        self.app = app
        # Store the Fernet key in the app config
        app.config['FERNET_KEY'] = FERNET_KEY
        
        # Initialize the JWT secret key
        app.config['JWT_SECRET_KEY'] = JWT_SECRET_KEY

    def generate_confirmation_token(self, email):
        """Generate a confirmation token for email verification."""
        expiration = datetime.utcnow() + timedelta(hours=24)
        token = jwt.encode(
            {'email': email, 'exp': expiration},
            JWT_SECRET_KEY,
            algorithm='HS256'
        )
        return token

    def verify_confirmation_token(self, token):
        """Verify the confirmation token."""
        try:
            data = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
            return data['email']
        except:
            return None

    def generate_reset_token(self, email):
        """Generate a password reset token."""
        expiration = datetime.utcnow() + timedelta(hours=1)
        token = jwt.encode(
            {'email': email, 'exp': expiration},
            JWT_SECRET_KEY,
            algorithm='HS256'
        )
        return token

    def verify_reset_token(self, token):
        """Verify the password reset token."""
        try:
            data = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
            return data['email']
        except:
            return None

    def send_email(self, to_email, subject, body):
        """Send an email using SMTP."""
        if not all([SMTP_USERNAME, SMTP_PASSWORD]):
            raise ValueError("SMTP credentials not configured")

        msg = MIMEMultipart()
        msg['From'] = SMTP_USERNAME
        msg['To'] = to_email
        msg['Subject'] = subject

        msg.attach(MIMEText(body, 'html'))

        try:
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
            server.quit()
            return True
        except Exception as e:
            print(f"Error sending email: {e}")
            return False

    def send_confirmation_email(self, email):
        """Send confirmation email to user."""
        token = self.generate_confirmation_token(email)
        confirm_url = f"http://localhost:5000/confirm/{token}"
        subject = "Please confirm your email"
        body = f"""
        <p>Welcome! Please click the link below to confirm your email address:</p>
        <p><a href="{confirm_url}">Confirm Email</a></p>
        <p>If you did not make this request, please ignore this email.</p>
        """
        return self.send_email(email, subject, body)

    def send_reset_password_email(self, email):
        """Send password reset email to user."""
        token = self.generate_reset_token(email)
        reset_url = f"http://localhost:5000/reset/{token}"
        subject = "Password Reset Request"
        body = f"""
        <p>To reset your password, please click the link below:</p>
        <p><a href="{reset_url}">Reset Password</a></p>
        <p>If you did not make this request, please ignore this email.</p>
        <p>This link will expire in 1 hour.</p>
        """
        return self.send_email(email, subject, body)

    def generate_2fa_secret(self):
        """Generate a new 2FA secret key."""
        return pyotp.random_base32()

    def verify_2fa_token(self, secret, token):
        """Verify a 2FA token."""
        totp = pyotp.TOTP(secret)
        return totp.verify(token)

    def get_2fa_qr_url(self, secret, email):
        """Get the QR code URL for 2FA setup."""
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(email, issuer_name="NER Resume Ranking")

def login_required(f):
    """Decorator to require login for routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'message': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function

def require_2fa(f):
    """Decorator to require 2FA verification for routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('2fa_verified'):
            return jsonify({'message': '2FA verification required'}), 401
        return f(*args, **kwargs)
    return decorated_function 