from flask import Flask, render_template, request, redirect, url_for, flash, session
import os
import uuid
from werkzeug.utils import secure_filename
from database import get_db, get_profile, init_db, update_profile, update_profile_picture, update_skills, update_social_links
from models import extract_entities_from_text, extract_text_from_pdf, rank_cvs_by_similarity
from datetime import datetime, timedelta
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
from cryptography.fernet import Fernet
from security import Security, login_required, require_2fa
import humanize
from utils.ranking_system import ResumeRankingSystem

app = Flask(__name__)
app.secret_key = 'ner_resume_ranking_secret_key'

# Configure upload folder
UPLOAD_FOLDER = os.path.join('data', 'resumes')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'pdf'}

# Ensure upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Add timeago filter
@app.template_filter('timeago')
def timeago_filter(date):
    if not date:
        return ""
    return humanize.naturaltime(datetime.now() - date)

# Add date filter
@app.template_filter('date')
def date_filter(date, format='%Y-%m-%d'):
    if not date:
        return ""
    return date.strftime(format)

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

# Initialize security
security = Security(app)

# Initialiser le système de classement
ranking_system = ResumeRankingSystem()

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
        email = request.form.get('email')
        user_type = request.form.get('user_type', 'candidate')
        
        db = get_db()
        
        if action == 'login':
            # Check if account exists and is not locked
            user = db.users.find_one({'username': username})
            
            if user:
                # Check if account is locked
                if user.get('account_locked') and user.get('account_locked_until') > datetime.now():
                    flash('Account is temporarily locked. Please try again later.')
                    return redirect(url_for('auth'))
                
                # Verify password
                if check_password_hash(user['password'], password):
                    # Reset failed login attempts
                    db.users.update_one(
                        {'_id': user['_id']},
                        {
                            '$set': {
                                'failed_login_attempts': 0,
                                'last_login': datetime.now()
                            }
                        }
                    )
                    
                    # Temporarily disable email confirmation check
                    # if not user.get('email_confirmed'):
                    #     flash('Please confirm your email address first.')
                    #     return redirect(url_for('auth'))
                    
                    # Check if 2FA is enabled
                    if user.get('two_factor_enabled'):
                        session['temp_user_id'] = str(user['_id'])
                        return redirect(url_for('two_factor_auth'))
                    
                    # Normal login - Set session variables
                    session['user_id'] = str(user['_id'])
                    session['username'] = user['username']
                    session['user_type'] = user['user_type']
                    
                    # Redirect based on user type
                    if user['user_type'] == 'recruiter':
                        return redirect(url_for('recruiter'))
                    else:
                        return redirect(url_for('candidate'))
                else:
                    # Increment failed login attempts
                    failed_attempts = user.get('failed_login_attempts', 0) + 1
                    update = {
                        '$set': {'failed_login_attempts': failed_attempts}
                    }
                    
                    # Lock account after 5 failed attempts
                    if failed_attempts >= 5:
                        lock_until = datetime.now() + timedelta(minutes=30)
                        update['$set'].update({
                            'account_locked': True,
                            'account_locked_until': lock_until
                        })
                        flash('Account locked for 30 minutes due to too many failed attempts.')
                    else:
                        flash('Invalid credentials')
                    
                    db.users.update_one({'_id': user['_id']}, update)
            else:
                flash('Invalid credentials')
        
        elif action == 'register':
            # Check if username or email already exists
            if db.users.find_one({'$or': [{'username': username}, {'email': email}]}):
                flash('Username or email already exists')
            else:
                # Create new user with email confirmed by default
                user_id = db.users.insert_one({
                    'username': username,
                    'email': email,
                    'password': generate_password_hash(password),
                    'user_type': user_type,
                    'created_at': datetime.now(),
                    'email_confirmed': True,  # Set to True by default
                    'email_confirmed_at': datetime.now(),  # Set confirmation time
                    'two_factor_secret': None,
                    'two_factor_enabled': False,
                    'last_login': None,
                    'failed_login_attempts': 0,
                    'account_locked': False,
                    'account_locked_until': None,
                    'password_reset_token': None,
                    'password_reset_expires': None,
                    'active': True
                }).inserted_id
                
                flash('Registration successful! You can now login.')
    
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
    
    # Add required_skills to each job
    for job in jobs:
        job['required_skills'] = list(job.get('keywords', {}).keys())
    
    # Get user information
    user = db.users.find_one({'_id': ObjectId(session['user_id'])})
    if not user:
        flash('User not found')
        return redirect(url_for('auth'))
    
    return render_template('recruiter.html', jobs=jobs, user=user)

