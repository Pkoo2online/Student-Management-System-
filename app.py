import hmac
import os
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from dotenv import load_dotenv
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "instance" / "student_management.db"
load_dotenv(BASE_DIR / ".env")
VALID_ATTENDANCE = {"Present", "Absent", "Late"}
DEMO_STUDENT_NAMES = (
    "Aarav Sharma", "Ananya Iyer", "Vivaan Patel", "Diya Nair", "Aditya Reddy",
    "Meera Kapoor", "Arjun Mehta", "Ishita Rao", "Sai Kumar", "Kavya Menon",
    "Rohan Desai", "Aadhya Singh", "Kabir Malhotra", "Saanvi Joshi", "Reyansh Gupta",
    "Anika Banerjee", "Krish Verma", "Myra Kulkarni", "Dev Shah", "Pari Chawla",
    "Atharv Mishra", "Kiara Fernandes", "Dhruv Bhat", "Avni Agarwal", "Ishaan Das",
    "Tara Krishnan", "Om Prakash", "Riya Sethi", "Yash Thakur", "Nisha Pillai",
    "Rahul Choudhary", "Sana Qureshi", "Manav Bansal", "Pooja Shetty", "Karan Gill",
    "Tanvi Ghosh", "Neil D'Souza", "Simran Kaur", "Varun Saxena", "Lakshmi Iyer",
)
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$")

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_HTTPS", "0") == "1",
    MAX_CONTENT_LENGTH=64 * 1024,
)


@contextmanager
def get_db():
    """Open a short-lived SQLite connection with foreign-key checks enabled."""
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def demo_email(name):
    username = re.sub(r"[^a-z0-9]+", ".", name.lower()).strip(".")
    return f"{username}@college.example"


def update_legacy_demo_names(db):
    for index, name in enumerate(DEMO_STUDENT_NAMES, start=1):
        enrollment_no = f"STU{index:03}"
        old_name = f"Student {index:02}"
        row = db.execute(
            "SELECT name, email FROM students WHERE enrollment_no = ?", (enrollment_no,)
        ).fetchone()
        if row and row["name"] == old_name:
            old_email = f"student{index:02}@college.example"
            email = demo_email(name) if row["email"] == old_email else row["email"]
            db.execute(
                "UPDATE students SET name = ?, email = ? WHERE enrollment_no = ?",
                (name, email, enrollment_no),
            )


