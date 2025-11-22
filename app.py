"""Flask-based prototype backend for the Medical AI Assistant.

This file exposes a simple HTTP API the `dashboard.html` frontend can call.
It uses the existing PatientAIAssistant logic and adds sqlite persistence,
basic token auth, CORS for local testing, and endpoints for doctor alerts.

Notes:
- Requires environment variables: GEMINI_API_KEY (for Google GenAI) and DEV_API_KEY (simple header token for prototype).
- Install dependencies with `pip install -r requirements.txt`.
"""

import os
import re
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Optional

import jwt
from passlib.hash import pbkdf2_sha256 as pwd_hasher
from werkzeug.utils import secure_filename
from flask import Flask, request, jsonify, g, send_from_directory
from flask_cors import CORS

try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except Exception:
    HAS_GENAI = False


DB_PATH = os.path.join(os.path.dirname(__file__), "chats.db")
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-jwt-secret")
JWT_ALGO = "HS256"
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


class PatientAIAssistant:
    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            self.client = None
        else:
            if not HAS_GENAI:
                self.client = None
            else:
                self.client = genai.Client(api_key=self.api_key)

        self.model = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")

        self.critical_keywords = [
            "chest pain", "difficulty breathing", "severe bleeding",
            "unconscious", "fainting", "loss of consciousness",
            "severe pain", "suicidal", "heart attack", "stroke",
            "emergency", "can't breathe", "paralysis", "confusion",
            "high fever", "seizure", "allergic reaction", "swelling",
        ]

        self.system_prompt = (
            "You are a helpful AI medical assistant designed to provide general guidance for patients. "
            "Provide general information, suggest basic home care, and identify potential emergencies. "
            "Always include a clear disclaimer and avoid prescribing specific medications or dosages."
        )

    def check_critical_condition(self, text: str) -> bool:
        lower = text.lower()
        return any(k in lower for k in self.critical_keywords)

    def generate_response(self, user_input: str, patient_info: Optional[dict] = None) -> str:
        # Basic sanitization and length limiting
        if not isinstance(user_input, str):
            return "I'm sorry — I could not understand your message."
        text = user_input.strip()
        if len(text) > 4000:
            text = text[:4000]

        if self.check_critical_condition(text):
            return self._emergency_message(patient_info)

        prompt = f"{self.system_prompt}\n\nPatient: {text}\n\nAssistant:"

        # If genai client is not available, return a fallback message
        if not self.client:
            return (
                "(Prototype mode - no model client configured) "
                "I can help with general health information. Please consult a healthcare professional for a diagnosis."
            )

        # Prepare request for Google GenAI (best-effort, may need adjustment based on SDK versions)
        try:
            contents = [
                types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
            ]
            response_text = ""
            for chunk in self.client.models.generate_content_stream(
                model=self.model,
                contents=contents,
            ):
                response_text += getattr(chunk, "text", "")

            if not response_text:
                response_text = "I'm sorry, I couldn't generate a response right now."

            disclaimer = (
                "\n\n⚠️ Disclaimer: This is not a substitute for professional medical advice. "
                "Please consult with a healthcare professional for diagnosis and treatment."
            )
            return response_text + disclaimer
        except Exception:
            return "I'm sorry — an internal error occurred while generating a response."

    def _emergency_message(self, patient_info: Optional[dict] = None) -> str:
        # Determine emergency number by locale if provided
        emergency_number = "911"
        if patient_info and isinstance(patient_info, dict):
            locale = patient_info.get("locale") or patient_info.get("country")
            if locale:
                locale = locale.lower()
                # Basic mapping (extendable)
                mapping = {"us": "911", "ke": "+254 112", "uk": "999", "in": "112"}
                emergency_number = mapping.get(locale[:2], emergency_number)

        return (
            f"⚠️ EMERGENCY WARNING ⚠️\n\nBased on your message, you may be experiencing a medical emergency. "
            f"Please seek immediate medical attention by:\n- Calling emergency services ({emergency_number})\n"
            "- Going to the nearest emergency room\n- Having someone take you to a doctor immediately\n\n"
            "Do not wait for a response from this AI system in an emergency situation."
        )


def get_db():
    db = getattr(g, "db", None)
    if db is None:
        db = g.db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db