@app.route('/jobs/<job_id>/rankings')
@login_required
def rankings(job_id):
    try:
        # Initialiser la connexion à la base de données
        db = get_db()
        
        # Récupérer l'offre d'emploi
        job = db.jobs.find_one({'_id': ObjectId(job_id)})
        if not job:
            print(f"Job not found: {job_id}")
            flash('Offre d\'emploi non trouvée', 'error')
            return redirect(url_for('recruiter'))
        
        print(f"Found job: {job['title']}")
        
        # Récupérer toutes les candidatures pour cette offre
        applications = list(db.applications.find({'job_id': ObjectId(job_id)}))
        print(f"Found {len(applications)} applications")
        
        if not applications:
            print("No applications found")
            flash('Aucune candidature n\'a encore été reçue pour cette offre d\'emploi', 'info')
            return render_template('rankings.html', job=job, ranked_applications=[])
        
        # Initialiser le système de classement
        ranking_system = ResumeRankingSystem()
        
        # Définir les poids des mots-clés basés sur les compétences requises
        keyword_weights = {}
        for skill in job.get('required_skills', []):
            keyword_weights[skill.lower()] = 1.0
        
        # Ajouter des mots-clés supplémentaires basés sur le titre et la description
        additional_keywords = [
            job.get('title', '').lower(),
            job.get('description', '').lower(),
            job.get('location', '').lower(),
            job.get('type', '').lower()
        ]
        
        for keyword in additional_keywords:
            if keyword:
                keyword_weights[keyword] = 0.5
        
        # Calculer le score pour chaque candidature
        ranked_applications = []
        for application in applications:
            try:
                print(f"Processing application: {application.get('_id')}")
                
                # Récupérer les informations du candidat
                candidate = db.users.find_one({'_id': application.get('candidate_id')})
                if not candidate:
                    print(f"Candidate not found for application {application.get('_id')}")
                    continue
                
                print(f"Found candidate: {candidate.get('username')}")
                
                # Récupérer le CV associé
                cv = db.cvs.find_one({'_id': application.get('cv_id')})
                if not cv:
                    print(f"CV not found for application {application.get('_id')}")
                    continue
                
                print(f"Found CV: {cv.get('file_path')}")
                
                # Extraire le texte du CV
                cv_text = ranking_system._extract_text_from_file(cv.get('file_path'))
                if not cv_text:
                    print(f"Could not extract text from CV for application {application.get('_id')}")
                    continue
                
                print(f"Extracted CV text length: {len(cv_text)}")
                
                # Calculer le score de correspondance
                match_score = ranking_system.compute_similarity(cv_text, job.get('description', ''), keyword_weights)
                print(f"Match score: {match_score}")
                
                # Ajouter la candidature classée à la liste
                ranked_applications.append({
                    'application': application,
                    'candidate_name': candidate.get('username', 'Unknown'),
                    'match_percentage': round(match_score * 100, 2),
                    'cv_text': cv_text[:200] + '...' if len(cv_text) > 200 else cv_text
                })
                
            except Exception as e:
                print(f"Error processing application {application.get('_id')}: {str(e)}")
                continue
        
        print(f"Successfully processed {len(ranked_applications)} applications")
        
        # Trier les candidatures par score de correspondance
        ranked_applications.sort(key=lambda x: x['match_percentage'], reverse=True)
        
        return render_template('rankings.html', job=job, ranked_applications=ranked_applications)
        
    except Exception as e:
        print(f"Error in rankings route: {str(e)}")
        flash('Une erreur est survenue lors du classement des candidatures', 'error')
        return redirect(url_for('recruiter'))

