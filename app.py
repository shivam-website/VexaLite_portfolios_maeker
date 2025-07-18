import os
import uuid
import time
import json
import google.generativeai as genai
from flask import Flask, request, jsonify, session, Response, stream_with_context, render_template
from flask_cors import CORS
from flask_dance.contrib.google import make_google_blueprint, google
from authlib.integrations.flask_client import OAuth

app = Flask(__name__)
CORS(app)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "fallback_secret")

# --- Gemini Setup ---
GEMINI_API_KEY = "AIzaSyDQJcS5wwBi65AdfW5zHT2ayu1ShWgWcJg"
genai.configure(api_key=GEMINI_API_KEY)
chat_model = genai.GenerativeModel("gemini-1.5-flash")  # Updated to faster model

# --- Chat History Folder ---
CHAT_HISTORY_DIR = os.path.join(app.root_path, 'chat_history')
os.makedirs(CHAT_HISTORY_DIR, exist_ok=True)

# --- Strict Instructions ---
SHIVAM_PROFILE = """
**About Shivam Sah:**
- 14-year-old developer from Nepal
- Specializes in AI-powered portfolio websites
- Offers custom chatbot integration
- Builds fast, modern web solutions

**Pricing Info:**
- Basic Portfolio: $X
- Premium Portfolio: $Y 
- Custom Solutions: Varies
(Always redirect to WhatsApp for exact quotes)
"""

SYSTEM_INSTRUCTIONS = f"""
You are Vexara, the official AI assistant for Shivam Sah's portfolio services at portfolios.fwh.is.

**Your Rules:**
1. ONLY discuss:
   - Portfolio website services
   - Shivam's work examples
   - Technical features
   - Pricing (redirect to WhatsApp)

2. REJECT all other topics with:
   "I specialize only in Shivam's portfolio services. Would you like info about his web development offerings?"

**Response Style:**
- Friendly but professional
- Use bullet points for features
- Keep answers under 3 sentences
- Always mention WhatsApp for pricing
- Never reveal you're an AI

**Shivam's Info:**
{SHIVAM_PROFILE}
"""

# --- User Management --- 
def get_user_id():
    if 'user_id' in session:
        return session['user_id']
    user_id = request.headers.get("X-Client-ID")
    return user_id if user_id else str(uuid.uuid4())

def get_chat_file_path(user_id, chat_id):
    return os.path.join(CHAT_HISTORY_DIR, f"{user_id}_{chat_id}.json")

def load_chat_history(user_id, chat_id):
    path = get_chat_file_path(user_id, chat_id)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_chat_history(user_id, chat_id, data):
    path = get_chat_file_path(user_id, chat_id)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

# --- Optimized AI Response ---
def ask_ai_with_memory(user_id, chat_id, instruction):
    history = load_chat_history(user_id, chat_id)

    messages = [
        {"role": "system", "parts": [{"text": SYSTEM_INSTRUCTIONS}]},
        *[{"role": "user" if msg["type"] == "user" else "model", 
           "parts": [{"text": msg["text"]}]} for msg in history],
        {"role": "user", "parts": [{"text": instruction}]}
    ]

    # First message greeting
    if not history:
        messages.insert(1, {"role": "model", "parts": [{"text": (
            "Hi! I'm Vexara, Shivam's assistant. Ask me about:\n"
            "- Portfolio pricing\n- Website features\n- Work examples\n"
            "- How to get started"
        )}]})

    response = chat_model.generate_content(messages)
    return response.text.strip()

# --- Your Original Routes (Unchanged) ---
@app.route('/embed')
def serve_embed_ui():
    return render_template("embed.html")

@app.route('/ask', methods=['GET', 'POST'])
def handle_query():
    if request.method == 'GET':
        return jsonify({"status": "ok", "message": "Use POST to send chat."})

    user_id = get_user_id()
    chat_id = request.form.get('chat_id')
    instruction = request.form.get('instruction', '').strip()

    if not chat_id or not instruction:
        return jsonify({"response": "Missing chat_id or instruction."}), 400

    history = load_chat_history(user_id, chat_id)
    history.append({"type": "user", "text": instruction, "timestamp": time.time()})
    save_chat_history(user_id, chat_id, history)

    ai_reply = ask_ai_with_memory(user_id, chat_id, instruction)

    history = load_chat_history(user_id, chat_id)
    history.append({"type": "bot", "text": ai_reply, "timestamp": time.time()})
    save_chat_history(user_id, chat_id, history)

    def stream_reply():
        yield ai_reply

    return Response(stream_with_context(stream_reply()), mimetype='text/plain')

@app.route('/start_new_chat', methods=['POST'])
def start_new_chat():
    user_id = get_user_id()
    chat_id = str(uuid.uuid4())
    save_chat_history(user_id, chat_id, [])
    return jsonify({"status": "success", "chat_id": chat_id})

@app.route('/guest_login')
def guest_login():
    session.clear()
    temp_id = str(uuid.uuid4())
    session['user_id'] = temp_id
    return jsonify({"status": "success", "user_id": temp_id})

@app.route('/logout')
def logout():
    session.clear()
    return jsonify({"status": "success", "message": "Logged out."})

@app.route('/user_info')
def user_info():
    return jsonify({
        "user_id": session.get("user_id"),
        "user_email": session.get("user")
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