def init_db():
    db = sqlite3.connect(DB_PATH)
    cur = db.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_name TEXT,
            age TEXT,
            gender TEXT,
            contact TEXT,
            medical_history TEXT,
            task TEXT,
            locale TEXT,
            created_at TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            role TEXT,
            content TEXT,
            emergency INTEGER DEFAULT 0,
            timestamp TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            stored_path TEXT,
            original_name TEXT,
            mime_type TEXT,
            uploaded_by INTEGER,
            timestamp TEXT
        )
        """
    )
    # Users table for patients and doctors
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password_hash TEXT,
            role TEXT,
            profession TEXT,
            created_at TEXT
        )
        """
    )

    # Add creator_id to users so doctors (or other staff) can be tracked as creators
    try:
        cur.execute("ALTER TABLE users ADD COLUMN creator_id INTEGER")
    except sqlite3.OperationalError:
        # column likely already exists
        pass
    # Ensure creator_id is present (backfill existing rows with NULL)
    try:
        cur.execute("UPDATE users SET creator_id = NULL WHERE creator_id IS NULL")
    except Exception:
        pass

    # Audit table to track actions such as patient creation
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_id INTEGER,
            action TEXT,
            target_id INTEGER,
            details TEXT,
            timestamp TEXT
        )
        """
    )

    # One-time tokens for temporary login links
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS one_time_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            token TEXT UNIQUE,
            expires_at TEXT,
            used INTEGER DEFAULT 0,
            created_at TEXT
        )
        """
    )

    # Add patient_user_id column to sessions if not present (safe for existing DB)
    try:
        cur.execute("ALTER TABLE sessions ADD COLUMN patient_user_id INTEGER")
    except sqlite3.OperationalError:
        # column likely already exists
        pass
    db.commit()
    db.close()


app = Flask(__name__)
CORS(app)
assistant = PatientAIAssistant()
init_db()


def check_api_key(req):
    expected = os.environ.get("DEV_API_KEY")
    if not expected:
        return False, "Server not configured with DEV_API_KEY"
    header = req.headers.get("X-API-KEY")
    if not header:
        return False, "Missing X-API-KEY header"
    if header != expected:
        return False, "Invalid API key"
    return True, "ok"


