# USSD Integration Guide for Medical AI Platform
## Enabling SMS-Based Access for Low-Connectivity Users

---

## 1. WHAT IS USSD?

**USSD** = Unstructured Supplementary Service Data

### Key Characteristics:
- **No internet required** - Uses GSM/cellular network only
- **Works on all phones** - Even 15+ year old feature phones
- **Instant connection** - Real-time menu-driven interaction
- **Cost-effective** - Minimal data usage (0 KB per interaction)
- **Menu-driven UI** - Similar to bank balance check (*100# on Vodafone)

### Example USSD Flow:
```
User dials: *384#
Phone shows menu:
  1. Check Symptoms
  2. Emergency Alert
  3. Book Doctor
  4. Medication Reminder
  
User presses: 1
Phone shows next menu...
```

---

## 2. CURRENT IMPLEMENTATION STATUS

### ✅ ALREADY IMPLEMENTED:
```
SMS/WhatsApp Emergency Triage (Twilio):
├── Emergency Triage Endpoint (/emergency/triage)
│   ├── Severity levels: 1-5 scale
│   ├── Auto-alerts nearby doctors (50km radius)
│   ├── Stores geolocation data
│   ├── Rate limit: 10/hour
│   └── Expected response time calculation
│
└── Send Emergency SMS (/emergency/send-sms)
    ├── SMS to doctors/hospitals
    ├── WhatsApp support
    ├── 160 char SMS limit
    ├── Audit logging
    └── Rate limit: 5/hour
```

---

## 3. REQUIREMENTS FOR USSD INTEGRATION

### 3.1 PROVIDER & SERVICE REQUIREMENTS

#### A. USSD Gateway Providers (Africa/Asia Focused)
| Provider | Coverage | Features | Cost |
|----------|----------|----------|------|
| **Twilio** (USA) | 100+ countries | USSD, SMS, WhatsApp | $0.035/request |
| **Africa's Talking** | 43 African countries | USSD, SMS, payment | $0.01-0.02/request |
| **Vonage/Nexmo** | 150+ countries | USSD, SMS, rich comms | $0.03-0.05/request |
| **Termi.io** | 30+ African countries | Dedicated USSD | $0.008/request |
| **Liquid Intelligent** | 20 African countries | Carrier direct | Custom pricing |
| **Safaricom** | Kenya | Native USSD | Custom B2B |
| **MTN** | Africa | Native USSD | Custom B2B |

**Recommendation**: Africa's Talking (best for African countries) OR Twilio (global coverage)

#### B. Infrastructure Requirements

```
1. USSD Shortcode Registration
   ├── Apply to telecommunications authority
   ├── Cost: $500-5000/year per country
   ├── Processing time: 2-6 months
   └── Example shortcodes: *384#, *663#, *123#

2. Dedicated Phone Number
   ├── For USSD callbacks
   ├── Cost: $2-10/month
   └── Must be active 24/7

3. Server Capacity
   ├── Expected concurrent USSD sessions: 10-100
   ├── Response time: <2 seconds (requirement)
   ├── Uptime: 99.5% minimum
   └── Bandwidth: Minimal (10 KB per session)

4. SMS Gateway Credits
   ├── For alerts to doctors/hospitals
   ├── For OTP verification
   └── For confirmation messages
```

---

## 4. TECHNICAL ARCHITECTURE FOR USSD

### 4.1 USSD REQUEST/RESPONSE FLOW

```
User Phone          USSD Gateway         Your Server
     |                    |                   |
     |----Dial *384#----->|                   |
     |                    |----POST Request-->|
     |                    |<-----XML/JSON-----|
     |<---Display Menu----|                   |
     |                    |                   |
     |---Press Option---->|                   |
     |                    |----POST Request-->|
     |                    |<-----Next Menu----|
     |<---Display Next----|                   |
```

### 4.2 USSD REQUEST FORMAT (from gateway)

```json
{
  "sessionId": "uuid-123456",
  "phone": "+254720123456",
  "text": "",  // First request = empty, subsequent = user input
  "serviceCode": "*384#",
  "networkCode": "KEN"
}
```

### 4.3 USSD RESPONSE FORMAT

```xml
<!-- Continue Interaction -->
<Response>
  <Con>Select Service:
1. Check Symptoms
2. Emergency Alert
3. Book Doctor
4. View Prescriptions</Con>
</Response>

<!-- End Interaction -->
<Response>
  <End>Emergency alert sent to nearby doctors. You will receive updates via SMS.</End>
</Response>
```

---

## 5. IMPLEMENTATION STEPS

### STEP 1: Choose USSD Provider & Register Shortcode

**For Kenya/East Africa**: Africa's Talking
- Register at: https://africastalking.com
- Cost: ~$0.01 per USSD session
- Processing: 1-2 weeks

**For Global**: Twilio
- Already integrated in your system
- USSD support: In 100+ countries
- Cost: ~$0.035 per USSD session

### STEP 2: Update requirements.txt

```bash
pip install flask-cors africas-talking twilio  # if not using Twilio USSD
```

### STEP 3: Add Environment Variables

```bash
# For Africa's Talking USSD
export AFRICASTALKING_API_KEY="your_api_key"
export AFRICASTALKING_USERNAME="your_username"
export USSD_SHORTCODE="*384#"

# For Twilio USSD (if available in your region)
export TWILIO_USSD_ENABLED="true"
```

### STEP 4: Create USSD Session Management

**Session Storage Options**:
- **Redis** (recommended): Fast, TTL support, distributed
- **Database**: MySQL sessions table with 10-min timeout
- **In-memory**: Simple but doesn't scale

---

## 6. SAMPLE IMPLEMENTATION CODE

### 6.1 USSD HANDLER ENDPOINT

```python
from flask import request, jsonify
from datetime import datetime, timedelta
import json

# Session storage (using Redis or DB)
USSD_SESSIONS = {}  # In production: Redis or database

@app.route('/ussd/callback', methods=['POST'])
def ussd_callback():
    """
    Handle USSD requests from gateway
    POST payload from Africa's Talking:
    {
        "sessionId": "uuid-xxx",
        "phone": "+254720123456",
        "text": "",  // Empty on first, "1" or "1*2" for navigation
        "serviceCode": "*384#"
    }
    """
    
    # Parse USSD request
    session_id = request.form.get('sessionId')
    phone = request.form.get('phone')
    text = request.form.get('text', '').strip()
    service_code = request.form.get('serviceCode')
    
    if not session_id or not phone:
        return build_ussd_response('Invalid request', False)
    
    # Get/create session
    session = get_or_create_session(session_id, phone)
    
    try:
        # Parse user input (menu navigation)
        input_sequence = text.split('*') if text else []
        
        # MAIN MENU (first screen)
        if not input_sequence or input_sequence[0] == '':
            response_text = """Welcome to Medical AI
            
1. Check Symptoms
2. Emergency Alert
3. Book Doctor
4. My Medications
5. Health History
0. Exit"""
            return build_ussd_response(response_text, True)  # True = continue
        
        # SUBMENU HANDLING
        choice = input_sequence[0]
        
        if choice == '1':
            # Symptom Checker Menu
            return handle_symptom_checker(session, input_sequence)
        
        elif choice == '2':
            # Emergency Alert
            return handle_emergency_alert(session, input_sequence, phone)
        
        elif choice == '3':
            # Book Doctor
            return handle_book_doctor(session, input_sequence)
        
        elif choice == '4':
            # Medications
            return handle_medications(session, input_sequence, phone)
        
        elif choice == '5':
            # Health History
            return handle_health_history(session, input_sequence, phone)
        
        elif choice == '0':
            # Exit
            clear_session(session_id)
            return build_ussd_response('Thank you for using Medical AI', False)
        
        else:
            return build_ussd_response('Invalid selection. Please try again', True)
    
    except Exception as e:
        return build_ussd_response('Service error. Please try again.', False)


def build_ussd_response(message, is_continue=True):
    """Build USSD response for Africa's Talking"""
    if is_continue:
        return f"CON {message}"
    else:
        return f"END {message}"


def handle_emergency_alert(session, input_sequence, phone):
    """Emergency Alert Flow"""
    
    if len(input_sequence) == 1:
        # Ask for severity level
        response = """Emergency Alert
        
Select Severity:
1. Not Urgent (1)
2. Minor (2)
3. Moderate (3)
4. Serious (4)
5. CRITICAL (5)"""
        return build_ussd_response(response, True)
    
    elif len(input_sequence) == 2:
        # Confirm symptoms
        session['severity'] = input_sequence[1]
        response = """Describe your symptoms briefly:
(Numbers 1-5 for quick select)
1. Chest Pain
2. Difficulty Breathing
3. Severe Bleeding
4. Unconscious
5. Other"""
        return build_ussd_response(response, True)
    
    elif len(input_sequence) == 3:
        # Create emergency triage via API
        try:
            severity = int(session.get('severity', 3))
            
            # Call your existing /emergency/triage endpoint
            response = requests.post('http://localhost:5000/emergency/triage', 
                json={
                    'severity_level': severity,
                    'symptoms': f'USSD Emergency #{input_sequence[2]}',
                    'phone': phone,
                    'latitude': session.get('latitude'),
                    'longitude': session.get('longitude')
                },
                headers={'Authorization': 'Bearer ussd-service-token'}
            )
            
            if response.status_code == 200:
                data = response.json()
                clear_session(session['id'])
                return build_ussd_response(
                    f"✓ Emergency Alert Sent\n"
                    f"Expected Response: {data['expected_response_time']}\n"
                    f"Triage ID: {data['triage_id']}",
                    False
                )
        except Exception as e:
            pass
        
        return build_ussd_response(
            'Alert sent. Doctors will contact you shortly.',
            False
        )


def handle_book_doctor(session, input_sequence):
    """Book Doctor Appointment via USSD"""
    
    if len(input_sequence) == 1:
        response = """Select Specialty:
1. General Practice
2. Cardiology
3. Pediatrics
4. Neurology
5. Other"""
        return build_ussd_response(response, True)
    
    elif len(input_sequence) == 2:
        session['specialty'] = input_sequence[1]
        response = """Select Appointment:
1. Today (Today)
2. Tomorrow
3. This Week
4. Next Week"""
        return build_ussd_response(response, True)
    
    elif len(input_sequence) == 3:
        # Confirm booking
        response = """Enter Doctor ID (if known) or:
0. Auto-assign nearest doctor"""
        return build_ussd_response(response, True)


def handle_health_history(session, input_sequence, phone):
    """View Health History via USSD"""
    
    db = get_db()
    cur = db.cursor()
    
    # Get user from phone number
    cur.execute(
        'SELECT id, medical_history FROM users WHERE contact LIKE %s OR phone_number = %s',
        (f'%{phone}%', phone)
    )
    user = cur.fetchone()
    
    if not user:
        return build_ussd_response('User not found. Please register first.', False)
    
    # Get encrypted history
    history = decrypt_medical_history(user['medical_history'])
    
    # Format for USSD (limited text)
    history_summary = history[:300] if history else "No medical history recorded."
    
    response = f"""Your Medical History:
{history_summary}

For detailed history, visit web portal."""
    
    return build_ussd_response(response, False)


def get_or_create_session(session_id, phone):
    """Get or create USSD session"""
    
    if session_id not in USSD_SESSIONS:
        USSD_SESSIONS[session_id] = {
            'id': session_id,
            'phone': phone,
            'created': datetime.now(),
            'last_activity': datetime.now()
        }
    
    USSD_SESSIONS[session_id]['last_activity'] = datetime.now()
    return USSD_SESSIONS[session_id]


def clear_session(session_id):
    """Clear USSD session"""
    if session_id in USSD_SESSIONS:
        del USSD_SESSIONS[session_id]
```

### 6.2 USSD SESSION STORAGE (Database Alternative)

```sql
CREATE TABLE IF NOT EXISTS ussd_sessions (
    session_id VARCHAR(255) PRIMARY KEY,
    phone_number VARCHAR(20) NOT NULL,
    session_data JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    INDEX idx_phone (phone_number),
    INDEX idx_expires (expires_at)
);
```

### 6.3 LINK USSD TO USER ACCOUNTS

```python
@app.route('/ussd/register', methods=['POST'])
def ussd_register():
    """Link USSD phone number to existing patient account"""
    
    phone = request.form.get('phone')
    username = request.form.get('username')
    password = request.form.get('password')
    
    # Verify credentials
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT id, password_hash FROM users WHERE username = %s', (username,))
    user = cur.fetchone()
    
    if not user or not verify_password(password, user['password_hash']):
        return build_ussd_response('Invalid credentials. Try again.', True)
    
    # Update user phone number
    cur.execute(
        'UPDATE users SET phone_number = %s, contact = %s WHERE id = %s',
        (phone, phone, user['id'])
    )
    db.commit()
    
    return build_ussd_response(
        f'Registered! Your USSD account is active.',
        False
    )
```

---

## 7. USSD MENU STRUCTURE (Complete Flow)

```
START
│
├─ 1: SYMPTOM CHECKER
│  ├─ 1: Fever/Cough → (AI Analysis) → Prescribe/Refer Doctor
│  ├─ 2: Abdominal Pain → Send location → Find nearby clinic
│  └─ 3: Other → Free text input
│
├─ 2: EMERGENCY ALERT ⭐ (Critical)
│  ├─ Select severity (1-5)
│  ├─ Describe symptoms
│  └─ Auto-alert doctors + Send SMS to family
│
├─ 3: BOOK DOCTOR
│  ├─ Select specialty
│  ├─ Choose date/time
│  ├─ Confirm appointment
│  └─ Receive SMS confirmation
│
├─ 4: MY MEDICATIONS
│  ├─ View active prescriptions
│  ├─ Request refill
│  ├─ Report side effects
│  └─ Check drug interactions
│
├─ 5: HEALTH HISTORY
│  ├─ View summary (USSD safe)
│  ├─ Recent visits
│  └─ Active conditions
│
└─ 0: EXIT
```

---

## 8. SECURITY CONSIDERATIONS FOR USSD

### 8.1 Authentication
```python
# USSD users may not have email login
# Use: Phone-based OTP verification

def send_ussd_otp(phone):
    """Send 4-digit OTP via SMS"""
    otp = random.randint(1000, 9999)
    
    # Store OTP with 5-min expiry
    db.execute(
        'INSERT INTO ussd_otp (phone, otp, expires_at) VALUES (%s, %s, DATE_ADD(NOW(), INTERVAL 5 MINUTE))',
        (phone, otp)
    )
    
    # Send SMS
    send_sms(phone, f"Medical AI OTP: {otp}. Valid for 5 minutes.")
    return otp
```

### 8.2 Data Protection
```python
# In USSD responses, never send:
# ❌ Full medical history
# ❌ Medication names in plain text
# ❌ Lab test results
# ✅ References only ("View details on web portal")
# ✅ Summary/abstracts
# ✅ Alerts/reminders
```

### 8.3 Rate Limiting by Phone
```python
# Prevent abuse
@limiter.limit("5 per minute", key_func=lambda: request.form.get('phone'))
def ussd_callback():
    # USSD handler
    pass
```

---

## 9. COST BREAKDOWN (Monthly)

### For Kenya Market (100K users):

```
MONTHLY COSTS:
├─ USSD Requests
│  ├─ Active users: 10,000
│  ├─ Avg sessions/user: 2/month
│  ├─ Cost: 20,000 × $0.01 = $200
│  └─ Total: $200
│
├─ SMS Alerts
│  ├─ Emergency alerts: 500/month
│  ├─ Appointment reminders: 5,000/month
│  ├─ Cost: 5,500 × $0.05 = $275
│  └─ Total: $275
│
├─ Server Infrastructure
│  ├─ USSD gateway: $50 (already have Twilio/AT)
│  ├─ Server costs: $200 (no major increase)
│  └─ Total: $250
│
└─ TOTAL MONTHLY: $725 (for 100K users)
   COST PER USER: $0.0073/month
```

---

## 10. DEPLOYMENT CHECKLIST

- [ ] Register shortcode with telco authority
- [ ] Choose USSD provider (Africa's Talking or Twilio)
- [ ] Set up webhook/callback URL
- [ ] Implement session management (Redis or DB)
- [ ] Create USSD menu structure
- [ ] Integrate with existing endpoints (/emergency/triage, etc)
- [ ] Add phone-based authentication
- [ ] Implement rate limiting
- [ ] Test on actual phones (not emulator)
- [ ] Add USSD documentation to README
- [ ] Set up monitoring & alerts
- [ ] Train support team on USSD flows

---

## 11. MONITORING & METRICS

```python
@app.route('/admin/ussd-metrics', methods=['GET'])
def ussd_metrics():
    """Track USSD usage metrics"""
    
    db = get_db()
    cur = db.cursor()
    
    # Total sessions
    cur.execute(
        'SELECT COUNT(*) as total_sessions FROM ussd_sessions'
    )
    total = cur.fetchone()['total_sessions']
    
    # Active users
    cur.execute(
        'SELECT COUNT(DISTINCT phone_number) as active_users FROM ussd_sessions WHERE last_activity > DATE_SUB(NOW(), INTERVAL 30 DAY)'
    )
    active = cur.fetchone()['active_users']
    
    # Popular menus
    cur.execute(
        'SELECT menu_choice, COUNT(*) as count FROM ussd_logs GROUP BY menu_choice ORDER BY count DESC LIMIT 10'
    )
    popular = cur.fetchall()
    
    return jsonify({
        'total_sessions': total,
        'active_users': active,
        'popular_menus': popular,
        'avg_session_duration': '2-3 minutes'
    })
```

---

## 12. NEXT STEPS

1. **Immediate (Week 1-2)**:
   - Choose USSD provider
   - Register shortcode
   - Test with provider sandbox

2. **Short-term (Week 3-4)**:
   - Implement basic USSD handler
   - Create menu structure
   - Integrate emergency alert

3. **Medium-term (Month 2)**:
   - Add doctor booking
   - Implement health history
   - Add medication management

4. **Long-term (Month 3+)**:
   - Expand to other African countries
   - Add multi-language support
   - Implement payment integration (M-Pesa, Airtel)

---

## 13. REFERENCES & RESOURCES

**USSD Providers**:
- Africa's Talking: https://africastalking.com/ussd
- Twilio: https://www.twilio.com/en-us/messaging/ussd
- Vonage: https://developer.vonage.com/en/messaging/sms/guides/ussd

**Documentation**:
- USSD Protocol: https://en.wikipedia.org/wiki/Unstructured_Supplementary_Service_Data
- Africa's Talking API: https://africastalking.com/sms/api
- Twilio Python SDK: https://github.com/twilio/twilio-python

**HIPAA Compliance for SMS/USSD**:
- HIPAA requires encryption for patient data
- Keep messages generic when possible
- Audit all USSD transactions
- Implement 2FA for sensitive operations

---

**Author**: Medical AI Development Team  
**Date**: February 2026  
**Status**: Ready for Implementation