# Candidate routes
@app.route('/candidate')
def candidate():
    if session.get('user_id') is None:
        flash('Please login first')
        return redirect(url_for('auth'))
    
    # Get applications by this candidate
    db = get_db()
    candidate_id = ObjectId(session['user_id'])
    
    # Get user information
    user = db.users.find_one({'_id': candidate_id})
    if not user:
        flash('User not found')
        return redirect(url_for('auth'))
    
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
            
            # Add required_skills from keywords
            job['required_skills'] = list(job.get('keywords', {}).keys())
            
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
        
        # Add required_skills from keywords
        job['required_skills'] = list(job.get('keywords', {}).keys())
    
    return render_template('candidate.html', 
                         applications=app_details, 
                         jobs=jobs,
                         user=user)

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

@app.route('/applications/<application_id>/schedule-interview', methods=['GET', 'POST'])
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
        return redirect(url_for('job_applications', job_id=str(application['job_id'])))
    
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
    if session.get('user_id') is None:
        flash('Please login first')
        return redirect(url_for('auth'))
    
    user_id = ObjectId(session['user_id'])
    db = get_db()
    
    if request.method == 'POST':
        if 'profile_picture' in request.files:
            file = request.files['profile_picture']
            if file and file.filename != '':
                # Save profile picture
                filename = secure_filename(file.filename)
                picture_path = os.path.join('static', 'profile_pictures', filename)
                os.makedirs(os.path.dirname(picture_path), exist_ok=True)
                file.save(picture_path)
                update_profile_picture(user_id, picture_path)
                flash('Profile picture updated successfully!')
                return redirect(url_for('profile'))
        
        # Handle form submission based on the active tab
        active_tab = request.form.get('active_tab', 'personal')
        
        if active_tab == 'personal':
            # Update personal information
            personal_data = {
                'full_name': request.form.get('full_name'),
                'first_name': request.form.get('first_name'),
                'bio': request.form.get('bio')
            }
            update_profile(user_id, personal_data)
        
        elif active_tab == 'contact':
            # Update contact information
            contact_data = {
                'email': request.form.get('email'),
                'phone': request.form.get('phone'),
                'location': request.form.get('location')
            }
            update_profile(user_id, contact_data)
        
        elif active_tab == 'skills':
            # Update skills
            technical_skills = request.form.getlist('technical_skills[]')
            soft_skills = request.form.getlist('soft_skills[]')
            languages = request.form.getlist('languages[]')
            
            update_skills(user_id, 'technical_skills', technical_skills)
            update_skills(user_id, 'soft_skills', soft_skills)
            update_skills(user_id, 'languages', languages)
        
        elif active_tab == 'experience':
            # Handle experience updates
            companies = request.form.getlist('company[]')
            positions = request.form.getlist('position[]')
            start_dates = request.form.getlist('start_date[]')
            end_dates = request.form.getlist('end_date[]')
            descriptions = request.form.getlist('description[]')
            
            experiences = []
            for i in range(len(companies)):
                if companies[i]:  # Only add if company name is provided
                    experiences.append({
                        'company': companies[i],
                        'position': positions[i],
                        'start_date': start_dates[i],
                        'end_date': end_dates[i],
                        'description': descriptions[i]
                    })
            
            update_profile(user_id, {'experience': experiences})
        
        elif active_tab == 'education':
            # Handle education updates
            institutions = request.form.getlist('institution[]')
            degrees = request.form.getlist('degree[]')
            edu_start_dates = request.form.getlist('edu_start_date[]')
            edu_end_dates = request.form.getlist('edu_end_date[]')
            edu_descriptions = request.form.getlist('edu_description[]')
            
            education = []
            for i in range(len(institutions)):
                if institutions[i]:  # Only add if institution name is provided
                    education.append({
                        'institution': institutions[i],
                        'degree': degrees[i],
                        'start_date': edu_start_dates[i],
                        'end_date': edu_end_dates[i],
                        'description': edu_descriptions[i]
                    })
            
            update_profile(user_id, {'education': education})
        
        elif active_tab == 'social':
            # Update social links
            social_links = {
                'linkedin': request.form.get('linkedin'),
                'github': request.form.get('github'),
                'website': request.form.get('website')
            }
            update_social_links(user_id, social_links)
        
        elif active_tab == 'security':
            # Handle password update
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')
            
            if current_password and new_password and confirm_password:
                user = db.users.find_one({'_id': user_id})
                if check_password_hash(user['password'], current_password):
                    if new_password == confirm_password:
                        hashed_password = generate_password_hash(new_password)
                        db.users.update_one(
                            {'_id': user_id},
                            {'$set': {'password': hashed_password}}
                        )
                        flash('Password updated successfully!')
                    else:
                        flash('New passwords do not match!')
                else:
                    flash('Current password is incorrect!')
        
        flash('Profile updated successfully!')
        return redirect(url_for('profile', _anchor=active_tab))
    
    # Get user profile for display
    user_profile = get_profile(user_id)
    if not user_profile:
        flash('Profile not found!')
        return redirect(url_for('home'))
    
    # Get user information
    user = db.users.find_one({'_id': user_id})
    
    return render_template('profile.html', profile=user_profile, user=user)

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

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/confirm/<token>')
def confirm_email(token):
    email = security.verify_confirmation_token(token)
    if email is None:
        flash('Invalid or expired confirmation link.')
        return redirect(url_for('auth'))
    
    db = get_db()
    user = db.users.find_one({'email': email})
    
    if user:
        if user['email_confirmed']:
            flash('Email already confirmed. Please login.')
        else:
            db.users.update_one(
                {'_id': user['_id']},
                {
                    '$set': {
                        'email_confirmed': True,
                        'email_confirmed_at': datetime.now()
                    }
                }
            )
            flash('Thank you for confirming your email!')
    else:
        flash('User not found.')
    
    return redirect(url_for('auth'))

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        db = get_db()
        user = db.users.find_one({'email': email})
        
        if user:
            if security.send_reset_password_email(email):
                flash('Password reset instructions have been sent to your email.')
            else:
                flash('Error sending password reset email. Please try again later.')
        else:
            flash('If an account exists with this email, you will receive password reset instructions.')
    
    return render_template('forgot_password.html')