def generate_jwt(user_id: int, role: str, expires_minutes: int = 1440) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "exp": datetime.utcnow() + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def decode_jwt(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        return payload
    except Exception:
        return None


def get_current_user():
    # Try Authorization header first
    auth = request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        token = auth.split(None, 1)[1]
        payload = decode_jwt(token)
        if payload:
            db = get_db()
            cur = db.cursor()
            cur.execute("SELECT id, username, role, profession FROM users WHERE id = ?", (payload.get('sub'),))
            row = cur.fetchone()
            if row:
                return dict(row)
    # Fallback to X-API-KEY (dev flow)
    ok, msg = check_api_key(request)
    if ok:
        return {"username": "dev", "role": "dev"}
    return None


@app.teardown_appcontext
def close_db(exc):
    db = getattr(g, "db", None)
    if db is not None:
        db.close()


@app.route("/")
def serve_dashboard():
    """Serve the unified auth page at root so users sign up / login first.

    The existing `dashboard.html` and `doctor.html` remain accessible directly
    (e.g. `/dashboard.html` or `/doctor`) for testing, but the app now lands
    on `auth.html` which guides users to the appropriate view based on role.
    """
    project_dir = os.path.dirname(__file__)
    auth_path = os.path.join(project_dir, "auth.html")
    if os.path.exists(auth_path):
        return send_from_directory(project_dir, "auth.html")
    # fallback to dashboard if auth.html missing
    dashboard_path = os.path.join(project_dir, "dashboard.html")
    if os.path.exists(dashboard_path):
        return send_from_directory(project_dir, "dashboard.html")
    return jsonify({"error": "auth.html and dashboard.html not found"}), 404


@app.route('/doctor')
def serve_doctor():
    """Serve doctor.html for clinician users (direct navigation support)."""
    project_dir = os.path.dirname(__file__)
    doctor_path = os.path.join(project_dir, "doctor.html")
    if os.path.exists(doctor_path):
        return send_from_directory(project_dir, "doctor.html")
    return jsonify({"error": "doctor.html not found"}), 404


@app.route('/dashboard.html')
def serve_dashboard_static():
    project_dir = os.path.dirname(__file__)
    dashboard_path = os.path.join(project_dir, "dashboard.html")
    if os.path.exists(dashboard_path):
        return send_from_directory(project_dir, "dashboard.html")
    return jsonify({"error": "dashboard.html not found"}), 404


@app.route('/chat', methods=['POST'])
def chat():
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401

    payload = request.get_json() or {}
    message = payload.get('message')
    patient_info = payload.get('patient_info', {})
    session_id = payload.get('session_id')

    if not message:
        return jsonify({'error': 'Missing message'}), 400

    db = get_db()
    cur = db.cursor()

    # Create session if none
    if not session_id:
        # Link session to patient user if current_user is a patient
        patient_user_id = None
        if current_user.get('role') == 'patient' and current_user.get('id'):
            patient_user_id = current_user.get('id')

        cur.execute(
            "INSERT INTO sessions (patient_user_id, patient_name, age, gender, contact, medical_history, task, locale, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                patient_user_id,
                patient_info.get("fullName"),
                patient_info.get("age"),
                patient_info.get("gender"),
                patient_info.get("contact"),
                patient_info.get("medicalHistory"),
                patient_info.get("task"),
                patient_info.get("locale"),
                datetime.utcnow().isoformat(),
            ),
        )
        session_id = cur.lastrowid
        db.commit()

    # Insert user message
    emergency_flag = 1 if assistant.check_critical_condition(message) else 0
    cur.execute(
        "INSERT INTO messages (session_id, role, content, emergency, timestamp) VALUES (?, ?, ?, ?, ?)",
        (session_id, "user", message, emergency_flag, datetime.utcnow().isoformat()),
    )
    db.commit()

    # If emergency detected, short-circuit with emergency message
    if emergency_flag:
        reply = assistant._emergency_message(patient_info)
        cur.execute(
            "INSERT INTO messages (session_id, role, content, emergency, timestamp) VALUES (?, ?, ?, ?, ?)",
            (session_id, "assistant", reply, 1, datetime.utcnow().isoformat()),
        )
        db.commit()
        return jsonify({"reply_text": reply, "reply_html": "<div class=\"alert alert-danger\">" + reply + "</div>", "emergency": True, "session_id": session_id})

    # Generate response (may return fallback if model not configured)
    reply_text = assistant.generate_response(message, patient_info)

    cur.execute(
        "INSERT INTO messages (session_id, role, content, emergency, timestamp) VALUES (?, ?, ?, ?, ?)",
        (session_id, "assistant", reply_text, 0, datetime.utcnow().isoformat()),
    )
    db.commit()

    reply_html = "<div>" + (reply_text.replace("\n", "<br>")) + "</div>"
    return jsonify({"reply_text": reply_text, "reply_html": reply_html, "emergency": False, "session_id": session_id})


@app.route("/doctor/alerts", methods=["GET"])
def doctor_alerts():
    current_user = get_current_user()
    if not current_user:
        return jsonify({"error": "Unauthorized"}), 401
    if current_user.get('role') != 'doctor' and current_user.get('role') != 'dev':
        return jsonify({"error": "Forbidden"}), 403

    db = get_db()
    cur = db.cursor()
    cur.execute(
        "SELECT m.id, m.session_id, m.content, m.timestamp, s.patient_name, s.task FROM messages m JOIN sessions s ON m.session_id = s.id WHERE m.emergency = 1 ORDER BY m.timestamp DESC"
    )
    rows = cur.fetchall()
    alerts = [dict(row) for row in rows]
    return jsonify({"alerts": alerts})


