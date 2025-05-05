# routes/Doctor_Portal/messaging.py

import mysql.connector
from flask import (
    Blueprint, render_template, request, flash, redirect, url_for,
    jsonify, current_app, abort, send_from_directory, session
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import os
from db import get_db_connection
from datetime import datetime
import math

from .utils import (
    check_doctor_authorization,
    check_provider_authorization,      # Import if used
    check_doctor_or_dietitian_authorization, # Import if used
    is_doctor_authorized_for_patient, # Import if used
    get_provider_id,
    get_enum_values,                 # Import if used
    get_all_simple,                  # Import if used
    calculate_age,                   # Import if used
    allowed_file,                    # Import if used
    generate_secure_filename,
    can_modify_appointment         # Import if used
)



# --- Blueprint Definition ---
messaging_bp = Blueprint(
    'messaging',
    __name__,
    url_prefix='/doctor/messaging',
    template_folder='../../templates' # Adjust if needed
)

# --- Configuration / Constants ---
MESSAGES_PER_PAGE = 20
CHATS_PER_PAGE = 15
# Allowed extensions are now read from app config

# --- Helper Functions ---

def allowed_attachment_file(filename):
    """Checks if the filename has an allowed extension for attachments (reads from config)."""
    allowed_extensions = current_app.config.get('ALLOWED_ATTACHMENT_EXTENSIONS', set())
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

def save_chat_attachment(file, uploader_user_id):
    """Saves an uploaded chat attachment securely (reads path from config)."""
    upload_folder = current_app.config.get('UPLOAD_FOLDER_ATTACHMENTS')
    if not upload_folder:
        current_app.logger.error("UPLOAD_FOLDER_ATTACHMENTS not configured in Flask app.")
        return None, "Server configuration error (upload path)."

    if file and allowed_attachment_file(file.filename):
        original_filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
        unique_filename = secure_filename(f"{uploader_user_id}_{timestamp}_{original_filename}")
        filepath = os.path.join(upload_folder, unique_filename)
        try:
            file.save(filepath)
            return unique_filename, None # Success
        except Exception as e:
            current_app.logger.error(f"Failed to save attachment {unique_filename} to {filepath}: {e}")
            if os.path.exists(filepath):
                try: os.remove(filepath)
                except OSError: pass
            return None, "Failed to save file."
    elif file:
        return None, "File type not allowed."
    else:
        return None, "No file provided."

def get_attachment_filepath(filename):
    """Constructs the full path for a given attachment filename (reads path from config)."""
    upload_folder = current_app.config.get('UPLOAD_FOLDER_ATTACHMENTS')
    if not upload_folder or not filename: return None
    if '..' in filename or filename.startswith('/'):
         current_app.logger.warning(f"Attempt to access potentially unsafe attachment path: {filename}")
         return None
    return os.path.join(upload_folder, filename)


# --- Database Interaction Functions ---
# These functions use queries compatible with the provided schema

def check_doctor_patient_relationship(doctor_id, patient_id):
    """ Checks if a doctor has a relationship with a patient (e.g., shared appointment). """
    conn = None; cursor = None
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        query = "SELECT 1 FROM appointments WHERE doctor_id = %s AND patient_id = %s LIMIT 1"
        cursor.execute(query, (doctor_id, patient_id))
        return cursor.fetchone() is not None
    except Exception as e:
        current_app.logger.error(f"Error checking doctor-patient relationship ({doctor_id}-{patient_id}): {e}")
        return False
    finally:
        if cursor: cursor.close();
        if conn and conn.is_connected(): conn.close()

def find_existing_chat(doctor_id, patient_id):
    """ Finds an existing active or pending chat between a doctor and patient. """
    conn = None; cursor = None
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        query = """SELECT chat_id, status FROM chats WHERE doctor_id = %s AND patient_id = %s
                   AND status IN ('active', 'pending') ORDER BY FIELD(status, 'active', 'pending'), start_time DESC LIMIT 1"""
        cursor.execute(query, (doctor_id, patient_id))
        return cursor.fetchone()
    except Exception as e:
        current_app.logger.error(f"Error finding existing chat ({doctor_id}-{patient_id}): {e}"); return None
    finally:
        if cursor: cursor.close();
        if conn and conn.is_connected(): conn.close()

def create_chat(doctor_id, patient_id, subject=None):
    """ Creates a new chat record. """
    conn = None; cursor = None
    try:
        conn = get_db_connection(); conn.start_transaction(); cursor = conn.cursor()
        query = """INSERT INTO chats (doctor_id, patient_id, subject, status, start_time, updated_at)
                   VALUES (%s, %s, %s, 'active', NOW(), NOW())"""
        cursor.execute(query, (doctor_id, patient_id, subject))
        new_chat_id = cursor.lastrowid; conn.commit(); return new_chat_id
    except Exception as e:
        if conn: conn.rollback(); current_app.logger.error(f"Error creating chat ({doctor_id}-{patient_id}): {e}"); return None
    finally:
        if cursor: cursor.close();
        if conn and conn.is_connected(): conn.close()

def get_doctor_chats(doctor_id, page, per_page, search_term=None, status_filter=None):
    """ Fetches paginated chats for a specific doctor. """
    conn = None; cursor = None; offset = (page - 1) * per_page
    result = {'items': [], 'total': 0}
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        sql_select = """SELECT SQL_CALC_FOUND_ROWS c.chat_id, c.subject, c.status, c.updated_at,
                        p.user_id as patient_user_id, p_user.first_name as patient_first_name, p_user.last_name as patient_last_name,
                        (SELECT COUNT(*) FROM chat_messages cm WHERE cm.chat_id = c.chat_id AND cm.read_at IS NULL AND cm.sender_id != %s) as unread_count,
                        (SELECT cm_last.message_text FROM chat_messages cm_last WHERE cm_last.chat_id = c.chat_id ORDER BY cm_last.sent_at DESC LIMIT 1) as last_message_snippet"""
        sql_from = " FROM chats c JOIN patients p ON c.patient_id = p.user_id JOIN users p_user ON p.user_id = p_user.user_id"
        sql_where = " WHERE c.doctor_id = %s"; params = [doctor_id, doctor_id]
        if search_term:
            search_like = f"%{search_term}%"; sql_where += " AND (c.subject LIKE %s OR p_user.first_name LIKE %s OR p_user.last_name LIKE %s)"
            params.extend([search_like, search_like, search_like])
        if status_filter and status_filter in ['active', 'pending', 'closed']:
            sql_where += " AND c.status = %s"; params.append(status_filter)
        sql_order = " ORDER BY c.updated_at DESC"; sql_limit = " LIMIT %s OFFSET %s"; params.extend([per_page, offset])
        query = f"{sql_select}{sql_from}{sql_where}{sql_order}{sql_limit}"
        cursor.execute(query, tuple(params)); result['items'] = cursor.fetchall()
        cursor.execute("SELECT FOUND_ROWS() as total"); total_row = cursor.fetchone()
        result['total'] = total_row['total'] if total_row else 0
    except Exception as e: current_app.logger.error(f"Error fetching chats for doctor {doctor_id}: {e}")
    finally:
        if cursor: cursor.close();
        if conn and conn.is_connected(): conn.close()
    return result

def get_chat_messages(chat_id, user_id, user_type, page, per_page):
    """ Fetches messages for a specific chat, handling authorization and pagination. """
    conn = None; cursor = None; offset = (page - 1) * per_page
    result = {'chat_info': None, 'messages': [], 'total_messages': 0, 'authorized': False}
    transaction_active = False # Flag to track if connection should be closed by this function
    try:
        conn = get_db_connection();
        if not conn or not conn.is_connected(): raise ConnectionError("DB connection failed.")
        cursor = conn.cursor(dictionary=True)

        # 1. Get Chat Info and check authorization
        query_chat = """SELECT c.*, doc_user.first_name as doctor_first_name, doc_user.last_name as doctor_last_name,
                        pat_user.first_name as patient_first_name, pat_user.last_name as patient_last_name
                        FROM chats c JOIN users doc_user ON c.doctor_id = doc_user.user_id JOIN users pat_user ON c.patient_id = pat_user.user_id
                        WHERE c.chat_id = %s"""
        cursor.execute(query_chat, (chat_id,)); chat_info = cursor.fetchone()
        if not chat_info: return result # Chat not found
        result['chat_info'] = chat_info
        is_doctor = user_type == 'doctor' and chat_info['doctor_id'] == user_id
        is_patient = user_type == 'patient' and chat_info['patient_id'] == user_id
        if not (is_doctor or is_patient): return result # Unauthorized
        result['authorized'] = True

        # 2. Get Paginated Messages
        query_messages = """SELECT SQL_CALC_FOUND_ROWS cm.*, att.attachment_id, att.file_name as attachment_filename, att.file_type as attachment_filetype
                            FROM chat_messages cm LEFT JOIN message_attachments att ON cm.message_id = att.message_id AND cm.has_attachment = TRUE
                            WHERE cm.chat_id = %s AND cm.is_deleted = FALSE ORDER BY cm.sent_at ASC LIMIT %s OFFSET %s"""
        cursor.execute(query_messages, (chat_id, per_page, offset)); result['messages'] = cursor.fetchall()
        cursor.execute("SELECT FOUND_ROWS() as total"); total_row = cursor.fetchone()
        result['total_messages'] = total_row['total'] if total_row else 0

        # 3. Mark messages as read (if authorized and messages exist)
        if result['messages']:
            # Assume mark_messages_as_read might commit if needed
            mark_messages_as_read(chat_id, user_id, conn)
            # We don't set transaction_active=True because mark_messages handles its own commit if necessary

    except Exception as e:
        current_app.logger.error(f"Error fetching messages for chat {chat_id}: {e}"); result['authorized'] = False
    finally:
        if cursor: cursor.close()
        # Close connection only if it wasn't successfully used by mark_messages (indicated by auth failure or exception)
        if conn and conn.is_connected() and not result['authorized']:
             conn.close()
    return result

def mark_messages_as_read(chat_id, reader_user_id, db_connection):
    """ Marks messages in a chat as read by the reader. Uses provided connection. """
    cursor = None;
    try:
        # Ensure connection is valid before proceeding
        if not db_connection or not db_connection.is_connected():
            current_app.logger.error("Mark messages read failed: Invalid DB connection passed.")
            return False # Indicate failure

        cursor = db_connection.cursor()
        query = "UPDATE chat_messages SET read_at = NOW() WHERE chat_id = %s AND sender_id != %s AND read_at IS NULL"
        cursor.execute(query, (chat_id, reader_user_id))
        rows_affected = cursor.rowcount

        # Commit if rows were updated and autocommit is off
        if rows_affected > 0 and db_connection.autocommit is False:
            db_connection.commit()
            # current_app.logger.debug(f"Committed message read update for chat {chat_id}, user {reader_user_id}")
        return True # Indicate success even if 0 rows updated

    except Exception as e:
        current_app.logger.error(f"Error marking messages as read for chat {chat_id}, user {reader_user_id}: {e}")
        # Don't rollback here, let the calling function handle it if it started the transaction
        return False # Indicate failure
    finally:
        if cursor: cursor.close()


def add_message(chat_id, sender_id, sender_type, message_text, attachment_filename=None, attachment_filetype=None, attachment_size=None):
    """ Adds a message and optional attachment to the database. """
    conn = None; cursor = None
    try:
        conn = get_db_connection(); conn.start_transaction(); cursor = conn.cursor()
        has_attachment = bool(attachment_filename)
        # 1. Insert Message
        sql_msg = "INSERT INTO chat_messages (chat_id, sender_id, sender_type, message_text, has_attachment, sent_at) VALUES (%s, %s, %s, %s, %s, NOW())"
        cursor.execute(sql_msg, (chat_id, sender_id, sender_type, message_text, has_attachment))
        message_id = cursor.lastrowid;
        if not message_id: raise mysql.connector.Error("Failed to insert message.")
        # 2. Insert Attachment
        if has_attachment:
            # Ensure file_path stores only the filename, not the full path
            sql_att = "INSERT INTO message_attachments (message_id, file_name, file_type, file_size, file_path, uploaded_at) VALUES (%s, %s, %s, %s, %s, NOW())"
            cursor.execute(sql_att, (message_id, attachment_filename, attachment_filetype, attachment_size, attachment_filename)) # file_path = filename
            if not cursor.lastrowid: raise mysql.connector.Error("Failed to insert attachment.")
        # 3. Update chat timestamp
        sql_update_chat = "UPDATE chats SET updated_at = NOW() WHERE chat_id = %s"
        cursor.execute(sql_update_chat, (chat_id,))
        conn.commit(); return message_id
    except Exception as e:
        if conn: conn.rollback(); current_app.logger.error(f"Error adding message to chat {chat_id}: {e}"); return None
    finally:
        if cursor: cursor.close();
        if conn and conn.is_connected(): conn.close()

def get_attachment_info_for_download(attachment_id, user_id, user_type):
    """ Gets attachment filename and verifies user authorization to download. """
    conn = None; cursor = None
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        query = """SELECT ma.file_name, c.doctor_id, c.patient_id FROM message_attachments ma
                   JOIN chat_messages cm ON ma.message_id = cm.message_id JOIN chats c ON cm.chat_id = c.chat_id
                   WHERE ma.attachment_id = %s"""
        cursor.execute(query, (attachment_id,)); info = cursor.fetchone()
        if not info: return None
        is_doctor = user_type == 'doctor' and info['doctor_id'] == user_id
        is_patient = user_type == 'patient' and info['patient_id'] == user_id
        # Return the filename stored in DB (which should NOT be a full path)
        return info['file_name'] if (is_doctor or is_patient) else None
    except Exception as e:
        current_app.logger.error(f"Error getting attachment info for download (ID: {attachment_id}): {e}"); return None
    finally:
        if cursor: cursor.close();
        if conn and conn.is_connected(): conn.close()

def update_chat_status(chat_id, doctor_id, new_status):
    """ Updates the status of a chat (e.g., 'closed'). Only doctor can change status. """
    conn = None; cursor = None; allowed_statuses = ['active', 'closed']
    if new_status not in allowed_statuses: return False, "Invalid status."
    try:
        conn = get_db_connection(); conn.start_transaction(); cursor = conn.cursor()
        sql = "UPDATE chats SET status = %s, updated_at = NOW() WHERE chat_id = %s AND doctor_id = %s"
        cursor.execute(sql, (new_status, chat_id, doctor_id)); rowcount = cursor.rowcount; conn.commit()
        if rowcount > 0: return True, "Status updated."
        else: return False, "Chat not found or unauthorized."
    except Exception as e:
        if conn: conn.rollback(); current_app.logger.error(f"Error updating status for chat {chat_id} by {doctor_id}: {e}"); return False, "Database error."
    finally:
        if cursor: cursor.close();
        if conn and conn.is_connected(): conn.close()


# --- Routes ---

@messaging_bp.route('/', methods=['GET'])
@login_required
def message_list():
    """Display list of chats for the logged-in doctor."""
    if not check_doctor_authorization(current_user): abort(403)
    page = request.args.get('page', 1, type=int); search_term = request.args.get('search', '').strip()
    status_filter = request.args.get('status', '')
    result = get_doctor_chats(current_user.id, page, CHATS_PER_PAGE, search_term, status_filter)
    total_pages = math.ceil(result['total'] / CHATS_PER_PAGE) if CHATS_PER_PAGE > 0 else 0
    return render_template('Doctor_Portal/Messaging/message_list.html', chats=result['items'],
                           current_page=page, total_pages=total_pages, search_term=search_term, status_filter=status_filter)

@messaging_bp.route('/start', methods=['GET', 'POST'])
@messaging_bp.route('/start/<int:patient_user_id>', methods=['GET', 'POST'])
@login_required
def start_chat(patient_user_id=None):
    """Initiate a new chat with a patient."""
    if not check_doctor_authorization(current_user): abort(403)
    doctor_id = current_user.id

    # Fetch available patients for the GET request or for re-rendering on POST error
    conn_patient = None; cursor_patient = None; available_patients = []
    try:
        conn_patient = get_db_connection(); cursor_patient = conn_patient.cursor(dictionary=True)
        query = """SELECT DISTINCT u.user_id, u.first_name, u.last_name FROM users u JOIN patients p ON u.user_id = p.user_id
                   JOIN appointments a ON p.user_id = a.patient_id
                   WHERE a.doctor_id = %s AND u.account_status = 'active' ORDER BY u.last_name, u.first_name"""
        cursor_patient.execute(query, (doctor_id,))
        available_patients = cursor_patient.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching available patients for doctor {doctor_id}: {e}")
        flash("Error loading available patients.", "warning")
    finally:
        if cursor_patient: cursor_patient.close();
        if conn_patient and conn_patient.is_connected(): conn_patient.close()


    if request.method == 'POST':
        patient_id = request.form.get('patient_user_id', type=int)
        subject = request.form.get('subject', '').strip() or None
        initial_message = request.form.get('initial_message', '').strip()

        if not patient_id:
            flash("Please select a patient.", "danger")
            return render_template('Doctor_Portal/Messaging/start_chat_form.html', patients=available_patients, selected_patient_id=patient_id)

        # Optional: Re-check relationship if needed (patient list should be pre-filtered)
        # if not check_doctor_patient_relationship(doctor_id, patient_id): ... flash error ...

        existing_chat = find_existing_chat(doctor_id, patient_id)
        if existing_chat:
            flash("An active or pending chat already exists with this patient.", "info")
            return redirect(url_for('.view_chat', chat_id=existing_chat['chat_id']))

        new_chat_id = create_chat(doctor_id, patient_id, subject)
        if not new_chat_id:
            flash("Failed to start new chat. Please try again.", "danger")
            return render_template('Doctor_Portal/Messaging/start_chat_form.html', patients=available_patients, selected_patient_id=patient_id)

        if initial_message:
            add_message(new_chat_id, doctor_id, 'doctor', initial_message)

        flash("New chat started successfully.", "success")
        return redirect(url_for('.view_chat', chat_id=new_chat_id))

    # GET Request
    return render_template('Doctor_Portal/Messaging/start_chat_form.html',
                           patients=available_patients, selected_patient_id=patient_user_id)


@messaging_bp.route('/chat/<int:chat_id>', methods=['GET'])
@login_required
def view_chat(chat_id):
    """Display a specific chat thread."""
    if not check_doctor_authorization(current_user): abort(403) # Check basic role
    page = request.args.get('page', 1, type=int)
    result = get_chat_messages(chat_id, current_user.id, current_user.user_type, page, MESSAGES_PER_PAGE)

    # Handle results from get_chat_messages
    if not result['chat_info']:
        flash("Chat not found.", "warning"); return redirect(url_for('.message_list'))
    if not result['authorized']:
        flash("You are not authorized to view this chat.", "danger"); return redirect(url_for('.message_list'))

    total_pages = math.ceil(result['total_messages'] / MESSAGES_PER_PAGE) if MESSAGES_PER_PAGE > 0 else 0
    return render_template('Doctor_Portal/Messaging/chat_view.html', chat=result['chat_info'], messages=result['messages'],
                           current_page=page, total_pages=total_pages, chat_id=chat_id)

@messaging_bp.route('/chat/<int:chat_id>/send', methods=['POST'])
@login_required
def send_message(chat_id):
    """Send a new message in a chat."""
    if not check_doctor_authorization(current_user): abort(403)

    message_text = request.form.get('message_text', '').strip()
    attachment_file = request.files.get('attachment')
    attachment_filename = None; attachment_filetype = None; attachment_size = None

    if not message_text and not attachment_file:
        flash("Message cannot be empty unless attaching a file.", "warning")
        return redirect(url_for('.view_chat', chat_id=chat_id))
    if not message_text: message_text = ""

    # --- Auth Check ---
    conn_check = None; cursor_check = None
    try:
        conn_check = get_db_connection(); cursor_check = conn_check.cursor()
        cursor_check.execute("SELECT 1 FROM chats WHERE chat_id = %s AND doctor_id = %s AND status = 'active'", (chat_id, current_user.id))
        if not cursor_check.fetchone():
             flash("Cannot send message. Chat not found, not yours, or closed.", "danger")
             return redirect(url_for('.message_list'))
    except Exception as e:
         current_app.logger.error(f"Auth check error before sending message to chat {chat_id}: {e}"); flash("Error verifying chat authorization.", "danger"); return redirect(url_for('.view_chat', chat_id=chat_id))
    finally:
        if cursor_check: cursor_check.close();
        if conn_check and conn_check.is_connected(): conn_check.close()


    # --- Handle Attachment ---
    if attachment_file and attachment_file.filename != '':
        max_size_bytes = current_app.config.get('MAX_CONTENT_LENGTH')
        file_length = 0
        file_size_ok = True
        if max_size_bytes:
            try:
                start_pos = attachment_file.tell()
                attachment_file.seek(0, os.SEEK_END)
                file_length = attachment_file.tell()
                attachment_file.seek(start_pos, os.SEEK_SET) # Seek back to original position
                if file_length > max_size_bytes:
                    file_size_ok = False
                    flash(f"Attachment exceeds maximum size limit ({max_size_bytes // 1024 // 1024}MB).", "danger")
            except Exception as e:
                 current_app.logger.warning(f"Could not accurately determine attachment size before saving: {e}")
                 # Decide: deny or proceed cautiously? Let's deny for safety.
                 flash("Could not verify attachment size.", "danger")
                 file_size_ok = False

        if not file_size_ok:
             return redirect(url_for('.view_chat', chat_id=chat_id))

        saved_filename, error_msg = save_chat_attachment(attachment_file, current_user.id)
        if error_msg:
            flash(f"Attachment error: {error_msg}", "danger")
            return redirect(url_for('.view_chat', chat_id=chat_id))
        attachment_filename = saved_filename
        attachment_filetype = attachment_file.content_type
        attachment_size = file_length if max_size_bytes and file_size_ok else None
        if attachment_size is None: # If size wasn't pre-checked, get from saved file
             filepath = get_attachment_filepath(attachment_filename)
             if filepath and os.path.exists(filepath): attachment_size = os.path.getsize(filepath)
             else: attachment_size = 0; current_app.logger.warning(f"Could not determine size for saved attachment: {attachment_filename}")

    # --- Add Message to DB ---
    message_id = add_message(chat_id, current_user.id, 'doctor', message_text,
                             attachment_filename, attachment_filetype, attachment_size)

    if message_id: pass # Redirect will show the new message
    else: flash("Failed to send message.", "danger")

    return redirect(url_for('.view_chat', chat_id=chat_id))

@messaging_bp.route('/chat/<int:chat_id>/status', methods=['POST'])
@login_required
def update_chat_status_route(chat_id):
    """Update the status of a chat (e.g., close)."""
    if not check_doctor_authorization(current_user): abort(403)
    new_status = request.form.get('status')
    if not new_status or new_status not in ['active', 'closed']:
        flash("Invalid status provided.", "warning"); return redirect(request.referrer or url_for('.view_chat', chat_id=chat_id))
    success, message = update_chat_status(chat_id, current_user.id, new_status)
    if success: flash(f"Chat marked as {new_status}.", "success")
    else: flash(f"Failed to update chat status: {message}", "danger")
    # Redirect intelligently
    redirect_url = url_for('.view_chat', chat_id=chat_id) # Default back to chat
    if request.referrer and 'message_list' in request.referrer:
         redirect_url = url_for('.message_list') # Go back to list if action came from there
    return redirect(redirect_url)

@messaging_bp.route('/attachment/<int:attachment_id>')
@login_required
def download_attachment(attachment_id):
    """Securely serves an attachment file after checking authorization."""
    user_id = current_user.id; user_type = current_user.user_type
    filename = get_attachment_info_for_download(attachment_id, user_id, user_type)

    if not filename:
        flash("Attachment not found or unauthorized.", "danger"); return redirect(url_for('doctor_main.dashboard'))

    directory = current_app.config.get('UPLOAD_FOLDER_ATTACHMENTS')
    if not directory:
        current_app.logger.error("UPLOAD_FOLDER_ATTACHMENTS not configured for download.")
        abort(500)

    try:
        # Use send_from_directory for security
        return send_from_directory(directory, filename, as_attachment=True)
    except FileNotFoundError:
         current_app.logger.warning(f"Attachment file not found on disk: {filename} in {directory}"); abort(404)
    except Exception as e:
         current_app.logger.error(f"Error serving attachment {filename}: {e}"); abort(500)

# --- END OF FILE messaging.py ---