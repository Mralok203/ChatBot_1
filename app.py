# ============================================================
# Alok's AI — Flask Backend (No JavaScript)
# All navigation and messaging done via HTML forms + redirects
# ============================================================

import os
import uuid
import json
from datetime import datetime, timezone
from flask import Flask, request, redirect, url_for, render_template
import requests

import google.generativeai as genai

def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()

app = Flask(__name__)

# ── Config ───────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "xxxxxxxxxxxxxxxxxxxxxxxxxxx")
DATA_FILE      = "data/conversations.json"
MODEL_NAME = "gemini-2.5-flash"


PERSONAL_INFO = {
    "name": "Alok Kumar Dash",
    "role": "AI/ML Engineer Intern",
    "skills": ["Python", "SQL", "Machine Learning", "TensorFlow", "Flask"],
    "education": "B.Tech CSE (AI), Expected 2026",
    "projects": [
        "Software Defect Prediction System",
        "Emotion Recognition System",
        "Diwali Sales Analytics"
    ],
    "experience": [
        "AI Intern at Smaket AI",
        "Data Science Intern at NullClass",
        "Software Development Intern at KTech"
    ],
    "links": {
        "linkedin": "YOUR_LINKEDIN_LINK",
        "github": "YOUR_GITHUB_LINK",
        "portfolio": "YOUR_PORTFOLIO_LINK"
    }
}


SYSTEM_PROMPT = f"""
You are Alok's AI assistant.

You know the following information about Alok:
Name: {PERSONAL_INFO['name']}
Role: {PERSONAL_INFO['role']}
Skills: {', '.join(PERSONAL_INFO['skills'])}
Projects: {', '.join(PERSONAL_INFO['projects'])}
Experience: {', '.join(PERSONAL_INFO['experience'])}

If someone asks about Alok, answer professionally using this info.

If someone asks for social media:
Direct them to:
LinkedIn: {PERSONAL_INFO['links']['linkedin']}
GitHub: {PERSONAL_INFO['links']['github']}
Portfolio: {PERSONAL_INFO['links']['portfolio']}

Keep answers short and natural.
"""

genai.configure(api_key=GEMINI_API_KEY)

# ── Storage helpers ───────────────────────────────────────────

def load_conversations() -> dict:
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def save_conversations(data: dict) -> None:
    os.makedirs("data", exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def generate_title(text: str) -> str:
    words = text.strip().split()
    title = " ".join(words[:6])
    return (title[:40] + "…") if len(title) > 40 else title

def format_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%-I:%M %p")
    except Exception:
        return ""

# ── Routes ────────────────────────────────────────────────────

@app.route("/")
def index():
    """Home — show welcome screen with sidebar."""
    conversations = load_conversations()
    sidebar = sorted(conversations.values(),
                     key=lambda c: c.get("updated_at", ""), reverse=True)
    return render_template("index.html",
                           sidebar=sidebar,
                           active_conv=None,
                           messages=[],
                           error=None)


@app.route("/new", methods=["POST"])
def new_conversation():
    """Create a new conversation and redirect to it."""
    conversations = load_conversations()
    cid = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    conversations[cid] = {
        "id":         cid,
        "title":      "New Chat",
        "created_at": now,
        "updated_at": now,
        "messages":   [],
    }
    save_conversations(conversations)
    return redirect(url_for("conversation", cid=cid))


@app.route("/chat/<cid>")
def conversation(cid):
    """Show a single conversation page."""
    conversations = load_conversations()
    if cid not in conversations:
        return redirect(url_for("index"))

    sidebar = sorted(conversations.values(),
                     key=lambda c: c.get("updated_at", ""), reverse=True)

    return render_template("index.html",
                           sidebar=sidebar,
                           active_conv=conversations[cid],
                           messages=conversations[cid]["messages"],
                           error=request.args.get("error"))


@app.route("/chat/<cid>/send", methods=["POST"])
def send_message(cid):
    """Handle a submitted message form, call Gemini, redirect back."""
    conversations = load_conversations()
    if cid not in conversations:
        return redirect(url_for("index"))

    user_text = request.form.get("message", "").strip()
    if not user_text:
        return redirect(url_for("conversation", cid=cid, error="empty"))

    conv = conversations[cid]
    now  = datetime.utcnow().isoformat()

    # Save user message
    conv["messages"].append({
        "id":        str(uuid.uuid4()),
        "role":      "user",
        "content":   user_text,
        "timestamp": now,
    })

    # Auto-title from first message
    if len(conv["messages"]) == 1:
        conv["title"] = generate_title(user_text)

    # Build Gemini history from prior messages
    history = []
    for msg in conv["messages"][:-1]:
        role = "user" if msg["role"] == "user" else "model"
        history.append({"role": role, "parts": [msg["content"]]})

    # Call Gemini
    try:
        model    = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
        chat     = model.start_chat(history=history)
        response = chat.send_message(user_text)
        ai_text  = response.text

    except Exception as exc:
        err = str(exc).lower()
        if "api_key" in err or "api key" in err or "invalid" in err:
            ai_text = " Invalid API Key — open app.py and replace YOUR_GEMINI_API_KEY_HERE with your real key from https://aistudio.google.com/app/apikey"
        elif "quota" in err or "limit" in err or "429" in err:
            ai_text = " API Quota Exceeded — wait a moment and try again."
        elif "network" in err or "connection" in err:
            ai_text = " Network Error — check your internet connection."
        else:
            print(f"[Alok's AI ERROR] {exc}")
            ai_text = f" Error: {str(exc)[:300]}"

    # Save AI message
    conv["messages"].append({
        "id":        str(uuid.uuid4()),
        "role":      "assistant",
        "content":   ai_text,
        "timestamp": datetime.utcnow().isoformat(),
    })
    conv["updated_at"] = datetime.utcnow().isoformat()

    save_conversations(conversations)
    return redirect(url_for("conversation", cid=cid) + "#bottom")


@app.route("/chat/<cid>/delete", methods=["POST"])
def delete_conversation(cid):
    """Delete a conversation and go home."""
    conversations = load_conversations()
    conversations.pop(cid, None)
    save_conversations(conversations)
    return redirect(url_for("index"))


# ── Template filter ───────────────────────────────────────────

@app.template_filter("ftime")
def ftime_filter(iso):
    return format_time(iso)


if __name__ == "__main__":
    print("=" * 50)
    print("  🚀  Alok's AI → http://localhost:5000")
    print("=" * 50)
    app.run(debug=True, port=5000)