@app.route('/doctor/patients', methods=['POST'])
def doctor_create_patient():
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401
    # allow any authenticated account to create patient accounts; track creator

    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')
    full_name = data.get('fullName') or data.get('patient_name')
    age = data.get('age')
    gender = data.get('gender')
    contact = data.get('contact')
    medical_history = data.get('medicalHistory')
    task = data.get('task')
    locale = data.get('locale')

    if not username:
        return jsonify({'error': 'username required'}), 400

    # generate a temporary password if none provided
    if not password:
        import secrets
        password = secrets.token_urlsafe(8)

    # basic password length guard
    if len(password.encode('utf-8')) > 4096:
        return jsonify({'error': 'password too long'}), 400

    pw_hash = pwd_hasher.hash(password)
    db = get_db()
    cur = db.cursor()
    try:
        creator_id = current_user.get('id') if current_user.get('id') else None
        cur.execute("INSERT INTO users (username, password_hash, role, profession, created_at, creator_id) VALUES (?, ?, ?, ?, ?, ?)",
                    (username, pw_hash, 'patient', None, datetime.utcnow().isoformat(), creator_id))
        user_id = cur.lastrowid

        # create an initial session for the patient with provided profile info
        cur.execute(
            "INSERT INTO sessions (patient_user_id, patient_name, age, gender, contact, medical_history, task, locale, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                full_name,
                age,
                gender,
                contact,
                medical_history,
                task,
                locale,
                datetime.utcnow().isoformat(),
            ),
        )
        session_id = cur.lastrowid
        # create a one-time login token valid for 24 hours
        import secrets
        token = secrets.token_urlsafe(24)
        expires = (datetime.utcnow() + timedelta(hours=24)).isoformat()
        cur.execute("INSERT INTO one_time_tokens (user_id, token, expires_at, used, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, token, expires, 0, datetime.utcnow().isoformat()))
        # audit entry
        details = f"created patient user {username} (session {session_id})"
        cur.execute("INSERT INTO audit (actor_id, action, target_id, details, timestamp) VALUES (?, ?, ?, ?, ?)",
                (creator_id, 'create_patient', user_id, details, datetime.utcnow().isoformat()))
        db.commit()
        one_time_link = f"/one_time_login?token={token}"
        return jsonify({'user_id': user_id, 'username': username, 'session_id': session_id, 'one_time_link': one_time_link, 'one_time_token': token, 'one_time_expires': expires})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'username already exists'}), 400


@app.route('/doctor/patients', methods=['GET'])
def doctor_list_patients():
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401
    db = get_db()
    cur = db.cursor()
    # If dev, return all patients; otherwise return patients created by this user
    if current_user.get('role') == 'dev':
        cur.execute("SELECT id, username, created_at FROM users WHERE role = 'patient' ORDER BY created_at DESC")
    else:
        creator_id = current_user.get('id')
        cur.execute("SELECT id, username, created_at FROM users WHERE role = 'patient' AND creator_id = ? ORDER BY created_at DESC", (creator_id,))
    rows = cur.fetchall()
    patients = [dict(r) for r in rows]
    return jsonify({'patients': patients})


@app.route('/doctor/audit', methods=['GET'])
def doctor_audit():
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401
    db = get_db()
    cur = db.cursor()
    # dev sees all; otherwise show entries where actor_id == current_user.id
    if current_user.get('role') == 'dev':
        cur.execute('SELECT id, actor_id, action, target_id, details, timestamp FROM audit ORDER BY timestamp DESC LIMIT 200')
    else:
        cur.execute('SELECT id, actor_id, action, target_id, details, timestamp FROM audit WHERE actor_id = ? ORDER BY timestamp DESC LIMIT 200', (current_user.get('id'),))
    rows = cur.fetchall()
    audits = [dict(r) for r in rows]
    return jsonify({'audit': audits})


@app.route("/sessions/<int:sid>/messages", methods=["GET"])
def get_session_messages(sid):
    current_user = get_current_user()
    if not current_user:
        return jsonify({"error": "Unauthorized"}), 401

    db = get_db()
    cur = db.cursor()
    # If user is doctor, allow. If patient, ensure they own the session
    if current_user.get('role') == 'doctor' or current_user.get('role') == 'dev':
        cur.execute("SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp", (sid,))
        rows = cur.fetchall()
        messages = [dict(r) for r in rows]
        return jsonify({"messages": messages})

    # patient
    cur.execute("SELECT patient_user_id FROM sessions WHERE id = ?", (sid,))
    row = cur.fetchone()
    if not row:
        return jsonify({"error": "Session not found"}), 404
    if row[0] != current_user.get('id'):
        return jsonify({"error": "Forbidden"}), 403

    cur.execute("SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp", (sid,))
    rows = cur.fetchall()
    messages = [dict(r) for r in rows]
    return jsonify({"messages": messages})


@app.route('/users/register', methods=['POST'])
def register_user():
    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')
    role = data.get('role')  # 'patient' or 'doctor'
    profession = data.get('profession')
    if not username or not password or role not in ('patient', 'doctor'):
        return jsonify({'error': 'username, password and valid role required'}), 400

    # simple guard against overly long passwords in this prototype
    if len(password.encode('utf-8')) > 4096:
        return jsonify({'error': 'password too long'}), 400

    pw_hash = pwd_hasher.hash(password)
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("INSERT INTO users (username, password_hash, role, profession, created_at) VALUES (?, ?, ?, ?, ?)",
                    (username, pw_hash, role, profession, datetime.utcnow().isoformat()))
        db.commit()
        return jsonify({'status': 'ok'})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'username already exists'}), 400


