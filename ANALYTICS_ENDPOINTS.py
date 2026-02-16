from datetime import datetime
import json

from flask import jsonify, request

from app import app, get_current_user
from db import get_db

# Analytics Endpoints for Phase 2
# To be added to app.py before the if __name__ == "__main__" line

@app.route('/patient/health-dashboard', methods=['GET'])
def patient_health_dashboard():
    """Get patient's health metrics and health trends."""
    current_user = get_current_user()
    if not current_user or current_user.get('role') != 'patient':
        return jsonify({'error': 'Unauthorized'}), 401
    
    db = get_db()
    cur = db.cursor()
    uid = current_user.get('id')
    
    # Fetch recent health metrics (last 30 days)
    cur.execute("""
        SELECT metric_type, metric_value, metric_date 
        FROM patient_health_metrics 
        WHERE patient_user_id = %s AND metric_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
        ORDER BY metric_date DESC
    """, (uid,))
    metrics = cur.fetchall()
    
    # Group metrics by type
    metrics_by_type = {}
    for m in metrics:
        mtype = m.get('metric_type') or 'Unknown'
        if mtype not in metrics_by_type:
            metrics_by_type[mtype] = []
        metrics_by_type[mtype].append({
            'date': str(m.get('metric_date')),
            'value': m.get('metric_value')
        })
    
    # Fetch risk score
    cur.execute("""
        SELECT risk_level, readmission_risk, no_show_risk, complication_risk, risk_factors
        FROM patient_risk_scores
        WHERE patient_user_id = %s
        ORDER BY calculated_at DESC LIMIT 1
    """, (uid,))
    risk_row = cur.fetchone()
    risk_score = dict(risk_row) if risk_row else {}
    
    # Fetch appointment count
    cur.execute("""
        SELECT COUNT(*) as total, 
               SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
               SUM(CASE WHEN status = 'no-show' THEN 1 ELSE 0 END) as no_show
        FROM appointments WHERE patient_user_id = %s
    """, (uid,))
    appt_row = cur.fetchone()
    appointments = dict(appt_row) if appt_row else {}
    
    return jsonify({
        'metrics': metrics_by_type,
        'risk_score': risk_score,
        'appointments': appointments
    })


@app.route('/patient/health-report', methods=['GET'])
def patient_health_report():
    """Generate a comprehensive health report for the patient."""
    current_user = get_current_user()
    if not current_user or current_user.get('role') != 'patient':
        return jsonify({'error': 'Unauthorized'}), 401
    
    db = get_db()
    cur = db.cursor()
    uid = current_user.get('id')
    
    # Get user profile
    cur.execute("SELECT full_name, age, gender FROM users WHERE id = %s", (uid,))
    user_row = cur.fetchone()
    user_info = dict(user_row) if user_row else {}
    
    # Get health metrics summary
    cur.execute("""
        SELECT metric_type, COUNT(*) as count, AVG(metric_value) as avg_value
        FROM patient_health_metrics
        WHERE patient_user_id = %s AND metric_date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
        GROUP BY metric_type
    """, (uid,))
    metrics_summary = cur.fetchall()
    
    # Get recent sessions and diagnoses
    cur.execute("""
        SELECT s.task, COUNT(*) as count
        FROM sessions s
        WHERE s.patient_user_id = %s AND s.created_at >= DATE_SUB(NOW(), INTERVAL 90 DAY)
        GROUP BY s.task
    """, (uid,))
    sessions_summary = cur.fetchall()
    
    # Generate summary
    report_summary = "Health Report Summary:\n"
    report_summary += f"Patient: {user_info.get('full_name', 'Unknown')}\n"
    report_summary += f"Age: {user_info.get('age', 'N/A')}, Gender: {user_info.get('gender', 'N/A')}\n\n"
    
    if metrics_summary:
        report_summary += "Health Metrics (Last 90 Days):\n"
        for m in metrics_summary:
            report_summary += f"- {m.get('metric_type')}: {m.get('count')} records, Avg: {m.get('avg_value'):.2f}\n"
    
    if sessions_summary:
        report_summary += "\nRecent Health Concerns:\n"
        for s in sessions_summary:
            report_summary += f"- {s.get('task')}: {s.get('count')} conversations\n"
    
    return jsonify({
        'user_info': user_info,
        'metrics_summary': [dict(m) for m in metrics_summary],
        'sessions_summary': [dict(s) for s in sessions_summary],
        'report_summary': report_summary
    })


