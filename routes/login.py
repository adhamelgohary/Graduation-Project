# login.py
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, session, current_app
)
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
import mysql.connector
from db import get_db_connection
from functools import wraps
from urllib.parse import urlparse, urljoin

login_bp = Blueprint('login', __name__, template_folder="../templates/auth")

# --- User Class (Keep As Is) ---
class User(UserMixin):
    def __init__(self, user_data_dict):
        self.id = user_data_dict['user_id']
        self.username = user_data_dict['username']
        self.email = user_data_dict['email']
        self.user_type = user_data_dict['user_type']
        self.account_status = user_data_dict['account_status']
        self.first_name = user_data_dict['first_name']
        self.last_name = user_data_dict['last_name']
        self.profile_picture = user_data_dict.get('profile_picture')
        self.phone = user_data_dict.get('phone')
        self.doctor_verification_status = user_data_dict.get('doctor_verification_status')

    def get_id(self):
        return str(self.id)

    @property
    def is_active(self):
        return self.account_status == 'active'

    @property
    def is_fully_verified_doctor(self):
        return self.is_doctor() and self.doctor_verification_status == 'approved'

    @property
    def doctor_needs_info(self):
        return self.is_doctor() and self.doctor_verification_status == 'pending_info'

    def is_admin(self):
        return self.user_type == 'admin'

    def is_doctor(self):
        return self.user_type == 'doctor'

    def is_patient(self):
        return self.user_type == 'patient'

# --- Flask-Login Configuration (Keep As Is) ---
login_manager = LoginManager()

def init_login_manager(app):
    login_manager.init_app(app)
    login_manager.login_view = 'login.login_route'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'

