# /auth/login.py
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, session, current_app
)
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash # Import these for secure passwords
import mysql.connector
from db import get_db_connection # Assuming db.py exists
from functools import wraps
from urllib.parse import urlparse, urljoin # Needed for safe redirect validation

login_bp = Blueprint('login', __name__, template_folder="../templates/auth") # Assuming templates are in templates/auth for this blueprint

# --- User Class (MODIFIED) ---
class User(UserMixin):
    def __init__(self, user_data_dict): # Renamed param for clarity
        self.id = user_data_dict['user_id'] # Stored as int in DB, UserMixin expects get_id() to return str
        self.username = user_data_dict['username']
        self.email = user_data_dict['email']
        self.user_type = user_data_dict['user_type']
        self.account_status = user_data_dict['account_status']
        self.first_name = user_data_dict['first_name']
        self.last_name = user_data_dict['last_name']
        self.profile_picture = user_data_dict.get('profile_picture')
        # <<< ADDED PHONE ATTRIBUTE >>>
        self.phone = user_data_dict.get('phone') # Get phone, default to None if not present
        self.doctor_verification_status = user_data_dict.get('doctor_verification_status')

    def get_id(self):
        return str(self.id) # Flask-Login expects string ID

    @property
    def is_active(self):
        # This ensures that if account_status is None or some other unexpected value,
        # it defaults to False, preventing login.
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

# --- Flask-Login Configuration ---
login_manager = LoginManager()

def init_login_manager(app): # This function should be called from your main app factory (create_app)
    login_manager.init_app(app)
    login_manager.login_view = 'login.login_route' # Correct: blueprint_name.route_function_name
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'

# --- User Loader (MODIFIED) ---
@login_manager.user_loader
def load_user(user_id_str): # user_id from session is a string
    connection = None
    cursor = None # Initialize cursor to None
    user = None
    if not user_id_str: # Handle empty user_id_str
        return None
    try:
        user_id = int(user_id_str) # Convert to int for DB query
        connection = get_db_connection()
        if connection:
            # <<< ADDED buffered=True >>>
            cursor = connection.cursor(dictionary=True, buffered=True)
            # <<< MODIFIED SQL QUERY TO INCLUDE u.phone >>>
            cursor.execute("""
                SELECT
                    u.user_id, u.username, u.email, u.password, u.user_type, u.account_status,
                    u.first_name, u.last_name, u.profile_picture, u.phone,
                    d.verification_status AS doctor_verification_status
                FROM users u
                LEFT JOIN doctors d ON u.user_id = d.user_id AND u.user_type = 'doctor'
                WHERE u.user_id = %s
            """, (user_id,)) # Pass user_id as int
            user_data = cursor.fetchone()
            if user_data:
                user = User(user_data) # User class __init__ now handles 'phone'
    except ValueError: # If user_id_str cannot be converted to int
        logger = current_app.logger if current_app else print
        logger(f"ValueError: Invalid user_id format '{user_id_str}' in session.")
        # Optionally, clear the invalid session data here or let Flask-Login handle it.
    except mysql.connector.Error as err:
        logger = current_app.logger if current_app else print
        # Log the specific user_id being loaded for better debugging
        logger.error(f"Database error loading user (ID: {user_id_str}): {err}")
    except Exception as e: # Catch any other unexpected errors
        logger = current_app.logger if current_app else print
        logger.error(f"Unexpected error loading user (ID: {user_id_str}): {e}", exc_info=True)
    finally:
        if cursor: # Ensure cursor is closed if it was opened
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
    return user


