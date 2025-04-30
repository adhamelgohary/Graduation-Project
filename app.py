# app.py (or your main Flask file)
import os
from flask import Flask, redirect, url_for, render_template # Added render_template
from flask_login import login_required, current_user

# --- Import Utility Functions ---
from utils.directory_configs import configure_directories
from utils.template_helpers import register_template_helpers
from utils.mail_config import configure_mail # Import even if mail is commented out

# --- Import Blueprints ---
from routes.login import login_bp, init_login_manager
from routes.register import register_bp
# from routes.password_reset import password_reset_bp # Assuming password reset uses mail
from routes.Admin_Portal.Dashboard import admin_main
from routes.Admin_Portal.Admins_Management import admin_management
from routes.Admin_Portal.Doctors_Management import Doctors_Management
from routes.Admin_Portal.Patient_Management import patient_management
from routes.Admin_Portal.Registiration_Approval_System import registration_approval
from routes.Admin_Portal.search_users import search_users_bp
from routes.Admin_Portal.Appointments import admin_appointments_bp
from routes.Doctor_Portal.Dashboard import doctor_main
from routes.Doctor_Portal.availability_management import availability_bp
from routes.Doctor_Portal.settings_management import settings_bp
from routes.Doctor_Portal.patients_management import patients_bp
from routes.Doctor_Portal.disease_management import disease_management_bp
from routes.Doctor_Portal.diet_plan_management import diet_plans_bp
from routes.Doctor_Portal.appointment_management import appointments_bp

# --- Create Flask App ---
app = Flask(__name__)

# --- Core App Configuration ---
# It's better to load secrets from environment variables or a config file
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'default-insecure-secret-key-change-me!')
if app.config['SECRET_KEY'] == 'default-insecure-secret-key-change-me!':
    app.logger.warning("SECURITY WARNING: Using default SECRET_KEY. Please set FLASK_SECRET_KEY environment variable.")
app.config['PERMANENT_SESSION_LIFETIME'] = int(os.environ.get('FLASK_SESSION_LIFETIME', 1800)) # e.g., 30 minutes
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # 16MB limit (Keep general config here)

# --- Configure Features using Utility Functions ---
configure_directories(app) # Sets upload paths and extension configs
configure_mail(app)      # Sets mail server config (reads from env vars)
register_template_helpers(app) # Registers Jinja filters and globals

# --- Initialize Extensions ---
# mail = Mail(app) # Initialize Mail if configure_mail doesn't do it
init_login_manager(app) # Initialize Flask-Login

# --- Register Blueprints ---
app.register_blueprint(login_bp)
app.register_blueprint(register_bp)
# app.register_blueprint(password_reset_bp)
app.register_blueprint(admin_main)
app.register_blueprint(admin_management)
app.register_blueprint(Doctors_Management)
app.register_blueprint(patient_management)
app.register_blueprint(registration_approval)
app.register_blueprint(search_users_bp)
app.register_blueprint(admin_appointments_bp)
app.register_blueprint(doctor_main)
app.register_blueprint(availability_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(patients_bp)
app.register_blueprint(disease_management_bp)
app.register_blueprint(diet_plans_bp)
app.register_blueprint(appointments_bp)

# --- Basic Routes ---
@app.route('/')
def home():
    # Redirect based on login status or show a landing page
    if current_user.is_authenticated:
        # Redirect to appropriate dashboard based on user type
        if getattr(current_user, 'user_type', None) == 'admin':
            return redirect(url_for('admin_main.admin_dashboard'))
        elif getattr(current_user, 'user_type', None) == 'doctor':
             return redirect(url_for('doctor_main.dashboard'))
        # Add other user types (patient, etc.) if they have dashboards
        else:
             return redirect(url_for('login.login_route')) # Fallback to login
    return redirect(url_for('login.login_route')) # Redirect unauthenticated users to login


# Add a simple health check endpoint (optional but good practice)
@app.route('/health')
def health_check():
    return "OK", 200


# --- Run the App ---
if __name__ == '__main__':
    # Use environment variables for host/port if possible
    host = os.environ.get('FLASK_RUN_HOST', '0.0.0.0')
    port = int(os.environ.get('FLASK_RUN_PORT', 54321))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() in ['true', '1', 't']
    app.logger.info(f"Starting Flask app on {host}:{port} (Debug: {debug})")
    app.run(debug=debug, host=host, port=port)