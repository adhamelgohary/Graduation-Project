import os
import time
import logging
from flask import Flask, redirect, url_for, render_template, request, g
from flask_login import login_required, current_user
from functools import wraps

from utils.directory_configs import configure_directories
from utils.template_helpers import register_template_helpers
from utils.logging_config import setup_logging, log_api_request, log_security_event

from routes.login import login_bp, init_login_manager
from routes.register import register_bp

from routes.Website.home import home_bp
from routes.Website.department import department_bp
from routes.Website.doctor import doctor_bp
from routes.Website.appointments import appointment_bp
from routes.Website.disease_info import disease_info_bp

from routes.Admin_Portal.Dashboard import admin_main
from routes.Admin_Portal.Admins_Management import admin_management
from routes.Admin_Portal.Doctors_Management import Doctors_Management
from routes.Admin_Portal.Patient_Management import patient_management
from routes.Admin_Portal.Registiration_Approval_System import registration_approval
from routes.Admin_Portal.search_users import search_users_bp
from routes.Admin_Portal.Appointments import admin_appointments_bp
from routes.Admin_Portal.structure_management import structure_bp

from routes.Patient_Portal.profile import patient_profile_bp
from routes.Patient_Portal.medical_info import patient_medical_info_bp
from routes.Patient_Portal.patient_messaging import patient_messaging_bp
from routes.Website.vaccines import vaccines_bp
from routes.Website.nutrition import nutrition_bp

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

from routes.api.user_alerts import user_alerts_bp

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get(
    "FLASK_SECRET_KEY", "default-insecure-secret-key-change-me!"
)
if app.config["SECRET_KEY"] == "default-insecure-secret-key-change-me!":
    app.logger.warning(
        "SECURITY WARNING: Using default SECRET_KEY. Please set FLASK_SECRET_KEY environment variable."
    )
app.config["PERMANENT_SESSION_LIFETIME"] = int(
    os.environ.get("FLASK_SESSION_LIFETIME", 1800)
)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

configure_directories(app)
register_template_helpers(app)

setup_logging(app)

init_login_manager(app)

app.register_blueprint(login_bp)
app.register_blueprint(register_bp)
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
app.register_blueprint(doctor_bp)
app.register_blueprint(appointment_bp)
app.register_blueprint(messaging_bp)
app.register_blueprint(locations_bp)
app.register_blueprint(structure_bp)
app.register_blueprint(disease_info_bp)
app.register_blueprint(food_items_bp)
app.register_blueprint(vaccine_management_bp)
app.register_blueprint(patient_profile_bp)
app.register_blueprint(patient_medical_info_bp)
app.register_blueprint(patient_messaging_bp)
app.register_blueprint(vaccines_bp, url_prefix="/vaccination-center")
app.register_blueprint(user_alerts_bp)
app.register_blueprint(nutrition_bp, url_prefix="/nutrition")


@app.before_request
def before_request_logging():
    g.start_time = time.time()
    g.request_ip = request.environ.get("HTTP_X_FORWARDED_FOR") or request.environ.get(
        "REMOTE_ADDR"
    )


@app.after_request
def after_request_logging(response):
    if hasattr(g, "start_time"):
        duration = (time.time() - g.start_time) * 1000
        user_id = current_user.get_id() if current_user.is_authenticated else None
        log_api_request(
            method=request.method,
            path=request.path,
            status_code=response.status_code,
            duration_ms=duration,
            user_id=user_id,
            ip_address=getattr(g, "request_ip", None),
        )
    return response


@app.errorhandler(Exception)
def handle_exception(e):
    app.logger.exception(f"Unhandled exception: {e}")
    log_security_event(
        event_type="UNHANDLED_EXCEPTION",
        user_id=current_user.get_id() if current_user.is_authenticated else None,
        ip_address=request.environ.get("REMOTE_ADDR"),
        details={"error": str(e), "path": request.path},
    )
    return render_template("errors/500.html"), 500


@app.route("/health")
def health_check():
    return "OK", 200


if __name__ == "__main__":
    sentry_dsn = os.environ.get("SENTRY_DSN")
    if sentry_dsn:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.flask import FlaskIntegration

            sentry_sdk.init(
                dsn=sentry_dsn,
                integrations=[FlaskIntegration()],
                traces_sample_rate=0.1,
                environment=os.environ.get("ENVIRONMENT", "production"),
            )
            app.logger.info("Sentry initialized")
        except ImportError:
            app.logger.warning("Sentry SDK not installed")

    host = os.environ.get("FLASK_RUN_HOST", "0.0.0.0")
    port = int(os.environ.get("FLASK_RUN_PORT", 54321))
    debug = os.environ.get("FLASK_DEBUG", "True").lower() in ["true", "1", "t"]
    app.logger.info(f"Starting Flask app on {host}:{port} (Debug: {debug})")
    app.run(debug=debug, host=host, port=port)