@app.route('/reset/<token>', methods=['GET', 'POST'])
def reset_password(token):
    email = security.verify_reset_token(token)
    if email is None:
        flash('Invalid or expired reset link.')
        return redirect(url_for('auth'))
    
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if password == confirm_password:
            db = get_db()
            db.users.update_one(
                {'email': email},
                {
                    '$set': {
                        'password': generate_password_hash(password),
                        'password_reset_token': None,
                        'password_reset_expires': None
                    }
                }
            )
            flash('Your password has been updated! Please login.')
            return redirect(url_for('auth'))
        else:
            flash('Passwords do not match.')
    
    return render_template('reset_password.html')

@app.route('/setup-2fa', methods=['GET', 'POST'])
@login_required
def setup_2fa():
    if request.method == 'GET':
        db = get_db()
        user = db.users.find_one({'_id': ObjectId(session['user_id'])})
        
        if not user.get('two_factor_secret'):
            # Generate new 2FA secret
            secret = security.generate_2fa_secret()
            db.users.update_one(
                {'_id': user['_id']},
                {'$set': {'two_factor_secret': secret}}
            )
        else:
            secret = user['two_factor_secret']
        
        # Generate QR code URL
        qr_url = security.get_2fa_qr_url(secret, user['email'])
        return render_template('setup_2fa.html', qr_url=qr_url, secret=secret)
    
    elif request.method == 'POST':
        token = request.form.get('token')
        db = get_db()
        user = db.users.find_one({'_id': ObjectId(session['user_id'])})
        
        if security.verify_2fa_token(user['two_factor_secret'], token):
            db.users.update_one(
                {'_id': user['_id']},
                {'$set': {'two_factor_enabled': True}}
            )
            flash('Two-factor authentication has been enabled!')
            return redirect(url_for('profile'))
        else:
            flash('Invalid verification code.')
            return redirect(url_for('setup_2fa'))