# --- User Loader (Keep As Is) ---
@login_manager.user_loader
def load_user(user_id_str):
    connection = None
    cursor = None
    user = None
    if not user_id_str:
        return None
    try:
        user_id = int(user_id_str)
        connection = get_db_connection()
        if connection and connection.is_connected():
            cursor = connection.cursor(dictionary=True, buffered=True)
            cursor.execute("""
                SELECT
                    u.user_id, u.username, u.email, u.password, u.user_type, u.account_status,
                    u.first_name, u.last_name, u.profile_picture, u.phone,
                    d.verification_status AS doctor_verification_status
                FROM users u
                LEFT JOIN doctors d ON u.user_id = d.user_id AND u.user_type = 'doctor'
                WHERE u.user_id = %s
            """, (user_id,))
            user_data = cursor.fetchone()
            if user_data:
                user = User(user_data)
        else:
            current_app.logger.error(f"load_user: Failed to get DB connection for user_id {user_id_str}")
    except ValueError:
        current_app.logger.error(f"ValueError: Invalid user_id format '{user_id_str}' in session for load_user.")
    except mysql.connector.Error as err:
        current_app.logger.error(f"Database error loading user (ID: {user_id_str}): {err}")
    except Exception as e:
        current_app.logger.error(f"Unexpected error loading user (ID: {user_id_str}): {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()
    return user

# --- Decorators (Keep As Is) ---
def fully_verified_doctor_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_fully_verified_doctor:
            flash('Full doctor verification required. Please complete your profile.', 'warning')
            return redirect(url_for('doctor_main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# --- Helper for Safe Redirect (Keep As Is, but we'll use it more explicitly) ---
def is_safe_url(target):
    if not target: return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    is_safe = test_url.scheme in ('http', 'https') and \
              (test_url.netloc == ref_url.netloc or not test_url.netloc) # Allow relative paths

    # Disallow redirection to login, register, or logout pages to prevent loops or unintended behavior
    # Ensure your endpoint names are correct here
    disallowed_endpoints = ['login.login_route', 'login.logout_route']
    if hasattr(current_app.blueprints.get('register'), 'register_route'): # Check if register blueprint and route exist
        disallowed_endpoints.append('register.register_route')

    if is_safe:
        try:
            # Attempt to match the path part of the URL to known disallowed endpoints
            # This is a bit more robust than simple string matching of the full URL
            from flask import match_ሶ_request
            rule, _ = current_app.url_map.bind_to_environ(request.environ).match(test_url.path)
            if rule in disallowed_endpoints:
                current_app.logger.debug(f"is_safe_url: Denying redirect to auth endpoint: {test_url.path} (matched {rule})")
                return False
        except Exception: # werkzeug.routing.exceptions.NotFound or other issues
            # If matching fails for some reason, fall back to simpler path check
            # This part might be less precise
            auth_url_paths = [url_for(ep) for ep in disallowed_endpoints if current_app.blueprints.get(ep.split('.')[0])] # Get paths of auth URLs
            if test_url.path in auth_url_paths:
                current_app.logger.debug(f"is_safe_url: Denying redirect to auth path: {test_url.path}")
                return False
    return is_safe

# --- Routes ---
@login_bp.route('/login', methods=['GET', 'POST'])
def login_route():
    # If user is already authenticated, redirect them appropriately
    if current_user.is_authenticated:
        # Admin and Doctor always go to their dashboards
        if current_user.is_admin():
            return redirect(url_for('admin_main.dashboard'))
        elif current_user.is_doctor():
            return redirect(url_for('doctor_main.dashboard'))
        # Patient can try to go to 'next' page or their profile
        elif current_user.is_patient():
            next_page = request.args.get('next')
            if is_safe_url(next_page):
                return redirect(next_page)
            return redirect(url_for('patient_profile.manage_profile')) # Default for patient
        else: # Fallback for other user types or if type not set
            return redirect(url_for('home.index')) # Ensure 'home.index' exists

    # --- POST Request ---
    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip()
        password_attempt = request.form.get('password', '').strip()
        remember = 'remember' in request.form
        
        # Get 'next' from form first, then from query args
        next_page_from_form = request.form.get('next')
        next_page_from_query = request.args.get('next')
        
        # Prioritize 'next' from the form if present and valid, otherwise from query
        # This helps persist 'next' across the POST request if it was in the form's hidden field
        final_next_page_attempt = None
        if next_page_from_form:
            final_next_page_attempt = next_page_from_form
        elif next_page_from_query:
            final_next_page_attempt = next_page_from_query

        if not identifier or not password_attempt:
            flash('Please enter both identifier (email/username) and password.', 'warning')
            return render_template('Login.html', next=final_next_page_attempt if is_safe_url(final_next_page_attempt) else None)

        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            if not connection or not connection.is_connected():
                flash('Database connection error. Please try again later.', 'danger')
                current_app.logger.error("Login attempt failed: Could not connect to database.")
                return render_template('Login.html', next=final_next_page_attempt if is_safe_url(final_next_page_attempt) else None)

            cursor = connection.cursor(dictionary=True, buffered=True)
            query = """
                SELECT
                    u.user_id, u.username, u.email, u.password, u.user_type, 
                    u.account_status, u.first_name, u.last_name, u.profile_picture, u.phone,
                    d.verification_status AS doctor_verification_status
                FROM users u
                LEFT JOIN doctors d ON u.user_id = d.user_id AND u.user_type = 'doctor'
                WHERE u.email = %s OR u.username = %s
            """
            cursor.execute(query, (identifier, identifier))
            user_data_dict = cursor.fetchone()

            if user_data_dict:
                stored_hashed_password = user_data_dict['password']
                if check_password_hash(stored_hashed_password, password_attempt):
                    if user_data_dict['account_status'] == 'active':
                        user_for_login = User(user_data_dict)
                        login_user(user_for_login, remember=remember)
                        current_app.logger.info(f"User {user_for_login.id} ({user_for_login.username}) logged in successfully.")

                        # --- REDIRECT LOGIC ---
                        if user_for_login.is_admin():
                            flash('Admin login successful!', 'success')
                            return redirect(url_for('admin_main.dashboard'))
                        elif user_for_login.is_doctor():
                            if user_for_login.is_fully_verified_doctor: flash('Doctor login successful!', 'success')
                            elif user_for_login.doctor_needs_info: flash('Login successful. Please complete verification.', 'info')
                            else: flash(f'Login successful. Account status: {user_for_login.doctor_verification_status or "Pending Review"}.', 'info')
                            return redirect(url_for('doctor_main.dashboard'))
                        elif user_for_login.is_patient():
                            flash('Login successful!', 'success')
                            if is_safe_url(final_next_page_attempt):
                                return redirect(final_next_page_attempt)
                            return redirect(url_for('patient_profile.manage_profile')) # Default for patient
                        else: # Fallback for other user types
                            flash('Login successful!', 'success')
                            return redirect(url_for('home.index')) # Ensure 'home.index' exists
                    
                    # ... (handling for non-active account_status: pending, suspended, inactive) ...
                    elif user_data_dict['account_status'] == 'pending':
                        flash('Your account is pending approval. Please wait for an administrator to review your registration.', 'warning')
                    elif user_data_dict['account_status'] == 'suspended':
                        flash('Your account has been suspended. Please contact support for assistance.', 'danger')
                    elif user_data_dict['account_status'] == 'inactive':
                        flash('Your account is currently inactive. Please contact support if you believe this is an error.', 'warning')
                    else:
                        flash(f'Your account has an unusual status ({user_data_dict["account_status"]}). Login has been denied. Please contact support.', 'warning')
                else: # Password mismatch
                    flash('Invalid credentials. Please check your email/username and password.', 'danger')
                    current_app.logger.warning(f"Failed login attempt for identifier: {identifier} (password mismatch)")
            else: # User not found
                flash('Invalid credentials. Please check your email/username and password.', 'danger')
                current_app.logger.warning(f"Failed login attempt for identifier: {identifier} (user not found)")

        except mysql.connector.Error as err:
            flash(f'An error occurred during login: {err}. Please try again.', 'danger')
            current_app.logger.error(f"Login DB Error for {identifier}: {err}", exc_info=True)
        except KeyError as e:
            flash('Login system configuration error. Please contact support.', 'danger')
            current_app.logger.error(f"Login KeyError: Missing key '{e}' in user_data. Schema mismatch or query issue.", exc_info=True)
        except Exception as e:
            flash('An unexpected error occurred. Please try again.', 'danger')
            current_app.logger.error(f"Unexpected login error for {identifier}: {e}", exc_info=True)
        finally:
            if cursor: cursor.close()
            if connection and connection.is_connected(): connection.close()
        
        # If any error occurred or login failed, re-render login page, preserving the 'next' URL if safe
        return render_template('Login.html', next=final_next_page_attempt if is_safe_url(final_next_page_attempt) else None, form_data=request.form)

    # --- GET Request ---
    # 'next' URL is fetched from query parameters
    next_url_from_query = request.args.get('next')
    safe_next_url_for_template = None
    if next_url_from_query and is_safe_url(next_url_from_query):
        safe_next_url_for_template = next_url_from_query
    elif next_url_from_query: # Log if it was present but unsafe
        current_app.logger.warning(f"Unsafe 'next' URL in GET request, not passing to template: {next_url_from_query}")
        
    return render_template('Login.html', next=safe_next_url_for_template)


@login_bp.route('/logout')
@login_required
def logout_route():
    user_id_for_log = current_user.id if hasattr(current_user, 'id') else 'Unknown ID'
    username_for_log = current_user.username if hasattr(current_user, 'username') else 'Unknown Username'
    current_app.logger.info(f"User {user_id_for_log} ({username_for_log}) logging out.")
    
    logout_user()
    flash('You have been successfully logged out.', 'info')
    return redirect(url_for('login.login_route'))