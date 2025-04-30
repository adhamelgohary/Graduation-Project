# /auth/login.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, session # Added Session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
# REMOVED: from werkzeug.security import check_password_hash - Still using plain text based on schema/comments
import mysql.connector
from db import get_db_connection # Assuming db.py exists
from functools import wraps

login_bp = Blueprint('login', __name__, template_folder="../templates") # Adjust path if needed

# User class for Flask-Login (Aligned with 'users' table)
# ADDED fetch for doctor verification status
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
        # Store doctor specific status if applicable
        self.doctor_verification_status = user_data.get('doctor_verification_status') # Will be None for non-doctors

    def get_id(self):
        return str(self.id)

    @property
    def is_active(self):
        # Core check remains the same - user needs active account to login AT ALL
        return self.account_status == 'active'

    # Add property to check if full doctor access is granted
    @property
    def is_fully_verified_doctor(self):
        return self.is_doctor() and self.doctor_verification_status == 'approved'

    # Add property to check if doctor needs to provide info
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

def init_login_manager(app):
    login_manager.init_app(app)
    login_manager.login_view = 'login.login_route' # Ensure this matches blueprint name and route function
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    connection = get_db_connection()
    user = None # Initialize user as None
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            # Fetch user data AND doctor verification status if user_type is doctor
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
            # Use current_app logger if available, otherwise print
            logger = current_app.logger if current_app else print
            logger(f"Database error loading user {user_id}: {err}")
            pass # Return None on error
        finally:
            if connection.is_connected():
                cursor.close()
                connection.close()
    return user

# --- Decorators ---
# (Keep existing decorators: admin_required, doctor_required)
# You might want a NEW decorator for features requiring FULL doctor verification

def fully_verified_doctor_required(f):
    @wraps(f)
    @login_required # Depends on login_required first
    def decorated_function(*args, **kwargs):
        # Check user type and verification status
        if not current_user.is_fully_verified_doctor:
            flash('Full doctor verification required to access this feature. Please complete your profile.', 'warning')
            # Redirect to doctor dashboard or specific info page
            return redirect(url_for('doctor_main.dashboard')) # Adjust target route as needed
        return f(*args, **kwargs)
    return decorated_function

# --- Routes ---

@login_bp.route('/login', methods=['GET', 'POST'])
def login_route():
    if current_user.is_authenticated:
        # Redirect based on type (no change here)
        if current_user.is_admin():
            return redirect(url_for('admin_main.dashboard'))
        elif current_user.is_patient():
            return redirect(url_for('patient.dashboard'))
        elif current_user.is_doctor():
            return redirect(url_for('doctor_main.dashboard'))
        else:
            return redirect(url_for('main.index')) # Fallback

    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip()
        password = request.form.get('password', '').strip()
        remember = 'remember' in request.form

        if not identifier or not password:
            flash('Please enter both identifier (email/username) and password.', 'warning')
            return render_template('Login.html')

        connection = get_db_connection()
        if not connection:
            flash('Database connection error. Please try again later.', 'danger')
            return render_template('Login.html')

        user_data = None
        try:
            cursor = connection.cursor(dictionary=True)

            # WARNING: Fetching plain text password. Extremely insecure.
            # Added doctor verification status fetch
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
            # WARNING: Direct password comparison. Extremely insecure. Replace with hash check ASAP.
            if user_data and user_data['password'] == password:
                # Check ACCOUNT status first (must be active to login)
                if user_data['account_status'] == 'active':
                    user = User(user_data)
                    login_user(user, remember=remember)
                    # flash('Login successful!', 'success') # Flash message moved below

                    # --- Post-Login Logic & Redirect ---
                    next_page = request.args.get('next')

                    if user.is_admin():
                        flash('Admin login successful!', 'success')
                        return redirect(next_page or url_for('admin_main.dashboard'))
                    elif user.is_patient():
                        flash('Login successful!', 'success')
                        return redirect(next_page or url_for('patient.dashboard'))
                    elif user.is_doctor():
                        # Check doctor-specific status for appropriate message/redirect
                        if user.is_fully_verified_doctor:
                            flash('Doctor login successful!', 'success')
                            return redirect(next_page or url_for('doctor_main.dashboard'))
                        elif user.doctor_needs_info:
                            flash('Login successful. Please upload the required documents to complete verification.', 'info')
                            # Redirect to doctor dashboard where the prompt should appear
                            return redirect(next_page or url_for('doctor_main.dashboard'))
                        else: # Other doctor statuses (pending, rejected - should ideally not be active)
                            flash(f'Login successful, but account verification status is: {user.doctor_verification_status}. Please contact support.', 'warning')
                            # Redirect to a limited view or dashboard
                            return redirect(next_page or url_for('doctor_main.dashboard')) # Adjust as needed
                    else:
                        # Fallback for unknown user types (if schema allows others)
                        flash('Login successful!', 'success')
                        return redirect(next_page or url_for('main.index'))

                # --- Handle Non-Active Account Statuses ---
                elif user_data['account_status'] == 'pending':
                     # This 'pending' should now primarily apply to initial creation before admin action
                     # Doctors moved to 'info_requested' will have 'active' status but 'pending_info' verification
                     flash('Your account is pending activation or initial approval. Please wait or contact support.', 'warning')
                elif user_data['account_status'] == 'suspended':
                     flash('Your account has been suspended. Please contact support.', 'danger')
                elif user_data['account_status'] == 'inactive':
                     flash('Your account is inactive. Please contact support.', 'warning')
                else:
                    # Catch any other unexpected account statuses
                    flash(f'Account status: {user_data["account_status"]}. Login denied.', 'warning')

            else: # Incorrect password or user not found
                flash('Invalid credentials. Please check your email/username and password.', 'danger')

        except mysql.connector.Error as err:
            flash(f'An error occurred during login: {err}. Please try again.', 'danger')
            current_app.logger.error(f"Login DB Error: {err}")
        except KeyError as e:
             flash('Login system configuration error. Please contact support.', 'danger')
             current_app.logger.error(f"Login Configuration Error: Missing key {e}. Ensure DB schema matches code expectations (e.g., 'password' column).")
        finally:
            if connection.is_connected():
                cursor.close()
                connection.close()

        # Render login again if any failure occurs before successful redirect
        return render_template('Login.html')

    # GET Request
    return render_template('Login.html')


@login_bp.route('/logout')
@login_required
def logout_route():
    logout_user()
    flash('You have been successfully logged out.', 'info')
    return redirect(url_for('login.login_route'))