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
import json
import base64
from datetime import datetime, timedelta
from typing import Optional

import jwt
from passlib.hash import pbkdf2_sha256 as pwd_hasher
from werkzeug.utils import secure_filename
from flask import Flask, request, jsonify, g, send_from_directory, Response
from flask_cors import CORS
from cryptography.fernet import Fernet

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

# Encryption key for medical history (generate with Fernet.generate_key() and store securely)
# In production, store this in environment variables or secure vault
ENCRYPTION_KEY = os.environ.get("MEDICAL_HISTORY_KEY")
if not ENCRYPTION_KEY:
    # Generate a key for development (store this securely in production!)
    ENCRYPTION_KEY = base64.urlsafe_b64encode(JWT_SECRET.encode().ljust(32)[:32])
else:
    ENCRYPTION_KEY = ENCRYPTION_KEY.encode()

fernet = Fernet(ENCRYPTION_KEY)


def encrypt_medical_history(plaintext: str) -> str:
    """Encrypt medical history data."""
    if not plaintext:
        return ""
    try:
        encrypted = fernet.encrypt(plaintext.encode())
        return base64.urlsafe_b64encode(encrypted).decode()
    except Exception as e:
        print(f"Encryption error: {e}")
        return ""


def decrypt_medical_history(ciphertext: str) -> str:
    """Decrypt medical history data."""
    if not ciphertext:
        return ""
    try:
        encrypted = base64.urlsafe_b64decode(ciphertext.encode())
        decrypted = fernet.decrypt(encrypted)
        return decrypted.decode()
    except Exception as e:
        print(f"Decryption error: {e}")
        return "[Encrypted data - unable to decrypt]"


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
        print("GEMINI_API_KEY:", self.api_key)
        print("HAS_GENAI:", HAS_GENAI)
        print("Client:", self.client)
        print("Model:", self.model)

        self.critical_keywords = [
            "chest pain", "difficulty breathing", "severe bleeding",
            "unconscious", "fainting", "loss of consciousness",
            "severe pain", "suicidal", "heart attack", "stroke",
            "emergency", "can't breathe", "paralysis", "confusion",
            "high fever", "seizure", "allergic reaction", "swelling",
        ]

        self.system_prompt = (
            "You are a knowledgeable and empathetic AI medical assistant. Your role is to:\n"
            "1. Provide clear, evidence-based health information in simple language\n"
            "2. Help patients understand symptoms and when to seek professional care\n"
            "3. Offer general guidance on medications, lifestyle, and wellness\n"
            "4. Be supportive and non-judgmental, especially for sensitive health topics\n"
            "5. Always prioritize patient safety — escalate emergencies immediately\n\n"
            "Guidelines:\n"
            "- Use a warm, conversational tone while remaining professional\n"
            "- Break down complex medical concepts into easy-to-understand terms\n"
            "- Ask clarifying questions when needed to better understand the patient's situation\n"
            "- Provide actionable advice when appropriate (e.g., home care tips, when to see a doctor)\n"
            "- Always include a disclaimer that you're not replacing professional medical advice\n"
            "- For emergencies, immediately direct patients to call emergency services\n"
            "- Be culturally sensitive and avoid making assumptions about patients' backgrounds or beliefs\n\n"
            "Remember: You're here to inform and support, not to diagnose or prescribe."
        )

    def generate_response(self, user_input: str, patient_info: Optional[dict] = None, session_id: Optional[int] = None):
        """Generate response for the given user input."""
        # Basic sanitization and length limiting
        if not isinstance(user_input, str):
            return "I'm sorry — I could not understand your message."
        text = user_input.strip()
        if len(text) > 4000:
            text = text[:4000]

        if self.check_critical_condition(text):
            return self._emergency_message(patient_info)

        # Decrypt medical history if present for AI context
        decrypted_history = ""
        if patient_info and patient_info.get('medicalHistory'):
            patient_info = patient_info.copy()
            decrypted_history = decrypt_medical_history(patient_info['medicalHistory'])
            patient_info['medicalHistory'] = decrypted_history
        
        # Build patient context for personalized responses
        patient_context = ""
        if patient_info:
            patient_context = f"\n\nPatient Profile:"
            if patient_info.get('fullName'):
                patient_context += f"\n- Name: {patient_info['fullName']}"
            if patient_info.get('age'):
                patient_context += f"\n- Age: {patient_info['age']}"
            if patient_info.get('gender'):
                patient_context += f"\n- Gender: {patient_info['gender']}"
            if decrypted_history:
                patient_context += f"\n- Medical History: {decrypted_history}"
            if patient_info.get('task'):
                patient_context += f"\n- Current Concern: {patient_info['task']}"
        
        # Fetch conversation history for context and learning
        conversation_history = ""
        if session_id:
            try:
                db = sqlite3.connect(DB_PATH)
                db.row_factory = sqlite3.Row
                cur = db.cursor()
                # Get last 10 messages for context
                cur.execute(
                    "SELECT role, content FROM messages WHERE session_id = ? ORDER BY timestamp DESC LIMIT 10",
                    (session_id,)
                )
                messages = cur.fetchall()
                db.close()
                
                if messages:
                    conversation_history = "\n\nRecent Conversation History:"
                    # Reverse to show chronological order
                    for msg in reversed(messages):
                        role = "Patient" if msg['role'] == 'user' else "Assistant"
                        conversation_history += f"\n{role}: {msg['content'][:200]}"  # Limit each message to 200 chars
            except Exception as e:
                print(f"Error fetching conversation history: {e}")
        
        # Build comprehensive prompt with context
        prompt = f"{self.system_prompt}{patient_context}{conversation_history}\n\nPatient's Current Question: {text}\n\nAssistant (provide a personalized response based on the patient's profile and conversation history):"

        # If genai client is not available, return a fallback message
        if not self.client:
            fallback = (
                "(Prototype mode - no model client configured) "
                "I can help with general health information. Please consult a healthcare professional for a diagnosis."
            )
            return fallback

        try:
            contents = [
                types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
            ]

            response_text = ""
            for chunk in self.client.models.generate_content_stream(
                model=self.model,
                contents=contents,
            ):
                chunk_text = getattr(chunk, "text", "")
                if chunk_text:
                    response_text += chunk_text

            if response_text:
                disclaimer = (
                    "\n\n⚠️ Disclaimer: This is not a substitute for professional medical advice. "
                    "Please consult with a healthcare professional for diagnosis and treatment."
                )
                return response_text + disclaimer
            return response_text
        except Exception as e:
            return f"I'm sorry — an internal error occurred: {str(e)}"

    def check_critical_condition(self, text: str) -> bool:
        """Check if the input contains critical keywords."""
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in self.critical_keywords)

    def generate_response_stream(self, user_input: str, patient_info: Optional[dict] = None, session_id: Optional[int] = None):
        """Generate streaming response for thinking mode."""
        # Basic sanitization and length limiting
        if not isinstance(user_input, str):
            yield {"error": "Invalid input"}
            return
        text = user_input.strip()
        if len(text) > 4000:
            text = text[:4000]

        if self.check_critical_condition(text):
            emergency_msg = self._emergency_message(patient_info)
            yield {"content": emergency_msg, "emergency": True}
            return

        # Decrypt medical history if present for AI context
        decrypted_history = ""
        if patient_info and patient_info.get('medicalHistory'):
            patient_info = patient_info.copy()
            decrypted_history = decrypt_medical_history(patient_info['medicalHistory'])
            patient_info['medicalHistory'] = decrypted_history
        
        # Build patient context for personalized responses
        patient_context = ""
        if patient_info:
            patient_context = f"\n\nPatient Profile:"
            if patient_info.get('fullName'):
                patient_context += f"\n- Name: {patient_info['fullName']}"
            if patient_info.get('age'):
                patient_context += f"\n- Age: {patient_info['age']}"
            if patient_info.get('gender'):
                patient_context += f"\n- Gender: {patient_info['gender']}"
            if decrypted_history:
                patient_context += f"\n- Medical History: {decrypted_history}"
            if patient_info.get('task'):
                patient_context += f"\n- Current Concern: {patient_info['task']}"
        
        # Fetch conversation history for context and learning
        conversation_history = ""
        if session_id:
            try:
                db = sqlite3.connect(DB_PATH)
                db.row_factory = sqlite3.Row
                cur = db.cursor()
                # Get last 10 messages for context
                cur.execute(
                    "SELECT role, content FROM messages WHERE session_id = ? ORDER BY timestamp DESC LIMIT 10",
                    (session_id,)
                )
                messages = cur.fetchall()
                db.close()
                
                if messages:
                    conversation_history = "\n\nRecent Conversation History:"
                    # Reverse to show chronological order
                    for msg in reversed(messages):
                        role = "Patient" if msg['role'] == 'user' else "Assistant"
                        conversation_history += f"\n{role}: {msg['content'][:200]}"  # Limit each message to 200 chars
            except Exception as e:
                print(f"Error fetching conversation history: {e}")
        
        # Build comprehensive prompt with context
        prompt = f"{self.system_prompt}{patient_context}{conversation_history}\n\nPatient's Current Question: {text}\n\nAssistant (provide a personalized response based on the patient's profile and conversation history):"

        # If genai client is not available, return a fallback message
        if not self.client:
            fallback = (
                "(Prototype mode - no model client configured) "
                "I can help with general health information. Please consult a healthcare professional for a diagnosis."
            )
            yield {"content": fallback}
            return

        try:
            contents = [
                types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
            ]

            response_text = ""
            for chunk in self.client.models.generate_content_stream(
                model=self.model,
                contents=contents,
            ):
                chunk_text = getattr(chunk, "text", "")
                if chunk_text:
                    response_text += chunk_text
                    # Clean up markdown formatting
                    clean_chunk = re.sub(r'^[#*\s]+', '', chunk_text)
                    clean_chunk = re.sub(r'\*\*\*', '', clean_chunk)
                    if clean_chunk.strip():
                        yield {"content": clean_chunk}

            if response_text:
                disclaimer = (
                    "\n\n⚠️ Disclaimer: This is not a substitute for professional medical advice. "
                    "Please consult with a healthcare professional for diagnosis and treatment."
                )
                yield {"content": disclaimer}

        except Exception as e:
            yield {"error": f"I'm sorry — an internal error occurred: {str(e)}"}

    def _emergency_message(self, patient_info: Optional[dict] = None) -> str:
        # Provide a calm, actionable message and local emergency number hint
        emergency_number = "911"
        if patient_info and isinstance(patient_info, dict):
            locale = patient_info.get("locale") or patient_info.get("country")
            if locale:
                locale = locale.lower()
                mapping = {"us": "911", "ke": "+254 112", "uk": "999", "in": "112"}
                emergency_number = mapping.get(locale[:2], emergency_number)

        return (
            "I may be concerned by what you described, and your safety is important. "
            f"If you think you are in immediate danger, please call emergency services ({emergency_number}) or go to the nearest emergency room.\n\n"
            "I've prepared an option to connect you with a clinician — would you like me to notify them now? "
            "If this is life‑threatening, do not wait for an online response; call local emergency services immediately."
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
            is_private INTEGER DEFAULT 0,
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
    # Add profile columns to users for patient information
    try:
        cur.execute("ALTER TABLE users ADD COLUMN full_name TEXT")
        cur.execute("ALTER TABLE users ADD COLUMN age TEXT")
        cur.execute("ALTER TABLE users ADD COLUMN gender TEXT")
        cur.execute("ALTER TABLE users ADD COLUMN contact TEXT")
        cur.execute("ALTER TABLE users ADD COLUMN medical_history TEXT")
    except sqlite3.OperationalError:
        # columns likely already exist
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
        try:
            token = auth.split(None, 1)[1]
            payload = decode_jwt(token)
            if payload:
                db = get_db()
                cur = db.cursor()
                cur.execute("SELECT id, username, role, profession FROM users WHERE id = ?", (payload.get('sub'),))
                row = cur.fetchone()
                if row:
                    return dict(row)
        except Exception:
            pass

    # X-API-KEY check
    ok, msg = check_api_key(request)
    if ok:
        return {"username": "dev", "role": "dev", "id": 9999}
        
    # DEMO MODE: If no valid auth found, return a default 'super' user who can do everything
    # This effectively disables real auth blocks for the presentation
    db = get_db()
    cur = db.cursor()
    # Check if a demo user exists, if not create one
    cur.execute("SELECT id, username, role FROM users WHERE username = 'demo_user'")
    row = cur.fetchone()
    if row:
        return dict(row)
    else:
        # Create on the fly
        try:
            cur.execute("INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                        ('demo_user', 'demo', 'dev', datetime.utcnow().isoformat()))
            db.commit()
            return {"username": "demo_user", "role": "dev", "id": cur.lastrowid}
        except Exception:
            # Fallback for race conditions or locking
            return {"username": "demo_super", "role": "dev", "id": 8888}


@app.teardown_appcontext
def close_db(exc):
    db = getattr(g, "db", None)
    if db is not None:
        db.close()

@app.route("/")
def serve_index():
    proj_dir = os.path.dirname(__file__)
    index_path = os.path.join(proj_dir, "index.html")
    if os.path.exists(index_path):
        return send_from_directory(proj_dir, "index.html")
    return jsonify({"error": "index.html not found"}), 404
    """Serve a simple index page."""
    return "<h1>Medical AI Assistant Backend</h1><p>The backend is running.</p>"

@app.route("/auth")
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


@app.route('/profile.html')
def serve_profile_static():
    project_dir = os.path.dirname(__file__)
    profile_path = os.path.join(project_dir, "profile.html")
    if os.path.exists(profile_path):
        return send_from_directory(project_dir, "profile.html")
    return jsonify({"error": "profile.html not found"}), 404

@app.route('/admin')
@app.route('/admin.html')
def serve_admin():
    """Serve admin.html (Reserved). Optionally restrict by role at the page level."""
    project_dir = os.path.dirname(__file__)
    admin_path = os.path.join(project_dir, "admin.html")
    if os.path.exists(admin_path):
        return send_from_directory(project_dir, "admin.html")
    return jsonify({"error": "admin.html not found"}), 404
    
    
@app.route('/chat', methods=['POST'])
def chat():
    # Allow anonymous posting so patients aren't forced to re-authenticate for each prompt.
    # `current_user` may be None when the client didn't provide a JWT.
    current_user = get_current_user()

    payload = request.get_json() or {}
    message = payload.get('message')
    patient_info = payload.get('patient_info', {})
    session_id = payload.get('session_id')
    is_private = 1 if payload.get('is_private') else 0

    if not message:
        return jsonify({'error': 'Missing message'}), 400

    db = get_db()
    cur = db.cursor()

    # Create session if none
    if not session_id:
        # Link session to patient user if current_user is a patient
        patient_user_id = None
        if current_user and current_user.get('role') == 'patient' and current_user.get('id'):
            patient_user_id = current_user.get('id')

        encrypted_history = encrypt_medical_history(patient_info.get("medicalHistory") or "")
        cur.execute(
            "INSERT INTO sessions (patient_user_id, patient_name, age, gender, contact, medical_history, task, locale, is_private, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                patient_user_id,
                patient_info.get("fullName"),
                patient_info.get("age"),
                patient_info.get("gender"),
                patient_info.get("contact"),
                encrypted_history,
                patient_info.get("task"),
                patient_info.get("locale"),
                is_private,
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

    # Fetch session data to get medical history and patient details
    cur.execute("SELECT patient_name, age, gender, medical_history, task FROM sessions WHERE id = ?", (session_id,))
    session_row = cur.fetchone()
    if session_row:
        session_data = dict(session_row)
        # Merge session data with patient_info for comprehensive context
        if not patient_info:
            patient_info = {}
        patient_info['fullName'] = patient_info.get('fullName') or session_data.get('patient_name')
        patient_info['age'] = patient_info.get('age') or session_data.get('age')
        patient_info['gender'] = patient_info.get('gender') or session_data.get('gender')
        patient_info['medicalHistory'] = patient_info.get('medicalHistory') or session_data.get('medical_history')
        patient_info['task'] = patient_info.get('task') or session_data.get('task')

    # Generate response with session context (may return fallback if model not configured)
    reply_text = assistant.generate_response(message, patient_info, session_id)

    cur.execute(
        "INSERT INTO messages (session_id, role, content, emergency, timestamp) VALUES (?, ?, ?, ?, ?)",
        (session_id, "assistant", reply_text, 0, datetime.utcnow().isoformat()),
    )
    db.commit()

    reply_html = "<div>" + (reply_text.replace("\n", "<br>")) + "</div>"
    return jsonify({"reply_text": reply_text, "reply_html": reply_html, "emergency": False, "session_id": session_id})


@app.route('/chat/stream', methods=['POST'])
def chat_stream():
    """Streaming chat endpoint for thinking mode."""
    # Allow anonymous posting so patients aren't forced to re-authenticate for each prompt.
    current_user = get_current_user()

    payload = request.get_json() or {}
    message = payload.get('message')
    patient_info = payload.get('patient_info', {})
    session_id = payload.get('session_id')

    if not message:
        return Response('data: {"error": "Missing message"}\n\n', mimetype='text/event-stream')

    db = get_db()
    cur = db.cursor()

    # Create session if none
    if not session_id:
        # Link session to patient user if current_user is a patient
        patient_user_id = None
        if current_user and current_user.get('role') == 'patient' and current_user.get('id'):
            patient_user_id = current_user.get('id')

        encrypted_history = encrypt_medical_history(patient_info.get("medicalHistory") or "")
        cur.execute(
            "INSERT INTO sessions (patient_user_id, patient_name, age, gender, contact, medical_history, task, locale, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                patient_user_id,
                patient_info.get("fullName"),
                patient_info.get("age"),
                patient_info.get("gender"),
                patient_info.get("contact"),
                encrypted_history,
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

    def generate():
        full_response = ""
        emergency_detected = False

        try:
            # Fetch session data for patient context
            cur.execute("SELECT patient_name, age, gender, medical_history, task FROM sessions WHERE id = ?", (session_id,))
            session_row = cur.fetchone()
            session_patient_info = patient_info.copy() if patient_info else {}
            if session_row:
                session_data = dict(session_row)
                session_patient_info['fullName'] = session_patient_info.get('fullName') or session_data.get('patient_name')
                session_patient_info['age'] = session_patient_info.get('age') or session_data.get('age')
                session_patient_info['gender'] = session_patient_info.get('gender') or session_data.get('gender')
                session_patient_info['medicalHistory'] = session_patient_info.get('medicalHistory') or session_data.get('medical_history')
                session_patient_info['task'] = session_patient_info.get('task') or session_data.get('task')
            
            for chunk in assistant.generate_response_stream(message, session_patient_info, session_id):
                if "error" in chunk:
                    yield f"data: {json.dumps(chunk)}\n\n"
                    break
                elif "content" in chunk:
                    full_response += chunk["content"]
                    if chunk.get("emergency"):
                        emergency_detected = True
                    yield f"data: {json.dumps(chunk)}\n\n"

            # Save the complete response to database
            cur.execute(
                "INSERT INTO messages (session_id, role, content, emergency, timestamp) VALUES (?, ?, ?, ?, ?)",
                (session_id, "assistant", full_response, 1 if emergency_detected else 0, datetime.utcnow().isoformat()),
            )
            db.commit()

            # Send session info
            yield f"data: {json.dumps({'session_id': session_id})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

        yield "data: [DONE]\n\n"

    return Response(generate(), mimetype='text/event-stream')


@app.route("/doctor/alerts", methods=["GET"])
def doctor_alerts():
    current_user = get_current_user()
    if not current_user:
        return jsonify({"error": "Unauthorized"}), 401
    # Check removed to allow demo user full access
    # if current_user.get('role') != 'doctor' and current_user.get('role') != 'dev':
    #     return jsonify({"error": "Forbidden"}), 403

    db = get_db()
    cur = db.cursor()
    # DEMO: Show ALL emergency alerts regardless of privacy
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

        # Encrypt medical history before storing
        encrypted_history = encrypt_medical_history(medical_history or "")
        
        # create an initial session for the patient with provided profile info
        cur.execute(
            "INSERT INTO sessions (patient_user_id, patient_name, age, gender, contact, medical_history, task, locale, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                full_name,
                age,
                gender,
                contact,
                encrypted_history,
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


@app.route('/my_sessions', methods=['GET'])
def my_sessions():
    """Return a list of sessions for the current authenticated patient.

    If the user is not authenticated as a patient, return an empty list.
    """
    current_user = get_current_user()
    if not current_user or current_user.get('role') not in ('patient', 'dev'):
        return jsonify({'sessions': []})

    db = get_db()
    cur = db.cursor()
    # dev can see all sessions; patient sees their own
    if current_user.get('role') == 'dev':
        cur.execute("SELECT id, patient_name, task, created_at FROM sessions ORDER BY created_at DESC LIMIT 200")
    else:
        cur.execute("SELECT id, patient_name, task, created_at FROM sessions WHERE patient_user_id = ? ORDER BY created_at DESC", (current_user.get('id'),))
    rows = cur.fetchall()
    sessions = [dict(r) for r in rows]
    return jsonify({'sessions': sessions})


@app.route('/sessions', methods=['POST'])
def create_session():
    """Create a new session explicitly. Expects JSON: patient_info (optional), task/category (optional), is_private (optional).

    Returns: { session_id }
    """
    current_user = get_current_user()
    data = request.get_json() or {}
    patient_info = data.get('patient_info') or {}
    task = data.get('task') or patient_info.get('task')
    is_private = 1 if data.get('is_private') else 0  # 1 = unmerged/private, 0 = merged/visible to doctors

    db = get_db()
    cur = db.cursor()

    patient_user_id = None
    if current_user and current_user.get('role') == 'patient' and current_user.get('id'):
        patient_user_id = current_user.get('id')

    encrypted_history = encrypt_medical_history(patient_info.get('medicalHistory') or patient_info.get('medical_history') or "")
    cur.execute(
        "INSERT INTO sessions (patient_user_id, patient_name, age, gender, contact, medical_history, task, locale, is_private, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            patient_user_id,
            patient_info.get('fullName') or patient_info.get('full_name'),
            patient_info.get('age'),
            patient_info.get('gender'),
            patient_info.get('contact'),
            encrypted_history,
            task,
            patient_info.get('locale'),
            is_private,
            datetime.utcnow().isoformat(),
        ),
    )
    sid = cur.lastrowid
    db.commit()
    return jsonify({'session_id': sid})


@app.route('/claim_session', methods=['POST'])
def claim_session():
    """Allow a clinician to claim/associate an existing session with a patient account.

    Request JSON: { session_id: int, patient_id?: int, username?: str }
    Only callable by users with role 'doctor' or 'dev'.
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401
    if current_user.get('role') not in ('doctor', 'dev'):
        return jsonify({'error': 'Forbidden'}), 403

    data = request.get_json() or {}
    session_id = data.get('session_id')
    patient_id = data.get('patient_id')
    username = data.get('username')

    if not session_id or (not patient_id and not username):
        return jsonify({'error': 'session_id and patient_id or username required'}), 400

    db = get_db()
    cur = db.cursor()

    # Resolve username if provided
    if not patient_id and username:
        cur.execute('SELECT id FROM users WHERE username = ? AND role = ?', (username, 'patient'))
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'patient username not found'}), 404
        patient_id = row[0]

    # Ensure session exists
    cur.execute('SELECT id FROM sessions WHERE id = ?', (session_id,))
    if not cur.fetchone():
        return jsonify({'error': 'session not found'}), 404

    # Update session to associate with patient
    cur.execute('UPDATE sessions SET patient_user_id = ? WHERE id = ?', (patient_id, session_id))

    # Insert audit entry for traceability
    details = f'claimed session {session_id} for patient {patient_id} by clinician {current_user.get("username") or current_user.get("id")} '
    cur.execute('INSERT INTO audit (actor_id, action, target_id, details, timestamp) VALUES (?, ?, ?, ?, ?)',
                (current_user.get('id'), 'claim_session', session_id, details, datetime.utcnow().isoformat()))
    db.commit()

    return jsonify({'status': 'ok', 'session_id': session_id, 'patient_id': patient_id})


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


@app.route('/profile', methods=['GET', 'POST'])
def profile():
    """GET returns current user's profile (patients). POST updates the profile.

    GET: requires authenticated user (patient). Returns stored profile fields.
    POST: accepts JSON { full_name, age, gender, contact, medical_history } and saves them for the user.
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401

    db = get_db()
    cur = db.cursor()

    if request.method == 'GET':
        # Get user ID from current_user
        user_id = current_user.get('id') or current_user.get('sub')
        if not user_id:
             return jsonify({'error': 'Unauthorized - No User ID'}), 401

        cur.execute('SELECT id, username, role, full_name, age, gender, contact, medical_history, created_at FROM users WHERE id = ?', (user_id,))
        row = cur.fetchone()
        
        if not row:
            return jsonify({'error': 'Profile not found'}), 404
            
        profile_data = dict(row)
        # Decrypt medical history before sending to patient/doctor
        if profile_data.get('medical_history'):
            profile_data['medical_history'] = decrypt_medical_history(profile_data['medical_history'])
        return jsonify(profile_data)

    # POST: update profile
    data = request.get_json() or {}
    full_name = data.get('full_name') or data.get('fullName')
    age = data.get('age')
    gender = data.get('gender')
    contact = data.get('contact')
    medical_history = data.get('medical_history') or data.get('medicalHistory')

    # ensure we have a user id
    uid = current_user.get('id') or current_user.get('sub')
    if not uid:
        auth = request.headers.get('Authorization')
        print('Profile POST: Authorization header:', auth)
        if auth and auth.lower().startswith('bearer '):
            token = auth.split(None, 1)[1]
            payload = decode_jwt(token)
            print('Profile POST: Decoded payload:', payload)
            uid = payload.get('sub') if payload else None
    print('Profile POST: Final uid:', uid)
    if not uid:
        print('Profile POST: Unauthorized error, could not resolve user id.')
        return jsonify({'error': 'Unauthorized'}), 401

    encrypted_history = encrypt_medical_history(medical_history or "")
    
    try:
        cur.execute('UPDATE users SET full_name = ?, age = ?, gender = ?, contact = ?, medical_history = ? WHERE id = ?',
                    (full_name, age, gender, contact, encrypted_history, uid))
        db.commit()
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': f'Failed to update profile: {str(e)}'}), 500



@app.route('/one_time_login')
def one_time_login():
    token = request.args.get('token')
    if not token:
        return jsonify({'error': 'token query param required'}), 400

    import json
    token_js = json.dumps(token)

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
                const token = {token_js};
                async function consume(){{
                    try{{
                        const resp = await fetch('/one_time_consume', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{token}})}});
                        const j = await resp.json();
                        if(!resp.ok){{ document.getElementById('status').textContent = 'Login failed: ' + (j.error || resp.statusText); return }}
                        sessionStorage.setItem('jwt_token', j.token);
                        sessionStorage.setItem('user_role', j.role || 'patient');
                        document.getElementById('status').textContent = 'Signed in. Redirecting…';
                        window.location.href = '/dashboard.html';
                    }}catch(e){{ document.getElementById('status').textContent = 'Network error'; }}
                }}
                document.getElementById('btn').addEventListener('click', consume);
                consume();
            </script>
        </body>
        </html>
        """
    return html


@app.route('/admin/users', methods=['GET'])
def admin_users():
    current_user = get_current_user()
    if not current_user: # or current_user.get('role') != 'dev':
        return jsonify({'error': 'Forbidden - Admin access required'}), 403
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT id, username, role, profession, created_at FROM users ORDER BY created_at DESC')
    rows = cur.fetchall()
    users = [dict(r) for r in rows]
    return jsonify({'users': users})


@app.route('/admin/sessions', methods=['GET'])
def admin_sessions():
    current_user = get_current_user()
    if not current_user or current_user.get('role') != 'dev':
        return jsonify({'error': 'Forbidden - Admin access required'}), 403
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT id, patient_name, task, created_at, patient_user_id FROM sessions ORDER BY created_at DESC LIMIT 500')
    rows = cur.fetchall()
    sessions = [dict(r) for r in rows]
    return jsonify({'sessions': sessions})


@app.route('/admin/delete_user', methods=['POST'])
def admin_delete_user():
    current_user = get_current_user()
    if not current_user or current_user.get('role') != 'dev':
        return jsonify({'error': 'Forbidden - Admin access required'}), 403
    data = request.get_json() or {}
    uid = data.get('user_id')
    if not uid:
        return jsonify({'error': 'user_id required'}), 400
    db = get_db()
    cur = db.cursor()
    cur.execute('DELETE FROM users WHERE id = ?', (uid,))
    db.commit()
    return jsonify({'status': 'ok'})


@app.route('/setup/create_dev', methods=['POST'])
def setup_create_dev():
    """Dev-only helper to create a 'dev' user. Protected by X-API-KEY == DEV_API_KEY.

    Request JSON: { username: str, password: str }
    This route is intended only for local/dev bootstrapping and should be removed
    or disabled in production.
    """
    ok, msg = check_api_key(request)
    if not ok:
        return jsonify({'error': 'forbidden'}), 403

    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({'error': 'username and password required'}), 400

    pw_hash = pwd_hasher.hash(password)
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                    (username, pw_hash, 'dev', datetime.utcnow().isoformat()))
        db.commit()
        return jsonify({'status': 'ok', 'username': username})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'username exists'}), 400


@app.route('/emergency_alert', methods=['POST'])
def emergency_alert():
    """Create an emergency alert for the current session and notify clinicians.

    Expected JSON body: { session_id?: int, patient_info?: dict }
    This is a lightweight prototype: it inserts an emergency message and audit entry
    that clinician UIs can poll via `/doctor/alerts`.
    """
    data = request.get_json() or {}
    session_id = data.get('session_id')
    patient_info = data.get('patient_info', {})

    db = get_db()
    cur = db.cursor()

    # If no session exists yet, create a minimal session record
    if not session_id:
        cur.execute(
            "INSERT INTO sessions (patient_name, age, gender, contact, medical_history, task, locale, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                patient_info.get('fullName'),
                patient_info.get('age'),
                patient_info.get('gender'),
                patient_info.get('contact'),
                patient_info.get('medicalHistory'),
                patient_info.get('task'),
                patient_info.get('locale'),
                datetime.utcnow().isoformat(),
            ),
        )
        session_id = cur.lastrowid

    # Insert a system message marking emergency so doctors see it in alerts
    content = 'Patient has requested an emergency chat. Clinician alerted.'
    cur.execute(
        "INSERT INTO messages (session_id, role, content, emergency, timestamp) VALUES (?, ?, ?, ?, ?)",
        (session_id, 'system', content, 1, datetime.utcnow().isoformat()),
    )

    # audit entry
    details = 'emergency_alert created via patient UI'
    cur.execute(
        "INSERT INTO audit (actor_id, action, target_id, details, timestamp) VALUES (?, ?, ?, ?, ?)",
        (None, 'emergency_alert', session_id, details, datetime.utcnow().isoformat()),
    )

    db.commit()

    # Prototype response: confirm to patient that clinicians have been notified
    return jsonify({
        'status': 'ok',
        'session_id': session_id,
        'message': 'A clinician has been notified and will review your session shortly. If you are in immediate danger, call local emergency services.'
    })


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

    import json
    one_link = f"/one_time_login?token={token}"
    one_link_js = json.dumps(one_link)

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
            const oneLink = {one_link_js};
            const full = window.location.origin + oneLink;
            new QRCode(document.getElementById('qrcode'), {{text: full, width:200, height:200}});
        </script>
    </body>
    </html>
    """
    return html


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)