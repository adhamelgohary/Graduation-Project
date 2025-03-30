import os
from flask import Flask, redirect, render_template, url_for
from flask_login import login_required, current_user
from routes.auth import auth_bp, init_login_manager
from routes.Admin_Portal.Dashboard import admin_main
from routes.Admin_Portal.Admins_Management import admin_management
from routes.Admin_Portal.Doctors_Management import Doctors_Management
from routes.Admin_Portal.Patient_Management import patient_management
from routes.Admin_Portal.Audit_Logs import admin_audit
from routes.Admin_Portal.Registiration_Approval_System import registration_approval


# Determine the absolute path to the project directory
# Assumes this file (app.py or __init__.py) is at the root level or one level inside
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
# If your app.py is inside an 'app' folder, you might need:
# BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'  # Change this to a secure random key
app.config['PERMANENT_SESSION_LIFETIME'] = 1800  # Session timeout in seconds (30 minutes)

# --- Configure Upload Folder ---
# Define the absolute path for uploads
UPLOAD_FOLDER_PATH = os.path.join(BASE_DIR, 'uploads')
# Create the directory if it doesn't exist
os.makedirs(UPLOAD_FOLDER_PATH, exist_ok=True)
# SET THE FLASK CONFIG VARIABLE
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER_PATH

# Register blueprints
app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(admin_main)
app.register_blueprint(admin_management)
app.register_blueprint(Doctors_Management)
app.register_blueprint(patient_management)
app.register_blueprint(admin_audit)
app.register_blueprint(registration_approval)

# Initialize login manager
init_login_manager(app)


@app.route('/')
def home():
    return redirect(url_for('auth.login'))  # Make sure 'auth.login' is the correct view

if __name__ == '__main__':
    app.run(debug=True,host='0.0.0.0',port=54321) # Set debug=True for easier development