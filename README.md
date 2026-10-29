# Student Management System

A small Flask and SQLite college project for managing student records, attendance, marks, and grades. It includes a role-based dashboard for Admin, Teacher, and Student demo accounts.

## Features in this build

- Session login with Admin, Teacher, and Student roles.
- Login screen starts with Student selected and provides Student, Admin, and Teacher options; the selected role must match the account.
- Admin student create, edit, delete, search, filter, and sort.
- Teacher/Admin attendance entry and marks entry.
- Unique daily attendance per student and score validation from 0 to 100.
- Automatic grades: A (90–100), B (80–89), C (70–79), D (60–69), F (below 60).
- Dashboard counts, attendance rate, class chart, and responsive light/dark theme.
- Student account can view their own record, attendance, marks, and grades.

Fees, timetable, parent messaging, multilingual support, biometric attendance, email alerts, notices, CSV export, and report-card printing are not implemented.

## Requirements

- Python 3.10 or later
- pip
- A current browser

## Installation and run

In PowerShell, from the project folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python app.py
```

If the Python launcher is unavailable in PowerShell, create the environment with the installed Python executable instead:

```powershell
& "$env:LocalAppData\Programs\Python\Python312\python.exe" -m venv .venv
```

Open `http://localhost:5000` (or `http://127.0.0.1:5000`). The server listens only on your own computer, not on your Wi-Fi network. Keep the terminal running while you use the app; press `Ctrl+C` there to stop it. The SQLite database is created and seeded automatically on first startup. A random development session key is generated if `FLASK_SECRET_KEY` is blank; set a persistent random value in `.env` before deployment.

### Demo accounts

| Role | Username | Password |
|---|---|---|
| Admin | `admin` | `Admin@123` |
| Teacher | `teacher` | `Teacher@123` |
| Student | `student` | `Student@123` |

Change these demonstration credentials before deploying anywhere accessible by other users. For deployment, configure a long random `FLASK_SECRET_KEY` environment variable, set `FLASK_HTTPS=1` behind HTTPS, and do not commit `.env`.

## Seed data

First run creates four classes, 40 Indian-named students, six subjects, 30 days of attendance for each student, and one account per role. The demonstration student account is linked to `STU001` (Aarav Sharma). Existing default records named `Student 01` through `Student 40` are updated on startup; records with a name you have already changed are left untouched. Sample passwords are hashed in the database.

## Tests

```powershell
python -m unittest discover -s tests -v
```

Tests cover seed counts and realistic names, old demo-name migration, role choices and matching login credentials, invalid login, role denial, input validation, CSRF protection, attendance, marks, and student record privacy. See [test cases](tests/TEST-CASES.md) for the corresponding case table.

## Project layout

```text
Student Management/
├── app.py
├── database/
│   └── schema.sql
├── static/
│   ├── app.js
│   └── styles.css
├── templates/
│   ├── dashboard.html
│   └── login.html
├── tests/
│   └── test_app.py
├── .env.example
├── .gitignore
└── requirements.txt
```

## Known limitations

This is a local college-project build, not a production deployment. It uses demonstration users, does not include account provisioning or password reset, and currently uses a single mark per student and subject. Chart.js and the web fonts are loaded from public CDNs, so those assets require internet access.
