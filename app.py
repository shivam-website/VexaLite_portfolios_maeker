import os
import uuid
import time
import json
import requests
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
chat_model = genai.GenerativeModel("gemini-2.0-flash")

# --- Chat History Folder ---
CHAT_HISTORY_DIR = os.path.join(app.root_path, 'chat_history')
os.makedirs(CHAT_HISTORY_DIR, exist_ok=True)

# --- User Management ---
def get_user_id():
    if 'user_id' in session:
        return session['user_id']
    session['user_id'] = str(uuid.uuid4())
    return session['user_id']

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

# --- Gemini Response ---
def ask_ai_with_memory(user_id, chat_id, instruction):
    history = load_chat_history(user_id, chat_id)
    messages = [
        {"role": "user", "parts": [{"text": (
            "You are Vexara, a smart and friendly AI assistant. "
            "Respond with clear, helpful Markdown-formatted answers."
        )}]},
        {"role": "model", "parts": [{"text": "Hello! How can I assist you today?"}]}
    ]

    for msg in history:
        role = "user" if msg["type"] == "user" else "model"
        messages.append({"role": role, "parts": [{"text": msg["text"]}]})
    
    messages.append({"role": "user", "parts": [{"text": instruction}]})
    response = chat_model.generate_content(messages)
    return response.text.strip()

# --- Routes ---
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

# Optional: logout, login, guest login (same as your code)
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
