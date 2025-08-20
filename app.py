from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, os, re, time
from datetime import datetime
from pathlib import Path

APP_NAME = "OSPOLY Chatbot By Adedeji Yinusa (23/CTN/0809) and Ayodele Oladapo (23/CTN/0810)"
DB_PATH = "database.db"
SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "change-this-secret-in-production")

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def setup_db():
    conn = get_db()
    c = conn.cursor()
    # Create tables if they don't exist
    c.execute("""CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS faqs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")
    conn.commit()

    # Seed a default admin if none exists
    c.execute("SELECT COUNT(*) AS n FROM admins")
    n_admins = c.fetchone()["n"]
    if n_admins == 0:
        username = "admin"
        password_hash = generate_password_hash("admin123")
        c.execute("INSERT INTO admins (username, password_hash, created_at) VALUES (?, ?, ?)",
                  (username, password_hash, datetime.utcnow().isoformat()))
        conn.commit()
        print("Default admin created -> username: admin, password: admin123")

    # Seed a few sample Q&A if empty
    c.execute("SELECT COUNT(*) AS n FROM faqs")
    n_faq = c.fetchone()["n"]
    if n_faq == 0:
        samples = [
            ("What is OSPOLY?", "Osun State Polytechnic, Iree (OSPOLY) is an institution offering ND and HND programmes."),
            ("How can I contact the registrar?", "You can contact the Registrar via the official school portal or visit the administrative office during working hours."),
            ("What are the admission requirements?", "Requirements vary by programme; typically you need relevant O'level credits and JAMB score as specified by OSPOLY."),
        ]
        now = datetime.utcnow().isoformat()
        for q, a in samples:
            c.execute("INSERT INTO faqs (question, answer, created_at, updated_at) VALUES (?, ?, ?, ?)", (q, a, now, now))
        conn.commit()

    conn.close()

def normalize_text(txt: str) -> list:
    txt = txt.lower()
    tokens = re.findall(r"[a-z0-9']+", txt)
    return tokens

def score_match(query: str, candidate_q: str) -> float:
    # Simple token overlap + soft scoring
    q_tokens = set(normalize_text(query))
    c_tokens = set(normalize_text(candidate_q))
    if not q_tokens or not c_tokens:
        return 0.0
    overlap = len(q_tokens & c_tokens)
    recall = overlap / len(q_tokens)
    precision = overlap / len(c_tokens)
    return 0.6 * recall + 0.4 * precision

@app.route("/")
def index():
    return render_template("index.html", app_name=APP_NAME)

@app.post("/api/ask")
def api_ask():
    data = request.get_json(silent=True) or {}
    user_msg = (data.get("message") or "").strip()
    if not user_msg:
        return jsonify({"reply": "Please type a question.", "meta": {"matched": None, "score": 0}})

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, question, answer FROM faqs")
    rows = c.fetchall()
    conn.close()

    best = None
    best_score = 0.0
    for row in rows:
        s = score_match(user_msg, row["question"])
        if s > best_score:
            best_score = s
            best = row

    threshold = 0.25  # tune if needed
    if best and best_score >= threshold:
        return jsonify({
            "reply": best["answer"],
            "meta": {"matched": {"id": best["id"], "question": best["question"]}, "score": round(best_score, 3)}
        })
    else:
        return jsonify({
            "reply": "Sorry, I couldn't find an exact answer. Please contact an admin or try rephrasing your question.",
            "meta": {"matched": None, "score": round(best_score, 3)}
        })

# -------- Admin Auth --------
@app.get("/admin/login")
def admin_login_form():
    return render_template("admin_login.html", app_name=APP_NAME)

@app.post("/admin/login")
def admin_login():
    username = request.form.get("username","").strip()
    password = request.form.get("password","").strip()
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM admins WHERE username = ?", (username,))
    row = c.fetchone()
    conn.close()
    if row and check_password_hash(row["password_hash"], password):
        session["admin_id"] = row["id"]
        session["admin_name"] = row["username"]
        flash("Welcome back!", "success")
        return redirect(url_for("admin_panel"))
    flash("Invalid credentials", "danger")
    return redirect(url_for("admin_login_form"))

@app.get("/admin/logout")
def admin_logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("admin_login_form"))

def admin_required():
    return "admin_id" in session

# -------- Admin Panel & CRUD --------
@app.get("/admin")
def admin_panel():
    if not admin_required():
        return redirect(url_for("admin_login_form"))
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM faqs ORDER BY id DESC")
    faqs = c.fetchall()
    conn.close()
    return render_template("admin_panel.html", faqs=faqs, app_name=APP_NAME)

@app.post("/admin/faq/new")
def faq_new():
    if not admin_required():
        return redirect(url_for("admin_login_form"))
    question = request.form.get("question","").strip()
    answer = request.form.get("answer","").strip()
    if not question or not answer:
        flash("Question and answer are required.", "warning")
        return redirect(url_for("admin_panel"))
    conn = get_db()
    now = datetime.utcnow().isoformat()
    conn.execute("INSERT INTO faqs (question, answer, created_at, updated_at) VALUES (?, ?, ?, ?)",
                 (question, answer, now, now))
    conn.commit()
    conn.close()
    flash("FAQ created.", "success")
    return redirect(url_for("admin_panel"))

@app.post("/admin/faq/<int:faq_id>/edit")
def faq_edit(faq_id):
    if not admin_required():
        return redirect(url_for("admin_login_form"))
    question = request.form.get("question","").strip()
    answer = request.form.get("answer","").strip()
    conn = get_db()
    now = datetime.utcnow().isoformat()
    conn.execute("UPDATE faqs SET question=?, answer=?, updated_at=? WHERE id=?",
                 (question, answer, now, faq_id))
    conn.commit()
    conn.close()
    flash("FAQ updated.", "success")
    return redirect(url_for("admin_panel"))

@app.post("/admin/faq/<int:faq_id>/delete")
def faq_delete(faq_id):
    if not admin_required():
        return redirect(url_for("admin_login_form"))
    conn = get_db()
    conn.execute("DELETE FROM faqs WHERE id=?", (faq_id,))
    conn.commit()
    conn.close()
    flash("FAQ deleted.", "info")
    return redirect(url_for("admin_panel"))

@app.get("/health")
def health():
    try:
        conn = get_db()
        conn.execute("SELECT 1")
        conn.close()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}, 500

if __name__ == "__main__":
    setup_db()
    app.run(debug=True)