@app.route('/users/login', methods=['POST'])
def login_user():
    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({'error': 'username and password required'}), 400

    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT id, password_hash, role FROM users WHERE username = ?', (username,))
    row = cur.fetchone()
    if not row:
        return jsonify({'error': 'invalid credentials'}), 401
    user_id, pw_hash, role = row
    if not pwd_hasher.verify(password, pw_hash):
        return jsonify({'error': 'invalid credentials'}), 401

    token = generate_jwt(user_id, role)
    return jsonify({'token': token, 'role': role, 'user_id': user_id})


@app.route('/sessions/<int:sid>/survey', methods=['POST'])
def post_survey(sid):
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401
    if current_user.get('role') != 'doctor' and current_user.get('role') != 'dev':
        return jsonify({'error': 'Forbidden'}), 403

    data = request.get_json() or {}
    survey_content = data.get('content')
    if not survey_content:
        return jsonify({'error': 'content required'}), 400

    db = get_db()
    cur = db.cursor()
    # Insert survey as a message with role 'doctor'
    cur.execute("INSERT INTO messages (session_id, role, content, emergency, timestamp) VALUES (?, ?, ?, ?, ?)",
                (sid, 'doctor', survey_content, 0, datetime.utcnow().isoformat()))
    db.commit()
    return jsonify({'status': 'ok'})


