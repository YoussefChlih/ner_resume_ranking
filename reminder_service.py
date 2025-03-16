import time
from datetime import datetime, timedelta
from database import get_db

def send_reminders():
    """Send reminders for upcoming interviews"""
    db = get_db()
    
    # Current time
    now = datetime.now()
    
    # Find appointments that need day-before reminders
    tomorrow = now + timedelta(days=1)
    day_before = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    day_after = day_before + timedelta(days=1)
    
    # Find appointments scheduled for tomorrow that haven't had reminders sent
    day_before_appointments = list(db.appointments.find({
        'interview_datetime': {'$gte': day_before, '$lt': day_after},
        'reminder_sent': False,
        'reminder_enabled': True
    }))
    
    for appointment in day_before_appointments:
        # Create notification for candidate
        job = db.jobs.find_one({'_id': appointment['job_id']})
        interview_time = appointment['interview_datetime'].strftime('%H:%M')
        
        notification_text = f"Reminder: Your interview for {job['title']} is tomorrow at {interview_time}."
        
        db.notifications.insert_one({
            'user_id': appointment['candidate_id'],
            'type': 'interview_reminder',
            'related_id': appointment['_id'],
            'message': notification_text,
            'read_status': False,
            'created_at': now
        })
        
        # Mark reminder as sent
        db.appointments.update_one(
            {'_id': appointment['_id']},
            {'$set': {'reminder_sent': True}}
        )
        
        print(f"Sent day-before reminder for appointment {appointment['_id']}")
    
    # Find appointments that need 5-minute reminders
    next_5_minutes = now + timedelta(minutes=5)
    
    # Find appointments starting in the next 5 minutes that haven't had last-minute reminders sent
    last_minute_appointments = list(db.appointments.find({
        'interview_datetime': {'$gte': now, '$lte': next_5_minutes},
        'last_minute_reminder_sent': False,
        'reminder_enabled': True
    }))
    
    for appointment in last_minute_appointments:
        # Create notification for candidate
        job = db.jobs.find_one({'_id': appointment['job_id']})
        
        notification_text = f"Your interview for {job['title']} starts in 5 minutes!"
        
        db.notifications.insert_one({
            'user_id': appointment['candidate_id'],
            'type': 'interview_starting',
            'related_id': appointment['_id'],
            'message': notification_text,
            'read_status': False,
            'created_at': now
        })
        
        # Mark last-minute reminder as sent
        db.appointments.update_one(
            {'_id': appointment['_id']},
            {'$set': {'last_minute_reminder_sent': True}}
        )
        
        print(f"Sent 5-minute reminder for appointment {appointment['_id']}")

if __name__ == "__main__":
    while True:
        send_reminders()
        # Check every minute
        time.sleep(60)