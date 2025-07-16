import json
import requests
import time
import uuid
import os
from flask import Flask, request, jsonify, session, Response, stream_with_context
import google.generativeai as genai
from flask_dance.contrib.google import make_google_blueprint, google
from authlib.integrations.flask_client import OAuth
from flask_cors import CORS # Import CORS

app = Flask(__name__)
CORS(app) # Enable CORS for all routes
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "your_fallback_secret_key_here")

# For Canvas, GEMINI_API_KEY can be left empty; Canvas will inject it.
GEMINI_API_KEY = "AIzaSyDQJcS5wwBi65AdfW5zHT2ayu1ShWgWcJg"

genai.configure(api_key=GEMINI_API_KEY)
chat_model = genai.GenerativeModel("gemini-2.0-flash")

CHAT_HISTORY_DIR = os.path.join(app.root_path, 'chat_history')
os.makedirs(CHAT_HISTORY_DIR, exist_ok=True)

# --- Chat History Management Functions ---
def get_user_id():
    if 'user_id' in session:
        return session['user_id']
    if 'temp_user_id' not in session:
        session['temp_user_id'] = str(uuid.uuid4())
        session['user_id'] = session['temp_user_id']
    return session['temp_user_id']

def get_chat_file_path(user_id, chat_id):
    safe_user_id = "".join(c for c in user_id if c.isalnum() or c in ('-', '_')).strip()
    return os.path.join(CHAT_HISTORY_DIR, f"{safe_user_id}_{chat_id}.json")

def load_chat_history_from_file(user_id, chat_id):
    file_path = get_chat_file_path(user_id, chat_id)
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"Warning: Could not decode JSON from {file_path}. Starting with empty chat.")
            return []
        except Exception as e:
            print(f"Error loading chat history from {file_path}: {e}")
            return []
    return []

def save_chat_history_to_file(user_id, chat_id, chat_data):
    file_path = get_chat_file_path(user_id, chat_id)
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(chat_data, f, indent=4)
    except IOError as e:
        print(f"Error saving chat history to {file_path}: {e}")

# --- AI Interaction Functions (Simplified) ---
def ask_ai_with_memory(user_id, chat_id, instruction):
    try:
        current_chat_history = load_chat_history_from_file(user_id, chat_id)

        gemini_chat_history = []
        system_instruction = (
            "You are Vexara, a smart and friendly AI assistant for general chat. "
            "Respond in a helpful and clear way, like a human who cares about helping. "
            "Use Markdown for formatting your responses. Keep replies concise unless more detail is requested."
        )

        gemini_chat_history.append({"role": "user", "parts": [{"text": system_instruction}]})
        gemini_chat_history.append({"role": "model", "parts": [{"text": "Hello! How can I assist you today?"}]})
        
        for msg in current_chat_history:
            if 'text' in msg: # Only include text messages
                role = "user" if msg['type'] == 'user' else "model"
                gemini_chat_history.append({"role": role, "parts": [{"text": msg['text']}]})

        final_user_parts = [{"text": instruction}]
        gemini_chat_history.append({"role": "user", "parts": final_user_parts})

        response = chat_model.generate_content(gemini_chat_history)
        return response.text.strip()
    except genai.types.StopCandidateException as e:
        print(f"Gemini AI Error: Content generation stopped due to safety policies. {e}")
        return "I apologize, but I cannot generate a response for that query due to safety policies."
    except Exception as e:
        print(f"Gemini AI Error: {e}")
        return "Sorry, I'm having trouble processing your request right now. Please try again later."

# --- Flask Routes ---
# Removed the root '/' route that rendered index.html

@app.route('/ask', methods=['POST'])
def handle_query():
    user_id = get_user_id()
    chat_id = request.form.get('chat_id') 
    instruction = request.form.get('instruction', '').strip()

    if not chat_id:
        return jsonify({"response": "Error: Chat ID not provided."}), 400
    if not instruction:
        return jsonify({"response": "Please provide a valid input."}), 400

    current_chat_history = load_chat_history_from_file(user_id, chat_id)
    current_chat_history.append({"type": "user", "text": instruction, "timestamp": time.time()})
    save_chat_history_to_file(user_id, chat_id, current_chat_history)

    ai_response = ask_ai_with_memory(user_id, chat_id, instruction) 
    
    current_chat_history = load_chat_history_from_file(user_id, chat_id) 
    current_chat_history.append({"type": "bot", "text": ai_response, "timestamp": time.time()})
    save_chat_history_to_file(user_id, chat_id, current_chat_history)

    # Return a streaming response
    def generate_response_stream():
        yield ai_response # Yield the full response at once

    return Response(stream_with_context(generate_response_stream()), mimetype='text/plain')

# Authentication Routes (modified to return JSON or simple responses)
google_bp = make_google_blueprint(
    client_id="978102306464-qdjll3uos10m1nd5gcnr9iql9688db58.apps.googleusercontent.com",
    client_secret="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",
    redirect_url="/google_login/authorized",
    scope=["openid", "https://www.googleapis.com/auth/userinfo.email", "https://www.googleapis.com/auth/userinfo.profile"]
)
app.register_blueprint(google_bp, url_prefix="/google_login")

