from pymongo import MongoClient
import os
from datetime import datetime
from werkzeug.security import generate_password_hash

# MongoDB connection
MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/')
DB_NAME = os.environ.get('DB_NAME', 'ner_resume_ranking')

_client = None
_db = None

def get_db():
    """Get database connection, initializing if needed."""
    global _client, _db
    if _db is None:
        _client = MongoClient(MONGO_URI)
        _db = _client[DB_NAME]
    return _db

def close_db():
    """Close the database connection."""
    global _client
    if _client is not None:
        _client.close()
        _client = None

def init_db():
    """Initialize database with necessary collections and indexes."""
    db = get_db()
    
    # Create collections if they don't exist
    if 'users' not in db.list_collection_names():
        db.create_collection('users')
        # Create index for username (must be unique)
        db.users.create_index('username', unique=True)
    
    if 'jobs' not in db.list_collection_names():
        db.create_collection('jobs')
        # Create indexes
        db.jobs.create_index('recruiter_id')
        db.jobs.create_index('status')
    
    if 'applications' not in db.list_collection_names():
        db.create_collection('applications')
        # Create indexes
        db.applications.create_index('job_id')
        db.applications.create_index('candidate_id')
    
    # Insert sample data if the database is empty
    if db.users.count_documents({}) == 0:
        # Insert sample recruiter with hashed password
        db.users.insert_one({
            'username': 'recruiter',
            'password': generate_password_hash('password'),
            'user_type': 'recruiter',
            'created_at': datetime.now()
        })
        
        # Insert sample candidate with hashed password
        db.users.insert_one({
            'username': 'candidate',
            'password': generate_password_hash('password'),
            'user_type': 'candidate',
            'created_at': datetime.now()
        })
    if 'appointments' not in db.list_collection_names():
        db.create_collection('appointments')
        # Create indexes
        db.appointments.create_index('recruiter_id')
        db.appointments.create_index('candidate_id')

    if 'notifications' not in db.list_collection_names():
        db.create_collection('notifications')
        # Create indexes
        db.notifications.create_index('user_id')
        db.notifications.create_index('read_status')