from flask import Flask, request, redirect, url_for, session, render_template, jsonify,flash
import json
import sqlite3
import hashlib
import os
from openai import OpenAI
app = Flask(__name__)
app.secret_key = "a_very_secret_and_complex_key_for_hospital_app"
DATABASE_NAME = "hospital.db"

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
    default_headers={
        "HTTP-Referer": "http://localhost:5000",
        "X-Title": "AI Diagnostic Support System"
    }
)

def get_db_connection():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            gender TEXT CHECK(gender IN ('Male','Female','Other')),
            age INTEGER,
            medical_history TEXT,                
            allergies TEXT,                      
            family_history TEXT,                 
            lifestyle TEXT,
            blood_group TEXT,
            blacklisted INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)
    conn.commit()
    conn.close()


def authenticate_user(username, password):
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()

    if user and user['password_hash'] == hash_password(password):
        return dict(user)
    return None

def fetch_doctor_dashboard_data(doctor_id):
    conn = get_db_connection()

    doctor = conn.execute(
        "SELECT name FROM users WHERE id = ?",
        (doctor_id,)
    ).fetchone()

    patients = conn.execute(
        "SELECT id, name, age, gender,blood_group FROM patients WHERE user_id = ?",
        (doctor_id,)
    ).fetchall()

    conn.close()

    return {
        "doctor_name": doctor["name"] if doctor else "",
        "patients": [dict(p) for p in patients]
    }

def fetch_patient_history(patient_name):
    conn = get_db_connection()
    patient_info = {
        'name': patient_name,
        'doctor_name': 'Dr. Alice Smith',
        'department': 'Cardiology'
    }
    visits = conn.execute("""
        SELECT visit_no, visit_type, tests_done, diagnosis, prescription, medicines
        FROM visits WHERE patient_name = ?
        ORDER BY visit_no DESC
    """, (patient_name,)).fetchall()
    conn.close()

    patient_info['visits'] = [dict(v) for v in visits]
    return patient_info


@app.route("/", methods=["GET"])
def home():
    return render_template("home.html")

@app.route("/home.html")
def redirect_to_home():
    return redirect(url_for('home'))

