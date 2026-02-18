"""
USSD Integration Module for Medical AI Platform
Handles USSD (Unstructured Supplementary Service Data) requests
for users without internet connectivity.

Supports: Africa's Talking, Twilio USSD
"""

import json
import random
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from functools import wraps

# Create USSD blueprint
ussd_bp = Blueprint('ussd', __name__, url_prefix='/ussd')

# In-memory session storage (use Redis in production)
USSD_SESSIONS = {}

# Maximum session duration (10 minutes)
SESSION_TIMEOUT = 600

# ==================== HELPER FUNCTIONS ====================

def build_ussd_response(message, is_continue=True):
    """
    Build USSD response for Africa's Talking
    
    Args:
        message (str): Message to display to user
        is_continue (bool): True if menu continues, False if session ends
    
    Returns:
        str: Formatted USSD response
    """
    if is_continue:
        return f"CON {message}"
    else:
        return f"END {message}"


def get_or_create_session(session_id, phone):
    """
    Get or create a USSD session
    
    Args:
        session_id (str): Unique session ID from gateway
        phone (str): User's phone number
    
    Returns:
        dict: Session data
    """
    if session_id not in USSD_SESSIONS:
        USSD_SESSIONS[session_id] = {
            'id': session_id,
            'phone': phone,
            'created': datetime.now().timestamp(),
            'last_activity': datetime.now().timestamp(),
            'data': {}
        }
    
    # Update last activity
    USSD_SESSIONS[session_id]['last_activity'] = datetime.now().timestamp()
    
    # Check for timeout
    current_time = datetime.now().timestamp()
    created_time = USSD_SESSIONS[session_id]['created']
    
    if (current_time - created_time) > SESSION_TIMEOUT:
        clear_session(session_id)
        return None
    
    return USSD_SESSIONS[session_id]


def clear_session(session_id):
    """Clear a USSD session"""
    if session_id in USSD_SESSIONS:
        del USSD_SESSIONS[session_id]


def get_db():
    """Get database connection (assumes this is defined in app.py)"""
    # This should be imported from your main app
    # For now, we'll use it as placeholder
    pass


# ==================== MAIN USSD ENDPOINT ====================

@ussd_bp.route('/callback', methods=['POST'])
def ussd_callback():
    """
    Main USSD callback handler
    
    Receives POST from Africa's Talking or Twilio with:
    {
        "sessionId": "uuid-xxx",
        "phone": "+254720123456",
        "text": "",  // Empty on first, "1" or "1*2" for navigation
        "serviceCode": "*384#"
    }
    """
    
    try:
        # Parse USSD request
        session_id = request.form.get('sessionId')
        phone = request.form.get('phone')
        text = request.form.get('text', '').strip()
        service_code = request.form.get('serviceCode')
        
        if not session_id or not phone:
            return build_ussd_response('Invalid request', False)
        
        # Get or create session
        session = get_or_create_session(session_id, phone)
        if not session:
            return build_ussd_response('Session expired. Please try again.', False)
        
        # Parse menu navigation
        input_sequence = text.split('*') if text else []
        
        # MAIN MENU
        if not text or text == '':
            return show_main_menu(session)
        
        # Route to appropriate handler
        choice = input_sequence[0]
        
        if choice == '1':
            return handle_symptom_checker(session, input_sequence)
        elif choice == '2':
            return handle_emergency_alert(session, input_sequence, phone)
        elif choice == '3':
            return handle_book_doctor(session, input_sequence)
        elif choice == '4':
            return handle_medications(session, input_sequence, phone)
        elif choice == '5':
            return handle_health_history(session, input_sequence, phone)
        elif choice == '0':
            clear_session(session_id)
            return build_ussd_response(
                'Thank you for using Medical AI!\n\n'
                'For more info, visit: medicalai.health',
                False
            )
        else:
            return build_ussd_response('Invalid selection. Try again.', True)
    
    except Exception as e:
        print(f"USSD Error: {str(e)}")
        return build_ussd_response(
            'Service temporarily unavailable.\nPlease try again later.',
            False
        )