# --- Decorators (Keep As Is) ---
def fully_verified_doctor_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_fully_verified_doctor:
            flash('Full doctor verification required to access this feature. Please complete your profile.', 'warning')
            return redirect(url_for('doctor_main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# --- Helper for Safe Redirect (Keep As Is) ---
def is_safe_url(target):
    if not target: return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    is_safe = test_url.scheme in ('http', 'https') and \
              (test_url.netloc == ref_url.netloc or not test_url.netloc)
    if is_safe:
        auth_endpoints = [url_for('login.login_route')]
        if test_url.path in auth_endpoints:
             return False
    return is_safe

# --- Routes ---
@login_bp.route('/login', methods=['GET', 'POST'])
def login_route():
    if current_user.is_authenticated:
        next_page = request.args.get('next')
        if is_safe_url(next_page):
            return redirect(next_page)
        else:
            default_url = url_for('main.index') # Define your main index route
            if hasattr(current_user, 'user_type'): # Check attribute before using
                if current_user.is_admin(): default_url = url_for('admin_main.dashboard')
                elif current_user.is_patient(): default_url = url_for('patient_profile.manage_profile')
                elif current_user.is_doctor(): default_url = url_for('doctor_main.dashboard')
            return redirect(default_url)

    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip()
        password_attempt = request.form.get('password', '').strip() # Renamed to avoid confusion
        remember = 'remember' in request.form
        next_page_attempt = request.form.get('next') or request.args.get('next')

        if not identifier or not password_attempt:
            flash('Please enter both identifier (email/username) and password.', 'warning')
            return render_template('Login.html', next=next_page_attempt)

        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            if not connection:
                flash('Database connection error. Please try again later.', 'danger')
                return render_template('Login.html', next=next_page_attempt)

            # <<< ADDED buffered=True FOR THIS CURSOR AS WELL >>>
            cursor = connection.cursor(dictionary=True, buffered=True)

            # Query now includes 'phone' which is good for consistency,
            # though User class in this file doesn't use password_hash directly from this query's result
            # it's needed by load_user.
            query = """
                SELECT
                    u.user_id, u.username, u.email, u.password AS password_hash, u.user_type,
                    u.account_status, u.first_name, u.last_name, u.profile_picture, u.phone,
                    d.verification_status AS doctor_verification_status
                FROM users u
                LEFT JOIN doctors d ON u.user_id = d.user_id AND u.user_type = 'doctor'
                WHERE u.email = %s OR u.username = %s
            """
            cursor.execute(query, (identifier, identifier))
            user_data_dict = cursor.fetchone() # Renamed for clarity

            # *** IMPORTANT: Implement Password Hashing! ***
            # You should be storing hashed passwords, not plain text.
            # Example with werkzeug.security:
            # if user_data_dict and check_password_hash(user_data_dict['password_hash'], password_attempt):
            # For now, using your existing plain text check, but flag it for URGENT security update.
            if user_data_dict and user_data_dict['password_hash'] == password_attempt: # INSECURE
                current_app.logger.warning(f"SECURITY ALERT: Plain text password check for user {identifier}. IMPLEMENT HASHING.")

                if user_data_dict['account_status'] == 'active':
                    # User data is passed to the User class, which now extracts 'phone'
                    user_for_login = User(user_data_dict)
                    login_user(user_for_login, remember=remember)
                    current_app.logger.info(f"User {user_for_login.id} ({user_for_login.username}) logged in successfully.")

                    if is_safe_url(next_page_attempt):
                        flash('Login successful!', 'success')
                        return redirect(next_page_attempt)
                    else:
                        default_redirect_url = url_for('home.index') # Define your main index route
                        if user_for_login.is_admin():
                            flash('Admin login successful!', 'success')
                            default_redirect_url = url_for('admin_main.dashboard')
                        elif user_for_login.is_patient():
                            flash('Login successful!', 'success')
                            default_redirect_url = url_for('patient_profile.manage_profile')
                        elif user_for_login.is_doctor():
                            if user_for_login.is_fully_verified_doctor: flash('Doctor login successful!', 'success')
                            elif user_for_login.doctor_needs_info: flash('Login successful. Please complete verification.', 'info')
                            else: flash(f'Login successful. Account status: {user_for_login.doctor_verification_status or "Pending Review"}.', 'info')
                            default_redirect_url = url_for('doctor_main.dashboard')
                        return redirect(default_redirect_url)
                # ... (rest of your account status checks) ...
                elif user_data_dict['account_status'] == 'pending': flash('Your account is pending approval.', 'warning')
                elif user_data_dict['account_status'] == 'suspended': flash('Your account has been suspended.', 'danger')
                elif user_data_dict['account_status'] == 'inactive': flash('Your account is inactive.', 'warning')
                else: flash(f'Account status: {user_data_dict["account_status"]}. Login denied.', 'warning')
            else:
                flash('Invalid credentials. Please check your email/username and password.', 'danger')
        except mysql.connector.Error as err:
            flash(f'An error occurred during login: {err}. Please try again.', 'danger')
            current_app.logger.error(f"Login DB Error for {identifier}: {err}")
        except KeyError as e:
             flash('Login system configuration error. Please contact support.', 'danger')
             current_app.logger.error(f"Login KeyError: Missing key {e} in user_data. Schema mismatch or query issue.")
        finally:
            if cursor: # Check if cursor was created before trying to close
                cursor.close()
            if connection and connection.is_connected():
                connection.close()
        return render_template('Login.html', next=next_page_attempt)

    next_url = request.args.get('next')
    safe_next_url = next_url if is_safe_url(next_url) else None
    if next_url and not safe_next_url:
        current_app.logger.warning(f"Unsafe 'next' URL in GET: {next_url}")
    return render_template('Login.html', next=safe_next_url)


@login_bp.route('/logout')
@login_required
def logout_route():
    # Log before logout when current_user is still available
    current_app.logger.info(f"User {current_user.id} ({current_user.username}) logging out.")
    logout_user()
    flash('You have been successfully logged out.', 'info')
    return redirect(url_for('login.login_route'))