# /auth/login.py
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, session, current_app
)
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
# You SHOULD be using this: from werkzeug.security import check_password_hash
import mysql.connector
from db import get_db_connection # Assuming db.py exists
from functools import wraps
from urllib.parse import urlparse, urljoin # Needed for safe redirect validation

login_bp = Blueprint('login', __name__, template_folder="../templates") # Adjust path if needed

# --- User Class and Flask-Login Setup (Keep As Is - No changes needed here for redirect) ---
class User(UserMixin):
    def __init__(self, user_data):
        self.id = user_data['user_id']
        self.username = user_data['username']
        self.email = user_data['email']
        self.user_type = user_data['user_type'] # 'patient', 'doctor', 'admin'
        self.account_status = user_data['account_status']
        self.first_name = user_data['first_name']
        self.last_name = user_data['last_name']
        self.profile_picture = user_data.get('profile_picture')
        self.doctor_verification_status = user_data.get('doctor_verification_status') # Will be None for non-doctors

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
    # This tells Flask-Login where to redirect users if @login_required fails
    login_manager.login_view = 'login.login_route'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    connection = get_db_connection()
    user = None
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("""
                SELECT
                    u.user_id, u.username, u.email, u.user_type, u.account_status,
                    u.first_name, u.last_name, u.profile_picture,
                    d.verification_status AS doctor_verification_status
                FROM users u
                LEFT JOIN doctors d ON u.user_id = d.user_id AND u.user_type = 'doctor'
                WHERE u.user_id = %s
            """, (user_id,))
            user_data = cursor.fetchone()
            if user_data:
                user = User(user_data)
        except mysql.connector.Error as err:
            logger = current_app.logger if current_app else print
            logger(f"Database error loading user {user_id}: {err}")
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()
    return user

# --- Decorators (Keep As Is) ---
def fully_verified_doctor_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_fully_verified_doctor:
            flash('Full doctor verification required to access this feature. Please complete your profile.', 'warning')
            return redirect(url_for('doctor_main.dashboard')) # Adjust target route as needed
        return f(*args, **kwargs)
    return decorated_function

# --- Helper for Safe Redirect ---
def is_safe_url(target):
    """Checks if a target URL is safe for redirection."""
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    # Allow same scheme (http/https), same network location (host:port) or relative paths
    is_safe = test_url.scheme in ('http', 'https') and \
              (test_url.netloc == ref_url.netloc or not test_url.netloc)
    # Prevent redirecting back to login/register pages after successful login
    if is_safe:
        # List of auth-related endpoints to avoid redirecting back to
        auth_endpoints = [
            url_for('login.login_route'),
            # Add other auth routes like registration, password reset etc. if they exist
            # url_for('register.register_route'),
            # url_for('auth.forgot_password_route'),
        ]
        # Check if the path part of the test URL matches any auth endpoint
        if test_url.path in auth_endpoints:
             return False # Not safe to redirect back to auth pages

    return is_safe

# --- Routes ---

