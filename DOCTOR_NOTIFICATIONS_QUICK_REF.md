# 🏥 Doctor Notification System - Quick Reference

## 4 New Endpoints

### 1️⃣ Send to One Patient
```bash
POST /doctor/send-notification

Body:
{
  "patient_id": 123,
  "title": "Medication Update",
  "message": "Your dose increased to 10mg",
  "priority": "urgent",  # normal, urgent, emergency
  "type": "medication"   # treatment, medication, appointment, general
}
```

---

### 2️⃣ View Patient's Notifications
```bash
GET /doctor/patients/{patient_id}/notifications

Returns: All notifications sent to that patient
```

---

### 3️⃣ Broadcast to All or Specific
```bash
POST /doctor/send-system-notification

Option A - All patients:
{
  "title": "Clinic Closed Feb 20",
  "message": "Maintenance scheduled",
  "priority": "normal"
}

Option B - Specific patients:
{
  "title": "Appointment Tomorrow",
  "message": "2 PM with Dr. Smith",
  "patients_ids": [1, 2, 5],
  "priority": "normal"
}
```

---

### 4️⃣ Patient Views Doctor Alerts
```bash
GET /patient/notifications/from-doctors

Returns: All notifications from doctors
```

---

## 🎯 Priority Behavior

| Priority | Email | SMS | Use Case |
|----------|-------|-----|----------|
| normal | ✅ | ❌ | Regular updates |
| urgent | ✅ | ✅ | Important alerts |
| emergency | ✅ | ✅ | Critical/life-threatening |

---

## 📋 Example Workflows

### Workflow 1: Doctor sends medication alert
```bash
1. Doctor fills form:
   - Patient ID: 123
   - Title: "Medication Change"
   - Priority: "urgent"

2. System:
   - Creates notification
   - Sends email to patient
   - Sends SMS to patient
   - Logs in audit trail

3. Patient:
   - Sees in-app notification
   - Gets email with details
   - Gets SMS alert
   - Can read full message in dashboard
```

### Workflow 2: Clinic-wide announcement
```bash
1. Admin fills form:
   - Title: "New Service Available"
   - Message about telehealth
   - Leave patients_ids empty

2. System:
   - Sends to ALL patients
   - 250+ emails sent
   - Logged in audit

3. Patients:
   - All see notification
   - Email in inbox
   - Can act on announcement
```

---

## 🧪 Test Commands

```bash
# Test 1: Send notification
curl -X POST http://localhost:5000/doctor/send-notification \
  -H "Authorization: Bearer DOCTOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "patient_id": 1,
    "title": "Test",
    "message": "Test message",
    "priority": "urgent",
    "type": "general"
  }'

# Test 2: Patient views notifications
curl -X GET http://localhost:5000/patient/notifications/from-doctors \
  -H "Authorization: Bearer PATIENT_TOKEN"

# Test 3: Doctor views sent notifications
curl -X GET http://localhost:5000/doctor/patients/1/notifications \
  -H "Authorization: Bearer DOCTOR_TOKEN"

# Test 4: Broadcast to all
curl -X POST http://localhost:5000/doctor/send-system-notification \
  -H "Authorization: Bearer DOCTOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "System Message",
    "message": "Important update",
    "priority": "normal"
  }'
```

---

## ✅ Features

- ✅ Direct doctor-to-patient messages
- ✅ System-wide broadcasts
- ✅ 3 priority levels
- ✅ Email delivery (SendGrid)
- ✅ SMS delivery (Twilio)
- ✅ In-app notifications
- ✅ Audit logging
- ✅ Role-based access

---

## 🔑 Requirements

**Doctor must have:**
- Role = 'doctor' in database
- Valid JWT token

**Patient must have:**
- Valid patient record
- Email (for notifications)
- Phone (for SMS - optional)

---

## 📊 Database Stored As

```sql
notifications table:
- id: auto-increment
- user_id: patient ID
- type: doctor_normal, doctor_urgent, doctor_emergency, system_*
- title: notification title
- body: full message
- data: JSON with sender info
- is_read: 0/1
- created_at: timestamp

audit table:
- actor_id: doctor ID
- action: doctor_notification_*
- target_id: patient ID
- details: what happened
- timestamp: when it happened
```

---

## 🚀 Ready to Use

Everything is implemented and tested. Just:

1. **Verify SendGrid** in .env
2. **Test with test_doctor_notifications.py**
3. **Add UI** to doctor.html (optional)
4. **Deploy** to production

---

## 📚 Full Docs

See: **DOCTOR_NOTIFICATION_SYSTEM.md** (500+ lines)

Including:
- Complete API specification
- All use cases
- Troubleshooting
- Database schema
- Security details
- Testing guide

---

**Status**: ✅ Production Ready  
**Date**: Feb 18, 2026  
**Version**: 1.0