@app.route("/register.html", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        new_username = request.form.get("username")
        new_password = request.form.get("password")
        new_name = request.form.get("name")

        if not new_username or not new_password or not new_name:
            return render_template(
                "register.html",
                error="All fields are required."
            )

        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO users (name, username, password_hash)
                VALUES (?, ?, ?)
                """,
                (new_name, new_username, hash_password(new_password))
            )
            conn.commit()
            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            return render_template(
                "register.html",
                error="Username already exists."
            )

        finally:
            conn.close()

    return render_template("register.html")

@app.route("/login.html", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        user = authenticate_user(username, password)

        if not user:
            return render_template(
                "login.html",
                error="Invalid username or password."
            )
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["doctor_name"] = user["name"]

        return redirect(url_for("doctor_home"))

    return render_template("login.html")

@app.route("/doctorhome.html")
def doctor_home():
    if "user_id" not in session:
        return redirect(url_for("login"))

    doctor_id = session["user_id"]

    dashboard_data = fetch_doctor_dashboard_data(doctor_id)

    return render_template(
        "doctorhome.html",
        doctor={"name": dashboard_data["doctor_name"]},
        patients=dashboard_data["patients"]
    )

@app.route("/add", methods=["GET", "POST"])
def add_patient():
    if "user_id" not in session:
        return "Doctor login required", 401

    if request.method == "GET":
        return render_template("add_patient.html")
    doctor_id = session["user_id"]
    name = request.form.get("name")
    gender = request.form.get("gender")
    age = request.form.get("age")
    medical_history = request.form.get("medical_history", "")
    allergies = request.form.get("allergies", "")
    family_history = request.form.get("family_history", "")
    lifestyle = request.form.get("lifestyle", "")
    blood_group = request.form.get("blood_group", "")

    if not name or not age:
        return "Name and age required", 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO patients
        (name, gender, age, medical_history, allergies,
         family_history, lifestyle, blood_group,user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        name, gender, age, medical_history,
        allergies, family_history, lifestyle, blood_group,doctor_id,
    ))
    conn.commit()
    conn.close()

    flash("Patient added successfully ✅", "success")
    return redirect(url_for("doctor_home"))


@app.route("/ai_assistant/<int:patient_id>")
def ai_assistant(patient_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    patient = conn.execute("""
        SELECT name, age, gender, medical_history,
               allergies, family_history, lifestyle, blood_group
        FROM patients
        WHERE id = ? AND user_id = ?
    """, (patient_id, session["user_id"])).fetchone()
    conn.close()

    if not patient:
        return "Patient not found or unauthorized", 404

    # 🔹 Store patient context in session for chat
    session["ai_patient_context"] = f"""
Patient Profile:
Name: {patient['name']}
Age: {patient['age']}
Gender: {patient['gender']}
Blood Group: {patient['blood_group']}
Medical History: {patient['medical_history']}
Allergies: {patient['allergies']}
Family History: {patient['family_history']}
Lifestyle: {patient['lifestyle']}
"""

    # 🔹 Reset chat history when opening AI
    session["ai_chat_history"] = []

    return render_template(
        "ai_assistant_chat.html",
        patient=patient
    )

@app.route("/ai_chat", methods=["POST"])
def ai_chat():
    if "user_id" not in session:
        return jsonify({"reply": "Session expired. Please login again."}), 401

    user_message = request.json.get("message", "").strip()
    if not user_message:
        return jsonify({"reply": "Please enter a question."}), 400

    patient_context = session.get("ai_patient_context", "")
    chat_history = session.get("ai_chat_history", [])

    system_prompt = f"""
SYSTEM ROLE:
You are an AI-powered Clinical Decision Support System (CDSS).
You assist licensed clinicians by providing conservative, structured, and explainable clinical insights.
You do NOT replace medical professionals.

You operate under strict medical safety, uncertainty, and validation constraints.

--------------------------------
INPUT VALIDATION RULES
--------------------------------
- If any input field is empty, null, contradictory, or clinically insufficient:
  - Do NOT infer missing facts
  - Do NOT extrapolate disease severity
  - Reduce confidence appropriately
- If reliable clinical reasoning is not possible, clearly state that data is insufficient.

--------------------------------
PATIENT DATA
--------------------------------
{patient_context}

--------------------------------
REASONING APPROACH (INTERNAL)
--------------------------------
Use the following structured reasoning internally:
1. Assess data completeness and internal consistency
2. Identify likely temporal pattern (acute, subacute, chronic, or unclear)
3. Determine possible organ-system involvement
4. Generate conservative differential considerations
5. Exclude unlikely conditions
6. Interpret laboratory findings cautiously
7. Identify red flags only if clearly supported
8. Maintain conservative confidence levels

--------------------------------
CLINICAL TASKS
--------------------------------
Provide clinician-facing insights covering:
- Possible conditions (differential only, not diagnosis)
- Disease pattern recognition
- Suggested diagnostic tests
- Red-flag indicators (if any)
- Data conflicts or missing information
- Overall clinical impression
- Urgency assessment

--------------------------------
STRICT MEDICAL & SAFETY RULES
--------------------------------
- Do NOT give a final diagnosis
- Do NOT prescribe medications or dosages
- Do NOT provide patient-facing advice
- Do NOT assume disease prevalence
- Do NOT speculate beyond provided data
- Favor under-assertion over overconfidence
- Avoid rare diseases unless strongly supported
- Keep responses concise, clinical, and professional
- Limit lists to a maximum of 5 items

--------------------------------
CONFIDENCE GUIDANCE
--------------------------------
- High confidence requires alignment of symptoms, history, and labs
- Medium confidence requires partial alignment
- Low confidence is default when uncertainty exists
- Conflicting data must lower confidence

--------------------------------
FAIL-SAFE BEHAVIOR
--------------------------------
If clinical analysis is unreliable due to insufficient or poor-quality data:
- Clearly state that data is insufficient
- Avoid generating differential diagnoses
- Recommend clarification or additional data
- Maintain low urgency unless red flags are explicit

--------------------------------
OUTPUT STYLE
--------------------------------
- Use clear headings
- Short, professional clinical sentences
- Physician-facing tone only
- No JSON, no code blocks, no system commentary

END OF INSTRUCTION

"""

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(chat_history)
    messages.append({"role": "user", "content": user_message})

    try:
        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=messages,
            temperature=0.3,
            max_tokens=400
        )
        ai_reply = response.choices[0].message.content
    except Exception as e:
        ai_reply = "AI assistant is currently unavailable."

    chat_history.append({"role": "user", "content": user_message})
    chat_history.append({"role": "assistant", "content": ai_reply})
    session["ai_chat_history"] = chat_history

    return jsonify({"reply": ai_reply})


@app.route("/patient/view/<int:patient_id>")
def view_patient(patient_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    patient = conn.execute("""
        SELECT *
        FROM patients
        WHERE id = ? AND user_id = ?
    """, (patient_id, session["user_id"])).fetchone()
    conn.close()

    if not patient:
        return "Patient not found or unauthorized", 404

    return render_template(
        "view_patient.html",
        patient=patient
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('home'))


@app.route("/_list_endpoints")
def _list_endpoints():
    return "<br>".join(sorted(rule.endpoint for rule in app.url_map.iter_rules()))
if __name__ == "__main__":
    init_db()
    app.run(debug=True)
