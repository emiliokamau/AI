"""Flask-based prototype backend for the Medical AI Assistant.

This file exposes a simple HTTP API the `dashboard.html` frontend can call.
It uses the existing PatientAIAssistant logic and adds MySQL persistence,
basic token auth, CORS for local testing, and endpoints for doctor alerts.

Notes:
- Requires environment variables: GEMINI_API_KEY (for Google GenAI) and DEV_API_KEY (simple header token for prototype).
- Install dependencies with `pip install -r requirements.txt`.
"""

import os
import re
from db import db_connect, get_db, init_db, IntegrityError
import time
import threading
import json
import base64
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
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
        print("GEMINI_API_KEY set:", bool(self.api_key))
        print("HAS_GENAI:", HAS_GENAI)
        print("Client:", bool(self.client))
        print("Model:", self.model)

        self.critical_keywords = [
            "chest pain", "difficulty breathing", "severe bleeding",
            "unconscious", "fainting", "loss of consciousness",
            "severe pain", "suicidal", "heart attack", "stroke",
            "emergency", "can't breathe", "paralysis", "confusion",
            "high fever", "seizure", "allergic reaction", "swelling",
        ]
        
        # Medical database mappings (simplified ICD-10 and SNOMED CT)
        self.medical_codes = {
            'fever': {'icd10': 'R50.9', 'snomed': '386661006', 'term': 'Fever'},
            'headache': {'icd10': 'R51', 'snomed': '25064002', 'term': 'Headache'},
            'cough': {'icd10': 'R05', 'snomed': '49727002', 'term': 'Cough'},
            'chest pain': {'icd10': 'R07.9', 'snomed': '29857009', 'term': 'Chest pain'},
            'shortness of breath': {'icd10': 'R06.00', 'snomed': '267036007', 'term': 'Dyspnea'},
            'abdominal pain': {'icd10': 'R10.9', 'snomed': '21522001', 'term': 'Abdominal pain'},
            'nausea': {'icd10': 'R11.0', 'snomed': '422587007', 'term': 'Nausea'},
            'vomiting': {'icd10': 'R11.10', 'snomed': '422400008', 'term': 'Vomiting'},
            'diarrhea': {'icd10': 'R19.7', 'snomed': '62315008', 'term': 'Diarrhea'},
            'fatigue': {'icd10': 'R53.83', 'snomed': '84229001', 'term': 'Fatigue'},
            'dizziness': {'icd10': 'R42', 'snomed': '404640003', 'term': 'Dizziness'},
            'diabetes': {'icd10': 'E11.9', 'snomed': '44054006', 'term': 'Diabetes mellitus type 2'},
            'hypertension': {'icd10': 'I10', 'snomed': '38341003', 'term': 'Hypertension'},
            'asthma': {'icd10': 'J45.909', 'snomed': '195967001', 'term': 'Asthma'},
            'depression': {'icd10': 'F32.9', 'snomed': '35489007', 'term': 'Depressive disorder'},
            'anxiety': {'icd10': 'F41.9', 'snomed': '48694002', 'term': 'Anxiety disorder'},
        }
        
        # Drug interaction database (simplified)
        self.drug_interactions = {
            'warfarin': {
                'dangerous': ['aspirin', 'ibuprofen', 'naproxen', 'vitamin k'],
                'warning': 'Warfarin has major interactions with NSAIDs and vitamin K. Increased bleeding risk.'
            },
            'aspirin': {
                'dangerous': ['warfarin', 'ibuprofen', 'alcohol'],
                'warning': 'Aspirin combined with blood thinners increases bleeding risk significantly.'
            },
            'metformin': {
                'dangerous': ['alcohol', 'iodinated contrast'],
                'warning': 'Metformin + alcohol or contrast can cause lactic acidosis.'
            },
            'ssri': {
                'dangerous': ['maoi', 'tramadol', 'warfarin'],
                'warning': 'SSRIs with MAOIs can cause serotonin syndrome. Use caution with blood thinners.'
            },
            'lisinopril': {
                'dangerous': ['potassium supplements', 'spironolactone', 'nsaids'],
                'warning': 'ACE inhibitors with potassium can cause hyperkalemia.'
            },
        }

        self.system_prompt = (
            "You are a knowledgeable and empathetic AI medical assistant. Your role is to:\n"
            "1. Provide clear, evidence-based health information in simple language\n"
            "2. Help patients understand symptoms and when to seek professional care\n"
            "3. Offer general guidance on medications, lifestyle, and wellness\n"
            "4. Be supportive and non-judgmental, especially for sensitive health topics\n"
            "5. Always prioritize patient safety — escalate emergencies immediately\n"
            "6. Ask context-aware follow-up questions to better understand the patient's condition\n"
            "7. Provide confidence scores for your assessments when appropriate\n"
            "8. Consider patient's medical history, age, and current medications in your responses\n\n"
            "Guidelines:\n"
            "- Use a warm, conversational tone while remaining professional\n"
            "- Break down complex medical concepts into easy-to-understand terms\n"
            "- Ask clarifying questions when needed to better understand the patient's situation\n"
            "- Provide actionable advice when appropriate (e.g., home care tips, when to see a doctor)\n"
            "- Always include a disclaimer that you're not replacing professional medical advice\n"
            "- For emergencies, immediately direct patients to call emergency services\n"
            "- Be culturally sensitive and avoid making assumptions about patients' backgrounds or beliefs\n"
            "- Generate personalized wellness recommendations based on patient data\n"
            "- Suggest lifestyle modifications when appropriate\n\n"
            "Remember: You're here to inform and support, not to diagnose or prescribe."
        )
    
    def detect_language(self, text: str) -> str:
        """Detect language of user input (simplified)."""
        # Common word patterns for quick detection
        spanish_patterns = ['hola', 'dolor', 'fiebre', 'síntomas', 'ayuda', 'gracias']
        french_patterns = ['bonjour', 'douleur', 'fièvre', 'symptômes', 'aide', 'merci']
        german_patterns = ['hallo', 'schmerz', 'fieber', 'symptome', 'hilfe', 'danke']
        swahili_patterns = ['habari', 'maumivu', 'homa', 'dalili', 'msaada', 'asante']
        arabic_patterns = ['مرحبا', 'ألم', 'حمى', 'أعراض', 'مساعدة', 'شكرا']
        
        text_lower = text.lower()
        
        if any(word in text_lower for word in spanish_patterns):
            return 'es'
        elif any(word in text_lower for word in french_patterns):
            return 'fr'
        elif any(word in text_lower for word in german_patterns):
            return 'de'
        elif any(word in text_lower for word in swahili_patterns):
            return 'sw'
        elif any(word in text for word in arabic_patterns):
            return 'ar'
        else:
            return 'en'  # Default to English
    
    def find_medical_codes(self, text: str) -> dict:
        """Find ICD-10 and SNOMED CT codes for symptoms/conditions mentioned."""
        text_lower = text.lower()
        found_codes = {}
        
        for condition, codes in self.medical_codes.items():
            if condition in text_lower:
                found_codes[condition] = codes
        
        return found_codes
    
    def check_drug_interactions(self, medications: list) -> dict:
        """Check for dangerous drug interactions."""
        interactions = []
        meds_lower = [m.lower() for m in medications if m]
        
        for med in meds_lower:
            if med in self.drug_interactions:
                for dangerous_med in self.drug_interactions[med]['dangerous']:
                    if any(dangerous_med in m for m in meds_lower):
                        interactions.append({
                            'drug1': med,
                            'drug2': dangerous_med,
                            'severity': 'high',
                            'warning': self.drug_interactions[med]['warning']
                        })
        
        return {'has_interactions': len(interactions) > 0, 'interactions': interactions}
    
    def generate_wellness_recommendations(self, patient_info: dict) -> list:
        """Generate personalized wellness recommendations based on patient data."""
        recommendations = []
        age = patient_info.get('age')
        medical_history = patient_info.get('medicalHistory', '').lower()
        
        # Age-based recommendations
        if age:
            if age < 18:
                recommendations.append({
                    'category': 'Sleep',
                    'recommendation': 'Aim for 8-10 hours of sleep per night for optimal growth and development.'
                })
            elif 18 <= age < 65:
                recommendations.append({
                    'category': 'Exercise',
                    'recommendation': 'Get at least 150 minutes of moderate aerobic activity per week.'
                })
            else:  # 65+
                recommendations.append({
                    'category': 'Mobility',
                    'recommendation': 'Include balance and flexibility exercises to prevent falls and maintain independence.'
                })
        
        # Condition-specific recommendations
        if 'diabetes' in medical_history:
            recommendations.append({
                'category': 'Diet',
                'recommendation': 'Monitor carbohydrate intake and maintain consistent meal times. Check blood sugar regularly.'
            })
        
        if 'hypertension' in medical_history or 'high blood pressure' in medical_history:
            recommendations.append({
                'category': 'Lifestyle',
                'recommendation': 'Reduce sodium intake to under 2,300mg/day. Practice stress-reduction techniques.'
            })
        
        if 'asthma' in medical_history:
            recommendations.append({
                'category': 'Environment',
                'recommendation': 'Avoid triggers like smoke, dust, and allergens. Keep rescue inhaler accessible.'
            })
        
        if 'anxiety' in medical_history or 'depression' in medical_history:
            recommendations.append({
                'category': 'Mental Health',
                'recommendation': 'Practice mindfulness or meditation. Maintain social connections and consider therapy.'
            })
        
        # General recommendations
        recommendations.append({
            'category': 'Nutrition',
            'recommendation': 'Eat a balanced diet rich in fruits, vegetables, whole grains, and lean proteins.'
        })
        
        recommendations.append({
            'category': 'Hydration',
            'recommendation': 'Drink 8 glasses (64 oz) of water daily. Adjust for activity level and climate.'
        })
        
        return recommendations[:5]  # Return top 5 recommendations
    
    def calculate_confidence_score(self, response_text: str, patient_context: str) -> int:
        """Calculate confidence score for AI assessment (0-100%)."""
        confidence = 75  # Base confidence
        
        # Increase confidence if patient provided detailed history
        if len(patient_context) > 200:
            confidence += 10
        
        # Increase if response includes specific medical terms
        medical_terms = ['diagnosis', 'treatment', 'symptoms', 'condition', 'medication']
        term_count = sum(1 for term in medical_terms if term in response_text.lower())
        confidence += min(term_count * 2, 10)
        
        # Decrease if response is vague or uncertain
        uncertainty_words = ['might', 'possibly', 'perhaps', 'could be', 'maybe']
        uncertainty_count = sum(1 for word in uncertainty_words if word in response_text.lower())
        confidence -= min(uncertainty_count * 5, 20)
        
        # Cap between 0-100
        return max(0, min(100, confidence))

    def lookup_icd10(self, query: str) -> list:
        """Lookup ICD-10 codes via external API if configured."""
        base_url = os.environ.get('ICD10_API_BASE')
        token = os.environ.get('ICD10_API_TOKEN')
        if not base_url or not token or not query:
            return []
        try:
            import requests
            resp = requests.get(
                f"{base_url.rstrip('/')}/icd10/search",
                params={"q": query},
                headers={"Authorization": f"Bearer {token}"},
                timeout=8,
            )
            if resp.status_code != 200:
                return []
            data = resp.json() or {}
            return data.get('results') or []
        except Exception:
            return []

    def lookup_snomed(self, query: str) -> list:
        """Lookup SNOMED CT terms via external API if configured."""
        base_url = os.environ.get('SNOMED_API_BASE')
        token = os.environ.get('SNOMED_API_TOKEN')
        if not base_url or not token or not query:
            return []
        try:
            import requests
            resp = requests.get(
                f"{base_url.rstrip('/')}/snomed/search",
                params={"q": query},
                headers={"Authorization": f"Bearer {token}"},
                timeout=8,
            )
            if resp.status_code != 200:
                return []
            data = resp.json() or {}
            return data.get('items') or data.get('results') or []
        except Exception:
            return []

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

        # Language detection
        language_code = self.detect_language(text)
        language_names = {
            'en': 'English',
            'es': 'Spanish',
            'fr': 'French',
            'de': 'German',
            'sw': 'Swahili',
            'ar': 'Arabic'
        }
        language_name = language_names.get(language_code, 'English')

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
                db = db_connect()
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
                        conversation_history += f"\n{role}: {msg['content'][:200]}"
            except Exception as e:
                print(f"Error fetching conversation history: {e}")

        # Extract medical codes for prompt context
        medical_codes = self.find_medical_codes(text)
        codes_context = ""
        if medical_codes:
            codes_context = "\n\nDetected Medical Codes:"
            for condition, codes in medical_codes.items():
                codes_context += f"\n- {condition.title()}: ICD-10 {codes['icd10']}, SNOMED {codes['snomed']}"

        # Build comprehensive prompt with context
        prompt = (
            f"{self.system_prompt}{patient_context}{conversation_history}{codes_context}\n\n"
            f"Patient's Current Question: {text}\n\n"
            f"Assistant: Respond in {language_name}. Use short paragraphs or bullet points. "
            "Do not use markdown symbols like *, #, _, or backticks. "
            "Ask 1-2 brief follow-up questions at the end."
        )

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
                    "\n\nDisclaimer: This is not a substitute for professional medical advice. "
                    "Please consult with a healthcare professional for diagnosis and treatment."
                )
                confidence = self.calculate_confidence_score(response_text, patient_context + conversation_history)
                confidence_level = "High" if confidence >= 80 else "Medium" if confidence >= 60 else "Low"
                confidence_text = f"\n\nConfidence score: {confidence}% ({confidence_level})"
                return sanitize_ai_text(response_text + disclaimer + confidence_text)
            return sanitize_ai_text(response_text)
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

        # Language detection
        language_code = self.detect_language(text)
        language_names = {
            'en': 'English',
            'es': 'Spanish',
            'fr': 'French',
            'de': 'German',
            'sw': 'Swahili',
            'ar': 'Arabic'
        }
        language_name = language_names.get(language_code, 'English')

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
                db = db_connect()
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
                        conversation_history += f"\n{role}: {msg['content'][:200]}"
            except Exception as e:
                print(f"Error fetching conversation history: {e}")

        # Extract medical codes for prompt context
        medical_codes = self.find_medical_codes(text)
        codes_context = ""
        if medical_codes:
            codes_context = "\n\nDetected Medical Codes:"
            for condition, codes in medical_codes.items():
                codes_context += f"\n- {condition.title()}: ICD-10 {codes['icd10']}, SNOMED {codes['snomed']}"

        # Build comprehensive prompt with context
        prompt = (
            f"{self.system_prompt}{patient_context}{conversation_history}{codes_context}\n\n"
            f"Patient's Current Question: {text}\n\n"
            f"Assistant: Respond in {language_name}. Use short paragraphs or bullet points. "
            "Do not use markdown symbols like *, #, _, or backticks. "
            "Ask 1-2 brief follow-up questions at the end."
        )

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
                    clean_chunk = chunk_text.replace("•", "-")
                    clean_chunk = re.sub(r"[*_`#]+", "", clean_chunk)
                    if clean_chunk.strip():
                        yield {"content": clean_chunk}

            if response_text:
                disclaimer = (
                    "\n\nDisclaimer: This is not a substitute for professional medical advice. "
                    "Please consult with a healthcare professional for diagnosis and treatment."
                )
                confidence = self.calculate_confidence_score(response_text, patient_context + conversation_history)
                confidence_level = "High" if confidence >= 80 else "Medium" if confidence >= 60 else "Low"
                confidence_text = f"\n\nConfidence score: {confidence}% ({confidence_level})"
                yield {"content": disclaimer + confidence_text}

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