@app.route('/upload', methods=['POST'])
def upload_file():
    """Accept file uploads (multipart/form-data) and associate with a session.
    Requires authentication (patient or doctor). Expects form fields: session_id (optional), file (required).
    Returns metadata about saved file.
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401

    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    f = request.files['file']
    if f.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    session_id = request.form.get('session_id')
    # If no session_id provided, require patient info to create a session
    db = get_db()
    cur = db.cursor()
    if not session_id:
        return jsonify({'error': 'session_id required'}), 400

    # Ensure the session exists
    cur.execute('SELECT id FROM sessions WHERE id = ?', (session_id,))
    if not cur.fetchone():
        return jsonify({'error': 'session not found'}), 404

    filename = secure_filename(f.filename)
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    stored_name = f"{timestamp}_{filename}"
    stored_path = os.path.join(UPLOAD_DIR, stored_name)
    f.save(stored_path)

    cur.execute(
        "INSERT INTO files (session_id, stored_path, original_name, mime_type, uploaded_by, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, stored_path, f.filename, f.mimetype, current_user.get('id'), datetime.utcnow().isoformat()),
    )
    file_id = cur.lastrowid
    db.commit()

    return jsonify({
        'file_id': file_id,
        'session_id': int(session_id),
        'original_name': f.filename,
        'mime_type': f.mimetype,
    })


@app.route('/sessions/<int:sid>/files', methods=['GET'])
def list_session_files(sid):
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401

    db = get_db()
    cur = db.cursor()
    # Access control: doctors or session owner
    if current_user.get('role') == 'doctor' or current_user.get('role') == 'dev':
        cur.execute('SELECT id, original_name, mime_type, timestamp FROM files WHERE session_id = ? ORDER BY timestamp DESC', (sid,))
    else:
        # patient: ensure they own the session
        cur.execute('SELECT patient_user_id FROM sessions WHERE id = ?', (sid,))
        row = cur.fetchone()
        if not row or row[0] != current_user.get('id'):
            return jsonify({'error': 'Forbidden'}), 403
        cur.execute('SELECT id, original_name, mime_type, timestamp FROM files WHERE session_id = ? ORDER BY timestamp DESC', (sid,))

    rows = cur.fetchall()
    files = [dict(r) for r in rows]
    return jsonify({'files': files})


@app.route('/files/<int:file_id>', methods=['GET'])
def download_file(file_id):
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401

    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT session_id, stored_path, original_name, mime_type FROM files WHERE id = ?', (file_id,))
    row = cur.fetchone()
    if not row:
        return jsonify({'error': 'File not found'}), 404

    session_id, stored_path, original_name, mime_type = row
    # Check access: doctors or owner
    if current_user.get('role') not in ('doctor', 'dev'):
        cur.execute('SELECT patient_user_id FROM sessions WHERE id = ?', (session_id,))
        srow = cur.fetchone()
        if not srow or srow[0] != current_user.get('id'):
            return jsonify({'error': 'Forbidden'}), 403

    # Stream file
    if not os.path.exists(stored_path):
        return jsonify({'error': 'File missing on server'}), 404
    return send_from_directory(UPLOAD_DIR, os.path.basename(stored_path), as_attachment=True, download_name=original_name)


@app.route('/one_time_consume', methods=['POST'])
def one_time_consume():
    data = request.get_json() or {}
    token = data.get('token')
    if not token:
        return jsonify({'error': 'token required'}), 400

    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT id, user_id, expires_at, used FROM one_time_tokens WHERE token = ?', (token,))
    row = cur.fetchone()
    if not row:
        return jsonify({'error': 'invalid token'}), 400
    tid, user_id, expires_at, used = row
    if used:
        return jsonify({'error': 'token already used'}), 400
    if datetime.fromisoformat(expires_at) < datetime.utcnow():
        return jsonify({'error': 'token expired'}), 400

    # mark as used
    cur.execute('UPDATE one_time_tokens SET used = 1 WHERE id = ?', (tid,))
    db.commit()

    # issue JWT for the user
    cur.execute('SELECT id, role FROM users WHERE id = ?', (user_id,))
    urow = cur.fetchone()
    if not urow:
        return jsonify({'error': 'user not found'}), 404
    uid, role = urow
    token_jwt = generate_jwt(uid, role)
    return jsonify({'token': token_jwt, 'role': role})


@app.route('/one_time_login')
def one_time_login():
        token = request.args.get('token')
        if not token:
                return jsonify({'error': 'token query param required'}), 400

        html = f"""
        <!doctype html>
        <html>
        <head>
            <meta charset='utf-8' />
            <title>One-time Login</title>
            <style>body{{font-family:Arial,Helvetica,sans-serif;padding:20px}}.box{{border:1px solid #ccc;padding:16px;border-radius:8px;max-width:640px}}</style>
        </head>
        <body>
            <div class='box'>
                <h3>One-time login</h3>
                <p class='small'>Attempting to sign you in automatically. If nothing happens, click the button below.</p>
                <div id='status'>Signing in…</div>
                <button id='btn'>Sign in</button>
            </div>
            <script>
                const token = '{token}';
                async function consume(){
                    try{
                        const resp = await fetch('/one_time_consume', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({token})});
                        const j = await resp.json();
                        if(!resp.ok){ document.getElementById('status').textContent = 'Login failed: ' + (j.error || resp.statusText); return }
                        sessionStorage.setItem('jwt_token', j.token);
                        sessionStorage.setItem('user_role', j.role || 'patient');
                        document.getElementById('status').textContent = 'Signed in. Redirecting…';
                        window.location.href = '/dashboard.html';
                    }catch(e){ document.getElementById('status').textContent = 'Network error'; }
                }
                document.getElementById('btn').addEventListener('click', consume);
                consume();
            </script>
        </body>
        </html>
        """
        return html


@app.route('/print/patient_card')
def print_patient_card():
        """Serve a printable patient card that uses a one-time login token.

        Expects query params: `username` (required), `token` (one-time token), `session_id` (optional), `name` (optional)
        """
        username = request.args.get('username')
        token = request.args.get('token')
        session_id = request.args.get('session_id')
        name = request.args.get('name')
        if not username or not token:
                return jsonify({'error': 'username and token query params required'}), 400

        html = f"""
        <!doctype html>
        <html>
        <head>
            <meta charset='utf-8' />
            <title>Patient Card - {username}</title>
            <style>body{{font-family:Arial,Helvetica,sans-serif;padding:20px}}.card{{border:1px solid #ccc;padding:16px;border-radius:8px;max-width:420px}}.meta{{margin-bottom:8px}}</style>
        </head>
        <body>
            <div class='card'>
                <h3>Patient Login Card</h3>
                <div class='meta'><strong>Name:</strong> {name or ''}</div>
                <div class='meta'><strong>Username:</strong> {username}</div>
                <div id='qrcode'></div>
                <p class='small'>Scan the QR code to open a one-time login link in the clinic device.</p>
                <p class='small'>One-time login link: <a id='oneLink' href='/one_time_login?token={token}' target='_blank'>/one_time_login?token={token}</a></p>
                <div style='margin-top:12px'><button onclick='window.print()'>Print Card</button></div>
            </div>
            <script src='https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js'></script>
            <script>
                const oneLink = '/one_time_login?token={token}';
                const full = window.location.origin + oneLink;
                new QRCode(document.getElementById('qrcode'), {text: full, width:200, height:200});
            </script>
        </body>
        </html>
        """
        return html


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)