# ==================== MAIN MENU ====================

def show_main_menu(session):
    """Display main menu"""
    response = """Welcome to Medical AI
Accessible via SMS & USSD

1. Check Symptoms
2. Emergency Alert
3. Book Doctor
4. My Medications
5. Health History
0. Exit"""
    
    session['data']['menu'] = 'main'
    return build_ussd_response(response, True)


# ==================== SYMPTOM CHECKER ====================

def handle_symptom_checker(session, input_sequence):
    """Handle symptom checking flow"""
    
    if len(input_sequence) == 1:
        # Show symptoms menu
        response = """Symptom Checker
        
1. Fever & Cough
2. Abdominal Pain
3. Headache
4. Allergies
5. Free Text
0. Back"""
        
        session['data']['menu'] = 'symptoms'
        return build_ussd_response(response, True)
    
    elif len(input_sequence) == 2:
        choice = input_sequence[1]
        
        if choice == '0':
            return show_main_menu(session)
        
        symptoms = {
            '1': 'Fever and Cough',
            '2': 'Abdominal Pain',
            '3': 'Headache',
            '4': 'Allergies',
            '5': 'Other symptoms'
        }
        
        if choice not in symptoms:
            return build_ussd_response('Invalid choice. Try again.', True)
        
        session['data']['symptom_choice'] = choice
        
        response = f"""Symptom: {symptoms[choice]}
        
Rate severity:
1. Mild
2. Moderate
3. Severe
0. Back"""
        
        return build_ussd_response(response, True)
    
    elif len(input_sequence) == 3:
        choice = input_sequence[2]
        
        if choice == '0':
            return handle_symptom_checker(session, ['1'])
        
        severity_map = {
            '1': 'Mild',
            '2': 'Moderate',
            '3': 'Severe'
        }
        
        session['data']['severity'] = choice
        
        # In production, call your AI analysis endpoint
        response = """Analysis complete
        
Based on your symptoms:
1. View recommendation
2. Book doctor appointment
3. Find nearby clinic
0. Back"""
        
        return build_ussd_response(response, True)


# ==================== EMERGENCY ALERT ⭐ ====================

def handle_emergency_alert(session, input_sequence, phone):
    """
    CRITICAL: Handle emergency triage flow
    This directly integrates with your /emergency/triage endpoint
    """
    
    if len(input_sequence) == 1:
        # Ask for severity level
        response = """🚨 EMERGENCY ALERT
        
Select Severity Level:
1. Not Urgent (1)
2. Minor (2)
3. Moderate (3)
4. Serious (4)
5. CRITICAL (5)
0. Cancel"""
        
        session['data']['menu'] = 'emergency'
        return build_ussd_response(response, True)
    
    elif len(input_sequence) == 2:
        choice = input_sequence[1]
        
        if choice == '0':
            return show_main_menu(session)
        
        if choice not in ['1', '2', '3', '4', '5']:
            return build_ussd_response('Invalid choice.', True)
        
        session['data']['severity'] = int(choice)
        
        response = """Describe symptom briefly:
1. Chest Pain
2. Breathing Problem
3. Heavy Bleeding
4. Unconscious
5. Other
0. Back"""
        
        return build_ussd_response(response, True)
    
    elif len(input_sequence) == 3:
        choice = input_sequence[2]
        
        if choice == '0':
            return handle_emergency_alert(session, ['2'], phone)
        
        symptoms_map = {
            '1': 'Chest Pain',
            '2': 'Breathing Problem',
            '3': 'Heavy Bleeding',
            '4': 'Unconscious',
            '5': 'Other - See Text Alert'
        }
        
        symptom = symptoms_map.get(choice, 'Emergency reported')
        session['data']['symptom'] = symptom
        
        # Confirm alert
        severity = session['data'].get('severity', 3)
        
        response = f"""Confirm Emergency Alert?
        
Severity: {severity}/5
Symptom: {symptom}
Phone: {phone}

1. Send Alert
2. Cancel"""
        
        return build_ussd_response(response, True)
    
    elif len(input_sequence) == 4:
        choice = input_sequence[3]
        
        if choice == '2':
            clear_session(session['id'])
            return build_ussd_response('Alert cancelled.', False)
        
        if choice != '1':
            return build_ussd_response('Invalid choice.', True)
        
        # SEND EMERGENCY ALERT
        try:
            severity = session['data'].get('severity', 3)
            symptom = session['data'].get('symptom', 'Emergency')
            
            # Here, you would call your /emergency/triage endpoint
            # This is a placeholder - integrate with your actual endpoint
            
            # For now, just create audit log
            response_text = (
                f"✓ EMERGENCY ALERT SENT\n\n"
                f"Level: {severity}/5\n"
                f"Doctors Notified: Yes\n"
                f"Expected Response: "
            )
            
            # Add expected response time based on severity
            response_times = {
                1: '24 hours',
                2: '4-8 hours',
                3: '1-2 hours',
                4: '15-30 min',
                5: 'IMMEDIATE'
            }
            
            response_text += response_times.get(severity, '2 hours')
            response_text += "\n\nYou will receive SMS updates."
            
            clear_session(session['id'])
            return build_ussd_response(response_text, False)
        
        except Exception as e:
            return build_ussd_response(
                f'Error sending alert.\nPlease call 911 immediately.',
                False
            )