def sanitize_ai_text(text: str) -> str:
    if not text:
        return ""
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = cleaned.replace("•", "-")
    cleaned = re.sub(r"[*_`#]+", "", cleaned)
    cleaned = re.sub(r"^[>\s]+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()




app = Flask(__name__)

# CORS Configuration: restrict to specific domains in production
cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:5000,https://mediai-lovat.vercel.app").split(",")
cors_origins = [origin.strip() for origin in cors_origins]  # Remove whitespace

CORS(
    app,
    origins=cors_origins,
    allow_headers=["Content-Type", "Authorization", "X-API-KEY"],
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    supports_credentials=True,
    max_age=3600,  # Cache preflight responses for 1 hour
    send_wildcard=False  # Don't send wildcard in production
)

# Session security configuration
app.config['SESSION_COOKIE_SECURE'] = os.environ.get("FLASK_ENV") == "production"
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
app.config['SESSION_REFRESH_EACH_REQUEST'] = True

assistant = PatientAIAssistant()
init_db()


@app.after_request
def add_security_headers(response):
    """Add comprehensive security headers for production."""
    is_production = os.environ.get("FLASK_ENV") == "production"
    
    # Force HTTPS in production (1 year, include subdomains, preload list)
    if is_production:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
    
    # Prevent MIME type sniffing
    response.headers['X-Content-Type-Options'] = 'nosniff'
    
    # Prevent clickjacking
    response.headers['X-Frame-Options'] = 'DENY'
    
    # Control referrer information
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    
    # Restrict browser APIs
    response.headers['Permissions-Policy'] = 'geolocation=(self), microphone=(), camera=(), payment=()'
    
    # Content Security Policy (restrictive by default)
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "img-src 'self' data: https:; "
        "font-src 'self' https://fonts.gstatic.com; "
        "connect-src 'self' https://maps.googleapis.com https://api.example.com; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self';"
    )
    response.headers['Content-Security-Policy'] = csp
    
    # Disable FLoC (Federated Learning of Cohorts)
    response.headers['Permissions-Policy'] = 'interest-cohort=()'
    
    # X-Powered-By disclosure (hide implementation details)
    response.headers.pop('Server', None)
    
    return response


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
                cur.execute("SELECT id, username, role, profession FROM users WHERE id = %s", (payload.get('sub'),))
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
            cur.execute("INSERT INTO users (username, password_hash, role, created_at) VALUES (%s, %s, %s, %s)",
                        ('demo_user', 'demo', 'dev', datetime.utcnow()))
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


@app.route('/hospital')
@app.route('/hospital.html')
def serve_hospital():
    """Serve hospital.html for hospital management."""
    project_dir = os.path.dirname(__file__)
    hospital_path = os.path.join(project_dir, "hospital.html")
    if os.path.exists(hospital_path):
        return send_from_directory(project_dir, "hospital.html")
    return jsonify({"error": "hospital.html not found"}), 404
    
    
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
            "INSERT INTO sessions (patient_user_id, patient_name, age, gender, contact, medical_history, task, locale, is_private, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
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
                datetime.utcnow(),
            ),
        )
        session_id = cur.lastrowid
        db.commit()

    # Insert user message
    emergency_flag = 1 if assistant.check_critical_condition(message) else 0
    cur.execute(
        "INSERT INTO messages (session_id, role, content, emergency, timestamp) VALUES (%s, %s, %s, %s, %s)",
        (session_id, "user", message, emergency_flag, datetime.utcnow()),
    )
    db.commit()

    # If emergency detected, short-circuit with emergency message
    if emergency_flag:
        reply = assistant._emergency_message(patient_info)
        cur.execute(
            "INSERT INTO messages (session_id, role, content, emergency, timestamp) VALUES (%s, %s, %s, %s, %s)",
            (session_id, "assistant", reply, 1, datetime.utcnow()),
        )
        db.commit()
        return jsonify({"reply_text": reply, "reply_html": "<div class=\"alert alert-danger\">" + reply + "</div>", "emergency": True, "session_id": session_id})

    # Fetch session data to get medical history and patient details
    cur.execute("SELECT patient_name, age, gender, medical_history, task FROM sessions WHERE id = %s", (session_id,))
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
        "INSERT INTO messages (session_id, role, content, emergency, timestamp) VALUES (%s, %s, %s, %s, %s)",
        (session_id, "assistant", reply_text, 0, datetime.utcnow()),
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
            "INSERT INTO sessions (patient_user_id, patient_name, age, gender, contact, medical_history, task, locale, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                patient_user_id,
                patient_info.get("fullName"),
                patient_info.get("age"),
                patient_info.get("gender"),
                patient_info.get("contact"),
                encrypted_history,
                patient_info.get("task"),
                patient_info.get("locale"),
                datetime.utcnow(),
            ),
        )
        session_id = cur.lastrowid
        db.commit()

    # Insert user message
    emergency_flag = 1 if assistant.check_critical_condition(message) else 0
    cur.execute(
        "INSERT INTO messages (session_id, role, content, emergency, timestamp) VALUES (%s, %s, %s, %s, %s)",
        (session_id, "user", message, emergency_flag, datetime.utcnow()),
    )
    db.commit()

    def generate():
        full_response = ""
        emergency_detected = False

        try:
            # Fetch session data for patient context
            cur.execute("SELECT patient_name, age, gender, medical_history, task FROM sessions WHERE id = %s", (session_id,))
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
                "INSERT INTO messages (session_id, role, content, emergency, timestamp) VALUES (%s, %s, %s, %s, %s)",
                (session_id, "assistant", full_response, 1 if emergency_detected else 0, datetime.utcnow()),
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
        cur.execute("INSERT INTO users (username, password_hash, role, profession, created_at, creator_id) VALUES (%s, %s, %s, %s, %s, %s)",
                    (username, pw_hash, 'patient', None, datetime.utcnow(), creator_id))
        user_id = cur.lastrowid

        # Encrypt medical history before storing
        encrypted_history = encrypt_medical_history(medical_history or "")
        
        # create an initial session for the patient with provided profile info
        cur.execute(
            "INSERT INTO sessions (patient_user_id, patient_name, age, gender, contact, medical_history, task, locale, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                user_id,
                full_name,
                age,
                gender,
                contact,
                encrypted_history,
                task,
                locale,
                datetime.utcnow(),
            ),
        )
        session_id = cur.lastrowid
        # create a one-time login token valid for 24 hours
        import secrets
        token = secrets.token_urlsafe(24)
        expires = datetime.utcnow() + timedelta(hours=24)
        cur.execute("INSERT INTO one_time_tokens (user_id, token, expires_at, used, created_at) VALUES (%s, %s, %s, %s, %s)",
            (user_id, token, expires, 0, datetime.utcnow()))
        # audit entry
        details = f"created patient user {username} (session {session_id})"
        cur.execute("INSERT INTO audit (actor_id, action, target_id, details, timestamp) VALUES (%s, %s, %s, %s, %s)",
            (creator_id, 'create_patient', user_id, details, datetime.utcnow()))
        db.commit()
        one_time_link = f"/one_time_login?token={token}"
        return jsonify({'user_id': user_id, 'username': username, 'session_id': session_id, 'one_time_link': one_time_link, 'one_time_token': token, 'one_time_expires': expires})
    except IntegrityError:
        return jsonify({'error': 'username already exists'}), 400


@app.route('/doctor/patients', methods=['GET'])
def doctor_list_patients():
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401
    db = get_db()
    cur = db.cursor()
    # For doctors and dev users, return all patients so messaging works across accounts
    if current_user.get('role') in ('doctor', 'dev'):
        cur.execute("SELECT id, username, full_name, created_at FROM users WHERE role = 'patient' ORDER BY created_at DESC")
    else:
        creator_id = current_user.get('id')
        cur.execute("SELECT id, username, full_name, created_at FROM users WHERE role = 'patient' AND creator_id = %s ORDER BY created_at DESC", (creator_id,))
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
        cur.execute('SELECT id, actor_id, action, target_id, details, timestamp FROM audit WHERE actor_id = %s ORDER BY timestamp DESC LIMIT 200', (current_user.get('id'),))
    rows = cur.fetchall()
    audits = [dict(r) for r in rows]
    return jsonify({'audit': audits})


