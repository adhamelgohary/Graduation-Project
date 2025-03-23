from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import mysql.connector
from db import get_db_connection
from datetime import datetime
from functools import wraps

auth_bp = Blueprint('auth', __name__, template_folder="templates")

# User class for Flask-Login
class User(UserMixin):
    def __init__(self, user_data):
        self.id = user_data['user_id']
        self.username = user_data['username']
        self.email = user_data['email']
        self.user_type = user_data['user_type']
        self.account_status = user_data['account_status']
        self.first_name = user_data['first_name']
        self.last_name = user_data['last_name']
        # Add any other user attributes you need

    def get_id(self):
        return str(self.id)
    
    def is_active(self):
        return self.account_status == 'active'
    
    def is_admin(self):
        return self.user_type == 'admin'

# Initialize Flask-Login
login_manager = LoginManager()

# This function needs to be called in your app's initialization
def init_login_manager(app):
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'

# Admin required decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.user_type != 'admin':
            flash('You need administrator privileges to access this page.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

# User loader callback
@login_manager.user_loader
def load_user(user_id):
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            user_data = cursor.fetchone()
            if user_data:
                return User(user_data)
        except mysql.connector.Error:
            pass
        finally:
            if connection.is_connected():
                cursor.close()
                connection.close()
    return None

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # Redirect if user is already logged in
    if current_user.is_authenticated:
        # Redirect to appropriate dashboard based on user type
        if current_user.user_type == 'admin':
            return redirect(url_for('admin_main.dashboard'))
        elif current_user.user_type == 'patient':
            return redirect(url_for('patient.dashboard'))
        elif current_user.user_type == 'doctor':
            return redirect(url_for('doctor.dashboard'))
        else:
            return redirect(url_for('index'))
        
    if request.method == 'POST':
        identifier = request.form.get('identifier')  # This will be email or username
        password = request.form.get('password')
        remember = 'remember' in request.form
        
        # Validate input fields
        if not identifier or not password:
            flash('Please enter both identifier and password', 'error')
            return render_template('Login.html')
        
        # Connect to database
        connection = get_db_connection()
        if connection:
            try:
                cursor = connection.cursor(dictionary=True)
                
                # Query to find user by email or username
                query = """
                SELECT * FROM users 
                WHERE (email = %s OR username = %s)
                """
                cursor.execute(query, (identifier, identifier))
                user_data = cursor.fetchone()
                
                # If not found, try checking patients table for insurance policy number
                if not user_data and identifier:
                    # First find the patient with this insurance policy number
                    query = """
                    SELECT u.* FROM users u
                    JOIN patients p ON u.user_id = p.user_id
                    WHERE p.insurance_policy_number = %s
                    """
                    cursor.execute(query, (identifier,))
                    user_data = cursor.fetchone()
                
                # Check if this user exists in pending registrations
                if not user_data:
                    query = """
                    SELECT * FROM pending_registrations 
                    WHERE (email = %s OR username = %s)
                    """
                    cursor.execute(query, (identifier, identifier))
                    pending_user = cursor.fetchone()
                    
                    if pending_user:
                        # Check password for pending user - direct comparison
                        if pending_user['password'] == password:
                            flash('Your account is pending approval. An administrator will review your registration soon.', 'info')
                        else:
                            flash('Invalid credentials. Please try again.', 'error')
                        return render_template('Login.html')
                
                if user_data and user_data['password'] == password:
                    # Create user object
                    user = User(user_data)
                    
                    # Check if account is active
                    if not user.is_active():
                        flash(f'Your account is {user_data["account_status"]}. Please contact support.', 'warning')
                        return render_template('Login.html')
                    
                    # Login the user
                    login_user(user, remember=remember)
                    
                    # Redirect based on user type
                    if user.user_type == 'admin':
                        return redirect(url_for('admin_main.dashboard'))
                    elif user.user_type == 'patient':
                        return redirect(url_for('patient.dashboard'))
                    elif user.user_type == 'doctor':
                        return redirect(url_for('doctor.dashboard'))
                    else:
                        return redirect(url_for('index'))
                else:
                    flash('Invalid credentials. Please try again.', 'error')
            except mysql.connector.Error as err:
                flash(f'Database error: {err}', 'error')
            finally:
                if connection.is_connected():
                    cursor.close()
                    connection.close()
        else:
            flash('Database connection error', 'error')
            
        return render_template('Login.html')
        
    # GET request - render login form
    return render_template('Login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    # Redirect if user is already logged in
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        user_type = request.form.get('user_type')
        phone = request.form.get('phone')
        city = request.form.get('city')
        country = request.form.get('country', 'United States')
        
        # Additional patient fields
        date_of_birth = request.form.get('date_of_birth')
        gender = request.form.get('gender')
        insurance_provider = request.form.get('insurance_provider')
        insurance_policy_number = request.form.get('insurance_policy_number')
        insurance_group_number = request.form.get('insurance_group_number')
        
        # Additional doctor fields
        specialization = request.form.get('specialization')
        license_number = request.form.get('license_number')
        license_state = request.form.get('license_state')
        license_expiration = request.form.get('license_expiration')
        
        # Validate required input fields
        if not all([username, email, password, confirm_password, first_name, last_name, user_type]):
            flash('Please fill in all required fields', 'error')
            return render_template('Register.html')
            
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('Register.html')
        
        # Validate user type specific fields
        if user_type == 'patient' and not all([date_of_birth, gender]):
            flash('Please fill in all required patient fields', 'error')
            return render_template('Register.html')
            
        if user_type == 'doctor' and not all([specialization, license_number, license_state, license_expiration]):
            flash('Please fill in all required doctor fields', 'error')
            return render_template('Register.html')
        
        # Connect to database
        connection = get_db_connection()
        if connection:
            try:
                cursor = connection.cursor(dictionary=True)
                
                # Check if email or username already exists in users table
                cursor.execute("SELECT * FROM users WHERE email = %s OR username = %s", (email, username))
                if cursor.fetchone():
                    flash('Email or username already registered', 'error')
                    return render_template('Register.html')
                
                # Check if email or username already exists in pending_registrations table
                cursor.execute("SELECT * FROM pending_registrations WHERE email = %s OR username = %s", (email, username))
                if cursor.fetchone():
                    flash('Email or username already pending approval', 'error')
                    return render_template('Register.html')
                
                # Start transaction
                connection.start_transaction()
                
                # Determine if registration should be immediate or pending approval
                needs_approval = user_type in ['admin', 'doctor']
                
                if needs_approval:
                    # Insert into pending_registrations table
                    query = """
                    INSERT INTO pending_registrations (
                        username, email, password, first_name, last_name, 
                        user_type, phone, city, country, 
                        date_submitted, status,
                        
                        -- Doctor/admin specific fields 
                        specialization, license_number, license_state, license_expiration,
                        
                        -- Patient specific fields (will be NULL for doctors/admins)
                        date_of_birth, gender, insurance_provider,
                        insurance_policy_number, insurance_group_number
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s
                    )
                    """
                    
                    cursor.execute(query, (
                        username, email, password, first_name, last_name,
                        user_type, phone, city, country,
                        datetime.now(), 'pending',
                        
                        # Doctor fields (will be None for non-doctors)
                        specialization if user_type == 'doctor' else None,
                        license_number if user_type == 'doctor' else None,
                        license_state if user_type == 'doctor' else None,
                        license_expiration if user_type == 'doctor' else None,
                        
                        # Patient fields (will be None for doctors/admins)
                        None, None, None, None, None
                    ))
                    
                    # Commit the transaction
                    connection.commit()
                    
                    flash('Registration submitted for approval. You will be notified when your account is approved.', 'info')
                    return redirect(url_for('auth.login'))
                    
                else:
                    # Regular registration process for patients
                    query = """
                    INSERT INTO users (
                        username, email, password, first_name, last_name, 
                        user_type, phone, city, country, account_status
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """
                    cursor.execute(query, (
                        username, email, password, first_name, last_name,
                        user_type, phone, city, country, 'active'
                    ))
                    
                    # Get the new user_id
                    user_id = cursor.lastrowid
                    
                    # If user_type is patient, add patient-specific info
                    if user_type == 'patient':
                        query = """
                        INSERT INTO patients (
                            user_id, date_of_birth, gender, insurance_provider,
                            insurance_policy_number, insurance_group_number
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s
                        )
                        """
                        cursor.execute(query, (
                            user_id, date_of_birth, gender, insurance_provider,
                            insurance_policy_number, insurance_group_number
                        ))
                    
                    # Commit the transaction
                    connection.commit()
                    
                    flash('Registration successful! Please log in.', 'success')
                    return redirect(url_for('auth.login'))
                
            except mysql.connector.Error as err:
                # Rollback in case of error
                connection.rollback()
                flash(f'Database error: {err}', 'error')
            finally:
                if connection.is_connected():
                    cursor.close()
                    connection.close()
        else:
            flash('Database connection error', 'error')
            
        return render_template('Register.html')
    
    # GET request - render registration form
    return render_template('Register.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('auth.login'))