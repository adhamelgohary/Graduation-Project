# routes/password_reset.py

from flask import (Blueprint, render_template, request, redirect, url_for, flash,current_app)
from werkzeug.security import generate_password_hash
import mysql.connector
from db import get_db_connection
from datetime import datetime, timedelta
import secrets # For secure token generation

# --- Flask-Mail Imports ---
from flask_mail import Message
# Import the 'mail' instance created and initialized in app.py
try:
    from app import mail # Assumes your main Flask app instance is in app.py
except ImportError:
    mail = None
    print("WARNING: Could not import 'mail' object from main app. Email sending will fail.")


password_reset_bp = Blueprint('password_reset', __name__, template_folder="../templates")

# --- Configuration ---
RESET_TOKEN_EXPIRY_MINUTES = 60 # How long the reset token is valid

# --- Helper Function to Send Email ---
def send_reset_email(user_email, token):
    """Sends the password reset email using Flask-Mail."""
    if mail is None:
        current_app.logger.error("Flask-Mail object ('mail') is not initialized. Cannot send email.")
        # Flash a generic error, don't reveal configuration issues to the user directly
        flash("Password reset email could not be sent due to a server configuration issue. Please contact support.", "danger")
        return False

    # Generate the password reset URL
    reset_url = url_for('password_reset.reset_password_route', token=token, _external=True)
    # _external=True is important to generate the full URL including domain

    try:
        # Create the email message object
        # Subject line
        # Sender is automatically taken from app.config['MAIL_DEFAULT_SENDER']
        # Recipients is a list containing the user's email
        msg = Message('Password Reset Request - Health Portal',
                      recipients=[user_email])

        # Email body (Plain Text)
        msg.body = f'''Dear User,

To reset your password for the Health Portal, please click the following link:
{reset_url}

This link will expire in {RESET_TOKEN_EXPIRY_MINUTES} minutes.

If you did not request a password reset, please ignore this email and your password will remain unchanged.

Sincerely,
The Health Portal Team
'''
        # Optionally, add an HTML version for richer emails:
        # msg.html = render_template('email/reset_password_email.html', # Create this template if desired
        #                            reset_url=reset_url,
        #                            expiry_minutes=RESET_TOKEN_EXPIRY_MINUTES)

        # Send the email
        mail.send(msg)
        current_app.logger.info(f"Password reset email successfully sent to {user_email}")
        return True # Indicate success

    except Exception as e:
        # Log the full error for debugging
        current_app.logger.error(f"Failed to send password reset email to {user_email}: {e}", exc_info=True)
        # Flash a generic error to the user
        flash("An error occurred while trying to send the reset email. Please try again later or contact support.", "danger")
        return False # Indicate failure


# --- Route to Request Password Reset ---
@password_reset_bp.route('/request_reset', methods=['GET', 'POST'])
def request_reset_route():
    """Handles the request for a password reset link."""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()

        # Basic validation
        if not email:
            flash('Please enter your email address.', 'warning')
            return render_template('request_reset.html', form_data=request.form)
        # Add more robust email validation if needed

        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            if not connection or not connection.is_connected():
                raise ConnectionError("Database connection failed.")

            # Make sure autocommit is off if needed by get_db_connection
            # connection.autocommit = False # Usually default

            cursor = connection.cursor(dictionary=True)

            # Find the user by email
            cursor.execute("SELECT user_id, email FROM users WHERE email = %s", (email,))
            user = cursor.fetchone()

            # Process whether user exists or not to prevent email enumeration
            user_exists = bool(user)
            user_id_log = user['user_id'] if user_exists else "N/A"

            if user_exists:
                # Generate secure token and expiry time
                token = secrets.token_urlsafe(32)
                expiry_time = datetime.utcnow() + timedelta(minutes=RESET_TOKEN_EXPIRY_MINUTES)

                # Store token and expiry in the database for the found user
                update_sql = """
                    UPDATE users
                    SET reset_token = %s, reset_token_expiry = %s
                    WHERE user_id = %s
                """
                cursor.execute(update_sql, (token, expiry_time, user['user_id']))
                connection.commit() # Commit the token update
                current_app.logger.info(f"Reset token generated and stored for user_id {user['user_id']} ({email}).")

                # Attempt to send the email
                send_reset_email(user['email'], token)
                # Don't flash success here, do it universally below

            else:
                # User not found, log it but don't tell the requester
                current_app.logger.warning(f"Password reset requested for non-existent email: {email}")

            # --- Universal User Feedback ---
            # Flash this message whether the user was found or not,
            # and regardless of email sending success (errors are flashed separately)
            flash('If an account with that email exists, instructions to reset your password have been sent.', 'info')
            # Redirect to login page to prevent repeated submissions easily
            return redirect(url_for('login.login_route'))

        except (mysql.connector.Error, ConnectionError) as db_err:
            # Rollback if a transaction was started and failed
            if connection and connection.is_connected():
                 try: connection.rollback()
                 except mysql.connector.Error: pass # Ignore rollback errors if connection already closed
            flash('An error occurred processing your request. Please try again later.', 'danger')
            current_app.logger.error(f"Database error during password reset request for {email} (User ID: {user_id_log}): {db_err}")
            return redirect(url_for('password_reset.request_reset_route')) # Redirect back to the request form

        except Exception as e:
            if connection and connection.is_connected():
                 try: connection.rollback()
                 except mysql.connector.Error: pass
            flash('An unexpected error occurred. Please try again later.', 'danger')
            current_app.logger.error(f"Unexpected error during password reset request for {email} (User ID: {user_id_log}): {e}", exc_info=True)
            return redirect(url_for('password_reset.request_reset_route'))

        finally:
            if cursor: cursor.close()
            if connection and connection.is_connected(): connection.close()

    # --- GET Request ---
    # Show the form to enter the email address
    return render_template('request_reset.html', form_data={})