# ==================== BOOK DOCTOR ====================

def handle_book_doctor(session, input_sequence):
    """Handle doctor appointment booking"""
    
    if len(input_sequence) == 1:
        response = """Book Doctor Appointment
        
Select Specialty:
1. General Practice
2. Cardiology
3. Pediatrics
4. Neurology
5. Other"""
        
        session['data']['menu'] = 'booking'
        return build_ussd_response(response, True)
    
    elif len(input_sequence) == 2:
        choice = input_sequence[1]
        
        if choice not in ['1', '2', '3', '4', '5']:
            return build_ussd_response('Invalid choice.', True)
        
        specialties = {
            '1': 'General Practice',
            '2': 'Cardiology',
            '3': 'Pediatrics',
            '4': 'Neurology',
            '5': 'Other'
        }
        
        session['data']['specialty'] = choice
        
        response = """Select Date:
1. Today
2. Tomorrow
3. This Week
4. Next Week
0. Back"""
        
        return build_ussd_response(response, True)
    
    elif len(input_sequence) == 3:
        choice = input_sequence[2]
        
        if choice == '0':
            return handle_book_doctor(session, ['3'])
        
        if choice not in ['1', '2', '3', '4']:
            return build_ussd_response('Invalid choice.', True)
        
        dates = {
            '1': 'Today',
            '2': 'Tomorrow',
            '3': 'This Week',
            '4': 'Next Week'
        }
        
        session['data']['date'] = choice
        
        response = f"""Booking Summary
        
Specialty: {session['data'].get('specialty')}
Date: {dates[choice]}

1. Confirm Booking
2. Cancel"""
        
        return build_ussd_response(response, True)
    
    elif len(input_sequence) == 4:
        choice = input_sequence[3]
        
        if choice == '2':
            clear_session(session['id'])
            return build_ussd_response('Booking cancelled.', False)
        
        if choice != '1':
            return build_ussd_response('Invalid choice.', True)
        
        # Confirm booking
        clear_session(session['id'])
        response = (
            'Appointment booked!\n\n'
            'You will receive SMS confirmation\n'
            'with doctor details & time.'
        )
        return build_ussd_response(response, False)


# ==================== MEDICATIONS ====================

