import os
import re

def fix_file():
    path = "app.py"
    if not os.path.exists(path):
        print("Error: app.py not found")
        return

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Part 1: Start to class definition line 79 (lines[0]..lines[78])
    part1_end = 79
    part1 = lines[:part1_end]

    # Part 3: Find generate_response_stream
    part3_start = -1
    for i, line in enumerate(lines):
        if i > 200 and line.strip().startswith("def generate_response_stream"):
            part3_start = i
            break
    
    if part3_start == -1:
        print("Error: could not find generate_response_stream")
        return

    part3 = lines[part3_start:]

    # Fix string
    fix_str = r'''    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            self.client = None
        else:
            if not HAS_GENAI:
                self.client = None
            else:
                try:
                    self.client = genai.Client(api_key=self.api_key)
                except Exception as e:
                    print(f"Error initializing Gemini client: {e}")
                    self.client = None

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

    def check_critical_condition(self, text: str) -> bool:
        """Check if the text contains critical medical keywords."""
        if not text:
            return False
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in self.critical_keywords)

    def generate_response(self, user_input: str, patient_info: Optional[dict] = None, session_id: Optional[int] = None) -> str:
        """Generate a response using Gemini."""
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
                        conversation_history += f"\n{role}: {msg['content'][:200]}"
            except Exception as e:
                print(f"Error fetching conversation history: {e}")

        # Build comprehensive prompt with context
        prompt = f"{self.system_prompt}{patient_context}{conversation_history}\n\nPatient's Current Question: {text}\n\nAssistant (provide a personalized response based on the patient's profile and conversation history):"

         # If genai client is not available, return a fallback message
        if not self.client:
            return (
                "(Prototype mode - no model client configured) "
                "I can help with general health information. Please consult a healthcare professional for a diagnosis."
            )

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=[
                    types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
                ]
            )
            response_text = response.text
            
            if not response_text:
                response_text = "I'm sorry, I couldn't generate a response right now."

            # Clean up markdown formatting characters (# and ***)
            response_text = re.sub(r'^[#*\s]+', '', response_text)  # Remove leading # and ***
            response_text = re.sub(r'\*\*\*', '', response_text)  # Remove bold markers
            response_text = response_text.strip()

            disclaimer = (
                "\n\n⚠️ Disclaimer: This is not a substitute for professional medical advice. "
                "Please consult with a healthcare professional for diagnosis and treatment."
            )
            return response_text + disclaimer
        except Exception:
            return "I'm sorry — an internal error occurred while generating a response."

'''
    # Append newline at the end of fix_str
    fix_str += "\n"

    new_content = "".join(part1) + fix_str + "".join(part3)
    
    with open("app.py", "w", encoding="utf-8") as f:
        f.write(new_content)
    
    print("Successfully patched app.py")

if __name__ == "__main__":
    fix_file()