@app.route('/2fa', methods=['GET', 'POST'])
def two_factor_auth():
    if 'temp_user_id' not in session:
        return redirect(url_for('auth'))
    
    if request.method == 'POST':
        token = request.form.get('token')
        db = get_db()
        user = db.users.find_one({'_id': ObjectId(session['temp_user_id'])})
        
        if security.verify_2fa_token(user['two_factor_secret'], token):
            # Complete login
            session.pop('temp_user_id')
            session['user_id'] = str(user['_id'])
            session['username'] = user['username']
            session['user_type'] = user['user_type']
            session['2fa_verified'] = True
            
            if user['user_type'] == 'recruiter':
                return redirect(url_for('recruiter'))
            else:
                return redirect(url_for('candidate'))
        else:
            flash('Invalid verification code.')
    
    return render_template('2fa.html')

@app.route('/dashboard')
def dashboard():
    if session.get('user_id') is None:
        flash('Please login first')
        return redirect(url_for('auth'))
    
    user_id = ObjectId(session['user_id'])
    db = get_db()
    
    # Get user profile
    user_profile = get_profile(user_id)
    if not user_profile:
        flash('Profile not found!')
        return redirect(url_for('home'))
    
    # Get user information
    user = db.users.find_one({'_id': user_id})
    
    # Get applications count
    applications_count = db.applications.count_documents({'candidate_id': user_id})
    
    # Get unread messages count
    unread_messages_count = db.messages.count_documents({
        'recipient_id': user_id,
        'read': False
    })
    
    # Get unread notifications count
    unread_notifications_count = db.notifications.count_documents({
        'user_id': user_id,
        'read_status': False
    })
    
    # Get upcoming appointments (next 3)
    upcoming_appointments = list(db.appointments.find({
        '$or': [
            {'candidate_id': user_id},
            {'recruiter_id': user_id}
        ],
        'interview_datetime': {'$gte': datetime.now()},
        'status': 'scheduled'
    }).sort('interview_datetime', 1).limit(3))
    
    # Get latest notifications (last 5)
    latest_notifications = list(db.notifications.find({
        'user_id': user_id
    }).sort('created_at', -1).limit(5))
    
    return render_template('dashboard.html',
                         profile=user_profile,
                         user=user,
                         applications_count=applications_count,
                         unread_messages_count=unread_messages_count,
                         unread_notifications_count=unread_notifications_count,
                         upcoming_appointments=upcoming_appointments,
                         latest_notifications=latest_notifications)

@app.route('/jobs/create', methods=['GET', 'POST'])
def create_job():
    if session.get('user_type') != 'recruiter':
        flash('Access denied')
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        db = get_db()
        
        # Get form data
        title = request.form.get('title')
        description = request.form.get('description')
        location = request.form.get('location')
        contract_type = request.form.get('contract_type')
        
        # Process keywords and weights
        keywords = {}
        keyword_list = request.form.getlist('keyword[]')
        weight_list = request.form.getlist('weight[]')
        
        for i in range(len(keyword_list)):
            if keyword_list[i] and weight_list[i]:
                keywords[keyword_list[i]] = float(weight_list[i])
        
        # Create job document
        job_id = db.jobs.insert_one({
            'title': title,
            'description': description,
            'location': location,
            'contract_type': contract_type,
            'recruiter_id': ObjectId(session['user_id']),
            'posted_date': datetime.now(),
            'status': 'open',
            'keywords': keywords,
            'applications': []
        }).inserted_id
        
        flash('Job created successfully!')
        return redirect(url_for('recruiter'))
    
    return render_template('create_job.html')

@app.route('/jobs/<job_id>/applications')
def job_applications(job_id):
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
    
    return render_template('job_applications.html', job=job, applications=app_users)