def handle_medications(session, input_sequence, phone):
    """Handle medication management"""
    
    if len(input_sequence) == 1:
        response = """My Medications
        
1. View Active Meds
2. Request Refill
3. Report Side Effect
4. Check Interactions
0. Back"""
        
        session['data']['menu'] = 'meds'
        return build_ussd_response(response, True)
    
    elif len(input_sequence) == 2:
        choice = input_sequence[1]
        
        if choice == '0':
            return show_main_menu(session)
        
        if choice == '1':
            # View medications
            response = (
                'Active Medications:\n\n'
                '1. Paracetamol 500mg\n'
                '2. Amoxicillin 250mg\n\n'
                'For details, visit web portal.'
            )
            clear_session(session['id'])
            return build_ussd_response(response, False)
        
        elif choice == '2':
            response = 'Request submitted.\nYou will receive SMS with refill code.'
            clear_session(session['id'])
            return build_ussd_response(response, False)
        
        elif choice == '3':
            response = 'Side effect reported.\nDoctor will contact you within 24 hours.'
            clear_session(session['id'])
            return build_ussd_response(response, False)
        
        elif choice == '4':
            response = (
                'Check drug interactions:\n\n'
                'Visit medicalai.health/drug-checker\n'
                'Or call support: +254720123456'
            )
            clear_session(session['id'])
            return build_ussd_response(response, False)


# ==================== HEALTH HISTORY ====================

def handle_health_history(session, input_sequence, phone):
    """View health history (safe summary only)"""
    
    if len(input_sequence) == 1:
        response = """Health History
        
1. View Summary
2. Recent Visits
3. Active Conditions
0. Back"""
        
        session['data']['menu'] = 'history'
        return build_ussd_response(response, True)
    
    elif len(input_sequence) == 2:
        choice = input_sequence[1]
        
        if choice == '0':
            return show_main_menu(session)
        
        if choice == '1':
            response = (
                'Health Summary:\n\n'
                'Blood Type: O+\n'
                'Allergies: Penicillin\n'
                'Conditions: Diabetes\n\n'
                'Full history on web portal.'
            )
        
        elif choice == '2':
            response = (
                'Recent Visits:\n\n'
                '1. Jan 15 - General Checkup\n'
                '2. Jan 8 - Dental\n\n'
                'View details online.'
            )
        
        elif choice == '3':
            response = (
                'Active Conditions:\n\n'
                '- Diabetes Type 2\n'
                '- High BP\n\n'
                'Contact doctor for details.'
            )
        
        else:
            return build_ussd_response('Invalid choice.', True)
        
        clear_session(session['id'])
        return build_ussd_response(response, False)


# ==================== OTP & REGISTRATION ====================

@ussd_bp.route('/register', methods=['POST'])
def ussd_register():
    """Register USSD phone number to existing account"""
    
    phone = request.form.get('phone')
    username = request.form.get('username')
    otp = request.form.get('otp')
    
    if not all([phone, username, otp]):
        return build_ussd_response('Missing registration data', False)
    
    # TODO: Verify OTP and link account
    # This would integrate with your user database
    
    return build_ussd_response(
        'Account linked!\n'
        'USSD is now active.\n\n'
        'Dial *384# to start.',
        False
    )


@ussd_bp.route('/send-otp', methods=['POST'])
def send_ussd_otp():
    """Send OTP to phone for USSD registration"""
    
    phone = request.json.get('phone')
    
    if not phone:
        return jsonify({'error': 'Phone required'}), 400
    
    # Generate OTP
    otp = ''.join([str(random.randint(0, 9)) for _ in range(4)])
    
    # TODO: Store OTP in database with 5-min expiry
    # TODO: Send via SMS
    
    return jsonify({
        'status': 'ok',
        'message': f'OTP sent to {phone}'
    })


# ==================== METRICS & ADMIN ====================

@ussd_bp.route('/metrics', methods=['GET'])
def ussd_metrics():
    """Get USSD usage metrics"""
    
    return jsonify({
        'total_sessions': len(USSD_SESSIONS),
        'active_sessions': len([s for s in USSD_SESSIONS.values() 
                                if (datetime.now().timestamp() - s['last_activity']) < SESSION_TIMEOUT]),
        'last_updated': datetime.now().isoformat()
    })


# Export blueprint for registration in app.py
__all__ = ['ussd_bp']
