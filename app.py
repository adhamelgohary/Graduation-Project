from flask import Flask, redirect, render_template, url_for
from flask_login import login_required, current_user
from routes.auth import auth_bp, init_login_manager
from routes.Admin_Portal.admin import admin_main
from routes.Admin_Portal.Doctors_Management import admin_doctors
from routes.Admin_Portal.Patient_Management import admin_patients
from routes.Admin_Portal.Users_Management import admin_users
from routes.Admin_Portal.Audit_Logs import admin_audit
from routes.Admin_Portal.Registiration_Approval_System import doctor_approvals

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'  # Change this to a secure random key
app.config['PERMANENT_SESSION_LIFETIME'] = 1800  # Session timeout in seconds (30 minutes)

# Register blueprints
app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(admin_main)
app.register_blueprint(admin_doctors)
app.register_blueprint(admin_patients)
app.register_blueprint(admin_users)
app.register_blueprint(admin_audit)
app.register_blueprint(doctor_approvals)

# Initialize login manager
init_login_manager(app)


@app.route('/')
def home():
    return redirect(url_for('auth.login'))  # Make sure 'auth.login' is the correct view

if __name__ == '__main__':
    app.run(debug=True,host='0.0.0.0',port=54321) # Set debug=True for easier development