def init_db():
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    with get_db() as db:
        schema = (BASE_DIR / "database" / "schema.sql").read_text(encoding="utf-8")
        db.executescript(schema)
        if db.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            update_legacy_demo_names(db)
            return

        db.executemany("INSERT INTO classes (name) VALUES (?)",
                       [(f"Class {letter}",) for letter in "ABCD"])
        db.executemany("INSERT INTO subjects (code, name) VALUES (?, ?)", [
            ("ENG101", "English"), ("MAT101", "Mathematics"),
            ("SCI101", "Science"), ("HIS101", "History"),
            ("CSC101", "Computer Science"), ("ART101", "Art"),
        ])
        for i, name in enumerate(DEMO_STUDENT_NAMES, start=1):
            class_id = ((i - 1) // 10) + 1
            db.execute(
                "INSERT INTO students (enrollment_no, name, email, class_id) "
                "VALUES (?, ?, ?, ?)",
                (f"STU{i:03}", name, demo_email(name), class_id),
            )
        student_id = db.execute(
            "SELECT id FROM students WHERE enrollment_no = 'STU001'"
        ).fetchone()["id"]
        db.executemany(
            "INSERT INTO users (username, password_hash, role, student_id) VALUES (?, ?, ?, ?)",
            [
                ("admin", generate_password_hash("Admin@123"), "admin", None),
                ("teacher", generate_password_hash("Teacher@123"), "teacher", None),
                ("student", generate_password_hash("Student@123"), "student", student_id),
            ],
        )
        teacher_id = db.execute(
            "SELECT id FROM users WHERE username = 'teacher'"
        ).fetchone()["id"]
        start = date.today() - timedelta(days=29)
        for student in db.execute("SELECT id FROM students").fetchall():
            for offset in range(30):
                status = "Absent" if (student["id"] + offset) % 12 == 0 else "Present"
                db.execute(
                    "INSERT INTO attendance (student_id, attendance_date, status, marked_by) "
                    "VALUES (?, ?, ?, ?)",
                    (student["id"], (start + timedelta(days=offset)).isoformat(),
                     status, teacher_id),
                )
        for student in db.execute("SELECT id FROM students").fetchall():
            for subject in db.execute("SELECT id FROM subjects").fetchall():
                score = 65 + ((student["id"] * 7 + subject["id"] * 3) % 36)
                db.execute(
                    "INSERT INTO marks (student_id, subject_id, score, updated_by) "
                    "VALUES (?, ?, ?, ?)",
                    (student["id"], subject["id"], score, teacher_id),
                )


def grade_for(score):
    """Convert a numeric score to the project's fixed letter-grade scale."""
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def attendance_percentage(total, attended):
    return round(100 * attended / total, 1) if total else 0


def api_error(message, status):
    return jsonify(error=message), status


def request_object():
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def require_login(roles=None):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return api_error("Login required.", 401)
            if roles and session.get("role") not in roles:
                return api_error("You do not have permission to perform this action.", 403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def require_csrf():
    supplied = request.headers.get("X-CSRF-Token", "")
    expected = session.get("csrf_token", "")
    return bool(expected) and hmac.compare_digest(supplied, expected)


@app.before_request
def enforce_csrf_for_writes():
    if request.path.startswith("/api/") and request.method in {"POST", "PUT", "DELETE"}:
        if "user_id" in session and not require_csrf():
            return api_error("Invalid or missing CSRF token.", 400)


@app.get("/")
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.get("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("home"))
    return render_template("dashboard.html")


@app.post("/api/login")
def login():
    payload = request_object()
    username = payload.get("username", "")
    password = payload.get("password", "")
    role = payload.get("role", "")
    if not isinstance(username, str) or not isinstance(password, str) or not isinstance(role, str):
        return api_error("Username, password, and role are required.", 400)
    if role not in {"admin", "teacher", "student"}:
        return api_error("Choose a valid account role.", 400)
    if not username.strip() or not password or len(username) > 80 or len(password) > 200:
        return api_error("Enter a valid username and password.", 400)
    with get_db() as db:
        user = db.execute(
            "SELECT id, username, password_hash, role, student_id FROM users WHERE username = ?",
            (username.strip(),),
        ).fetchone()
    if (not user or user["role"] != role
            or not check_password_hash(user["password_hash"], password)):
        return api_error("Invalid username or password.", 401)
    session.clear()
    session.update(user_id=user["id"], username=user["username"], role=user["role"],
                   student_id=user["student_id"], csrf_token=secrets.token_urlsafe(32))
    return jsonify(user=dict(id=user["id"], username=user["username"], role=user["role"]),
                   csrf_token=session["csrf_token"])


@app.post("/api/logout")
@require_login()
def logout():
    session.clear()
    return jsonify(message="Logged out.")


@app.get("/api/me")
@require_login()
def me():
    return jsonify(user=dict(id=session["user_id"], username=session["username"],
                             role=session["role"], student_id=session.get("student_id")),
                   csrf_token=session["csrf_token"])


@app.get("/api/classes")
@require_login()
def classes():
    with get_db() as db:
        rows = db.execute("SELECT id, name FROM classes ORDER BY name").fetchall()
    return jsonify(classes=[dict(row) for row in rows])


@app.get("/api/subjects")
@require_login()
def subjects():
    with get_db() as db:
        rows = db.execute("SELECT id, code, name FROM subjects ORDER BY name").fetchall()
    return jsonify(subjects=[dict(row) for row in rows])


@app.get("/api/dashboard")
@require_login()
def dashboard_data():
    with get_db() as db:
        student_filter = ""
        params = ()
        if session["role"] == "student":
            student_filter, params = " WHERE id = ?", (session.get("student_id"),)
        count = db.execute(f"SELECT COUNT(*) FROM students{student_filter}", params).fetchone()[0]
        if session["role"] == "student":
            class_counts = db.execute(
                "SELECT c.name, COUNT(s.id) AS total FROM classes c "
                "JOIN students s ON s.class_id = c.id WHERE s.id = ? "
                "GROUP BY c.id ORDER BY c.name", (session.get("student_id"),)
            ).fetchall()
        else:
            class_counts = db.execute(
                "SELECT c.name, COUNT(s.id) AS total FROM classes c "
                "LEFT JOIN students s ON s.class_id = c.id GROUP BY c.id ORDER BY c.name"
            ).fetchall()
        if session["role"] == "student":
            attendance = db.execute(
                "SELECT attendance_date, status FROM attendance WHERE student_id = ? "
                "ORDER BY attendance_date DESC LIMIT 7", (session.get("student_id"),)
            ).fetchall()
            today_count = int(any(row["attendance_date"] == date.today().isoformat()
                                  for row in attendance))
            overall = db.execute(
                "SELECT COUNT(*) AS total, SUM(status IN ('Present','Late')) AS attended "
                "FROM attendance WHERE student_id = ?", (session.get("student_id"),)
            ).fetchone()
        else:
            today_count = db.execute(
                "SELECT COUNT(*) FROM attendance WHERE attendance_date = ? AND status IN ('Present','Late')",
                (date.today().isoformat(),),
            ).fetchone()[0]
            overall = db.execute(
                "SELECT COUNT(*) AS total, SUM(status IN ('Present','Late')) AS attended FROM attendance"
            ).fetchone()
    percentage = attendance_percentage(overall["total"], overall["attended"] or 0)
    return jsonify(student_count=count, class_counts=[dict(row) for row in class_counts],
                   present_today=today_count, attendance_percentage=percentage)


@app.get("/api/students")
@require_login()
def list_students():
    search = request.args.get("q", "").strip()[:100]
    class_id = request.args.get("class_id", "").strip()
    sort = request.args.get("sort", "name")
    sort_columns = {"name": "s.name", "enrollment": "s.enrollment_no", "class": "c.name"}
    if sort not in sort_columns:
        return api_error("Invalid sort field.", 400)
    sql = ("SELECT s.id, s.enrollment_no, s.name, s.email, s.class_id, c.name AS class_name "
           "FROM students s JOIN classes c ON c.id = s.class_id")
    conditions, params = [], []
    if session["role"] == "student":
        conditions.append("s.id = ?")
        params.append(session.get("student_id"))
    if search:
        conditions.append("(s.name LIKE ? OR s.enrollment_no LIKE ? OR s.email LIKE ?)")
        params.extend([f"%{search}%"] * 3)
    if class_id:
        if not class_id.isdigit():
            return api_error("Class must be a valid ID.", 400)
        conditions.append("s.class_id = ?")
        params.append(int(class_id))
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY " + sort_columns[sort]
    with get_db() as db:
        rows = db.execute(sql, params).fetchall()
    return jsonify(students=[dict(row) for row in rows])


def validate_student(payload):
    name = payload.get("name")
    enrollment = payload.get("enrollment_no")
    email = payload.get("email")
    class_id = payload.get("class_id")
    if not all(isinstance(value, str) for value in (name, enrollment, email)):
        return None, "Name, enrollment number, and email are required."
    name, enrollment, email = name.strip(), enrollment.strip(), email.strip().lower()
    if not 1 <= len(name) <= 100 or not re.fullmatch(r"[A-Za-z0-9-]{2,30}", enrollment):
        return None, "Name or enrollment number has an invalid format."
    if not EMAIL_RE.fullmatch(email) or not isinstance(class_id, int) or isinstance(class_id, bool):
        return None, "Enter a valid email address and class."
    return dict(name=name, enrollment_no=enrollment, email=email, class_id=class_id), None


@app.post("/api/students")
@require_login({"admin"})
def create_student():
    payload = request_object()
    student, error = validate_student(payload)
    if error:
        return api_error(error, 400)
    try:
        with get_db() as db:
            db.execute(
                "INSERT INTO students (enrollment_no, name, email, class_id) VALUES (?, ?, ?, ?)",
                (student["enrollment_no"], student["name"], student["email"], student["class_id"]),
            )
    except sqlite3.IntegrityError:
        return api_error("Enrollment number or email already exists, or class is invalid.", 409)
    return jsonify(message="Student created."), 201


@app.route("/api/students/<int:student_id>", methods=["PUT", "DELETE"])
@require_login({"admin"})
def modify_student(student_id):
    if request.method == "DELETE":
        with get_db() as db:
            cursor = db.execute("DELETE FROM students WHERE id = ?", (student_id,))
        if not cursor.rowcount:
            return api_error("Student not found.", 404)
        return jsonify(message="Student deleted.")
    student, error = validate_student(request_object())
    if error:
        return api_error(error, 400)
    try:
        with get_db() as db:
            cursor = db.execute(
                "UPDATE students SET enrollment_no=?, name=?, email=?, class_id=? WHERE id=?",
                (student["enrollment_no"], student["name"], student["email"],
                 student["class_id"], student_id),
            )
    except sqlite3.IntegrityError:
        return api_error("Enrollment number or email already exists, or class is invalid.", 409)
    if not cursor.rowcount:
        return api_error("Student not found.", 404)
    return jsonify(message="Student updated.")


@app.route("/api/attendance", methods=["GET", "POST"])
@require_login()
def attendance_api():
    if request.method == "POST":
        if session["role"] not in {"admin", "teacher"}:
            return api_error("Only admins and teachers can mark attendance.", 403)
        payload = request_object()
        student_id, attendance_date, status = (
            payload.get("student_id"), payload.get("attendance_date"), payload.get("status")
        )
        if not isinstance(student_id, int) or isinstance(student_id, bool):
            return api_error("Student ID must be an integer.", 400)
        try:
            if not isinstance(attendance_date, str) or not re.fullmatch(
                    r"\d{4}-\d{2}-\d{2}", attendance_date):
                raise ValueError
            parsed_date = date.fromisoformat(attendance_date)
        except (TypeError, ValueError):
            return api_error("Date must use YYYY-MM-DD format.", 400)
        if (parsed_date > date.today() or not isinstance(status, str)
                or status not in VALID_ATTENDANCE):
            return api_error("Date cannot be in the future and status must be valid.", 400)
        with get_db() as db:
            exists = db.execute("SELECT 1 FROM students WHERE id=?", (student_id,)).fetchone()
            if not exists:
                return api_error("Student not found.", 404)
            db.execute(
                "INSERT INTO attendance (student_id, attendance_date, status, marked_by) "
                "VALUES (?, ?, ?, ?) ON CONFLICT(student_id, attendance_date) "
                "DO UPDATE SET status=excluded.status, marked_by=excluded.marked_by",
                (student_id, parsed_date.isoformat(), status, session["user_id"]),
            )
        return jsonify(message="Attendance saved."), 201
    student_id = request.args.get("student_id")
    if session["role"] == "student":
        student_id = session.get("student_id")
    query = ("SELECT a.id, a.student_id, s.name AS student_name, a.attendance_date, a.status "
             "FROM attendance a JOIN students s ON s.id=a.student_id")
    params = []
    if student_id:
        query += " WHERE a.student_id=?"
        params.append(student_id)
    query += " ORDER BY a.attendance_date DESC LIMIT 300"
    with get_db() as db:
        rows = db.execute(query, params).fetchall()
    return jsonify(attendance=[dict(row) for row in rows])


@app.route("/api/marks", methods=["GET", "POST"])
@require_login()
def marks_api():
    if request.method == "POST":
        if session["role"] not in {"admin", "teacher"}:
            return api_error("Only admins and teachers can enter marks.", 403)
        payload = request_object()
        student_id, subject_id, score = (
            payload.get("student_id"), payload.get("subject_id"), payload.get("score")
        )
        if (not isinstance(student_id, int) or isinstance(student_id, bool)
                or not isinstance(subject_id, int) or isinstance(subject_id, bool)
                or not isinstance(score, (int, float)) or isinstance(score, bool)
                or not 0 <= score <= 100):
            return api_error("Provide valid student, subject, and score (0-100).", 400)
        with get_db() as db:
            try:
                db.execute(
                    "INSERT INTO marks (student_id, subject_id, score, updated_by) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(student_id, subject_id) DO UPDATE SET "
                    "score=excluded.score, updated_by=excluded.updated_by",
                    (student_id, subject_id, score, session["user_id"]),
                )
            except sqlite3.IntegrityError:
                return api_error("Student or subject not found.", 404)
        return jsonify(message="Marks saved.", grade=grade_for(score)), 201
    query = ("SELECT m.id, m.student_id, s.name AS student_name, sub.name AS subject_name, "
             "m.score, m.score AS grade_score FROM marks m "
             "JOIN students s ON s.id=m.student_id JOIN subjects sub ON sub.id=m.subject_id")
    params = []
    if session["role"] == "student":
        query += " WHERE m.student_id=?"
        params.append(session.get("student_id"))
    query += " ORDER BY s.name, sub.name"
    with get_db() as db:
        rows = db.execute(query, params).fetchall()
    return jsonify(marks=[dict(id=row["id"], student_id=row["student_id"],
                               student_name=row["student_name"], subject_name=row["subject_name"],
                               score=row["score"], grade=grade_for(row["grade_score"]))
                         for row in rows])


@app.errorhandler(413)
def request_too_large(_error):
    return api_error("Request body is too large.", 413)


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")),
            debug=os.environ.get("FLASK_DEBUG", "0") == "1")
