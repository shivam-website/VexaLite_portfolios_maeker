import os
import uuid
import time
import json
from flask import Flask, request, jsonify, session, Response, stream_with_context
from flask_cors import CORS
import google.generativeai as genai

app = Flask(__name__)
CORS(app)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "fallback_secret")

# --- Gemini Setup ---
GEMINI_API_KEY = "AIzaSyDQJcS5wwBi65AdfW5zHT2ayu1ShWgWcJg"
genai.configure(api_key=GEMINI_API_KEY)
chat_model = genai.GenerativeModel("gemini-2.0-flash")

# --- Strict System Instructions ---
SYSTEM_PROMPT = """
You are Vexara, the official AI assistant for Shivam Sah's portfolio services at portfolios.fwh.is. 

ABOUT SHIVAM:
- 14-year-old developer from Nepal
- Specializes in AI-powered portfolio websites
- Offers custom chatbot integration
- Provides fast, modern web solutions

YOUR RULES:
1. ONLY discuss:
   - Portfolio website services
   - Pricing (redirect to WhatsApp)
   - Shivam's work examples
   - Technical features of his offerings

2. For portfolio pricing say:
   "Portfolio pricing starts at $X depending on features. For exact quotes, message Shivam on WhatsApp: [NUMBER]"

3. REJECT all other topics with:
   "I specialize only in Shivam's portfolio services. Let me know if you need info about his web development offerings!"

RESPONSE FORMAT:
- Friendly but professional tone
- Use bullet points for features
- Keep answers under 3 sentences
"""

# --- Chat Management ---
CHAT_HISTORY_DIR = 'chat_history'
os.makedirs(CHAT_HISTORY_DIR, exist_ok=True)

def get_user_id():
    return session.get('user_id', str(uuid.uuid4()))

def get_chat_file(user_id, chat_id):
    return f"{CHAT_HISTORY_DIR}/{user_id}_{chat_id}.json"

def load_chat(user_id, chat_id):
    try:
        with open(get_chat_file(user_id, chat_id), 'r') as f:
            return json.load(f)
    except:
        return []

def save_chat(user_id, chat_id, messages):
    with open(get_chat_file(user_id, chat_id), 'w') as f:
        json.dump(messages, f)

# --- AI Response Generator ---
def generate_response(user_id, chat_id, query):
    history = load_chat(user_id, chat_id)
    
    messages = [{"role": "user", "parts": [SYSTEM_PROMPT]}]
    messages.extend(history)
    messages.append({"role": "user", "parts": [query]})
    
    response = chat_model.generate_content(messages)
    return response.text

# --- Routes ---
@app.route('/ask', methods=['POST'])
def ask():
    user_id = get_user_id()
    chat_id = request.json.get('chat_id', str(uuid.uuid4()))
    query = request.json.get('query', '').strip()
    
    if not query:
        return jsonify({"error": "Empty query"}), 400
    
    # Save user message
    history = load_chat(user_id, chat_id)
    history.append({"role": "user", "parts": [query]})
    
    # Get AI response
    response = generate_response(user_id, chat_id, query)
    
    # Save AI response
    history.append({"role": "model", "parts": [response]})
    save_chat(user_id, chat_id, history)
    
    return jsonify({
        "response": response,
        "chat_id": chat_id
    })

@app.route('/new_chat', methods=['POST'])
def new_chat():
    user_id = get_user_id()
    chat_id = str(uuid.uuid4())
    save_chat(user_id, chat_id, [])
    return jsonify({"chat_id": chat_id})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
