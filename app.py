from flask import Flask, render_template, request, redirect, url_for, flash, session
import os
import uuid
from werkzeug.utils import secure_filename
from database import get_db, init_db
from models import extract_entities_from_text, extract_text_from_pdf, rank_cvs_by_similarity
from datetime import datetime
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
from cryptography.fernet import Fernet

app = Flask(__name__)
app.secret_key = 'ner_resume_ranking_secret_key'

# Configure upload folder
UPLOAD_FOLDER = os.path.join('data', 'resumes')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'pdf'}

# Ensure upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Generate a key for encryption and decryption
# You should store this key securely
key = Fernet.generate_key()
cipher_suite = Fernet(key)

def encrypt_message(message: str) -> bytes:
    """Encrypts a message."""
    return cipher_suite.encrypt(message.encode())

def decrypt_message(encrypted_message: bytes) -> str:
    """Decrypts a message."""
    return cipher_suite.decrypt(encrypted_message).decode()

# Utility functions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Routes
@app.route('/')
def home():
    return render_template('base.html')

# Combined auth route (login/register)
@app.route('/auth', methods=['GET', 'POST'])
def auth():
    if request.method == 'POST':
        action = request.form.get('action')
        username = request.form.get('username')
        password = request.form.get('password')
        user_type = request.form.get('user_type', 'candidate')
        
        db = get_db()
        
        if action == 'login':
            # Login logic with hashed password check
            user = db.users.find_one({'username': username})
            if user and check_password_hash(user['password'], password):
                session['user_id'] = str(user['_id'])
                session['username'] = user['username']
                session['user_type'] = user['user_type']
                
                if user['user_type'] == 'recruiter':
                    return redirect(url_for('recruiter'))
                else:
                    return redirect(url_for('candidate'))
            else:
                flash('Invalid credentials')
        
        elif action == 'register':
            # Register with password hashing
            if db.users.find_one({'username': username}):
                flash('Username already exists')
            else:
                hashed_password = generate_password_hash(password)
                user_id = db.users.insert_one({
                    'username': username,
                    'password': hashed_password,  # Hashed password
                    'user_type': user_type,
                    'created_at': datetime.now()
                }).inserted_id
                
                flash('Registration successful! Please login.')
    
    return render_template('auth.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# Recruiter routes
@app.route('/recruiter', methods=['GET', 'POST'])
def recruiter():
    if session.get('user_type') != 'recruiter':
        flash('Access denied')
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        # Handle job posting
        title = request.form['title']
        description = request.form['description']
        
        # Process keywords and weights
        keywords = {}
        keyword_list = request.form.getlist('keyword[]')
        weight_list = request.form.getlist('weight[]')
        
        for i in range(len(keyword_list)):
            if keyword_list[i] and weight_list[i]:
                keywords[keyword_list[i]] = float(weight_list[i])
        
        # Insert job into MongoDB
        db = get_db()
        job_id = db.jobs.insert_one({
            'title': title,
            'description': description,
            'recruiter_id': ObjectId(session['user_id']),
            'posted_date': datetime.now(),
            'status': 'open',
            'keywords': keywords
        }).inserted_id
        
        flash('Job posted successfully!')
    
    # Get jobs for this recruiter
    db = get_db()
    jobs = list(db.jobs.find({'recruiter_id': ObjectId(session['user_id'])}))
    
    return render_template('recruiter.html', jobs=jobs)

@app.route('/rankings/<job_id>')
def rankings(job_id):
    if session.get('user_type') != 'recruiter':
        flash('Access denied')
        return redirect(url_for('home'))
    
    db = get_db()
    
    # Get job details
    job = db.jobs.find_one({'_id': ObjectId(job_id)})
    if not job:
        flash('Job not found')
        return redirect(url_for('recruiter'))
    
    # Get applications for this job
    applications = list(db.applications.find({'job_id': ObjectId(job_id)}))
    app_users = []
    
    if applications:
        # Get user details for each application
        for app in applications:
            user = db.users.find_one({'_id': app['candidate_id']})
            if user:
                app_users.append({
                    'application': app,
                    'username': user['username']
                })
    
    # Perform ranking if there are applications
    ranked_applicants = []
    if applications:
        # Extract job description entities
        job_entities = extract_entities_from_text(job['description'])
        
        # Get CV texts and extract entities
        cv_texts = []
        cv_usernames = []
        
        for app_user in app_users:
            resume_path = app_user['application']['resume_path']
            cv_usernames.append(app_user['username'])
            
            # Extract text from PDF
            cv_text = extract_text_from_pdf(resume_path)
            cv_texts.append(cv_text)
        
        # Define keyword weights (from the job document)
        keyword_weights = job.get('keywords', {"python": 0.8, "data science": 0.9})
        
        # Rank CVs
        ranked_applicants = rank_cvs_by_similarity(cv_texts, job_entities, keyword_weights)
        
        # Add usernames to ranked applicants
        for i, rank in enumerate(ranked_applicants):
            rank["name"] = cv_usernames[i]
    
    return render_template('rankings.html', job=job, applications=app_users, ranked_applicants=ranked_applicants)

# Candidate routes
@app.route('/candidate')
def candidate():
    if session.get('user_id') is None:
        flash('Please login first')
        return redirect(url_for('auth'))
    
    # Get applications by this candidate
    db = get_db()
    candidate_id = ObjectId(session['user_id'])
    
    # Find all applications by this candidate
    applications = list(db.applications.find({'candidate_id': candidate_id}))
    
    # Get job details for each application
    app_details = []
    for app in applications:
        job = db.jobs.find_one({'_id': app['job_id']})
        if job:
            # Get recruiter info
            recruiter = db.users.find_one({'_id': job['recruiter_id']})
            job['recruiter_info'] = recruiter if recruiter else None  # Ensure recruiter_info always exists
            
            app_details.append({
                'application': app,
                'job': job
            })
    
    # Get all open jobs
    jobs = list(db.jobs.find({'status': 'open'}))
    
    # Get recruiter info for each job
    for job in jobs:
        recruiter = db.users.find_one({'_id': job['recruiter_id']})
        job['recruiter_info'] = recruiter if recruiter else None  # Ensure recruiter_info always exists
    
    return render_template('candidate.html', applications=app_details, jobs=jobs)

@app.route('/apply/<job_id>', methods=['GET', 'POST'])
def apply(job_id):
    if session.get('user_id') is None:
        flash('Please login first')
        return redirect(url_for('auth'))
    
    db = get_db()
    job = db.jobs.find_one({'_id': ObjectId(job_id)})
    
    if not job:
        flash('Job not found')
        return redirect(url_for('candidate'))
    
    if request.method == 'POST':
        # Check if the post request has the file part
        if 'resume' not in request.files:
            flash('No resume part')
            return redirect(request.url)
        
        file = request.files['resume']
        
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            # Generate unique filename
            filename = secure_filename(f"{str(uuid.uuid4())}_{file.filename}")
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            # Save application to database
            db.applications.insert_one({
                'job_id': ObjectId(job_id),
                'candidate_id': ObjectId(session['user_id']),
                'resume_path': file_path,
                'applied_date': datetime.now(),
                'status': 'pending'
            })
            
            flash('Application submitted successfully!')
            return redirect(url_for('candidate'))
    
    return render_template('apply.html', job=job)
@app.route('/schedule_interview/<application_id>', methods=['GET', 'POST'])
def schedule_interview(application_id):
    if session.get('user_type') != 'recruiter':
        flash('Access denied')
        return redirect(url_for('home'))
    
    db = get_db()
    application = db.applications.find_one({'_id': ObjectId(application_id)})
    
    if not application:
        flash('Application not found')
        return redirect(url_for('recruiter'))
    
    if request.method == 'POST':
        # Get form data
        interview_date = request.form.get('interview_date')
        interview_time = request.form.get('interview_time')
        interview_type = request.form.get('interview_type')
        interview_details = request.form.get('interview_details')
        reminder_enabled = request.form.get('reminder_enabled') == 'on'
        
        # Create timestamp from date and time
        interview_datetime = datetime.strptime(f"{interview_date} {interview_time}", "%Y-%m-%d %H:%M")
        
        # Create appointment document
        appointment_id = db.appointments.insert_one({
            'application_id': ObjectId(application_id),
            'job_id': application['job_id'],
            'recruiter_id': ObjectId(session['user_id']),
            'candidate_id': application['candidate_id'],
            'interview_datetime': interview_datetime,
            'interview_type': interview_type,
            'interview_details': interview_details,
            'status': 'scheduled',
            'reminder_enabled': reminder_enabled,
            'reminder_sent': False,
            'last_minute_reminder_sent': False,
            'created_at': datetime.now()
        }).inserted_id
        
        # Create notification for candidate
        job = db.jobs.find_one({'_id': application['job_id']})
        notification_text = f"You have been invited to an interview for the position: {job['title']}"
        
        db.notifications.insert_one({
            'user_id': application['candidate_id'],
            'type': 'interview_invitation',
            'related_id': appointment_id,
            'message': notification_text,
            'read_status': False,
            'created_at': datetime.now()
        })
        
        # Update application status
        db.applications.update_one(
            {'_id': ObjectId(application_id)},
            {'$set': {'status': 'interview_scheduled'}}
        )
        
        flash('Interview scheduled and candidate notified')
        return redirect(url_for('rankings', job_id=str(application['job_id'])))
    
    # Get candidate info
    candidate = db.users.find_one({'_id': application['candidate_id']})
    job = db.jobs.find_one({'_id': application['job_id']})
    
    return render_template('schedule_interview.html', 
                          application=application, 
                          candidate=candidate,
                          job=job)

@app.route('/notifications')
def notifications():
    if 'user_id' not in session:
        flash('Please login first')
        return redirect(url_for('auth'))
    
    db = get_db()
    user_id = ObjectId(session['user_id'])
    
    # Get user's notifications
    user_notifications = list(db.notifications.find({
        'user_id': user_id
    }).sort('created_at', -1))
    
    # Mark notifications as read
    db.notifications.update_many(
        {'user_id': user_id, 'read_status': False},
        {'$set': {'read_status': True}}
    )
    
    return render_template('notifications.html', notifications=user_notifications)

@app.route('/appointments')
def appointments():
    if 'user_id' not in session:
        flash('Please login first')
        return redirect(url_for('auth'))
    
    db = get_db()
    user_id = ObjectId(session['user_id'])
    user_type = session.get('user_type')
    
    # Different queries for candidates and recruiters
    if user_type == 'recruiter':
        appointments = list(db.appointments.find({
            'recruiter_id': user_id
        }).sort('interview_datetime', 1))
        
        # Enrich appointments with candidate names
        for appointment in appointments:
            candidate = db.users.find_one({'_id': appointment['candidate_id']})
            job = db.jobs.find_one({'_id': appointment['job_id']})
            appointment['candidate_name'] = candidate['username'] if candidate else 'Unknown'
            appointment['job_title'] = job['title'] if job else 'Unknown Position'
    else:
        appointments = list(db.appointments.find({
            'candidate_id': user_id
        }).sort('interview_datetime', 1))
        
        # Enrich appointments with recruiter names and job titles
        for appointment in appointments:
            recruiter = db.users.find_one({'_id': appointment['recruiter_id']})
            job = db.jobs.find_one({'_id': appointment['job_id']})
            appointment['recruiter_name'] = recruiter['username'] if recruiter else 'Unknown'
            appointment['job_title'] = job['title'] if job else 'Unknown Position'
    
    return render_template('appointments.html', appointments=appointments, user_type=user_type)

# Add a notification counter for the navigation
@app.context_processor
def notification_count():
    if 'user_id' in session:
        db = get_db()
        notification_count = db.notifications.count_documents({
            'user_id': ObjectId(session['user_id']),
            'read_status': False
        })
        
        unread_message_count = db.messages.count_documents({
            'recipient_id': ObjectId(session['user_id']),
            'read': False
        })
        
        return {
            'notification_count': notification_count,
            'unread_message_count': unread_message_count
        }
    return {
        'notification_count': 0,
        'unread_message_count': 0
    }

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        flash('Please login first')
        return redirect(url_for('auth'))
    
    db = get_db()
    user_id = ObjectId(session['user_id'])
    
    # Get existing profile or create new one
    user_profile = db.profiles.find_one({'user_id': user_id})
    if not user_profile:
        user_profile = {
            'user_id': user_id,
            'full_name': '',
            'first_name': '',
            'email': '',
            'phone': '',
            'linkedin': '',
            'github': '',
            'bio': '',
            'location': '',
            'website': '',
            'profile_picture': ''
        }
    
    if request.method == 'POST':
        # Update profile information
        profile_data = {
            'user_id': user_id,
            'full_name': request.form.get('full_name', ''),
            'first_name': request.form.get('first_name', ''),
            'email': request.form.get('email', ''),
            'phone': request.form.get('phone', ''),
            'linkedin': request.form.get('linkedin', ''),
            'github': request.form.get('github', ''),
            'bio': request.form.get('bio', ''),
            'location': request.form.get('location', ''),
            'website': request.form.get('website', ''),
            'profile_picture': user_profile.get('profile_picture', '')
        }
        
        # Handle profile picture upload
        if 'profile_picture' in request.files:
            file = request.files['profile_picture']
            if file and file.filename != '':
                filename = secure_filename(f"{str(uuid.uuid4())}_profile.jpg")
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                profile_data['profile_picture'] = file_path
        
        # Update or create profile
        if user_profile.get('_id'):
            db.profiles.update_one({'_id': user_profile['_id']}, {'$set': profile_data})
        else:
            db.profiles.insert_one(profile_data)
        
        flash('Profile updated successfully')
        return redirect(url_for('profile'))
    
    return render_template('profile.html', profile=user_profile)

@app.route('/contact/<candidate_id>', methods=['GET', 'POST'])
def contact_candidate(candidate_id):
    if session.get('user_type') != 'recruiter':
        flash('Access denied')
        return redirect(url_for('home'))
    
    db = get_db()
    candidate = db.users.find_one({'_id': ObjectId(candidate_id)})
    
    if not candidate:
        flash('Candidate not found')
        return redirect(url_for('recruiter'))
    
    # Get candidate profile for contact details
    profile = db.profiles.find_one({'user_id': ObjectId(candidate_id)})
    
    # Get candidate applications and extract skills, experience, education from the last application
    applications = list(db.applications.find({'candidate_id': ObjectId(candidate_id)}))
    
    candidate_skills = []
    candidate_experience = []
    candidate_education = []
    applications_history = []
    
    for app in applications:
        # Get job details
        job = db.jobs.find_one({'_id': app['job_id']})
        job_title = job['title'] if job else 'Unknown Position'
        
        # Add to applications history
        applications_history.append({
            'job_title': job_title,
            'applied_date': app['applied_date'],
            'status': app['status']
        })
        
        # For the most recent application, try to get skills, experience, education
        if app.get('resume_path'):
            # If we have extracted entities for this application, use them
            if app.get('entities'):
                if 'COMPETENCES' in app['entities'] and not candidate_skills:
                    candidate_skills = app['entities']['COMPETENCES']
                
                if 'EXPERIENCE' in app['entities'] and not candidate_experience:
                    candidate_experience = app['entities']['EXPERIENCE']
                
                if 'DIPLOME' in app['entities'] and not candidate_education:
                    candidate_education = app['entities']['DIPLOME']
            else:
                # Try to extract entities from the resume if not already done
                try:
                    cv_text = extract_text_from_pdf(app['resume_path'])
                    entities = extract_entities_from_text(cv_text)
                    
                    # Store entities in the application document for future use
                    db.applications.update_one(
                        {'_id': app['_id']},
                        {'$set': {'entities': entities}}
                    )
                    
                    if 'COMPETENCES' in entities and not candidate_skills:
                        candidate_skills = entities['COMPETENCES']
                    
                    if 'EXPERIENCE' in entities and not candidate_experience:
                        candidate_experience = entities['EXPERIENCE']
                    
                    if 'DIPLOME' in entities and not candidate_education:
                        candidate_education = entities['DIPLOME']
                except:
                    # Ignore extraction errors
                    pass
    
    if request.method == 'POST':
        message_subject = request.form.get('subject')
        message_body = request.form.get('message')
        job_id = request.form.get('job_id')
        
        # Send message to candidate (store in DB)
        message_id = db.messages.insert_one({
            'sender_id': ObjectId(session['user_id']),
            'recipient_id': ObjectId(candidate_id),
            'subject': message_subject,
            'message': message_body,
            'job_id': ObjectId(job_id) if job_id else None,
            'read': False,
            'sent_at': datetime.now()
        }).inserted_id
        
        # Create notification for candidate
        notification_text = f"You have a new message: {message_subject}"
        
        db.notifications.insert_one({
            'user_id': ObjectId(candidate_id),
            'type': 'message',
            'related_id': message_id,
            'message': notification_text,
            'read_status': False,
            'created_at': datetime.now()
        })
        
        flash('Message sent to candidate')
        if job_id:
            return redirect(url_for('rankings', job_id=job_id))
        return redirect(url_for('recruiter'))
    
    # Get jobs from this recruiter
    jobs = list(db.jobs.find({'recruiter_id': ObjectId(session['user_id'])}))
    
    # Pre-fill job_id if provided
    job_id = request.args.get('job_id')
    selected_job = None
    if job_id:
        selected_job = db.jobs.find_one({'_id': ObjectId(job_id)})
    
    return render_template('contact.html', 
                          candidate=candidate,
                          profile=profile,
                          jobs=jobs,
                          selected_job=selected_job,
                          candidate_skills=candidate_skills,
                          candidate_experience=candidate_experience,
                          candidate_education=candidate_education,
                          applications_history=applications_history)

@app.route('/messages')
def messages():
    if 'user_id' not in session:
        flash('Please login first')
        return redirect(url_for('auth'))
    
    db = get_db()
    user_id = ObjectId(session['user_id'])
    
    # Get received messages
    received_messages = list(db.messages.find({
        'recipient_id': user_id
    }).sort('sent_at', -1))
    
    # Get sent messages
    sent_messages = list(db.messages.find({
        'sender_id': user_id
    }).sort('sent_at', -1))
    
    # Get user names for messages
    for message in received_messages:
        sender = db.users.find_one({'_id': message['sender_id']})
        message['sender_name'] = sender['username'] if sender else 'Unknown'
        
        if message.get('job_id'):
            job = db.jobs.find_one({'_id': message['job_id']})
            message['job_title'] = job['title'] if job else 'Unknown Position'
    
    for message in sent_messages:
        recipient = db.users.find_one({'_id': message['recipient_id']})
        message['recipient_name'] = recipient['username'] if recipient else 'Unknown'
        
        if message.get('job_id'):
            job = db.jobs.find_one({'_id': message['job_id']})
            message['job_title'] = job['title'] if job else 'Unknown Position'
    
    # Mark unread messages as read
    db.messages.update_many(
        {'recipient_id': user_id, 'read': False},
        {'$set': {'read': True}}
    )
    
    return render_template('messages.html', 
                          received_messages=received_messages,
                          sent_messages=sent_messages)

@app.route('/reply/<message_id>', methods=['GET', 'POST'])
def reply_message(message_id):
    if 'user_id' not in session:
        flash('Please login first')
        return redirect(url_for('auth'))
    
    db = get_db()
    original_message = db.messages.find_one({'_id': ObjectId(message_id)})
    
    if not original_message:
        flash('Message not found')
        return redirect(url_for('messages'))
    
    # Ensure the user is the recipient of the message
    if str(original_message['recipient_id']) != session['user_id']:
        flash('Access denied')
        return redirect(url_for('messages'))
    
    if request.method == 'POST':
        reply_text = request.form.get('reply')
        
        # Send reply
        reply_id = db.messages.insert_one({
            'sender_id': ObjectId(session['user_id']),
            'recipient_id': original_message['sender_id'],
            'subject': f"Re: {original_message['subject']}",
            'message': reply_text,
            'job_id': original_message.get('job_id'),
            'in_reply_to': original_message['_id'],
            'read': False,
            'sent_at': datetime.now()
        }).inserted_id
        
        # Create notification for recipient
        db.notifications.insert_one({
            'user_id': original_message['sender_id'],
            'type': 'message',
            'related_id': reply_id,
            'message': f"You have a new reply from {session['username']}",
            'read_status': False,
            'created_at': datetime.now()
        })
        
        flash('Reply sent successfully')
        return redirect(url_for('messages'))
    
    # Get sender info
    sender = db.users.find_one({'_id': original_message['sender_id']})
    
    return render_template('reply.html', 
                          message=original_message,
                          sender=sender)

@app.route('/send_message/<user_id>', methods=['GET', 'POST'])
def send_message(user_id):
    if 'user_id' not in session:
        flash('Please login first')
        return redirect(url_for('auth'))
    
    db = get_db()
    recipient = db.users.find_one({'_id': ObjectId(user_id)})
    
    if not recipient:
        flash('User not found')
        return redirect(url_for('messages'))
    
    # Don't allow sending messages to yourself
    if session['user_id'] == str(recipient['_id']):
        flash('You cannot send messages to yourself')
        return redirect(url_for('messages'))
    
    if request.method == 'POST':
        subject = request.form.get('subject')
        message_text = request.form.get('message')
        
        # Send message
        message_id = db.messages.insert_one({
            'sender_id': ObjectId(session['user_id']),
            'recipient_id': recipient['_id'],
            'subject': subject,
            'message': message_text,
            'read': False,
            'sent_at': datetime.now()
        }).inserted_id
        
        # Create notification for recipient
        db.notifications.insert_one({
            'user_id': recipient['_id'],
            'type': 'message',
            'related_id': message_id,
            'message': f"You have a new message from {session['username']}",
            'read_status': False,
            'created_at': datetime.now()
        })
        
        flash('Message sent successfully')
        return redirect(url_for('messages'))
    
    return render_template('send_message.html', recipient=recipient)

@app.route('/users')
def users_directory():
    if 'user_id' not in session:
        flash('Please login first')
        return redirect(url_for('auth'))
    
    db = get_db()
    current_user_id = ObjectId(session['user_id'])
    
    # Get all users except the current one
    users = list(db.users.find({
        '_id': {'$ne': current_user_id}
    }))
    
    # Get profiles for users
    for user in users:
        profile = db.profiles.find_one({'user_id': user['_id']})
        if profile:
            user['profile'] = profile
    
    return render_template('users_directory.html', users=users)

if __name__ == '__main__':
    # Initialize the database if needed
    init_db()
    app.run(debug=True)