@app.route('/my_sessions', methods=['GET'])
def my_sessions():
    """Return a list of sessions for the current authenticated patient with AI-generated titles.

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
        cur.execute("SELECT id, patient_name, task, created_at FROM sessions WHERE patient_user_id = %s ORDER BY created_at DESC", (current_user.get('id'),))
    rows = cur.fetchall()
    sessions = []
    
    for row in rows:
        session_dict = dict(row)
        session_id = session_dict['id']
        
        # Fetch messages for this session to generate title
        cur.execute("SELECT role, content FROM messages WHERE session_id = %s ORDER BY timestamp", (session_id,))
        messages = cur.fetchall()
        
        # Generate AI title if no title exists
        if not session_dict.get('task') or session_dict['task'] == 'general':
            session_dict['title'] = generate_session_title(messages)
        else:
            session_dict['title'] = session_dict['task']
        
        sessions.append(session_dict)
    
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
        "INSERT INTO sessions (patient_user_id, patient_name, age, gender, contact, medical_history, task, locale, is_private, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
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
            datetime.utcnow(),
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
        cur.execute('SELECT id FROM users WHERE username = %s AND role = %s', (username, 'patient'))
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'patient username not found'}), 404
        patient_id = row.get('id')

    # Ensure session exists
    cur.execute('SELECT id FROM sessions WHERE id = %s', (session_id,))
    if not cur.fetchone():
        return jsonify({'error': 'session not found'}), 404

    # Update session to associate with patient
    cur.execute('UPDATE sessions SET patient_user_id = %s WHERE id = %s', (patient_id, session_id))

    # Insert audit entry for traceability
    details = f'claimed session {session_id} for patient {patient_id} by clinician {current_user.get("username") or current_user.get("id")} '
    cur.execute('INSERT INTO audit (actor_id, action, target_id, details, timestamp) VALUES (%s, %s, %s, %s, %s)',
                (current_user.get('id'), 'claim_session', session_id, details, datetime.utcnow()))
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
        cur.execute("SELECT * FROM messages WHERE session_id = %s ORDER BY timestamp", (sid,))
        rows = cur.fetchall()
        messages = [dict(r) for r in rows]
        return jsonify({"messages": messages})

    # patient
    cur.execute("SELECT patient_user_id FROM sessions WHERE id = %s", (sid,))
    row = cur.fetchone()
    if not row:
        return jsonify({"error": "Session not found"}), 404
    if row.get('patient_user_id') != current_user.get('id'):
        return jsonify({"error": "Forbidden"}), 403

    cur.execute("SELECT * FROM messages WHERE session_id = %s ORDER BY timestamp", (sid,))
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
        cur.execute("INSERT INTO users (username, password_hash, role, profession, created_at) VALUES (%s, %s, %s, %s, %s)",
                (username, pw_hash, role, profession, datetime.utcnow()))
        db.commit()
        return jsonify({'status': 'ok'})
    except IntegrityError:
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
    cur.execute('SELECT id, password_hash, role FROM users WHERE username = %s', (username,))
    row = cur.fetchone()
    if not row:
        return jsonify({'error': 'invalid credentials'}), 401
    user_id = row.get('id')
    pw_hash = row.get('password_hash')
    role = row.get('role')
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
    cur.execute("INSERT INTO messages (session_id, role, content, emergency, timestamp) VALUES (%s, %s, %s, %s, %s)",
                (sid, 'doctor', survey_content, 0, datetime.utcnow()))
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
    cur.execute('SELECT id FROM sessions WHERE id = %s', (session_id,))
    if not cur.fetchone():
        return jsonify({'error': 'session not found'}), 404

    filename = secure_filename(f.filename)
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    stored_name = f"{timestamp}_{filename}"
    stored_path = os.path.join(UPLOAD_DIR, stored_name)
    f.save(stored_path)

    cur.execute(
        "INSERT INTO files (session_id, stored_path, original_name, mime_type, uploaded_by, timestamp) VALUES (%s, %s, %s, %s, %s, %s)",
        (session_id, stored_path, f.filename, f.mimetype, current_user.get('id'), datetime.utcnow()),
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
        cur.execute('SELECT id, original_name, mime_type, timestamp FROM files WHERE session_id = %s ORDER BY timestamp DESC', (sid,))
    else:
        # patient: ensure they own the session
        cur.execute('SELECT patient_user_id FROM sessions WHERE id = %s', (sid,))
        row = cur.fetchone()
        if not row or row.get('patient_user_id') != current_user.get('id'):
            return jsonify({'error': 'Forbidden'}), 403
        cur.execute('SELECT id, original_name, mime_type, timestamp FROM files WHERE session_id = %s ORDER BY timestamp DESC', (sid,))

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
    cur.execute('SELECT session_id, stored_path, original_name, mime_type FROM files WHERE id = %s', (file_id,))
    row = cur.fetchone()
    if not row:
        return jsonify({'error': 'File not found'}), 404

    session_id = row.get('session_id')
    stored_path = row.get('stored_path')
    original_name = row.get('original_name')
    mime_type = row.get('mime_type')
    # Check access: doctors or owner
    if current_user.get('role') not in ('doctor', 'dev'):
        cur.execute('SELECT patient_user_id FROM sessions WHERE id = %s', (session_id,))
        srow = cur.fetchone()
        if not srow or srow.get('patient_user_id') != current_user.get('id'):
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
    cur.execute('SELECT id, user_id, expires_at, used FROM one_time_tokens WHERE token = %s', (token,))
    row = cur.fetchone()
    if not row:
        return jsonify({'error': 'invalid token'}), 400
    tid = row.get('id')
    user_id = row.get('user_id')
    expires_at = row.get('expires_at')
    used = row.get('used')
    if used:
        return jsonify({'error': 'token already used'}), 400
    expires_dt = expires_at if isinstance(expires_at, datetime) else datetime.fromisoformat(expires_at)
    if expires_dt < datetime.utcnow():
        return jsonify({'error': 'token expired'}), 400

    # mark as used
    cur.execute('UPDATE one_time_tokens SET used = 1 WHERE id = %s', (tid,))
    db.commit()

    # issue JWT for the user
    cur.execute('SELECT id, role FROM users WHERE id = %s', (user_id,))
    urow = cur.fetchone()
    if not urow:
        return jsonify({'error': 'user not found'}), 404
    uid = urow.get('id')
    role = urow.get('role')
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

        cur.execute('SELECT id, username, role, full_name, age, gender, contact, medical_history, created_at FROM users WHERE id = %s', (user_id,))
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
        cur.execute('UPDATE users SET full_name = %s, age = %s, gender = %s, contact = %s, medical_history = %s WHERE id = %s',
                    (full_name, age, gender, contact, encrypted_history, uid))
        db.commit()
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': f'Failed to update profile: {str(e)}'}), 500


@app.route('/doctor/profile', methods=['GET', 'POST'])
def doctor_profile():
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401
    if current_user.get('role') not in ('doctor', 'dev'):
        return jsonify({'error': 'Forbidden'}), 403

    uid = current_user.get('id') or current_user.get('sub')
    if not uid:
        return jsonify({'error': 'Unauthorized'}), 401

    db = get_db()
    cur = db.cursor()

    if request.method == 'GET':
        cur.execute(
            """
            SELECT u.id, u.username, u.full_name, dp.professionalism, dp.specialization,
                   dp.experience_years, dp.hospital_id, dp.bio
            FROM users u
            LEFT JOIN doctor_profiles dp ON u.id = dp.user_id
            WHERE u.id = %s
            """,
            (uid,)
        )
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Profile not found'}), 404
        return jsonify(dict(row))

    data = request.get_json() or {}
    professionalism = data.get('professionalism')
    specialization = data.get('specialization')
    experience_years = data.get('experience_years')
    hospital_id = data.get('hospital_id')
    bio = data.get('bio')
    now = datetime.utcnow()

    cur.execute(
        """
        INSERT INTO doctor_profiles (user_id, professionalism, specialization, experience_years, hospital_id, bio, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            professionalism = VALUES(professionalism),
            specialization = VALUES(specialization),
            experience_years = VALUES(experience_years),
            hospital_id = VALUES(hospital_id),
            bio = VALUES(bio),
            updated_at = VALUES(updated_at)
        """,
        (uid, professionalism, specialization, experience_years, hospital_id, bio, now, now),
    )
    db.commit()
    return jsonify({'status': 'ok'})


@app.route('/hospitals', methods=['GET', 'POST'])
def hospitals():
    if request.method == 'GET':
        db = get_db()
        cur = db.cursor()
        cur.execute('SELECT id, name, address, city, country, phone, email, website, map_query, description FROM hospitals ORDER BY name')
        rows = cur.fetchall()
        return jsonify({'hospitals': rows})

    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401
    if current_user.get('role') not in ('doctor', 'dev'):
        return jsonify({'error': 'Forbidden'}), 403

    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name required'}), 400
    address = data.get('address')
    city = data.get('city')
    country = data.get('country')
    phone = data.get('phone')
    email = data.get('email')
    website = data.get('website')
    map_query = data.get('map_query') or data.get('mapQuery') or address
    description = data.get('description')
    now = datetime.utcnow()

    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO hospitals (name, address, city, country, phone, email, website, map_query, description, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (name, address, city, country, phone, email, website, map_query, description, now, now),
    )
    db.commit()
    return jsonify({'status': 'ok', 'hospital_id': cur.lastrowid})


@app.route('/hospitals/<int:hospital_id>', methods=['GET'])
def hospital_detail(hospital_id):
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT id, name, address, city, country, phone, email, website, map_query, description FROM hospitals WHERE id = %s', (hospital_id,))
    row = cur.fetchone()
    if not row:
        return jsonify({'error': 'not found'}), 404
    return jsonify(dict(row))


@app.route('/doctors', methods=['GET'])
def list_doctors():
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT u.id, u.full_name, u.username, dp.professionalism, dp.specialization,
               dp.experience_years, dp.hospital_id, h.name AS hospital_name
        FROM users u
        LEFT JOIN doctor_profiles dp ON u.id = dp.user_id
        LEFT JOIN hospitals h ON dp.hospital_id = h.id
        WHERE u.role = 'doctor'
        ORDER BY u.full_name, u.username
        """
    )
    rows = cur.fetchall()
    return jsonify({'doctors': rows})