@app.route('/doctor/analytics', methods=['GET'])
def doctor_analytics():
    """Get doctor's practice analytics and statistics."""
    current_user = get_current_user()
    if not current_user or current_user.get('role') not in ('doctor', 'dev'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    db = get_db()
    cur = db.cursor()
    uid = current_user.get('id')
    
    # Get or create doctor statistics
    cur.execute("""
        SELECT * FROM doctor_statistics WHERE doctor_user_id = %s
    """, (uid,))
    stats = cur.fetchone()
    
    if not stats:
        # Calculate stats
        cur.execute("""
            SELECT COUNT(DISTINCT patient_user_id) as total_patients,
                   COUNT(*) as total_appointments
            FROM appointments WHERE doctor_user_id = %s
        """, (uid,))
        counts = cur.fetchone()
        
        total_patients = counts.get('total_patients', 0) if counts else 0
        total_appointments = counts.get('total_appointments', 0) if counts else 0
        
        # Insert stats
        cur.execute("""
            INSERT INTO doctor_statistics (doctor_user_id, total_patients, total_appointments, updated_at)
            VALUES (%s, %s, %s, %s)
        """, (uid, total_patients, total_appointments, datetime.utcnow()))
        db.commit()
        stats_dict = {
            'doctor_user_id': uid,
            'total_patients': total_patients,
            'total_appointments': total_appointments
        }
    else:
        stats_dict = dict(stats)
    
    return jsonify({'statistics': stats_dict})


@app.route('/doctor/patient-cases', methods=['GET'])
def doctor_patient_cases():
    """Get all patient cases handled by the doctor."""
    current_user = get_current_user()
    if not current_user or current_user.get('role') not in ('doctor', 'dev'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    db = get_db()
    cur = db.cursor()
    uid = current_user.get('id')
    
    # Get all sessions with this doctor as assigned
    cur.execute("""
        SELECT DISTINCT s.id, s.patient_name, s.task, s.created_at, COUNT(m.id) as message_count
        FROM sessions s
        LEFT JOIN messages m ON s.id = m.session_id
        WHERE s.patient_user_id IN (
            SELECT DISTINCT patient_user_id FROM appointments WHERE doctor_user_id = %s
        )
        GROUP BY s.id
        ORDER BY s.created_at DESC
    """, (uid,))
    cases = cur.fetchall()
    
    return jsonify({
        'cases': [dict(c) for c in cases],
        'total_cases': len(cases)
    })


@app.route('/calculate-patient-risk', methods=['POST'])
def calculate_patient_risk():
    """Calculate risk scores for a patient based on their health data."""
    current_user = get_current_user()
    if not current_user or current_user.get('role') not in ('doctor', 'dev'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json() or {}
    patient_user_id = data.get('patient_user_id')
    
    if not patient_user_id:
        return jsonify({'error': 'patient_user_id required'}), 400
    
    db = get_db()
    cur = db.cursor()
    
    # Fetch patient health data
    cur.execute("""
        SELECT age FROM users WHERE id = %s
    """, (patient_user_id,))
    user_row = cur.fetchone()
    age = user_row.get('age', 0) if user_row else 0
    
    # Count recent appointments
    cur.execute("""
        SELECT COUNT(*) as no_show_count FROM appointments
        WHERE patient_user_id = %s AND status = 'no-show' AND appointment_time >= DATE_SUB(NOW(), INTERVAL 6 MONTH)
    """, (patient_user_id,))
    no_show_row = cur.fetchone()
    no_show_count = no_show_row.get('no_show_count', 0) if no_show_row else 0
    
    # Calculate risks
    no_show_risk = min(100, no_show_count * 15)
    readmission_risk = max(0, age - 50) * 0.5
    complication_risk = 10.0
    
    risk_factors = {
        'age': age,
        'no_show_history': no_show_count,
        'recent_appointments': 0
    }
    
    # Determine risk level
    avg_risk = (no_show_risk + readmission_risk + complication_risk) / 3
    if avg_risk < 20:
        risk_level = 'LOW'
    elif avg_risk < 50:
        risk_level = 'MEDIUM'
    else:
        risk_level = 'HIGH'
    
    # Store risk score
    cur.execute("""
        INSERT INTO patient_risk_scores (patient_user_id, risk_level, readmission_risk, no_show_risk, complication_risk, risk_factors, calculated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (patient_user_id, risk_level, readmission_risk, no_show_risk, complication_risk, json.dumps(risk_factors), datetime.utcnow()))
    db.commit()
    
    return jsonify({
        'patient_user_id': patient_user_id,
        'risk_level': risk_level,
        'readmission_risk': round(readmission_risk, 2),
        'no_show_risk': round(no_show_risk, 2),
        'complication_risk': round(complication_risk, 2),
        'risk_factors': risk_factors
    })


@app.route('/log-analytics-event', methods=['POST'])
def log_analytics_event():
    """Log user interaction events for analytics."""
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json() or {}
    event_type = data.get('event_type')
    event_data = data.get('event_data', {})
    
    if not event_type:
        return jsonify({'error': 'event_type required'}), 400
    
    db = get_db()
    cur = db.cursor()
    
    ip_address = request.remote_addr
    user_agent = request.headers.get('User-Agent', '')[:500]
    
    cur.execute("""
        INSERT INTO analytics_events (user_id, event_type, event_data, ip_address, user_agent, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (current_user.get('id'), event_type, json.dumps(event_data), ip_address, user_agent, datetime.utcnow()))
    db.commit()
    
    return jsonify({'success': True})
