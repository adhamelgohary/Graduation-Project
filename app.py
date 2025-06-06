# app.py (or your main Flask file)
import os
from turtle import numinput
from flask import Flask, redirect, url_for, render_template # Added render_template
from flask_login import login_required, current_user

# --- Import Utility Functions ---
from utils.directory_configs import configure_directories
from utils.template_helpers import register_template_helpers

# --- Import Blueprints ---
from routes.login import login_bp, init_login_manager
from routes.register import register_bp
# from routes.password_reset import password_reset_bp # Assuming password reset uses mail

# routes of website
from routes.Website.home import home_bp
from routes.Website.department import department_bp
from routes.Website.doctor import doctor_bp # <-- Import doctor blueprint
from routes.Website.appointments import appointment_bp # Example appointment blueprint
from routes.Website.disease_info import disease_info_bp

# routes of admin portal
from routes.Admin_Portal.Dashboard import admin_main
from routes.Admin_Portal.Admins_Management import admin_management
from routes.Admin_Portal.Doctors_Management import Doctors_Management
from routes.Admin_Portal.Patient_Management import patient_management
from routes.Admin_Portal.Registiration_Approval_System import registration_approval
from routes.Admin_Portal.search_users import search_users_bp
from routes.Admin_Portal.Appointments import admin_appointments_bp
from routes.Admin_Portal.structure_management import structure_bp
# Import Patient Portal Blueprints
from routes.Patient_Portal.profile import patient_profile_bp
from routes.Patient_Portal.medical_info import patient_medical_info_bp
from routes.Patient_Portal.patient_messaging import patient_messaging_bp
from routes.Website.vaccines import vaccines_bp
from routes.Website.nutrition import nutrition_bp
# routes of doctor portal
from routes.Doctor_Portal.Dashboard import doctor_main
from routes.Doctor_Portal.availability_management import availability_bp
from routes.Doctor_Portal.settings_management import settings_bp
from routes.Doctor_Portal.patients_management import patients_bp
from routes.Doctor_Portal.disease_management import disease_management_bp
from routes.Doctor_Portal.diet_plan_management import diet_plans_bp
from routes.Doctor_Portal.appointment_management import appointments_bp
from routes.Doctor_Portal.messaging import messaging_bp
from routes.Doctor_Portal.location_management import locations_bp
from routes.Doctor_Portal.food_item_management import food_items_bp
from routes.Doctor_Portal.vaccine_management import vaccine_management_bp

#Apis
from routes.api.user_alerts import user_alerts_bp

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
app.register_blueprint(home_bp)
app.register_blueprint(department_bp)
app.register_blueprint(doctor_bp) # <-- Register doctor blueprint
app.register_blueprint(appointment_bp) # Example
app.register_blueprint(messaging_bp)
app.register_blueprint(locations_bp)
app.register_blueprint(structure_bp)
app.register_blueprint(disease_info_bp)
app.register_blueprint(food_items_bp)
app.register_blueprint(vaccine_management_bp)
# Patient Portal
app.register_blueprint(patient_profile_bp)
app.register_blueprint(patient_medical_info_bp)
app.register_blueprint(patient_messaging_bp)
app.register_blueprint(vaccines_bp, url_prefix='/vaccination-center') # Or your desired prefix
app.register_blueprint(user_alerts_bp)
# In your app.py or wherever you create the app
app.register_blueprint(nutrition_bp, url_prefix='/nutrition')
# --- Basic Routes ---

# Add a simple health check endpoint (optional but good practice)
@app.route('/health')
def health_check():
    return "OK", 200

# --- Run the App ---
if __name__ == '__main__':
    # Use environment variables for host/port if possible
    host = os.environ.get('FLASK_RUN_HOST', '0.0.0.0')
    port = int(os.environ.get('FLASK_RUN_PORT', 54321))
    debug = os.environ.get('FLASK_DEBUG', 'True').lower() in ['true', '1', 't']
    app.logger.info(f"Starting Flask app on {host}:{port} (Debug: {debug})")
    app.run(debug=debug, host=host, port=port)