@login_bp.route('/login', methods=['GET', 'POST'])
def login_route():
    # --- Handle users already logged in ---
    if current_user.is_authenticated:
        # If already logged in, check for 'next' and redirect if safe, otherwise dashboard
        next_page = request.args.get('next')
        if is_safe_url(next_page):
            current_app.logger.info(f"Authenticated user accessing login, redirecting to safe next: {next_page}")
            return redirect(next_page)
        else:
            # Determine default dashboard based on user type
            if current_user.is_admin():
                default_url = url_for('admin_main.dashboard')
            elif current_user.is_patient():
                default_url = url_for('patient_profile.manage_profile') # Or patient dashboard
            elif current_user.is_doctor():
                default_url = url_for('doctor_main.dashboard')
            else:
                default_url = url_for('main.index') # Fallback
            current_app.logger.info(f"Authenticated user accessing login, redirecting to default: {default_url}")
            return redirect(default_url)

    # --- Handle POST request (Login attempt) ---
    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip()
        password = request.form.get('password', '').strip()
        remember = 'remember' in request.form
        # Get 'next' value preferably from the hidden form field, fallback to query arg
        next_page_attempt = request.form.get('next') or request.args.get('next')

        if not identifier or not password:
            flash('Please enter both identifier (email/username) and password.', 'warning')
            # Pass 'next' back to the template so it persists in the hidden field
            return render_template('Login.html', next=next_page_attempt)

        connection = get_db_connection()
        if not connection:
            flash('Database connection error. Please try again later.', 'danger')
            return render_template('Login.html', next=next_page_attempt)

        user_data = None
        try:
            cursor = connection.cursor(dictionary=True)

            # *** EXTREMELY INSECURE: Fetching plain text password. Replace with hashing. ***
            query = """
                SELECT
                    u.user_id, u.username, u.email, u.password, u.user_type,
                    u.account_status, u.first_name, u.last_name, u.profile_picture,
                    d.verification_status AS doctor_verification_status
                FROM users u
                LEFT JOIN doctors d ON u.user_id = d.user_id AND u.user_type = 'doctor'
                WHERE u.email = %s OR u.username = %s
            """
            cursor.execute(query, (identifier, identifier))
            user_data = cursor.fetchone()

            # --- Password Verification & Status Check ---
            # *** EXTREMELY INSECURE: Direct password comparison. Replace with check_password_hash(user_data['password_hash'], password) ***
            if user_data and user_data['password'] == password:
                # Check ACCOUNT status first (must be active to login)
                if user_data['account_status'] == 'active':
                    user = User(user_data)
                    login_user(user, remember=remember)
                    current_app.logger.info(f"User {user.id} ({user.username}) logged in successfully.")

                    # --- Post-Login Logic & REDIRECT ---
                    # Validate the next_page URL before redirecting!
                    if is_safe_url(next_page_attempt):
                        flash('Login successful!', 'success') # Flash general success message
                        current_app.logger.info(f"Redirecting user {user.id} to safe next URL: {next_page_attempt}")
                        return redirect(next_page_attempt)
                    else:
                        # If 'next' is invalid or not provided, determine default redirect
                        default_redirect_url = None
                        if user.is_admin():
                            flash('Admin login successful!', 'success')
                            default_redirect_url = url_for('admin_main.dashboard')
                        elif user.is_patient():
                            flash('Login successful!', 'success')
                            default_redirect_url = url_for('patient_profile.manage_profile') # Or patient dashboard
                        elif user.is_doctor():
                            # Doctor-specific messages and default redirect
                            if user.is_fully_verified_doctor:
                                flash('Doctor login successful!', 'success')
                            elif user.doctor_needs_info:
                                flash('Login successful. Please complete verification.', 'info')
                            else: # Other statuses like pending review, rejected etc.
                                flash(f'Login successful. Account status: {user.doctor_verification_status or "Pending Review"}.', 'info')
                            default_redirect_url = url_for('doctor_main.dashboard')
                        else:
                            flash('Login successful!', 'success')
                            default_redirect_url = url_for('main.index') # Fallback

                        current_app.logger.info(f"Redirecting user {user.id} to default URL: {default_redirect_url} (next URL '{next_page_attempt}' was unsafe or missing)")
                        return redirect(default_redirect_url)

                # --- Handle Non-Active Account Statuses ---
                elif user_data['account_status'] == 'pending':
                     flash('Your account is pending activation or approval. Please wait or contact support.', 'warning')
                     current_app.logger.warning(f"Login attempt failed for {identifier}: Account pending.")
                elif user_data['account_status'] == 'suspended':
                     flash('Your account has been suspended. Please contact support.', 'danger')
                     current_app.logger.warning(f"Login attempt failed for {identifier}: Account suspended.")
                elif user_data['account_status'] == 'inactive':
                     flash('Your account is inactive. Please contact support.', 'warning')
                     current_app.logger.warning(f"Login attempt failed for {identifier}: Account inactive.")
                else:
                    flash(f'Account status: {user_data["account_status"]}. Login denied.', 'warning')
                    current_app.logger.warning(f"Login attempt failed for {identifier}: Unknown account status '{user_data['account_status']}'.")

            else: # Incorrect password or user not found
                flash('Invalid credentials. Please check your email/username and password.', 'danger')
                current_app.logger.warning(f"Login attempt failed for identifier: {identifier} - Invalid credentials.")

        except mysql.connector.Error as err:
            flash(f'An error occurred during login: {err}. Please try again.', 'danger')
            current_app.logger.error(f"Login DB Error for identifier {identifier}: {err}")
        except KeyError as e:
             flash('Login system configuration error. Please contact support.', 'danger')
             current_app.logger.error(f"Login Configuration Error: Missing key {e}. DB schema might not match code.")
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()

        # Render login again if any failure occurs before successful redirect
        # Pass 'next' back to the template so it persists
        return render_template('Login.html', next=next_page_attempt)

    # --- Handle GET Request (Show Login Form) ---
    # Get 'next' from URL query parameter if present
    next_url = request.args.get('next')
    # Don't pass along unsafe URLs to the template's hidden field
    safe_next_url = next_url if is_safe_url(next_url) else None
    if next_url and not safe_next_url:
        current_app.logger.warning(f"Unsafe 'next' URL detected in GET request: {next_url}")

    return render_template('Login.html', next=safe_next_url)


@login_bp.route('/logout')
@login_required
def logout_route():
    user_id = current_user.id
    username = current_user.username
    logout_user()
    flash('You have been successfully logged out.', 'info')
    current_app.logger.info(f"User {user_id} ({username}) logged out.")
    # Redirect to the login page after logout
    return redirect(url_for('login.login_route'))