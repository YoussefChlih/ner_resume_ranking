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
        # Create indexes
        db.users.create_index('username', unique=True)
        db.users.create_index('email', unique=True)
        
        # Insert sample data if the database is empty
        if db.users.count_documents({}) == 0:
            # Insert sample recruiter
            db.users.insert_one({
                'username': 'recruiter',
                'email': 'recruiter@example.com',
                'password': generate_password_hash('password'),
                'user_type': 'recruiter',
                'created_at': datetime.now(),
                'email_confirmed': False,
                'email_confirmed_at': None,
                'two_factor_secret': None,
                'two_factor_enabled': False,
                'last_login': None,
                'failed_login_attempts': 0,
                'account_locked': False,
                'account_locked_until': None,
                'password_reset_token': None,
                'password_reset_expires': None,
                'active': True
            })
            
            # Insert sample candidate
            db.users.insert_one({
                'username': 'candidate',
                'email': 'candidate@example.com',
                'password': generate_password_hash('password'),
                'user_type': 'candidate',
                'created_at': datetime.now(),
                'email_confirmed': False,
                'email_confirmed_at': None,
                'two_factor_secret': None,
                'two_factor_enabled': False,
                'last_login': None,
                'failed_login_attempts': 0,
                'account_locked': False,
                'account_locked_until': None,
                'password_reset_token': None,
                'password_reset_expires': None,
                'active': True
            })
    
    if 'profiles' not in db.list_collection_names():
        db.create_collection('profiles')
        # Create index for user_id (must be unique)
        db.profiles.create_index('user_id', unique=True)
        
        # Default profile schema
        default_profile = {
            'full_name': '',
            'first_name': '',
            'bio': '',
            'profile_picture': '',
            'email': '',
            'phone': '',
            'location': '',
            'technical_skills': [],
            'soft_skills': [],
            'languages': [],
            'experience': [],
            'education': [],
            'social_links': {
                'linkedin': '',
                'github': '',
                'website': ''
            },
            'applications': [],
            'matches': [],
            'messages': [],
            'created_at': datetime.now(),
            'updated_at': datetime.now()
        }
        
        # Create a profile for existing users
        for user in db.users.find():
            profile = default_profile.copy()
            profile['user_id'] = user['_id']
            profile['email'] = user.get('email', '')
            db.profiles.insert_one(profile)
    
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

def get_profile(user_id):
    """Get user profile from database."""
    db = get_db()
    profile = db.profiles.find_one({'user_id': user_id})
    
    if not profile:
        # Create a default profile if none exists
        default_profile = {
            'user_id': user_id,
            'full_name': '',
            'first_name': '',
            'bio': '',
            'profile_picture': '',
            'email': '',
            'phone': '',
            'location': '',
            'technical_skills': [],
            'soft_skills': [],
            'languages': [],
            'experience': [],
            'education': [],
            'social_links': {
                'linkedin': '',
                'github': '',
                'website': ''
            },
            'applications': [],
            'matches': [],
            'messages': [],
            'created_at': datetime.now(),
            'updated_at': datetime.now()
        }
        db.profiles.insert_one(default_profile)
        return default_profile
    
    # Ensure all required fields are present
    required_fields = {
        'social_links': {'linkedin': '', 'github': '', 'website': ''},
        'technical_skills': [],
        'soft_skills': [],
        'languages': [],
        'experience': [],
        'education': [],
        'applications': [],
        'matches': [],
        'messages': []
    }
    
    for field, default_value in required_fields.items():
        if field not in profile:
            profile[field] = default_value
    
    return profile

def update_profile(user_id, profile_data):
    """Update user profile in database."""
    db = get_db()
    
    # Update the profile data
    profile_data['updated_at'] = datetime.now()
    
    # Handle arrays (skills, experience, education)
    if 'technical_skills' in profile_data:
        profile_data['technical_skills'] = list(set(profile_data['technical_skills']))
    if 'soft_skills' in profile_data:
        profile_data['soft_skills'] = list(set(profile_data['soft_skills']))
    if 'languages' in profile_data:
        profile_data['languages'] = list(set(profile_data['languages']))
    
    # Update the profile
    result = db.profiles.update_one(
        {'user_id': user_id},
        {'$set': profile_data}
    )
    
    return result.modified_count > 0

def update_profile_picture(user_id, picture_path):
    """Update user profile picture."""
    db = get_db()
    result = db.profiles.update_one(
        {'user_id': user_id},
        {
            '$set': {
                'profile_picture': picture_path,
                'updated_at': datetime.now()
            }
        }
    )
    return result.modified_count > 0

def add_experience(user_id, experience_data):
    """Add new experience to user profile."""
    db = get_db()
    result = db.profiles.update_one(
        {'user_id': user_id},
        {
            '$push': {'experience': experience_data},
            '$set': {'updated_at': datetime.now()}
        }
    )
    return result.modified_count > 0

def update_experience(user_id, experience_index, experience_data):
    """Update specific experience in user profile."""
    db = get_db()
    update_key = f'experience.{experience_index}'
    result = db.profiles.update_one(
        {'user_id': user_id},
        {
            '$set': {
                update_key: experience_data,
                'updated_at': datetime.now()
            }
        }
    )
    return result.modified_count > 0

def remove_experience(user_id, experience_index):
    """Remove experience from user profile."""
    db = get_db()
    result = db.profiles.update_one(
        {'user_id': user_id},
        {
            '$unset': {f'experience.{experience_index}': 1},
            '$set': {'updated_at': datetime.now()}
        }
    )
    if result.modified_count > 0:
        # Pull null values to clean up the array
        db.profiles.update_one(
            {'user_id': user_id},
            {'$pull': {'experience': None}}
        )
    return result.modified_count > 0

def add_education(user_id, education_data):
    """Add new education to user profile."""
    db = get_db()
    result = db.profiles.update_one(
        {'user_id': user_id},
        {
            '$push': {'education': education_data},
            '$set': {'updated_at': datetime.now()}
        }
    )
    return result.modified_count > 0

def update_education(user_id, education_index, education_data):
    """Update specific education in user profile."""
    db = get_db()
    update_key = f'education.{education_index}'
    result = db.profiles.update_one(
        {'user_id': user_id},
        {
            '$set': {
                update_key: education_data,
                'updated_at': datetime.now()
            }
        }
    )
    return result.modified_count > 0

def remove_education(user_id, education_index):
    """Remove education from user profile."""
    db = get_db()
    result = db.profiles.update_one(
        {'user_id': user_id},
        {
            '$unset': {f'education.{education_index}': 1},
            '$set': {'updated_at': datetime.now()}
        }
    )
    if result.modified_count > 0:
        # Pull null values to clean up the array
        db.profiles.update_one(
            {'user_id': user_id},
            {'$pull': {'education': None}}
        )
    return result.modified_count > 0

def update_skills(user_id, skill_type, skills):
    """Update user skills of a specific type."""
    db = get_db()
    if skill_type not in ['technical_skills', 'soft_skills', 'languages']:
        return False
    
    result = db.profiles.update_one(
        {'user_id': user_id},
        {
            '$set': {
                skill_type: list(set(skills)),
                'updated_at': datetime.now()
            }
        }
    )
    return result.modified_count > 0

def update_social_links(user_id, social_links):
    """Update user social links."""
    db = get_db()
    result = db.profiles.update_one(
        {'user_id': user_id},
        {
            '$set': {
                'social_links': social_links,
                'updated_at': datetime.now()
            }
        }
    )
    return result.modified_count > 0