@app.route('/jobs/<job_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_job(job_id):
    if session.get('user_type') != 'recruiter':
        flash('Accès non autorisé', 'error')
        return redirect(url_for('home'))
    
    job = db.jobs.find_one({'_id': ObjectId(job_id)})
    if not job:
        flash('Offre d\'emploi non trouvée', 'error')
        return redirect(url_for('recruiter_dashboard'))
    
    if request.method == 'POST':
        # Récupérer les données du formulaire
        title = request.form.get('title')
        description = request.form.get('description')
        location = request.form.get('location')
        salary = request.form.get('salary')
        required_skills = request.form.getlist('required_skills')
        status = request.form.get('status')
        
        # Mettre à jour l'offre d'emploi
        db.jobs.update_one(
            {'_id': ObjectId(job_id)},
            {
                '$set': {
                    'title': title,
                    'description': description,
                    'location': location,
                    'salary': salary,
                    'required_skills': required_skills,
                    'status': status,
                    'updated_at': datetime.utcnow()
                }
            }
        )
        
        flash('Offre d\'emploi mise à jour avec succès', 'success')
        return redirect(url_for('recruiter_dashboard'))
    
    return render_template('edit_job.html', job=job)

@app.route('/jobs/<job_id>/delete', methods=['POST'])
@login_required
def delete_job(job_id):
    if session.get('user_type') != 'recruiter':
        flash('Accès non autorisé', 'error')
        return redirect(url_for('home'))
    
    # Supprimer l'offre d'emploi
    result = db.jobs.delete_one({'_id': ObjectId(job_id)})
    
    if result.deleted_count > 0:
        flash('Offre d\'emploi supprimée avec succès', 'success')
    else:
        flash('Offre d\'emploi non trouvée', 'error')
    
    return redirect(url_for('recruiter_dashboard'))

@app.route('/debug/job/<job_id>')
@login_required
def debug_job(job_id):
    try:
        print(f"Debugging job with ID: {job_id}")
        db = get_db()
        
        # Récupérer l'offre d'emploi
        job = db.jobs.find_one({'_id': ObjectId(job_id)})
        if not job:
            print(f"Job not found with ID: {job_id}")
            return "Job not found"
        
        print(f"Found job: {job.get('title')}")
        
        # Récupérer les candidatures
        applications = list(db.applications.find({'job_id': ObjectId(job_id)}))
        print(f"Found {len(applications)} applications")
        
        # Initialiser le système de classement
        ranking_system = ResumeRankingSystem()
        
        # Enrichir les applications avec les informations des utilisateurs et les scores de similarité
        enriched_applications = []
        for app in applications:
            # Trouver l'utilisateur associé
            user = db.users.find_one({'_id': app.get('candidate_id')})
            
            # Calculer le score de similarité si le CV existe
            similarity_score = None
            cv_entities = None
            if app.get('resume_path'):
                try:
                    print(f"Processing CV for application {app['_id']}: {app['resume_path']}")
                    # Extraire le texte du CV
                    cv_text = ranking_system._extract_text_from_file(app['resume_path'])
                    print(f"Extracted CV text length: {len(cv_text)}")
                    
                    # Extraire les entités du CV
                    cv_entities = ranking_system.extract_unique_entities(cv_text)
                    print(f"Extracted entities: {cv_entities}")
                    
                    # Calculer le score de similarité
                    similarity_score = ranking_system.compute_similarity(
                        cv_text,
                        job['description'],
                        job.get('required_skills', [])
                    )
                    print(f"Computed similarity score: {similarity_score}")
                except Exception as e:
                    print(f"Error processing CV for application {app['_id']}: {str(e)}")
            
            enriched_app = {
                'application': app,
                'user': user,
                'similarity_score': similarity_score,
                'cv_entities': cv_entities
            }
            enriched_applications.append(enriched_app)
        
        # Trier les applications par score de similarité (si disponible)
        enriched_applications.sort(key=lambda x: x['similarity_score'] if x['similarity_score'] is not None else 0, reverse=True)
        
        debug_info = {
            'job': job,
            'applications_count': len(applications),
            'applications': enriched_applications
        }
        
        return render_template('debug.html', debug_info=debug_info)
        
    except Exception as e:
        print(f"Error in debug_job: {str(e)}")
        return f"Error: {str(e)}"

if __name__ == '__main__':
    # Initialize the database if needed
    init_db()
    app.run(debug=True)