@app.route('/hospitals/nearby', methods=['POST'])
def get_nearby_hospitals():
    """Get nearby hospitals based on patient location.
    
    Expected JSON: { latitude: float, longitude: float, radius?: int (km, default 10) }
    Returns list of hospitals from database within specified radius.
    """
    data = request.get_json() or {}
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    radius = data.get('radius', 10)  # default 10km
    
    if not latitude or not longitude:
        return jsonify({'error': 'Location coordinates required'}), 400
    
    try:
        db = get_db()
        cur = db.cursor()
        
        # Using Haversine formula to calculate distance
        # This is a simple approximation - for production use PostGIS or similar
        query = """
            SELECT 
                id,
                name,
                location,
                contact,
                latitude,
                longitude,
                (
                    6371 * acos(
                        cos(radians(%s)) * cos(radians(latitude)) *
                        cos(radians(longitude) - radians(%s)) +
                        sin(radians(%s)) * sin(radians(latitude))
                    )
                ) AS distance
            FROM hospitals
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
            HAVING distance <= %s
            ORDER BY distance
            LIMIT 20
        """
        
        cur.execute(query, (latitude, longitude, latitude, radius))
        hospitals = cur.fetchall()
        
        result = []
        for h in hospitals:
            result.append({
                'id': h[0],
                'name': h[1],
                'location': h[2],
                'contact': h[3],
                'latitude': float(h[4]) if h[4] else None,
                'longitude': float(h[5]) if h[5] else None,
                'distance': round(float(h[6]), 2) if len(h) > 6 else None
            })
        
        return jsonify({
            'hospitals': result,
            'count': len(result),
            'search_radius': radius
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/hospitals/<int:hospital_id>/location', methods=['PUT'])
def update_hospital_location(hospital_id):
    """Update hospital GPS coordinates (admin/dev only).
    
    Expected JSON: { latitude: float, longitude: float }
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401
    
    role = current_user.get('role')
    if role not in ('dev', 'admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.get_json() or {}
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    
    if latitude is None or longitude is None:
        return jsonify({'error': 'latitude and longitude required'}), 400
    
    try:
        db = get_db()
        cur = db.cursor()
        
        # Check if hospital exists
        cur.execute("SELECT id FROM hospitals WHERE id = %s", (hospital_id,))
        if not cur.fetchone():
            return jsonify({'error': 'Hospital not found'}), 404
        
        # Update coordinates
        cur.execute(
            "UPDATE hospitals SET latitude = %s, longitude = %s WHERE id = %s",
            (latitude, longitude, hospital_id)
        )
        db.commit()
        
        return jsonify({
            'status': 'ok',
            'message': 'Hospital location updated',
            'hospital_id': hospital_id
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/appointments', methods=['GET', 'POST'])
def appointments():
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401

    uid = current_user.get('id') or current_user.get('sub')
    if request.method == 'GET':
        db = get_db()
        cur = db.cursor()
        cur.execute(
            """
            SELECT a.id, a.appointment_time, a.reason, a.status,
                   d.full_name AS doctor_name, h.name AS hospital_name
            FROM appointments a
            LEFT JOIN users d ON a.doctor_user_id = d.id
            LEFT JOIN hospitals h ON a.hospital_id = h.id
            WHERE a.patient_user_id = %s
            ORDER BY a.appointment_time DESC
            """,
            (uid,)
        )
        rows = cur.fetchall()
        return jsonify({'appointments': rows})

    if current_user.get('role') not in ('patient', 'dev'):
        return jsonify({'error': 'Forbidden'}), 403

    data = request.get_json() or {}
    doctor_id = data.get('doctor_id')
    hospital_id = data.get('hospital_id')
    appointment_time = data.get('appointment_time') or data.get('appointmentTime')
    reason = data.get('reason')
    if not appointment_time:
        return jsonify({'error': 'appointment_time required'}), 400

    try:
        appt_dt = datetime.fromisoformat(appointment_time)
    except Exception:
        return jsonify({'error': 'invalid appointment_time'}), 400

    now = datetime.utcnow()
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO appointments (patient_user_id, doctor_user_id, hospital_id, appointment_time, reason, status, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (uid, doctor_id, hospital_id, appt_dt, reason, 'requested', now, now),
    )
    db.commit()
    return jsonify({'status': 'ok', 'appointment_id': cur.lastrowid})


@app.route('/doctor/appointments', methods=['GET'])
def doctor_appointments():
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401
    if current_user.get('role') not in ('doctor', 'dev'):
        return jsonify({'error': 'Forbidden'}), 403

    uid = current_user.get('id') or current_user.get('sub')
    db = get_db()
    cur = db.cursor()
    if current_user.get('role') == 'dev':
        cur.execute(
            """
            SELECT a.id, a.appointment_time, a.reason, a.status,
                   p.full_name AS patient_name, p.username AS patient_username,
                   h.name AS hospital_name
            FROM appointments a
            LEFT JOIN users p ON a.patient_user_id = p.id
            LEFT JOIN hospitals h ON a.hospital_id = h.id
            ORDER BY a.appointment_time DESC
            """
        )
    else:
        cur.execute(
            """
            SELECT a.id, a.appointment_time, a.reason, a.status,
                   p.full_name AS patient_name, p.username AS patient_username,
                   h.name AS hospital_name
            FROM appointments a
            LEFT JOIN users p ON a.patient_user_id = p.id
            LEFT JOIN hospitals h ON a.hospital_id = h.id
            WHERE a.doctor_user_id = %s
            ORDER BY a.appointment_time DESC
            """,
            (uid,)
        )
    rows = cur.fetchall()
    return jsonify({'appointments': rows})


def generate_session_title(messages):
    """Generate an AI-powered title for a session based on conversation messages."""
    if not messages:
        return "Untitled Conversation"

    # If model not available, use fallback
    if not assistant.client:
        # Try to extract key topic from first user message
        for m in messages:
            if m.get('role') == 'user':
                content = m.get('content', '')[:100]
                # Clean up and capitalize
                return content.split('\n')[0][:50].strip() or "Conversation"
        return "Conversation"

    # Get first few and last few messages for context
    context_msgs = messages[:3] + messages[-2:]
    convo = "\n".join([f"{m.get('role')}: {m.get('content')[:150]}" for m in context_msgs])
    
    prompt = (
        "Generate a very short (3-5 words max) descriptive title for this medical conversation. "
        "Focus on the main health topic or concern. Return ONLY the title, nothing else.\n\n"
        "Conversation:\n" + convo
    )
    try:
        if HAS_GENAI:
            contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
            response_text = ""
            for chunk in assistant.client.models.generate_content_stream(
                model=assistant.model,
                contents=contents,
            ):
                chunk_text = getattr(chunk, "text", "")
                if chunk_text:
                    response_text += chunk_text
            title = response_text.strip()[:60]
            return title if title else "Conversation"
    except Exception:
        pass
    
    # Fallback: extract from first user message
    for m in messages:
        if m.get('role') == 'user':
            content = m.get('content', '')[:50]
            return content.split('\n')[0].strip() or "Conversation"
    return "Conversation"


def build_session_summary(messages):
    if not messages:
        return "No conversation available to summarize."

    # If model not configured, fallback to a compact extract
    if not assistant.client:
        patient_msgs = [m.get('content') for m in messages if m.get('role') == 'user']
        assistant_msgs = [m.get('content') for m in messages if m.get('role') == 'assistant']
        problems = " ".join([p for p in patient_msgs[-3:] if p])[:400]
        responses = " ".join([r for r in assistant_msgs[-2:] if r])[:400]
        summary = (
            "Patient problems: " + (problems or "No details available.") + "\n"
            "Assistant response summary: " + (responses or "No response available.")
        )
        return sanitize_ai_text(summary)

    convo = "\n".join([f"{m.get('role')}: {m.get('content')}" for m in messages])
    prompt = (
        "Summarize this patient conversation for a doctor. Keep it concise with short sentences. "
        "Return plain text only (no markdown symbols). Provide two sections: "
        "Patient problems (symptoms, timeline, risks) and Assistant response summary (advice given).\n\nConversation:\n"
        + convo
    )
    try:
        if HAS_GENAI:
            contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
            response_text = ""
            for chunk in assistant.client.models.generate_content_stream(
                model=assistant.model,
                contents=contents,
            ):
                chunk_text = getattr(chunk, "text", "")
                if chunk_text:
                    response_text += chunk_text
            return sanitize_ai_text(response_text.strip()) or "Summary unavailable."
    except Exception:
        return "Summary unavailable."
    return "Summary unavailable."


@app.route('/sessions/<int:sid>/summary', methods=['GET'])
def session_summary(sid):
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401
    if current_user.get('role') not in ('doctor', 'dev'):
        return jsonify({'error': 'Forbidden'}), 403

    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT id FROM sessions WHERE id = %s', (sid,))
    if not cur.fetchone():
        return jsonify({'error': 'session not found'}), 404

    cur.execute('SELECT role, content, timestamp FROM messages WHERE session_id = %s ORDER BY timestamp', (sid,))
    messages = cur.fetchall()
    summary_text = sanitize_ai_text(build_session_summary(messages))
    cur.execute('INSERT INTO session_summaries (session_id, summary, created_at) VALUES (%s, %s, %s)',
                (sid, summary_text, datetime.utcnow()))
    db.commit()
    return jsonify({'summary': summary_text})


@app.route('/preferences', methods=['GET', 'POST'])
def preferences():
    """GET returns current user's AI preferences. POST updates preferences.

    Fields: language, response_style, reminders, privacy_default
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401

    uid = current_user.get('id') or current_user.get('sub')
    if not uid:
        return jsonify({'error': 'Unauthorized'}), 401

    db = get_db()
    cur = db.cursor()

    if request.method == 'GET':
        cur.execute('SELECT language, response_style, reminders, privacy_default FROM user_preferences WHERE user_id = %s', (uid,))
        row = cur.fetchone()
        if row:
            return jsonify(dict(row))
        # Defaults if not set
        return jsonify({
            'language': 'en',
            'response_style': 'detailed',
            'reminders': 'daily',
            'privacy_default': 'merged'
        })

    data = request.get_json() or {}
    language = data.get('language') or 'en'
    response_style = data.get('response_style') or data.get('responseStyle') or 'detailed'
    reminders = data.get('reminders') or 'daily'
    privacy_default = data.get('privacy_default') or data.get('privacy') or 'merged'
    now = datetime.utcnow()

    cur.execute(
        """
        INSERT INTO user_preferences (user_id, language, response_style, reminders, privacy_default, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            language = VALUES(language),
            response_style = VALUES(response_style),
            reminders = VALUES(reminders),
            privacy_default = VALUES(privacy_default),
            updated_at = VALUES(updated_at)
        """,
        (uid, language, response_style, reminders, privacy_default, now, now),
    )
    db.commit()
    return jsonify({'status': 'ok'})


@app.route('/health_goals', methods=['GET', 'POST'])
def health_goals():
    """GET returns current user's health goals. POST adds a new goal."""
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401

    uid = current_user.get('id') or current_user.get('sub')
    if not uid:
        return jsonify({'error': 'Unauthorized'}), 401

    db = get_db()
    cur = db.cursor()

    if request.method == 'GET':
        cur.execute(
            'SELECT id, title, notes, target_date, status, created_at, updated_at FROM health_goals WHERE user_id = %s ORDER BY created_at DESC',
            (uid,)
        )
        rows = cur.fetchall()
        goals = [dict(r) for r in rows]
        return jsonify({'goals': goals})

    data = request.get_json() or {}
    title = (data.get('title') or '').strip()
    notes = data.get('notes') or data.get('description') or ''
    target_date = data.get('target_date') or data.get('targetDate')
    status = data.get('status') or 'active'
    if not title:
        return jsonify({'error': 'title required'}), 400

    now = datetime.utcnow()
    cur.execute(
        'INSERT INTO health_goals (user_id, title, notes, target_date, status, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s)',
        (uid, title, notes, target_date, status, now, now),
    )
    db.commit()
    return jsonify({'status': 'ok', 'goal_id': cur.lastrowid})


@app.route('/health_goals/<int:goal_id>', methods=['DELETE'])
def delete_health_goal(goal_id):
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401

    uid = current_user.get('id') or current_user.get('sub')
    if not uid:
        return jsonify({'error': 'Unauthorized'}), 401

    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT id FROM health_goals WHERE id = %s AND user_id = %s', (goal_id, uid))
    row = cur.fetchone()
    if not row:
        return jsonify({'error': 'goal not found'}), 404

    cur.execute('DELETE FROM health_goals WHERE id = %s AND user_id = %s', (goal_id, uid))
    db.commit()
    return jsonify({'status': 'ok'})


# ==================== AI/ML ENHANCEMENT ENDPOINTS ====================

@app.route('/ai/medical_codes', methods=['POST'])
def get_medical_codes():
    """Extract ICD-10 and SNOMED CT codes from symptom text."""
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json() or {}
    text = data.get('text', '')
    
    if not text:
        return jsonify({'error': 'text required'}), 400
    
    codes = assistant.find_medical_codes(text)
    return jsonify({'codes': codes, 'count': len(codes)})


@app.route('/ai/medical_codes/search', methods=['POST'])
def search_medical_codes():
    """Search ICD-10/SNOMED CT via external APIs if configured."""
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json() or {}
    query = (data.get('query') or '').strip()
    if not query:
        return jsonify({'error': 'query required'}), 400

    icd10_results = assistant.lookup_icd10(query)
    snomed_results = assistant.lookup_snomed(query)

    return jsonify({
        'query': query,
        'icd10': icd10_results,
        'snomed': snomed_results,
        'configured': {
            'icd10': bool(os.environ.get('ICD10_API_BASE') and os.environ.get('ICD10_API_TOKEN')),
            'snomed': bool(os.environ.get('SNOMED_API_BASE') and os.environ.get('SNOMED_API_TOKEN')),
        }
    })


@app.route('/ai/drug_interactions', methods=['POST'])
def check_drug_interactions():
    """Check for dangerous drug interactions."""
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json() or {}
    medications = data.get('medications', [])
    
    if not medications:
        return jsonify({'error': 'medications array required'}), 400
    
    result = assistant.check_drug_interactions(medications)
    return jsonify(result)


@app.route('/ai/wellness_recommendations', methods=['POST'])
def get_wellness_recommendations():
    """Generate personalized wellness recommendations."""
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401
    
    uid = current_user.get('id') or current_user.get('sub')
    if not uid:
        return jsonify({'error': 'Unauthorized'}), 401
    
    # Fetch patient profile
    db = get_db()
    cur = db.cursor()
    cur.execute(
        'SELECT full_name, age, gender, medical_history FROM users WHERE id = %s',
        (uid,)
    )
    row = cur.fetchone()
    
    if not row:
        return jsonify({'error': 'Profile not found'}), 404
    
    patient_info = dict(row)
    
    # Decrypt medical history
    if patient_info.get('medical_history'):
        patient_info['medicalHistory'] = decrypt_medical_history(patient_info['medical_history'])
    
    recommendations = assistant.generate_wellness_recommendations(patient_info)
    return jsonify({'recommendations': recommendations, 'count': len(recommendations)})


@app.route('/ai/confidence_score', methods=['POST'])
def calculate_confidence():
    """Calculate confidence score for AI assessment."""
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json() or {}
    response_text = data.get('response_text', '')
    patient_context = data.get('patient_context', '')
    
    if not response_text:
        return jsonify({'error': 'response_text required'}), 400
    
    confidence = assistant.calculate_confidence_score(response_text, patient_context)
    
    # Determine confidence level
    if confidence >= 80:
        level = 'High'
        color = 'success'
    elif confidence >= 60:
        level = 'Medium'
        color = 'warning'
    else:
        level = 'Low'
        color = 'danger'
    
    return jsonify({
        'confidence_score': confidence,
        'level': level,
        'color': color,
        'message': f'AI is {confidence}% confident in this assessment'
    })


@app.route('/ai/detect_language', methods=['POST'])
def detect_language():
    """Detect language of user input."""
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json() or {}
    text = data.get('text', '')
    
    if not text:
        return jsonify({'error': 'text required'}), 400
    
    language_code = assistant.detect_language(text)
    
    language_names = {
        'en': 'English',
        'es': 'Spanish',
        'fr': 'French',
        'de': 'German',
        'sw': 'Swahili',
        'ar': 'Arabic'
    }
    
    return jsonify({
        'language_code': language_code,
        'language_name': language_names.get(language_code, 'English')
    })


# ==================== END AI/ML ENDPOINTS ====================


# ==================== MEDICATION & DOCUMENTS ====================

@app.route('/medications', methods=['GET', 'POST'])
def medications():
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401

    uid = current_user.get('id') or current_user.get('sub')
    if not uid:
        return jsonify({'error': 'Unauthorized'}), 401

    db = get_db()
    cur = db.cursor()

    if request.method == 'GET':
        cur.execute(
            """
            SELECT id, medication_name, dosage, frequency, times, start_date, end_date, notes, active, created_at
            FROM medication_schedules
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (uid,)
        )
        rows = cur.fetchall()
        for r in rows:
            if r.get('times'):
                try:
                    r['times'] = json.loads(r['times'])
                except Exception:
                    pass
        return jsonify({'medications': rows})

    data = request.get_json() or {}
    medication_name = data.get('medication_name') or data.get('medicationName')
    if not medication_name:
        return jsonify({'error': 'medication_name required'}), 400

    dosage = data.get('dosage')
    frequency = data.get('frequency')
    times = data.get('times')
    start_date = data.get('start_date') or data.get('startDate')
    end_date = data.get('end_date') or data.get('endDate')
    notes = data.get('notes')

    times_json = json.dumps(times) if isinstance(times, list) else None

    cur.execute(
        """
        INSERT INTO medication_schedules (user_id, medication_name, dosage, frequency, times, start_date, end_date, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (uid, medication_name, dosage, frequency, times_json, start_date, end_date, notes)
    )
    db.commit()
    return jsonify({'status': 'ok', 'id': cur.lastrowid})


@app.route('/medications/<int:schedule_id>', methods=['PUT', 'DELETE'])
def update_medication(schedule_id):
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401

    uid = current_user.get('id') or current_user.get('sub')
    if not uid:
        return jsonify({'error': 'Unauthorized'}), 401

    db = get_db()
    cur = db.cursor()

    cur.execute("SELECT id FROM medication_schedules WHERE id = %s AND user_id = %s", (schedule_id, uid))
    if not cur.fetchone():
        return jsonify({'error': 'Medication schedule not found'}), 404

    if request.method == 'DELETE':
        cur.execute("DELETE FROM medication_schedules WHERE id = %s AND user_id = %s", (schedule_id, uid))
        db.commit()
        return jsonify({'status': 'deleted'})

    data = request.get_json() or {}
    fields = []
    values = []
    mapping = {
        'medication_name': 'medication_name',
        'dosage': 'dosage',
        'frequency': 'frequency',
        'times': 'times',
        'start_date': 'start_date',
        'end_date': 'end_date',
        'notes': 'notes',
        'active': 'active'
    }

    for key, column in mapping.items():
        if key in data:
            val = data.get(key)
            if key == 'times' and isinstance(val, list):
                val = json.dumps(val)
            fields.append(f"{column} = %s")
            values.append(val)

    if not fields:
        return jsonify({'error': 'No fields to update'}), 400

    values.extend([schedule_id, uid])
    cur.execute(f"UPDATE medication_schedules SET {', '.join(fields)} WHERE id = %s AND user_id = %s", values)
    db.commit()
    return jsonify({'status': 'ok'})


@app.route('/medications/<int:schedule_id>/intake', methods=['POST'])
def log_medication_intake(schedule_id):
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401

    uid = current_user.get('id') or current_user.get('sub')
    if not uid:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json() or {}
    status = data.get('status', 'taken')
    scheduled_time = data.get('scheduled_time') or data.get('scheduledTime') or datetime.utcnow()
    taken_time = data.get('taken_time') or data.get('takenTime') or (datetime.utcnow() if status == 'taken' else None)
    notes = data.get('notes')

    db = get_db()
    cur = db.cursor()

    cur.execute(
        """
        INSERT INTO medication_intake_log (schedule_id, user_id, scheduled_time, taken_time, status, notes)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (schedule_id, uid, scheduled_time, taken_time, status, notes)
    )
    db.commit()
    return jsonify({'status': 'ok', 'id': cur.lastrowid})


@app.route('/medications/adherence', methods=['GET'])
def medication_adherence():
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401

    uid = current_user.get('id') or current_user.get('sub')
    if not uid:
        return jsonify({'error': 'Unauthorized'}), 401

    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT status, COUNT(*) AS count
        FROM medication_intake_log
        WHERE user_id = %s AND scheduled_time >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL 30 DAY)
        GROUP BY status
        """,
        (uid,)
    )
    rows = cur.fetchall()

    counts = {'taken': 0, 'missed': 0, 'skipped': 0, 'pending': 0}
    for r in rows:
        counts[r['status']] = r['count']

    total = sum(counts.values())
    adherence = round((counts['taken'] / total) * 100, 2) if total else 0

    return jsonify({
        'adherence_percent': adherence,
        'counts': counts,
        'period_days': 30
    })


@app.route('/medications/remind', methods=['POST'])
def send_medication_reminder():
    """Send a medication reminder notification to the current user."""
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401

    uid = current_user.get('id') or current_user.get('sub')
    if not uid:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json() or {}
    schedule_id = data.get('schedule_id') or data.get('scheduleId')
    reminder_time = data.get('time') or data.get('reminder_time')

    db = get_db()
    cur = db.cursor()
    if schedule_id:
        cur.execute(
            """
            SELECT medication_name, dosage, frequency
            FROM medication_schedules
            WHERE id = %s AND user_id = %s
            """,
            (schedule_id, uid)
        )
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Medication schedule not found'}), 404
        med_name = row.get('medication_name')
        dosage = row.get('dosage') or ''
        frequency = row.get('frequency') or ''
    else:
        med_name = data.get('medication_name') or 'Medication'
        dosage = data.get('dosage') or ''
        frequency = data.get('frequency') or ''

    title = 'Medication Reminder'
    time_text = f" at {reminder_time}" if reminder_time else ''
    body = f"Time to take {med_name} {dosage} {frequency}{time_text}."

    create_notification(uid, 'medication_reminder', title, body, {'schedule_id': schedule_id})
    return jsonify({'status': 'sent'})


@app.route('/notifications/preferences', methods=['GET', 'POST'])
def notification_preferences():
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401

    uid = current_user.get('id') or current_user.get('sub')
    if not uid:
        return jsonify({'error': 'Unauthorized'}), 401

    db = get_db()
    cur = db.cursor()

    if request.method == 'GET':
        cur.execute(
            """
            SELECT medication_reminders, health_alerts, appointment_reminders, wellness_tips,
                   email_notifications, sms_notifications, push_notifications,
                   quiet_hours_start, quiet_hours_end, timezone
            FROM notification_preferences WHERE user_id = %s
            """,
            (uid,)
        )
        row = cur.fetchone()
        if not row:
            return jsonify(get_notification_preferences(uid))
        return jsonify(dict(row))

    data = request.get_json() or {}
    fields = {
        'medication_reminders': data.get('medication_reminders'),
        'health_alerts': data.get('health_alerts'),
        'appointment_reminders': data.get('appointment_reminders'),
        'wellness_tips': data.get('wellness_tips'),
        'email_notifications': data.get('email_notifications'),
        'sms_notifications': data.get('sms_notifications'),
        'push_notifications': data.get('push_notifications'),
        'quiet_hours_start': data.get('quiet_hours_start'),
        'quiet_hours_end': data.get('quiet_hours_end'),
        'timezone': data.get('timezone')
    }

    # Ensure row exists
    cur.execute("SELECT user_id FROM notification_preferences WHERE user_id = %s", (uid,))
    exists = cur.fetchone()

    if not exists:
        cur.execute(
            """
            INSERT INTO notification_preferences (user_id, medication_reminders, health_alerts, appointment_reminders,
                wellness_tips, email_notifications, sms_notifications, push_notifications, quiet_hours_start, quiet_hours_end, timezone, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                uid,
                fields['medication_reminders'] if fields['medication_reminders'] is not None else True,
                fields['health_alerts'] if fields['health_alerts'] is not None else True,
                fields['appointment_reminders'] if fields['appointment_reminders'] is not None else True,
                fields['wellness_tips'] if fields['wellness_tips'] is not None else True,
                fields['email_notifications'] if fields['email_notifications'] is not None else True,
                fields['sms_notifications'] if fields['sms_notifications'] is not None else False,
                fields['push_notifications'] if fields['push_notifications'] is not None else True,
                fields['quiet_hours_start'],
                fields['quiet_hours_end'],
                fields['timezone'] or 'UTC',
                datetime.utcnow(),
            )
        )
        db.commit()
        return jsonify({'status': 'ok'})

    update_fields = []
    values = []
    for key, value in fields.items():
        if value is not None:
            update_fields.append(f"{key} = %s")
            values.append(value)

    update_fields.append("updated_at = %s")
    values.append(datetime.utcnow())
    values.append(uid)

    cur.execute(
        f"UPDATE notification_preferences SET {', '.join(update_fields)} WHERE user_id = %s",
        values
    )
    db.commit()
    return jsonify({'status': 'ok'})


@app.route('/documents', methods=['GET'])
def list_documents():
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401

    uid = current_user.get('id') or current_user.get('sub')
    if not uid:
        return jsonify({'error': 'Unauthorized'}), 401

    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT id, document_type, file_name, extracted_text, processed, upload_date
        FROM medical_documents
        WHERE user_id = %s
        ORDER BY upload_date DESC
        """,
        (uid,)
    )
    rows = cur.fetchall()
    return jsonify({'documents': rows})


@app.route('/documents/upload', methods=['POST'])
def upload_document():
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401

    uid = current_user.get('id') or current_user.get('sub')
    if not uid:
        return jsonify({'error': 'Unauthorized'}), 401

    if 'file' not in request.files:
        return jsonify({'error': 'file is required'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'error': 'filename is required'}), 400

    # Security: validate file extension and size (5MB max)
    allowed_ext = {'.png', '.jpg', '.jpeg'}
    filename = secure_filename(file.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in allowed_ext:
        return jsonify({'error': 'Only image files (PNG, JPG, JPEG) are allowed'}), 400
    if request.content_length and request.content_length > 5 * 1024 * 1024:
        return jsonify({'error': 'File too large (max 5MB)'}), 400

    document_type = request.form.get('document_type', 'report')
    subdir = os.path.join(UPLOAD_DIR, 'medical_docs')
    os.makedirs(subdir, exist_ok=True)
    filepath = os.path.join(subdir, filename)
    file.save(filepath)

    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO medical_documents (user_id, document_type, file_path, file_name, processed)
        VALUES (%s, %s, %s, %s, 0)
        """,
        (uid, document_type, filepath, filename)
    )
    db.commit()

    return jsonify({'status': 'ok', 'id': cur.lastrowid})


@app.route('/documents/<int:doc_id>/process', methods=['POST'])
def process_document(doc_id):
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401

    uid = current_user.get('id') or current_user.get('sub')
    if not uid:
        return jsonify({'error': 'Unauthorized'}), 401

    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT id, file_path, processed
        FROM medical_documents
        WHERE id = %s AND user_id = %s
        """,
        (doc_id, uid)
    )
    row = cur.fetchone()
    if not row:
        return jsonify({'error': 'Document not found'}), 404

    if row.get('processed'):
        return jsonify({'status': 'already processed'})

    file_path = row.get('file_path')
    extracted_text = None

    try:
        import importlib
        pil_image = importlib.import_module("PIL.Image")
        pytesseract = importlib.import_module("pytesseract")

        img = pil_image.open(file_path)
        extracted_text = pytesseract.image_to_string(img)
    except Exception as e:
        return jsonify({'error': f'OCR not available: {str(e)}'}), 500

    cur.execute(
        """
        UPDATE medical_documents
        SET extracted_text = %s, processed = 1
        WHERE id = %s AND user_id = %s
        """,
        (extracted_text, doc_id, uid)
    )
    db.commit()

    return jsonify({'status': 'ok', 'extracted_text': extracted_text})


@app.route('/ai/predict_risk', methods=['POST'])
def predict_health_risk():
    """Predict basic health risk based on provided data."""
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json() or {}
    age = data.get('age')
    systolic = data.get('systolic')
    diastolic = data.get('diastolic')
    medical_history = (data.get('medical_history') or '').lower()

    risk_score = 10
    factors = []

    if age:
        if age >= 60:
            risk_score += 25
            factors.append('Age 60+')
        elif age >= 45:
            risk_score += 15
            factors.append('Age 45-59')

    if systolic and systolic >= 140:
        risk_score += 20
        factors.append('High systolic blood pressure')
    if diastolic and diastolic >= 90:
        risk_score += 15
        factors.append('High diastolic blood pressure')

    if 'diabetes' in medical_history:
        risk_score += 20
        factors.append('Diabetes history')
    if 'hypertension' in medical_history:
        risk_score += 15
        factors.append('Hypertension history')
    if 'smoking' in medical_history:
        risk_score += 10
        factors.append('Smoking history')

    risk_score = max(0, min(100, risk_score))

    if risk_score >= 75:
        level = 'high'
    elif risk_score >= 50:
        level = 'medium'
    else:
        level = 'low'

    return jsonify({
        'risk_score': risk_score,
        'risk_level': level,
        'factors': factors,
        'message': 'This is a basic risk estimate. Consult a professional for medical advice.'
    })


# ==================== END MEDICATION & DOCUMENTS ====================


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
    cur.execute('DELETE FROM users WHERE id = %s', (uid,))
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
        cur.execute("INSERT INTO users (username, password_hash, role, created_at) VALUES (%s, %s, %s, %s)",
                (username, pw_hash, 'dev', datetime.utcnow()))
        db.commit()
        return jsonify({'status': 'ok', 'username': username})
    except IntegrityError:
        return jsonify({'error': 'username exists'}), 400


@app.route('/emergency_alert', methods=['POST'])
def emergency_alert():
    """Create an emergency alert for the current session and notify clinicians.

    Expected JSON body: { session_id?: int, patient_info?: dict, location?: { latitude: float, longitude: float } }
    This is a lightweight prototype: it inserts an emergency message and audit entry
    that clinician UIs can poll via `/doctor/alerts`.
    """
    data = request.get_json() or {}
    session_id = data.get('session_id')
    patient_info = data.get('patient_info', {})
    location = data.get('location')  # { latitude, longitude }

    db = get_db()
    cur = db.cursor()

    # If no session exists yet, create a minimal session record
    if not session_id:
        cur.execute(
            "INSERT INTO sessions (patient_name, age, gender, contact, medical_history, task, locale, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                patient_info.get('fullName'),
                patient_info.get('age'),
                patient_info.get('gender'),
                patient_info.get('contact'),
                patient_info.get('medicalHistory'),
                patient_info.get('task'),
                patient_info.get('locale'),
                datetime.utcnow(),
            ),
        )
        session_id = cur.lastrowid

    # Build emergency message with location if provided
    content = 'Patient has requested an emergency chat. Clinician alerted.'
    if location and location.get('latitude') and location.get('longitude'):
        content += f" Location: {location['latitude']}, {location['longitude']}"
    
    # Insert a system message marking emergency so doctors see it in alerts
    cur.execute(
        "INSERT INTO messages (session_id, role, content, emergency, timestamp) VALUES (%s, %s, %s, %s, %s)",
        (session_id, 'system', content, 1, datetime.utcnow()),
    )

    # audit entry with location
    details = 'emergency_alert created via patient UI'
    if location:
        details += f" | Location: {location.get('latitude')}, {location.get('longitude')}"
    cur.execute(
        "INSERT INTO audit (actor_id, action, target_id, details, timestamp) VALUES (%s, %s, %s, %s, %s)",
        (None, 'emergency_alert', session_id, details, datetime.utcnow()),
    )

    db.commit()

    # Prototype response: confirm to patient that clinicians have been notified
    return jsonify({
        'status': 'ok',
        'session_id': session_id,
        'message': 'A clinician has been notified and will review your session shortly. If you are in immediate danger, call local emergency services.',
        'location_shared': bool(location)
    })


@app.route('/print/patient_card')
def print_patient_card():
    """Mock endpoint to generate a simple patient card (in real app, PDF generation)."""
    return jsonify({'pdf_url': '/static/sample_patient_card.pdf', 'message': 'Card generated (mock)'})


@app.route('/print/patient_card_old')
def print_patient_card_old():
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


# ==================== PHASE 2: ADVANCED ANALYTICS ENDPOINTS ====================

@app.route('/patient/health-dashboard', methods=['GET'])
def get_patient_health_dashboard():
    """Get patient's health metrics and risk scores for last 30 days"""
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = current_user.get('id') or current_user.get('sub')
    
    db = get_db()
    cur = db.cursor()
    
    try:
        # Get health metrics from last 30 days
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        cur.execute(
            "SELECT metric_type, metric_value, metric_date FROM patient_health_metrics WHERE patient_user_id = %s AND metric_date >= %s ORDER BY metric_date DESC",
            (user_id, thirty_days_ago)
        )
        metrics = [dict(row) for row in cur.fetchall()]
        
        # Get current risk score
        cur.execute(
            "SELECT risk_level, readmission_risk, no_show_risk, complication_risk, risk_factors FROM patient_risk_scores WHERE patient_user_id = %s ORDER BY calculated_at DESC LIMIT 1",
            (user_id,)
        )
        risk_row = cur.fetchone()
        risk_score = dict(risk_row) if risk_row else {
            'risk_level': 'LOW',
            'readmission_risk': 0,
            'no_show_risk': 0,
            'complication_risk': 10,
            'risk_factors': '{}'
        }
        
        # Get appointment statistics
        cur.execute(
            "SELECT COUNT(*) as total_appointments FROM appointments WHERE patient_user_id = %s",
            (user_id,)
        )
        appt_row = cur.fetchone()
        total_appointments = dict(appt_row)['total_appointments'] if appt_row else 0
        
        return jsonify({
            'health_metrics': metrics,
            'risk_score': risk_score,
            'appointment_statistics': {
                'total_appointments': total_appointments
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()


@app.route('/patient/health-report', methods=['GET'])
def get_patient_health_report():
    """Get comprehensive 90-day health report"""
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = current_user.get('id') or current_user.get('sub')
    
    db = get_db()
    cur = db.cursor()
    
    try:
        # Get metrics from last 90 days
        ninety_days_ago = datetime.utcnow() - timedelta(days=90)
        cur.execute(
            "SELECT metric_type, AVG(metric_value) as avg_value, MAX(metric_value) as max_value, MIN(metric_value) as min_value FROM patient_health_metrics WHERE patient_user_id = %s AND metric_date >= %s GROUP BY metric_type",
            (user_id, ninety_days_ago)
        )
        metrics_summary = {}
        for row in cur.fetchall():
            row_dict = dict(row)
            metrics_summary[row_dict['metric_type']] = {
                'average': round(row_dict['avg_value'], 2),
                'maximum': round(row_dict['max_value'], 2),
                'minimum': round(row_dict['min_value'], 2)
            }
        
        # Get session summary
        cur.execute(
            "SELECT COUNT(*) as total_sessions, AVG(TIMESTAMPDIFF(MINUTE, created_at, updated_at)) as avg_duration FROM sessions WHERE patient_user_id = %s AND created_at >= %s",
            (user_id, ninety_days_ago)
        )
        session_row = cur.fetchone()
        session_summary = dict(session_row) if session_row else {'total_sessions': 0, 'avg_duration': 0}
        
        # Generate AI insights
        report_text = f"""
Health Report Summary (Last 90 Days):

Metrics Summary:
{json.dumps(metrics_summary, indent=2)}

Session Activity:
- Total Sessions: {session_summary.get('total_sessions', 0)}
- Average Duration: {session_summary.get('avg_duration', 0):.1f} minutes

Recommendations:
1. Continue monitoring your health metrics regularly
2. Maintain consistent logging of vital measurements
3. Schedule regular check-ups with your healthcare provider
4. If you notice any significant changes in your metrics, consult your doctor

Note: This report is generated based on your logged health metrics and should not replace professional medical advice.
        """
        
        return jsonify({
            'metrics_summary': metrics_summary,
            'session_summary': session_summary,
            'report_text': report_text
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()


@app.route('/log-health-metric', methods=['POST'])
def log_health_metric():
    """Log a new health metric"""
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = current_user.get('id') or current_user.get('sub')
    data = request.get_json()
    
    metric_type = data.get('metric_type')
    metric_value = data.get('metric_value')
    metric_date = data.get('metric_date')
    notes = data.get('notes', '')
    
    if not metric_type or metric_value is None or not metric_date:
        return jsonify({'error': 'Missing required fields'}), 400
    
    db = get_db()
    cur = db.cursor()
    
    try:
        # Convert metric_date to datetime
        metric_datetime = datetime.fromisoformat(metric_date)
        
        cur.execute(
            "INSERT INTO patient_health_metrics (patient_user_id, metric_type, metric_value, metric_date, notes, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
            (user_id, metric_type, metric_value, metric_datetime, notes, datetime.utcnow())
        )
        db.commit()
        
        return jsonify({'success': True, 'message': 'Health metric logged successfully'})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()


@app.route('/doctor/analytics', methods=['GET'])
def get_doctor_analytics():
    """Get doctor's practice statistics"""
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = current_user.get('id') or current_user.get('sub')
    
    db = get_db()
    cur = db.cursor()
    
    try:
        # Get doctor statistics
        cur.execute(
            "SELECT total_patients, total_appointments, avg_response_time_minutes, patient_satisfaction_score, cases_handled_this_month FROM doctor_statistics WHERE doctor_user_id = %s LIMIT 1",
            (user_id,)
        )
        stats_row = cur.fetchone()
        
        if stats_row:
            stats = dict(stats_row)
        else:
            # Return default stats if none exist
            stats = {
                'total_patients': 0,
                'total_appointments': 0,
                'avg_response_time_minutes': 0,
                'patient_satisfaction_score': 0,
                'cases_handled_this_month': 0
            }
        
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()


def _calculate_risk_from_metrics(metrics: list) -> tuple:
    """Return (risk_score, factors) from a list of metric rows."""
    risk_score = 10
    factors = []

    by_type = {}
    for m in metrics:
        by_type.setdefault(m['metric_type'], []).append(m['metric_value'])

    def avg(values):
        return sum(values) / len(values) if values else 0

    if 'Blood Pressure' in by_type:
        bp = avg(by_type['Blood Pressure'])
        if bp >= 140:
            risk_score += 25
            factors.append('High blood pressure trend')
        elif bp >= 130:
            risk_score += 15
            factors.append('Elevated blood pressure trend')

    if 'Glucose' in by_type:
        glu = avg(by_type['Glucose'])
        if glu >= 180:
            risk_score += 25
            factors.append('High glucose trend')
        elif glu >= 140:
            risk_score += 15
            factors.append('Elevated glucose trend')

    if 'Heart Rate' in by_type:
        hr = avg(by_type['Heart Rate'])
        if hr >= 110:
            risk_score += 15
            factors.append('High heart rate trend')

    if 'Temperature' in by_type:
        temp = avg(by_type['Temperature'])
        if temp >= 38:
            risk_score += 15
            factors.append('Fever trend')

    risk_score = max(0, min(100, risk_score))
    return risk_score, factors


@app.route('/doctor/medication-adherence', methods=['GET'])
def doctor_medication_adherence():
    current_user = get_current_user()
    if not current_user or current_user.get('role') not in ('doctor', 'dev'):
        return jsonify({'error': 'Forbidden'}), 403

    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(
            """
            SELECT l.user_id,
                   COALESCE(u.full_name, u.username) AS patient_name,
                   SUM(CASE WHEN l.status = 'taken' THEN 1 ELSE 0 END) AS taken,
                   SUM(CASE WHEN l.status = 'missed' THEN 1 ELSE 0 END) AS missed,
                   SUM(CASE WHEN l.status = 'skipped' THEN 1 ELSE 0 END) AS skipped,
                   SUM(CASE WHEN l.status = 'pending' THEN 1 ELSE 0 END) AS pending,
                   COUNT(*) AS total
            FROM medication_intake_log l
            JOIN users u ON u.id = l.user_id
            WHERE l.scheduled_time >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL 30 DAY)
            GROUP BY l.user_id
            ORDER BY total DESC
            """
        )
        rows = cur.fetchall()
        results = []
        for r in rows:
            total = r.get('total') or 0
            taken = r.get('taken') or 0
            adherence = round((taken / total) * 100, 2) if total else 0
            results.append({
                'user_id': r.get('user_id'),
                'patient_name': r.get('patient_name'),
                'taken': taken,
                'missed': r.get('missed') or 0,
                'skipped': r.get('skipped') or 0,
                'pending': r.get('pending') or 0,
                'total': total,
                'adherence_percent': adherence
            })
        return jsonify({'patients': results})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()


@app.route('/doctor/predictive-alerts', methods=['GET'])
def doctor_predictive_alerts():
    current_user = get_current_user()
    if not current_user or current_user.get('role') not in ('doctor', 'dev'):
        return jsonify({'error': 'Forbidden'}), 403

    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(
            """
            SELECT DISTINCT patient_user_id
            FROM patient_health_metrics
            WHERE metric_date >= DATE_SUB(UTC_DATE(), INTERVAL 30 DAY)
            """
        )
        patient_ids = [row['patient_user_id'] for row in cur.fetchall()]

        alerts = []
        for pid in patient_ids:
            cur.execute(
                """
                SELECT metric_type, metric_value
                FROM patient_health_metrics
                WHERE patient_user_id = %s
                  AND metric_date >= DATE_SUB(UTC_DATE(), INTERVAL 30 DAY)
                """,
                (pid,)
            )
            metrics = cur.fetchall() or []
            if not metrics:
                continue

            risk_score, factors = _calculate_risk_from_metrics(metrics)
            if risk_score >= 75:
                level = 'high'
            elif risk_score >= 50:
                level = 'medium'
            else:
                level = 'low'

            # upsert prediction
            cur.execute(
                """
                SELECT id FROM health_predictions WHERE user_id = %s AND prediction_type = 'general_risk'
                """,
                (pid,)
            )
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    """
                    UPDATE health_predictions
                    SET risk_score = %s, risk_level = %s, factors = %s, predicted_at = %s, expires_at = %s
                    WHERE id = %s
                    """,
                    (risk_score, level, json.dumps(factors), datetime.utcnow(), datetime.utcnow() + timedelta(days=7), existing['id'])
                )
            else:
                cur.execute(
                    """
                    INSERT INTO health_predictions (user_id, prediction_type, risk_score, risk_level, factors, predicted_at, expires_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (pid, 'general_risk', risk_score, level, json.dumps(factors), datetime.utcnow(), datetime.utcnow() + timedelta(days=7))
                )

            cur.execute("SELECT COALESCE(full_name, username) AS name FROM users WHERE id = %s", (pid,))
            urow = cur.fetchone()
            alerts.append({
                'user_id': pid,
                'patient_name': urow.get('name') if urow else 'Patient',
                'risk_score': risk_score,
                'risk_level': level,
                'factors': factors
            })

        db.commit()
        alerts.sort(key=lambda x: x['risk_score'], reverse=True)
        return jsonify({'alerts': alerts})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()


@app.route('/doctor/patient-cases', methods=['GET'])
def get_doctor_patient_cases():
    """Get list of patient cases handled by doctor"""
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = current_user.get('id') or current_user.get('sub')
    
    db = get_db()
    cur = db.cursor()
    
    try:
        # Sessions table does not store doctor_id; return recent cases for demo/doctor view
        cur.execute(
            """SELECT
                s.id AS session_id,
                s.patient_user_id,
                COALESCE(u.full_name, s.patient_name) AS patient_name,
                s.task AS task_description,
                s.created_at,
                (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id) AS message_count
            FROM sessions s
            LEFT JOIN users u ON s.patient_user_id = u.id
            ORDER BY s.created_at DESC
            LIMIT 200"""
        )

        cases = []
        for row in cur.fetchall():
            row_dict = dict(row)
            cases.append({
                'session_id': row_dict.get('session_id'),
                'patient_id': row_dict.get('patient_user_id'),
                'patient_name': row_dict.get('patient_name') or 'Patient',
                'message_count': row_dict.get('message_count', 0),
                'date': row_dict.get('created_at').isoformat() if row_dict.get('created_at') else None,
                'concern': row_dict.get('task_description') or 'General Consultation'
            })

        return jsonify({'cases': cases})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()


@app.route('/calculate-patient-risk', methods=['POST'])
def calculate_patient_risk():
    """Calculate patient risk scores based on medical history"""
    data = request.get_json()
    user_id = data.get('patient_user_id')
    
    if not user_id:
        return jsonify({'error': 'patient_user_id required'}), 400
    
    db = get_db()
    cur = db.cursor()
    
    try:
        # Get patient demographics
        cur.execute("SELECT date_of_birth FROM users WHERE id = %s", (user_id,))
        patient = cur.fetchone()
        
        if not patient:
            return jsonify({'error': 'Patient not found'}), 404
        
        # Calculate age
        dob = dict(patient)['date_of_birth']
        if dob:
            age = (datetime.utcnow().date() - dob).days // 365
        else:
            age = 0
        
        # Get appointment history
        cur.execute(
            "SELECT COUNT(*) as no_show_count FROM appointments WHERE patient_user_id = %s AND status = 'no_show'",
            (user_id,)
        )
        no_show_row = cur.fetchone()
        no_show_count = dict(no_show_row)['no_show_count'] if no_show_row else 0
        
        # Calculate risk scores
        no_show_risk = min(100, no_show_count * 15)  # 15% per no-show
        readmission_risk = max(0, min(100, (age - 50) * 0.5)) if age > 50 else 0  # Age-based
        complication_risk = 10.0  # Baseline
        
        # Calculate overall risk
        average_risk = (no_show_risk + readmission_risk + complication_risk) / 3
        
        if average_risk < 20:
            risk_level = 'LOW'
        elif average_risk < 50:
            risk_level = 'MEDIUM'
        else:
            risk_level = 'HIGH'
        
        risk_factors = {
            'age': age,
            'no_show_count': no_show_count,
            'reason': f'Age: {age}, No-shows: {no_show_count}'
        }
        
        # Store risk score
        cur.execute(
            """INSERT INTO patient_risk_scores 
            (patient_user_id, risk_level, readmission_risk, no_show_risk, complication_risk, risk_factors, calculated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (user_id, risk_level, readmission_risk, no_show_risk, complication_risk, json.dumps(risk_factors), datetime.utcnow())
        )
        db.commit()
        
        return jsonify({
            'patient_user_id': user_id,
            'risk_level': risk_level,
            'readmission_risk': readmission_risk,
            'no_show_risk': no_show_risk,
            'complication_risk': complication_risk,
            'average_risk': average_risk,
            'risk_factors': risk_factors
        })
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()


@app.route('/log-analytics-event', methods=['POST'])
def log_analytics_event():
    """Log user interaction event for analytics"""
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = current_user.get('id') or current_user.get('sub')
    data = request.get_json()
    
    event_type = data.get('event_type')
    event_data = data.get('event_data', {})
    
    if not event_type:
        return jsonify({'error': 'event_type required'}), 400
    
    db = get_db()
    cur = db.cursor()
    
    try:
        ip_address = request.remote_addr
        user_agent = request.headers.get('User-Agent', '')
        
        cur.execute(
            """INSERT INTO analytics_events (user_id, event_type, event_data, ip_address, user_agent, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)""",
            (user_id, event_type, json.dumps(event_data), ip_address, user_agent, datetime.utcnow())
        )
        db.commit()
        
        return jsonify({'success': True, 'message': 'Event logged'})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()


# ==================== PHASE 3: COMMUNICATION FEATURES ====================

def get_user_email(user_id: int) -> Optional[str]:
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT contact FROM users WHERE id = %s", (user_id,))
    row = cur.fetchone()
    if not row:
        return None
    contact = (row.get('contact') or '').strip()
    if '@' in contact:
        return contact
    return None


def get_user_phone(user_id: int) -> Optional[str]:
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT contact FROM users WHERE id = %s", (user_id,))
    row = cur.fetchone()
    if not row:
        return None
    contact = (row.get('contact') or '').strip()
    digits = ''.join(ch for ch in contact if ch.isdigit() or ch == '+')
    if len(digits.replace('+', '')) >= 9:
        return digits
    return None


def send_email_api_notification(to_email: str, subject: str, body: str) -> bool:
    provider = (os.environ.get('EMAIL_PROVIDER') or 'sendgrid').lower()
    if provider != 'sendgrid':
        return False

    api_key = os.environ.get('SENDGRID_API_KEY')
    from_email = os.environ.get('SENDGRID_FROM')
    if not api_key or not from_email:
        return False

    try:
        import requests
        payload = {
            "personalizations": [{"to": [{"email": to_email}]}],
            "from": {"email": from_email},
            "subject": subject,
            "content": [{"type": "text/plain", "value": body}]
        }
        resp = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=10,
        )
        return resp.status_code in (200, 202)
    except Exception:
        return False


def send_email_notification(to_email: str, subject: str, body: str) -> bool:
    email_api_enabled = os.environ.get('ENABLE_EMAIL_API', '1') == '1'
    if email_api_enabled and send_email_api_notification(to_email, subject, body):
        return True

    smtp_host = os.environ.get('SMTP_HOST')
    smtp_port = int(os.environ.get('SMTP_PORT', '587'))
    smtp_user = os.environ.get('SMTP_USER')
    smtp_password = os.environ.get('SMTP_PASSWORD')
    smtp_use_tls = os.environ.get('SMTP_USE_TLS', '1') == '1'
    smtp_from = os.environ.get('SMTP_FROM') or smtp_user

    if not smtp_host or not smtp_user or not smtp_password or not smtp_from:
        return False

    try:
        from email.mime.text import MIMEText
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = smtp_from
        msg['To'] = to_email

        import smtplib
        server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
        if smtp_use_tls:
            server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_from, [to_email], msg.as_string())
        server.quit()
        return True
    except Exception:
        return False


def daraja_access_token() -> Optional[str]:
    consumer_key = os.environ.get('DARAJA_CONSUMER_KEY')
    consumer_secret = os.environ.get('DARAJA_CONSUMER_SECRET')
    base_url = os.environ.get('DARAJA_BASE_URL', 'https://sandbox.safaricom.co.ke')
    if not consumer_key or not consumer_secret:
        return None

    try:
        import requests
        from requests.auth import HTTPBasicAuth
        url = f"{base_url}/oauth/v1/generate?grant_type=client_credentials"
        resp = requests.get(url, auth=HTTPBasicAuth(consumer_key, consumer_secret), timeout=10)
        if resp.status_code != 200:
            return None
        return resp.json().get('access_token')
    except Exception:
        return None


def send_sms_notification(to_phone: str, message: str) -> bool:
    if os.environ.get('ENABLE_DARAJA_SMS', '0') != '1':
        return False

    access_token = daraja_access_token()
    if not access_token:
        return False

    base_url = os.environ.get('DARAJA_BASE_URL', 'https://sandbox.safaricom.co.ke')
    sms_url = os.environ.get('DARAJA_SMS_URL') or f"{base_url}/sms/v1/send"
    sender_id = os.environ.get('DARAJA_SENDER', 'MedicalAI')

    try:
        import requests
        payload = {
            "sender_id": sender_id,
            "message": message,
            "phone_number": to_phone,
        }
        resp = requests.post(
            sms_url,
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json=payload,
            timeout=10,
        )
        return resp.status_code in (200, 201, 202)
    except Exception:
        return False


def get_notification_preferences(user_id: int) -> dict:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT medication_reminders, health_alerts, appointment_reminders, wellness_tips,
               email_notifications, sms_notifications, push_notifications,
               quiet_hours_start, quiet_hours_end
        FROM notification_preferences WHERE user_id = %s
        """,
        (user_id,)
    )
    row = cur.fetchone()
    if not row:
        return {
            'medication_reminders': True,
            'health_alerts': True,
            'appointment_reminders': True,
            'wellness_tips': True,
            'email_notifications': True,
            'sms_notifications': False,
            'push_notifications': True,
            'quiet_hours_start': None,
            'quiet_hours_end': None,
            'timezone': 'UTC',
        }
    return dict(row)


def create_notification(user_id: int, notif_type: str, title: str, body: str, data: Optional[dict] = None):
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """INSERT INTO notifications (user_id, type, title, body, data, is_read, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (user_id, notif_type, title, body, json.dumps(data or {}), 0, datetime.utcnow())
    )
    db.commit()

    prefs = get_notification_preferences(user_id)
    if notif_type in ('medication', 'medication_reminder') and not prefs.get('medication_reminders'):
        return
    if notif_type in ('health', 'health_alert') and not prefs.get('health_alerts'):
        return
    if notif_type in ('appointment', 'appointment_reminder') and not prefs.get('appointment_reminders'):
        return
    if notif_type in ('wellness', 'wellness_tip') and not prefs.get('wellness_tips'):
        return

    email = get_user_email(user_id)
    if email and prefs.get('email_notifications'):
        send_email_notification(email, title, body)

    phone = get_user_phone(user_id)
    if phone and prefs.get('sms_notifications'):
        send_sms_notification(phone, f"{title}: {body}")


_med_reminder_lock = threading.Lock()
_med_reminder_cache = {}
_med_retry_cache = {}
_med_missed_cache = {}


def _should_send_med_reminder(user_id: int, schedule_id: int, time_key: str) -> bool:
    cache_key = (user_id, schedule_id, time_key)
    now = datetime.utcnow()
    with _med_reminder_lock:
        last_sent = _med_reminder_cache.get(cache_key)
        if last_sent and (now - last_sent).total_seconds() < 60 * 50:
            return False
        _med_reminder_cache[cache_key] = now
        # cleanup old entries
        stale_keys = [k for k, v in _med_reminder_cache.items() if (now - v).total_seconds() > 60 * 120]
        for k in stale_keys:
            _med_reminder_cache.pop(k, None)
    return True


def _is_quiet_hours(now: datetime, start_time, end_time) -> bool:
    if not start_time or not end_time:
        return False
    try:
        if isinstance(start_time, str):
            start_time = datetime.strptime(start_time, '%H:%M:%S').time()
        if isinstance(end_time, str):
            end_time = datetime.strptime(end_time, '%H:%M:%S').time()
    except Exception:
        return False

    now_t = now.time()
    if start_time < end_time:
        return start_time <= now_t <= end_time
    # overnight quiet hours (e.g., 22:00 - 06:00)
    return now_t >= start_time or now_t <= end_time


def _has_intake(cur, schedule_id: int, scheduled_dt: datetime) -> bool:
    cur.execute(
        """
        SELECT id FROM medication_intake_log
        WHERE schedule_id = %s AND scheduled_time = %s
        LIMIT 1
        """,
        (schedule_id, scheduled_dt),
    )
    return bool(cur.fetchone())


def medication_reminder_worker():
    while True:
        try:
            with app.app_context():
                db = db_connect()
                cur = db.cursor()
                cur.execute(
                    """
                    SELECT id, user_id, medication_name, dosage, frequency, times
                    FROM medication_schedules
                    WHERE active = 1
                      AND (start_date IS NULL OR start_date <= UTC_DATE())
                      AND (end_date IS NULL OR end_date >= UTC_DATE())
                    """
                )
                rows = cur.fetchall() or []
                now = datetime.utcnow()

                # cache preferences per user for this run
                prefs_cache = {}

                for row in rows:
                    user_id = row.get('user_id')
                    if user_id not in prefs_cache:
                        prefs_cache[user_id] = get_notification_preferences(user_id)
                    prefs = prefs_cache[user_id]

                    tz_name = (prefs.get('timezone') or 'UTC').strip() or 'UTC'
                    try:
                        tz = ZoneInfo(tz_name)
                    except Exception:
                        tz = ZoneInfo('UTC')
                    local_now = datetime.now(tz)

                    times = row.get('times')
                    if isinstance(times, str):
                        try:
                            times = json.loads(times)
                        except Exception:
                            times = []
                    if not isinstance(times, list):
                        times = []

                    quiet = _is_quiet_hours(local_now, prefs.get('quiet_hours_start'), prefs.get('quiet_hours_end'))

                    for t in times:
                        try:
                            hh, mm = t.split(':')
                            scheduled_local = local_now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
                        except Exception:
                            continue

                        # if scheduled time in future, skip
                        if scheduled_local > local_now:
                            continue

                        scheduled_dt = scheduled_local.astimezone(ZoneInfo('UTC'))

                        # check if already logged
                        if _has_intake(cur, row.get('id'), scheduled_dt):
                            continue

                        time_key = scheduled_dt.strftime('%Y-%m-%d %H:%M')

                        # send initial reminder within 0-15 minutes window
                        if (local_now - scheduled_local).total_seconds() <= 15 * 60:
                            if quiet:
                                continue
                            if not _should_send_med_reminder(user_id, row.get('id'), time_key):
                                continue
                            title = 'Medication Reminder'
                            body = f"Time to take {row.get('medication_name')} {row.get('dosage') or ''} {row.get('frequency') or ''}."
                            create_notification(user_id, 'medication_reminder', title, body, {'schedule_id': row.get('id')})
                            _med_retry_cache[(user_id, row.get('id'), time_key)] = {"count": 1, "ts": now}
                            continue

                        # retry reminder between 15-30 minutes if not taken
                        if 15 * 60 < (local_now - scheduled_local).total_seconds() <= 30 * 60:
                            if quiet:
                                continue
                            retry_key = (user_id, row.get('id'), time_key)
                            retry_val = _med_retry_cache.get(retry_key, {"count": 0, "ts": now})
                            if retry_val.get('count', 0) >= 2:
                                continue
                            title = 'Medication Reminder (Follow-up)'
                            body = f"Reminder: please take {row.get('medication_name')} {row.get('dosage') or ''} {row.get('frequency') or ''}."
                            create_notification(user_id, 'medication_reminder', title, body, {'schedule_id': row.get('id')})
                            _med_retry_cache[retry_key] = {
                                "count": retry_val.get('count', 0) + 1,
                                "ts": now
                            }
                            continue

                        # mark missed after 60 minutes
                        if (local_now - scheduled_local).total_seconds() > 60 * 60:
                            missed_key = (user_id, row.get('id'), time_key)
                            if _med_missed_cache.get(missed_key):
                                continue
                            cur.execute(
                                """
                                INSERT INTO medication_intake_log (schedule_id, user_id, scheduled_time, status, created_at)
                                VALUES (%s, %s, %s, %s, %s)
                                """,
                                (row.get('id'), user_id, scheduled_dt, 'missed', datetime.utcnow())
                            )
                            if not quiet:
                                title = 'Missed Dose Alert'
                                body = f"You missed a dose of {row.get('medication_name')}. Please follow your care plan or consult your provider."
                                create_notification(user_id, 'medication', title, body, {'schedule_id': row.get('id')})
                            _med_missed_cache[missed_key] = now

                db.commit()
                db.close()

                # cleanup caches
                cutoff = now - timedelta(days=2)
                with _med_reminder_lock:
                    for key, val in list(_med_retry_cache.items()):
                        if isinstance(val, dict) and val.get('ts') and val.get('ts') < cutoff:
                            _med_retry_cache.pop(key, None)
                    for key, val in list(_med_missed_cache.items()):
                        if isinstance(val, datetime) and val < cutoff:
                            _med_missed_cache.pop(key, None)
        except Exception:
            pass
        time.sleep(60)


def start_medication_reminder_worker():
    if os.environ.get('ENABLE_MED_REMINDERS', '0') != '1':
        return
    # Avoid duplicate threads in Flask debug reloader
    if os.environ.get('WERKZEUG_RUN_MAIN') not in (None, 'true'):
        return
    t = threading.Thread(target=medication_reminder_worker, daemon=True)
    t.start()


@app.route('/messages/threads', methods=['GET'])
def list_message_threads():
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = current_user.get('id') or current_user.get('sub')
    db = get_db()
    cur = db.cursor()

    try:
        cur.execute(
            """
            SELECT
                CASE WHEN sender_id = %s THEN recipient_id ELSE sender_id END AS other_user_id,
                MAX(created_at) AS last_message_at
            FROM direct_messages
            WHERE sender_id = %s OR recipient_id = %s
            GROUP BY other_user_id
            ORDER BY last_message_at DESC
            """,
            (user_id, user_id, user_id)
        )
        threads = []
        for row in cur.fetchall():
            other_user_id = row['other_user_id']
            cur.execute(
                """
                SELECT dm.message_text, dm.created_at, u.full_name, u.username, u.role
                FROM direct_messages dm
                JOIN users u ON u.id = %s
                WHERE (dm.sender_id = %s AND dm.recipient_id = %s) OR (dm.sender_id = %s AND dm.recipient_id = %s)
                ORDER BY dm.created_at DESC
                LIMIT 1
                """,
                (other_user_id, user_id, other_user_id, other_user_id, user_id)
            )
            last_msg = cur.fetchone()
            cur.execute(
                """
                SELECT COUNT(*) AS unread_count
                FROM direct_messages
                WHERE recipient_id = %s AND sender_id = %s AND read_at IS NULL
                """,
                (user_id, other_user_id)
            )
            unread_row = cur.fetchone()

            threads.append({
                'other_user_id': other_user_id,
                'other_user_name': (last_msg or {}).get('full_name') or (last_msg or {}).get('username') or 'User',
                'other_user_role': (last_msg or {}).get('role'),
                'last_message': (last_msg or {}).get('message_text', ''),
                'last_message_at': (last_msg or {}).get('created_at'),
                'unread_count': (unread_row or {}).get('unread_count', 0)
            })

        return jsonify({'threads': threads})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()


@app.route('/messages', methods=['GET'])
def list_messages():
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = current_user.get('id') or current_user.get('sub')
    other_user_id = request.args.get('other_user_id', type=int)
    if not other_user_id:
        return jsonify({'error': 'other_user_id is required'}), 400

    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(
            """
            SELECT id, sender_id, recipient_id, message_text, attachment_path, created_at, read_at
            FROM direct_messages
            WHERE (sender_id = %s AND recipient_id = %s) OR (sender_id = %s AND recipient_id = %s)
            ORDER BY created_at ASC
            """,
            (user_id, other_user_id, other_user_id, user_id)
        )
        messages = [dict(row) for row in cur.fetchall()]
        return jsonify({'messages': messages})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()


@app.route('/messages/send', methods=['POST'])
def send_message():
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = current_user.get('id') or current_user.get('sub')
    data = request.get_json() or {}
    recipient_id = data.get('recipient_id')
    message_text = (data.get('message_text') or '').strip()

    if not recipient_id or not message_text:
        return jsonify({'error': 'recipient_id and message_text are required'}), 400

    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(
            """
            INSERT INTO direct_messages (sender_id, recipient_id, message_text, created_at)
            VALUES (%s, %s, %s, %s)
            """,
            (user_id, recipient_id, message_text, datetime.utcnow())
        )
        db.commit()

        create_notification(
            recipient_id,
            'direct_message',
            'New message',
            'You received a new direct message.',
            {'sender_id': user_id}
        )

        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()


@app.route('/messages/mark-read', methods=['POST'])
def mark_messages_read():
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = current_user.get('id') or current_user.get('sub')
    data = request.get_json() or {}
    other_user_id = data.get('other_user_id')
    if not other_user_id:
        return jsonify({'error': 'other_user_id is required'}), 400

    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(
            """
            UPDATE direct_messages
            SET read_at = %s
            WHERE recipient_id = %s AND sender_id = %s AND read_at IS NULL
            """,
            (datetime.utcnow(), user_id, other_user_id)
        )
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()


@app.route('/notifications', methods=['GET'])
def list_notifications():
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = current_user.get('id') or current_user.get('sub')
    unread_only = request.args.get('unread', default='0') == '1'

    db = get_db()
    cur = db.cursor()
    try:
        if unread_only:
            cur.execute(
                """
                SELECT id, type, title, body, data, is_read, created_at
                FROM notifications
                WHERE user_id = %s AND is_read = 0
                ORDER BY created_at DESC
                """,
                (user_id,)
            )
        else:
            cur.execute(
                """
                SELECT id, type, title, body, data, is_read, created_at
                FROM notifications
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT 50
                """,
                (user_id,)
            )
        notifications = [dict(row) for row in cur.fetchall()]
        return jsonify({'notifications': notifications})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()


@app.route('/notifications/mark-read', methods=['POST'])
def mark_notifications_read():
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = current_user.get('id') or current_user.get('sub')
    data = request.get_json() or {}
    notification_id = data.get('notification_id')

    db = get_db()
    cur = db.cursor()
    try:
        if notification_id:
            cur.execute(
                """
                UPDATE notifications SET is_read = 1
                WHERE id = %s AND user_id = %s
                """,
                (notification_id, user_id)
            )
        else:
            cur.execute(
                """
                UPDATE notifications SET is_read = 1
                WHERE user_id = %s
                """,
                (user_id,)
            )
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()


@app.route('/forum/posts', methods=['GET', 'POST'])
def forum_posts():
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401

    if request.method == 'POST':
        data = request.get_json() or {}
        title = (data.get('title') or '').strip()
        body = (data.get('body') or '').strip()
        condition_tag = (data.get('condition_tag') or '').strip() or None
        if not title or not body:
            return jsonify({'error': 'title and body are required'}), 400

        db = get_db()
        cur = db.cursor()
        try:
            cur.execute(
                """
                INSERT INTO forum_posts (user_id, title, body, condition_tag, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (current_user.get('id') or current_user.get('sub'), title, body, condition_tag, datetime.utcnow(), datetime.utcnow())
            )
            db.commit()
            return jsonify({'success': True, 'post_id': cur.lastrowid})
        except Exception as e:
            db.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()

    condition = request.args.get('condition_tag')
    db = get_db()
    cur = db.cursor()
    try:
        if condition:
            cur.execute(
                """
                SELECT fp.id, fp.title, fp.body, fp.condition_tag, fp.created_at, fp.updated_at,
                       u.full_name, u.username,
                       (SELECT COUNT(*) FROM forum_replies fr WHERE fr.post_id = fp.id) AS reply_count
                FROM forum_posts fp
                JOIN users u ON u.id = fp.user_id
                WHERE fp.condition_tag = %s
                ORDER BY fp.created_at DESC
                """,
                (condition,)
            )
        else:
            cur.execute(
                """
                SELECT fp.id, fp.title, fp.body, fp.condition_tag, fp.created_at, fp.updated_at,
                       u.full_name, u.username,
                       (SELECT COUNT(*) FROM forum_replies fr WHERE fr.post_id = fp.id) AS reply_count
                FROM forum_posts fp
                JOIN users u ON u.id = fp.user_id
                ORDER BY fp.created_at DESC
                LIMIT 50
                """
            )
        posts = [dict(row) for row in cur.fetchall()]
        return jsonify({'posts': posts})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()


@app.route('/forum/posts/<int:post_id>', methods=['GET'])
def forum_post_detail(post_id):
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401

    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(
            """
            SELECT fp.id, fp.title, fp.body, fp.condition_tag, fp.created_at, fp.updated_at,
                   u.full_name, u.username
            FROM forum_posts fp
            JOIN users u ON u.id = fp.user_id
            WHERE fp.id = %s
            """,
            (post_id,)
        )
        post = cur.fetchone()
        if not post:
            return jsonify({'error': 'Post not found'}), 404

        cur.execute(
            """
            SELECT fr.id, fr.body, fr.created_at, u.full_name, u.username
            FROM forum_replies fr
            JOIN users u ON u.id = fr.user_id
            WHERE fr.post_id = %s
            ORDER BY fr.created_at ASC
            """,
            (post_id,)
        )
        replies = [dict(row) for row in cur.fetchall()]
        return jsonify({'post': dict(post), 'replies': replies})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()


@app.route('/forum/posts/<int:post_id>/replies', methods=['POST'])
def forum_reply(post_id):
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json() or {}
    body = (data.get('body') or '').strip()
    if not body:
        return jsonify({'error': 'body is required'}), 400

    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(
            """
            INSERT INTO forum_replies (post_id, user_id, body, created_at)
            VALUES (%s, %s, %s, %s)
            """,
            (post_id, current_user.get('id') or current_user.get('sub'), body, datetime.utcnow())
        )
        db.commit()
        return jsonify({'success': True, 'reply_id': cur.lastrowid})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()


@app.route('/health', methods=['GET'])
def health_check():
    """Production health check endpoint for load balancers and monitoring."""
    try:
        # Check database connectivity
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT 1")
        db_ok = True
        cur.close()
    except Exception as e:
        print(f"[HEALTH CHECK] Database error: {e}")
        db_ok = False
    
    # Determine overall health status
    status = 'healthy' if db_ok else 'degraded'
    http_status = 200 if db_ok else 503  # 503 Service Unavailable if degraded
    
    return jsonify({
        'status': status,
        'database': 'connected' if db_ok else 'disconnected',
        'timestamp': datetime.utcnow().isoformat(),
        'version': '1.0.0'
    }), http_status


@app.route('/test/notifications', methods=['POST'])
def test_notifications():
    """Test endpoint to verify email and SMS delivery"""
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json() or {}
    test_email = data.get('email')
    test_phone = data.get('phone')
    
    results = {
        'email_sent': False,
        'sms_sent': False,
        'email_configured': False,
        'sms_configured': False
    }

    # Test email
    if test_email:
        results['email_configured'] = bool(
            os.environ.get('SENDGRID_API_KEY') or 
            (os.environ.get('SMTP_HOST') and os.environ.get('SMTP_USER'))
        )
        if results['email_configured']:
            results['email_sent'] = send_email_notification(
                test_email,
                'Test Notification from Medical AI',
                'This is a test notification to verify email delivery is working correctly.'
            )

    # Test SMS
    if test_phone:
        results['sms_configured'] = bool(
            os.environ.get('DARAJA_CONSUMER_KEY') and 
            os.environ.get('ENABLE_DARAJA_SMS') == '1'
        )
        if results['sms_configured']:
            results['sms_sent'] = send_sms_notification(
                test_phone,
                'Test SMS from Medical AI: Your notifications are working!'
            )

    return jsonify(results)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    start_medication_reminder_worker()
    
    # Production HTTPS configuration
    ssl_context = None
    is_production = os.environ.get("FLASK_ENV") == "production"
    
    if is_production:
        cert_path = os.environ.get("SSL_CERT_PATH", "/etc/letsencrypt/live/yourdomain.com/fullchain.pem")
        key_path = os.environ.get("SSL_KEY_PATH", "/etc/letsencrypt/live/yourdomain.com/privkey.pem")
        
        if os.path.exists(cert_path) and os.path.exists(key_path):
            ssl_context = (cert_path, key_path)
            print("[SECURITY] Running with HTTPS (SSL/TLS enabled)")
        else:
            print("[WARNING] HTTPS certificate files not found at:")
            print(f"  Cert: {cert_path}")
            print(f"  Key: {key_path}")
            print("[WARNING] Running without HTTPS - ensure reverse proxy (Nginx/Apache) handles SSL")
    
    # Production: disable debug mode, disable Werkzeug reloader
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    
    if debug_mode:
        print("[WARNING] Debug mode ENABLED - only for development!")
    else:
        print("[SECURITY] Debug mode DISABLED - production ready")
    
    # Flask production settings
    app.config['JSON_SORT_KEYS'] = False
    app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False
    
    app.run(
        host=os.environ.get("BIND_HOST", "0.0.0.0"),
        port=port,
        debug=debug_mode,
        ssl_context=ssl_context,
        use_reloader=False  # Disable Werkzeug reloader in production
    )