oauth = OAuth(app)
microsoft = oauth.register(
    name='microsoft',
    client_id="your_microsoft_client_id",
    client_secret="your_microsoft_client_secret",
    access_token_url='https://login.microsoftonline.com/common/oauth2/v2.0/token',
    authorize_url='https://login.microsoftonline.com/common/oauth2/v2.0/authorize',
    api_base_url='https://graph.microsoft.com/v1.0/',
    client_kwargs={'scope': 'User.Read'}
)

@app.route('/google_login/authorized')
def google_login_authorized():
    if not google.authorized:
        return jsonify({"status": "error", "message": "Google authorization failed."}), 401
    try:
        user_info = google.get("/oauth2/v2/userinfo")
        if user_info.ok:
            session['user'] = user_info.json().get("email")
            session['user_id'] = f"google_{user_info.json().get('id')}"
            print(f"User {session['user']} logged in with Google.")
            return jsonify({"status": "success", "message": "Logged in with Google.", "user_id": session['user_id']})
        else:
            print(f"Google user info request failed: {user_info.text}")
            return jsonify({"status": "error", "message": "Google user info request failed."}), 500
    except Exception as e:
        print(f"Error during Google login: {e}")
        return jsonify({"status": "error", "message": f"Error during Google login: {str(e)}"}), 500

@app.route('/login')
def login():
    # This route is now a placeholder for the backend.
    # The frontend will handle the actual login UI.
    if 'user_id' in session:
        return jsonify({"status": "success", "message": "Already logged in.", "user_id": session['user_id']})
    return jsonify({"status": "info", "message": "Please log in via the frontend."})

@app.route('/guest_login')
def guest_login():
    session.clear()
    temp_id = str(uuid.uuid4())
    session['temp_user_id'] = temp_id
    session['user_id'] = temp_id
    session['is_guest'] = True
    print(f"User logged in as guest with temporary ID: {temp_id}")
    return jsonify({"status": "success", "message": "Logged in as guest.", "user_id": session['user_id']})

@app.route('/logout')
def logout():
    session.clear()
    return jsonify({"status": "success", "message": "Logged out."})

@app.route('/user_info', methods=['GET'])
def user_info():
    user_email = session.get('user', None)
    user_id = session.get('user_id', None)
    return jsonify({"user_email": user_email, "user_id": user_id})

# Chat Management Routes (kept for history persistence)
@app.route('/start_new_chat', methods=['POST'])
def start_new_chat_endpoint():
    user_id = get_user_id()
    new_chat_id = str(uuid.uuid4())
    save_chat_history_to_file(user_id, new_chat_id, [])
    has_previous_chats = False
    for filename in os.listdir(CHAT_HISTORY_DIR):
        if filename.startswith(f"{user_id}_") and filename.endswith(".json") and filename != f"{user_id}_{new_chat_id}.json":
            has_previous_chats = True
            break
    return jsonify({"status": "success", "chat_id": new_chat_id, "has_previous_chats": has_previous_chats})

@app.route('/clear_all_chats', methods=['POST'])
def clear_all_chats_endpoint():
    user_id = get_user_id()
    try:
        count = 0
        for filename in os.listdir(CHAT_HISTORY_DIR):
            if filename.startswith(f"{user_id}_") and filename.endswith(".json"):
                os.remove(os.path.join(CHAT_HISTORY_DIR, filename))
                count += 1
        print(f"Cleared {count} chat files for user: {user_id}")
        return jsonify({"status": "success", "message": f"Cleared {count} chats."})
    except Exception as e:
        print(f"Error clearing all chats for user {user_id}: {e}")
        return jsonify({"status": "error", "message": "Failed to clear all chats.", "error": str(e)}), 500

@app.route('/get_chat_history_list', methods=['GET'])
def get_chat_history_list():
    user_id = get_user_id()
    chat_summaries = []
    user_chat_files = [f for f in os.listdir(CHAT_HISTORY_DIR) if f.startswith(f"{user_id}_") and f.endswith(".json")]
    user_chat_files.sort(key=lambda f: os.path.getmtime(os.path.join(CHAT_HISTORY_DIR, f)), reverse=True)
    for filename in user_chat_files:
        chat_id = filename.replace(f"{user_id}_", "").replace(".json", "")
        chat_data = load_chat_history_from_file(user_id, chat_id)
        display_title = "New Chat"
        if chat_data:
            first_meaningful_message = next((
                msg for msg in chat_data 
                if msg['type'] == 'user' and msg['text'].strip()
            ), None)
            if first_meaningful_message:
                display_title = first_meaningful_message['text'].split('\n')[0][:30]
                if len(first_meaningful_message['text'].split('\n')[0]) > 30:
                    display_title += "..."
            elif chat_data and chat_data[0]['type'] == 'bot':
                display_title = chat_data[0]['text'].split('\n')[0][:30]
                if len(chat_data[0]['text'].split('\n')[0]) > 30:
                    display_title += "..."
            if not display_title.strip() or display_title == "New Chat":
                display_title = f"Chat {chat_id[:8]}"
        else:
             display_title = f"Chat {chat_id[:8]}"
        chat_summaries.append({'id': chat_id, 'title': display_title})
    return jsonify(chat_summaries)

@app.route('/get_chat_messages/<chat_id>', methods=['GET'])
def get_chat_messages(chat_id):
    user_id = get_user_id()
    chat_data = load_chat_history_from_file(user_id, chat_id)
    return jsonify(chat_data)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
