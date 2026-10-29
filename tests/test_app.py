import os
import tempfile
import unittest
from datetime import date
from pathlib import Path

import app as student_app


class StudentManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        student_app.DATABASE = Path(self.temp_dir.name) / "test.db"
        student_app.init_db()
        student_app.app.config.update(TESTING=True, SECRET_KEY="test-secret")
        self.client = student_app.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def login(self, username, password, role=None):
        role = role or {"admin": "admin", "teacher": "teacher", "student": "student"}[username]
        response = self.client.post("/api/login", json={
            "username": username, "password": password, "role": role
        })
        self.assertEqual(response.status_code, 200)
        return response.get_json()["csrf_token"]

    def write_headers(self, token):
        return {"X-CSRF-Token": token}

    def test_seed_contains_expected_demo_data(self):
        with student_app.get_db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM classes").fetchone()[0], 4)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM students").fetchone()[0], 40)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM subjects").fetchone()[0], 6)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM attendance").fetchone()[0], 1200)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM users").fetchone()[0], 3)
            names = [row["name"] for row in db.execute(
                "SELECT name FROM students ORDER BY id"
            ).fetchall()]
            self.assertEqual(names, list(student_app.DEMO_STUDENT_NAMES))
            self.assertEqual(len(set(names)), 40)

    def test_existing_generic_demo_names_are_migrated(self):
        with student_app.get_db() as db:
            db.execute(
                "UPDATE students SET name = ?, email = ? WHERE enrollment_no = ?",
                ("Student 01", "student01@college.example", "STU001"),
            )
            db.execute(
                "UPDATE students SET name = ?, email = ? WHERE enrollment_no = ?",
                ("Custom Student", "custom@example.com", "STU002"),
            )
        student_app.init_db()
        with student_app.get_db() as db:
            students = db.execute(
                "SELECT enrollment_no, name, email FROM students WHERE enrollment_no IN "
                "('STU001', 'STU002') ORDER BY enrollment_no"
            ).fetchall()
        self.assertEqual((students[0]["name"], students[0]["email"]),
                         ("Aarav Sharma", "aarav.sharma@college.example"))
        self.assertEqual((students[1]["name"], students[1]["email"]),
                         ("Custom Student", "custom@example.com"))

    def test_grade_thresholds(self):
        self.assertEqual([student_app.grade_for(n) for n in (90, 89, 80, 79, 70, 69, 60, 59)],
                         ["A", "B", "B", "C", "C", "D", "D", "F"])

    def test_attendance_percentage_and_empty_history(self):
        self.assertEqual(student_app.attendance_percentage(3, 2), 66.7)
        self.assertEqual(student_app.attendance_percentage(0, 0), 0)

    def test_login_rejects_bad_credentials_and_accepts_seed_user(self):
        self.assertEqual(self.client.post("/api/login", json={
            "username": "admin", "password": "wrong", "role": "admin"
        }).status_code, 401)
        self.assertEqual(self.client.post("/api/login", json=["unexpected"]).status_code, 400)
        self.assertEqual(self.login("admin", "Admin@123") != "", True)

    def test_login_requires_selected_role_matching_credentials(self):
        missing_role = self.client.post("/api/login", json={
            "username": "student", "password": "Student@123"
        })
        self.assertEqual(missing_role.status_code, 400)

        invalid_role = self.client.post("/api/login", json={
            "username": "student", "password": "Student@123", "role": "superuser"
        })
        self.assertEqual(invalid_role.status_code, 400)

        mismatched_role = self.client.post("/api/login", json={
            "username": "admin", "password": "Admin@123", "role": "student"
        })
        self.assertEqual(mismatched_role.status_code, 401)
        self.assertEqual(self.client.get("/api/me").status_code, 401)

    def test_login_page_offers_student_admin_and_teacher_with_student_default(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn('value="student" checked', page)
        self.assertIn('value="admin"', page)
        self.assertIn('value="teacher"', page)

    def test_unauthorized_student_cannot_create_student(self):
        token = self.login("student", "Student@123")
        response = self.client.post("/api/students", headers=self.write_headers(token), json={
            "name": "Unauthorized", "enrollment_no": "NEW-1",
            "email": "new@example.com", "class_id": 1
        })
        self.assertEqual(response.status_code, 403)

    def test_admin_can_create_student_and_invalid_email_is_rejected(self):
        token = self.login("admin", "Admin@123")
        bad = self.client.post("/api/students", headers=self.write_headers(token), json={
            "name": "New Student", "enrollment_no": "NEW-1",
            "email": "bad", "class_id": 1
        })
        self.assertEqual(bad.status_code, 400)
        good = self.client.post("/api/students", headers=self.write_headers(token), json={
            "name": "New Student", "enrollment_no": "NEW-1",
            "email": "new@example.com", "class_id": 1
        })
        self.assertEqual(good.status_code, 201)

    def test_attendance_requires_csrf_and_valid_data(self):
        token = self.login("teacher", "Teacher@123")
        payload = {"student_id": 1, "attendance_date": date.today().isoformat(), "status": "Present"}
        self.assertEqual(self.client.post("/api/attendance", json=payload).status_code, 400)
        response = self.client.post("/api/attendance", headers=self.write_headers(token), json=payload)
        self.assertEqual(response.status_code, 201)
        payload["status"] = "Excused"
        self.assertEqual(self.client.post("/api/attendance", headers=self.write_headers(token),
                                          json=payload).status_code, 400)
        payload.update(attendance_date="20261030", status="Present")
        self.assertEqual(self.client.post("/api/attendance", headers=self.write_headers(token),
                                          json=payload).status_code, 400)

    def test_dashboard_redirects_until_login(self):
        self.assertEqual(self.client.get("/dashboard").status_code, 302)
        self.login("admin", "Admin@123")
        self.assertEqual(self.client.get("/dashboard").status_code, 200)

    def test_marks_calculates_grade_and_rejects_out_of_range(self):
        token = self.login("teacher", "Teacher@123")
        response = self.client.post("/api/marks", headers=self.write_headers(token), json={
            "student_id": 1, "subject_id": 1, "score": 91
        })
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["grade"], "A")
        invalid = self.client.post("/api/marks", headers=self.write_headers(token), json={
            "student_id": 1, "subject_id": 1, "score": 101
        })
        self.assertEqual(invalid.status_code, 400)

    def test_student_only_sees_own_records(self):
        self.login("student", "Student@123")
        response = self.client.get("/api/students")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.get_json()["students"]), 1)


if __name__ == "__main__":
    unittest.main()