# --- Route to Actually Reset the Password (using token) ---
@password_reset_bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password_route(token):
    """Handles the form submission for setting a new password using a token."""
    connection = None
    cursor = None

    # --- Verify Token First (before showing form or processing POST) ---
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            raise ConnectionError("Database connection failed.")
        cursor = connection.cursor(dictionary=True)

        # Find user by token AND check expiry time using MySQL's UTC_TIMESTAMP()
        # It's crucial that reset_token_expiry was stored as UTC time
        cursor.execute("""
            SELECT user_id, email
            FROM users
            WHERE reset_token = %s AND reset_token_expiry > UTC_TIMESTAMP()
        """, (token,))
        user = cursor.fetchone()

        # If no user found with that valid token, redirect
        if not user:
            flash('Invalid or expired password reset link. Please request a new one if needed.', 'danger')
            current_app.logger.warning(f"Invalid or expired token used for password reset attempt: {token}")
            return redirect(url_for('login.login_route'))

        # --- Token is VALID ---

        # --- Handle POST Request (Form Submission) ---
        if request.method == 'POST':
            password = request.form.get('password')
            confirm_password = request.form.get('confirm_password')

            # Validate passwords
            errors = []
            if not password or not confirm_password:
                errors.append('Please enter and confirm your new password.')
            elif password != confirm_password:
                errors.append('Passwords do not match.')
            elif len(password) < 8: # Basic length check
                 errors.append('Password must be at least 8 characters long.')
            # Add more password complexity rules if desired

            if errors:
                for error in errors:
                    flash(error, 'danger')
                # Render the form again, passing the token so the form action URL works
                return render_template('reset_password.html', token=token, form_data=request.form)

            # --- Passwords are valid, proceed to update ---
            try:
                hashed_password = generate_password_hash(password)

                # Start transaction for the update
                connection.start_transaction()

                # Update password and clear token fields in the database
                # Use the user_id AND token in WHERE clause for extra check
                update_sql = """
                    UPDATE users
                    SET password = %s, reset_token = NULL, reset_token_expiry = NULL
                    WHERE user_id = %s AND reset_token = %s
                """
                cursor.execute(update_sql, (hashed_password, user['user_id'], token))

                # Check if the update actually affected a row
                if cursor.rowcount == 1:
                    connection.commit() # Commit the changes
                    flash('Your password has been successfully reset! You can now log in.', 'success')
                    current_app.logger.info(f"Password successfully reset for user_id {user['user_id']} using token {token[:6]}...") # Log partial token
                    # Optional: Log the user in automatically here
                    # from flask_login import login_user
                    # Fetch the full user object if needed by login_user
                    # login_user(user_object_needed_by_loader)
                    return redirect(url_for('login.login_route'))
                else:
                    # Very unlikely, but could happen if token was used/invalidated between verify check and update
                    connection.rollback()
                    flash('Could not reset password. The link might have expired or been used already. Please request a new link.', 'danger')
                    current_app.logger.error(f"Failed to update password for user_id {user['user_id']} - rowcount was 0 (token mismatch/concurrency?). Token: {token[:6]}...")
                    return redirect(url_for('login.login_route'))

            except (mysql.connector.Error, ConnectionError) as db_err_update:
                 if connection.is_connected():
                      try: connection.rollback()
                      except mysql.connector.Error: pass
                 flash('A database error occurred while updating your password. Please try again.', 'danger')
                 current_app.logger.error(f"Database error during password update for user_id {user['user_id']}: {db_err_update}")
                 # Render form again, keeping token
                 return render_template('reset_password.html', token=token, form_data=request.form)
            except Exception as e_update:
                 if connection.is_connected():
                      try: connection.rollback()
                      except mysql.connector.Error: pass
                 flash('An unexpected error occurred while updating your password. Please try again.', 'danger')
                 current_app.logger.error(f"Unexpected error during password update for user_id {user['user_id']}: {e_update}", exc_info=True)
                 return render_template('reset_password.html', token=token, form_data=request.form)

        # --- GET Request ---
        # Token was validated above, show the password reset form
        return render_template('reset_password.html', token=token, form_data={})

    # --- Handle Errors During Initial Token Verification ---
    except (mysql.connector.Error, ConnectionError) as db_err_check:
        flash('An error occurred verifying the reset link. Please try again later or contact support.', 'danger')
        current_app.logger.error(f"Database error checking reset token {token[:6]}...: {db_err_check}")
        return redirect(url_for('login.login_route'))
    except Exception as e_check:
        flash('An unexpected error occurred. Please try again later or contact support.', 'danger')
        current_app.logger.error(f"Unexpected error checking reset token {token[:6]}...: {e_check}", exc_info=True)
        return redirect(url_for('login.login_route'))
    finally:
        # Ensure DB resources are released
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()