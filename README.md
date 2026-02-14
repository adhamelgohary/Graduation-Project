# Graduation Project - Health Guide

This project is a FastAPI-based health management system migrated from Flask. It uses SQLAlchemy (asynchronous) for ORM and Alembic for database migrations.

## 🛠 Setup and Installation

### 1. Install Dependencies
Ensure you have Python 3.10+ installed. It is recommended to use a virtual environment.
```bash
pip install -r requirements.txt
```

### 2. Database Configuration
Update the database connection string in `alembic.ini` and `db.py`:
- **alembic.ini**: `sqlalchemy.url = mysql+aiomysql://user:password@localhost/db_name`
- **db.py**: `DATABASE_URL = "mysql+aiomysql://user:password@localhost/db_name"`

---

## 🚀 Running the Application

### Start the Development Server
Runs the FastAPI app with auto-reload enabled.
```bash
uvicorn main:app --reload
```
- **Documentation**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) (Swagger UI)

---

## 🏗 Database Migrations (Alembic)

Alembic handles all changes to your database schema.

### Generate a New Migration
Use this whenever you modify `models.py`. It compares your models to the actual database and creates a script.
```bash
python3 -m alembic revision --autogenerate -m "description of changes"
```

### Apply Migrations
Updates your database to the latest schema version.
```bash
python3 -m alembic upgrade head
```

### Rollback Migration
Reverts the last applied migration.
```bash
python3 -m alembic downgrade -1
```

---

## ⚡️ Infrastructure Services (Redis)

This project uses **Redis** for rate limiting to prevent brute-force attacks on sensitive routes (Login, Register).

### Runs Redis via Docker
```bash
docker-compose up -d redis
```

---

## 🛠 Database Visual Interface (SQLAdmin)

A built-in web interface is provided for managing the database models directly from the browser.

- **URL**: [http://127.0.0.1:8000/admin_db](http://127.0.0.1:8000/admin_db)
- **Features**: View, edit, and manage `Users`, `Doctors`, `Patients`, `Admins`, `Appointments`, and more.

---

## 🛡 Security & Error Handling

- **Rate Limiting**: Implemented on `Auth` routes using `fastapi-limiter`.
- **Global Error Popups**: Custom 404 and 500 handlers ensure that instead of a blank page, users see a user-friendly popup notification with navigation options.

---

## 🐳 Docker Deployment

### Build and Start All Services (App, MySQL, Redis)
```bash
docker-compose up -d --build
```

### View Logs
```bash
docker-compose logs -f
```

### Stop Containers
```bash
docker-compose down
```

---

## 🧪 Utilities

### Verify SQLAlchemy Models
```bash
python3 verify_models.py
```

### Generate Password Hash
```bash
python3 generate_password_hash.py
```
