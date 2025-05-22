# routes/Patient_Portal/patient_messaging.py

import mysql.connector
from flask import (
    Blueprint, render_template, request, flash, redirect, url_for,
    jsonify, current_app, abort, send_from_directory, session, has_app_context
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import os
from db import get_db_connection
from datetime import datetime, date, time, timedelta # Ensure all are imported
import math
import logging

# Configure a logger for this module
module_logger = logging.getLogger(__name__)

# --- Attempt to import REAL functions from utils ---
# This structure attempts to find utils and provides fallbacks if necessary.
# It's crucial that your project structure allows these imports.
# Best practice: Have a single `utils` package accessible by all blueprints.

try:
    # Assuming utils is a package at the same level as 'routes' or in PYTHONPATH
    # e.g., project_root/utils/auth_helpers.py, project_root/utils/file_helpers.py
    from utils.auth_helpers import check_patient_authorization
    from utils.file_helpers import allowed_file, generate_secure_filename_from_file # Renamed for clarity
    
    # Verify successful import
    if 'check_patient_authorization' not in locals():
        raise ImportError("check_patient_authorization not found in utils.auth_helpers")
    if 'allowed_file' not in locals() or 'generate_secure_filename_from_file' not in locals():
        raise ImportError("File helpers (allowed_file, generate_secure_filename_from_file) not found in utils.file_helpers")
    module_logger.info("Successfully imported utils for patient_messaging.")

except ImportError as e:
    module_logger.error(f"CRITICAL: Failed to import utility functions for patient_messaging: {e}. Using basic fallbacks.", exc_info=True)
    # Define minimal fallbacks. THESE ARE NOT ROBUST AND SHOULD BE AVOIDED IN PRODUCTION.
    # Your app should ideally fail at startup if critical utils are missing.
    def check_patient_authorization(user):
        module_logger.warning("FALLBACK: check_patient_authorization called.")
        return user.is_authenticated and hasattr(user, 'user_type') and user.user_type == 'patient'

    def allowed_file(filename, allowed_extensions_config_key='ALLOWED_ATTACHMENT_EXTENSIONS'):
        module_logger.warning(f"FALLBACK: allowed_file called for {filename}")
        # This fallback needs current_app if used directly, but the primary one doesn't.
        # For simplicity in fallback, hardcode some common extensions or make it very permissive (not recommended)
        allowed_extensions = current_app.config.get(allowed_extensions_config_key, {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'txt'})
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

    def generate_secure_filename_from_file(file, uploader_id_prefix=""): # Renamed to accept file object
        module_logger.warning("FALLBACK: generate_secure_filename_from_file called.")
        original_filename = secure_filename(file.filename) if file and file.filename else "unknown_file"
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
        return secure_filename(f"{uploader_id_prefix}{timestamp}_{original_filename}")


# --- Blueprint Definition ---
patient_messaging_bp = Blueprint(
    'patient_messaging',
    __name__,
    url_prefix='/patient/messages',
    template_folder='../../templates'
)

# --- Configuration / Constants ---
MESSAGES_PER_PAGE = 20
CHATS_PER_PAGE = 15

# --- Helper Functions (Messaging Specific) ---

def save_chat_attachment_pm(file, uploader_user_id):
    """Saves an uploaded chat attachment securely using configured paths and helpers."""
    # current_app is safe to use here because this function is called from within a route context
    upload_folder = current_app.config.get('UPLOAD_FOLDER_ATTACHMENTS') # From directory_configs
    if not upload_folder:
        current_app.logger.error("UPLOAD_FOLDER_ATTACHMENTS not configured in Flask app.")
        return None, "Server configuration error (upload path)."

    # Use the imported (or fallback) allowed_file helper
    # Pass the config key for allowed extensions for attachments
    if file and allowed_file(file.filename, 'ALLOWED_ATTACHMENT_EXTENSIONS'):
        # Use the imported (or fallback) generate_secure_filename_from_file helper
        unique_filename = generate_secure_filename_from_file(file, uploader_id_prefix=f"{uploader_user_id}_chat_")
        
        filepath = os.path.join(upload_folder, unique_filename)
        try:
            os.makedirs(upload_folder, exist_ok=True) # Ensure directory exists
            file.save(filepath)
            current_app.logger.info(f"Attachment saved: {filepath}")
            # Return only the filename, not the full path, for DB storage.
            # The `get_relative_upload_path` from directory_configs could be used here if desired.
            return unique_filename, None 
        except Exception as e:
            current_app.logger.error(f"Failed to save attachment {unique_filename} to {filepath}: {e}")
            if os.path.exists(filepath):
                try: os.remove(filepath)
                except OSError: pass # Silently ignore if removal fails (rare)
            return None, "Failed to save file on server."
    elif file:
        return None, "File type not allowed for attachments."
    else:
        return None, "No file was provided for attachment."


def get_attachment_filepath_pm(filename):
    """Constructs the full path for a given attachment filename."""
    # current_app is safe here
    upload_folder = current_app.config.get('UPLOAD_FOLDER_ATTACHMENTS')
    if not upload_folder or not filename:
        current_app.logger.warning("UPLOAD_FOLDER_ATTACHMENTS not set or no filename for get_attachment_filepath_pm")
        return None
    # Basic security: prevent path traversal
    if '..' in filename or filename.startswith('/') or filename.startswith('\\'):
         current_app.logger.warning(f"Attempt to access potentially unsafe attachment path: {filename}")
         return None
    return os.path.join(upload_folder, filename)


# --- Database Interaction Functions (Adapted for Patient Context) ---
# (get_patient_chats, get_chat_messages_for_patient, mark_messages_as_read_pm, 
#  add_message_from_patient, get_attachment_info_for_download_pm remain largely the same as previous version)

# routes/Patient_Portal/patient_messaging.py

# ... (other imports and code) ...

def get_patient_chats(patient_id, page, per_page, search_term=None, status_filter=None):
    """ Fetches paginated chats for a specific patient. """
    conn = None; cursor = None; offset = (page - 1) * per_page
    result = {'items': [], 'total': 0}
    log = current_app.logger if has_app_context() else module_logger
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        # Patient sees chats with doctors
        sql_select = """SELECT SQL_CALC_FOUND_ROWS c.chat_id, c.subject, c.status, c.updated_at,
                        d.user_id as doctor_user_id, d_user.first_name as doctor_first_name, d_user.last_name as doctor_last_name,
                        (SELECT COUNT(*) FROM chat_messages cm WHERE cm.chat_id = c.chat_id AND cm.read_at IS NULL AND cm.sender_id != %s AND cm.sender_type = 'doctor') as unread_count,
                        (SELECT cm_last.message_text FROM chat_messages cm_last WHERE cm_last.chat_id = c.chat_id ORDER BY cm_last.sent_at DESC LIMIT 1) as last_message_snippet"""
        sql_from = " FROM chats c JOIN doctors d ON c.doctor_id = d.user_id JOIN users d_user ON d.user_id = d_user.user_id"
        sql_where = " WHERE c.patient_id = %s"; params = [patient_id, patient_id] # patient_id for unread count sender_id check

        if search_term:
            search_like = f"%{search_term}%"
            sql_where += " AND (c.subject LIKE %s OR d_user.first_name LIKE %s OR d_user.last_name LIKE %s OR CONCAT(d_user.first_name, ' ', d_user.last_name) LIKE %s)"
            params.extend([search_like, search_like, search_like, search_like])
        if status_filter and status_filter in ['active', 'pending', 'closed']:
            sql_where += " AND c.status = %s"; params.append(status_filter)

        # *** CORRECTED ORDER BY CLAUSE ***
        sql_order = " ORDER BY c.status = 'active' DESC, c.status = 'pending' DESC, unread_count DESC, c.updated_at DESC";
        # Refer to the alias 'unread_count' directly, not 'c.unread_count'

        sql_limit = " LIMIT %s OFFSET %s"; params.extend([per_page, offset])
        query = f"{sql_select}{sql_from}{sql_where}{sql_order}{sql_limit}"
        
        log.debug(f"Executing get_patient_chats query: {query} with params: {params}") # Optional: for debugging
        
        cursor.execute(query, tuple(params)); result['items'] = cursor.fetchall()
        cursor.execute("SELECT FOUND_ROWS() as total"); total_row = cursor.fetchone()
        result['total'] = total_row['total'] if total_row else 0
    except Exception as e:
        log.error(f"Error fetching chats for patient {patient_id}: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return result

# ... (rest of the file) ...
def get_chat_messages_for_patient(chat_id, patient_user_id, page, per_page):
    conn = None; cursor = None; offset = (page - 1) * per_page
    result = {'chat_info': None, 'messages': [], 'total_messages': 0, 'authorized': False}
    log = current_app.logger if has_app_context() else module_logger
    db_conn_for_mark = None # Separate connection for marking messages read
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        query_chat = """SELECT c.*,
                        doc_user.first_name as doctor_first_name, doc_user.last_name as doctor_last_name,
                        pat_user.first_name as patient_first_name, pat_user.last_name as patient_last_name
                        FROM chats c
                        JOIN users doc_user ON c.doctor_id = doc_user.user_id
                        JOIN users pat_user ON c.patient_id = pat_user.user_id
                        WHERE c.chat_id = %s AND c.patient_id = %s"""
        cursor.execute(query_chat, (chat_id, patient_user_id)); chat_info = cursor.fetchone()
        if not chat_info: return result
        result['chat_info'] = chat_info; result['authorized'] = True

        query_messages = """SELECT SQL_CALC_FOUND_ROWS cm.*, att.attachment_id, att.file_name as attachment_filename, att.file_type as attachment_filetype
                            FROM chat_messages cm LEFT JOIN message_attachments att ON cm.message_id = att.message_id AND cm.has_attachment = TRUE
                            WHERE cm.chat_id = %s AND cm.is_deleted = FALSE ORDER BY cm.sent_at ASC LIMIT %s OFFSET %s"""
        cursor.execute(query_messages, (chat_id, per_page, offset)); result['messages'] = cursor.fetchall()
        cursor.execute("SELECT FOUND_ROWS() as total"); total_row = cursor.fetchone()
        result['total_messages'] = total_row['total'] if total_row else 0

        if result['messages']:
            db_conn_for_mark = get_db_connection()
            if db_conn_for_mark:
                mark_messages_as_read_pm(chat_id, patient_user_id, db_conn_for_mark)
            else:
                log.error(f"Could not get DB connection to mark messages as read for chat {chat_id}")

    except Exception as e:
        log.error(f"Error fetching messages for chat {chat_id} by patient {patient_user_id}: {e}", exc_info=True)
        result['authorized'] = False
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
        if db_conn_for_mark and db_conn_for_mark.is_connected(): db_conn_for_mark.close()
    return result

def mark_messages_as_read_pm(chat_id, reader_user_id, db_connection):
    cursor = None
    log = current_app.logger if has_app_context() else module_logger
    try:
        if not db_connection or not db_connection.is_connected():
            log.error("Mark messages read (patient) failed: Invalid DB connection.")
            return False
        cursor = db_connection.cursor()
        query = "UPDATE chat_messages SET read_at = NOW() WHERE chat_id = %s AND sender_id != %s AND sender_type = 'doctor' AND read_at IS NULL"
        cursor.execute(query, (chat_id, reader_user_id))
        if cursor.rowcount > 0 and not db_connection.get_autocommit(): # Check autocommit status
            db_connection.commit()
        return True
    except Exception as e:
        log.error(f"Error marking messages as read (patient) chat {chat_id}, user {reader_user_id}: {e}", exc_info=True)
        # Do not rollback here as this function uses a connection passed to it.
        return False
    finally:
        if cursor: cursor.close()
        # The passed-in db_connection should be closed by the caller of this function

def add_message_from_patient(chat_id, patient_id, message_text, attachment_filename=None, attachment_filetype=None, attachment_size=None):
    conn = None; cursor = None
    log = current_app.logger if has_app_context() else module_logger
    try:
        conn = get_db_connection(); conn.start_transaction(); cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM chats WHERE chat_id = %s AND patient_id = %s AND status = 'active'", (chat_id, patient_id))
        if not cursor.fetchone():
            log.warning(f"Patient {patient_id} attempted to send message to inactive/unauthorized chat {chat_id}")
            return None, "Cannot send message to this chat. It may be closed or you are not a participant."

        has_attachment = bool(attachment_filename)
        sql_msg = "INSERT INTO chat_messages (chat_id, sender_id, sender_type, message_text, has_attachment, sent_at) VALUES (%s, %s, 'patient', %s, %s, NOW())"
        cursor.execute(sql_msg, (chat_id, patient_id, message_text, has_attachment))
        message_id = cursor.lastrowid
        if not message_id: raise mysql.connector.Error("Failed to insert patient message, no message_id returned.")

        if has_attachment:
            # Use the relative path (just filename) for file_path as UPLOAD_FOLDER_ATTACHMENTS is the base
            relative_file_path_for_db = attachment_filename # Storing just the filename
            sql_att = "INSERT INTO message_attachments (message_id, file_name, file_type, file_size, file_path, uploaded_at) VALUES (%s, %s, %s, %s, %s, NOW())"
            cursor.execute(sql_att, (message_id, attachment_filename, attachment_filetype, attachment_size, relative_file_path_for_db))
            if not cursor.lastrowid: raise mysql.connector.Error("Failed to insert patient attachment record.")
        
        sql_update_chat = "UPDATE chats SET updated_at = NOW() WHERE chat_id = %s"
        cursor.execute(sql_update_chat, (chat_id,))
        conn.commit()
        return message_id, None
    except mysql.connector.Error as db_err: # More specific DB error
        if conn: conn.rollback()
        log.error(f"DB error adding patient message to chat {chat_id}: {db_err}", exc_info=True)
        return None, f"Database error: {db_err.msg}"
    except Exception as e:
        if conn: conn.rollback()
        log.error(f"Unexpected error adding patient message to chat {chat_id}: {e}", exc_info=True)
        return None, "An unexpected error occurred."
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

def get_attachment_info_for_download_pm(attachment_id, user_id):
    conn = None; cursor = None
    log = current_app.logger if has_app_context() else module_logger
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        # file_path from DB should be just the filename
        query = """SELECT ma.file_path as db_filename, c.patient_id FROM message_attachments ma
                   JOIN chat_messages cm ON ma.message_id = cm.message_id JOIN chats c ON cm.chat_id = c.chat_id
                   WHERE ma.attachment_id = %s AND c.patient_id = %s"""
        cursor.execute(query, (attachment_id, user_id)); info = cursor.fetchone()
        return info['db_filename'] if info else None
    except Exception as e:
        log.error(f"Error getting attachment info (patient view, ID: {attachment_id}): {e}", exc_info=True); return None
    finally:
        if cursor: cursor.close();
        if conn and conn.is_connected(): conn.close()


# --- Patient Messaging Routes ---

@patient_messaging_bp.route('/')
@login_required
def list_my_chats():
    if not check_patient_authorization(current_user): abort(403)
    patient_id = current_user.id
    page = request.args.get('page', 1, type=int)
    search_term = request.args.get('search', '').strip()
    status_filter = request.args.get('status', '')

    result = get_patient_chats(patient_id, page, CHATS_PER_PAGE, search_term, status_filter)
    total_pages = math.ceil(result['total'] / CHATS_PER_PAGE) if CHATS_PER_PAGE > 0 and result['total'] > 0 else 0

    return render_template('Patient_Portal/Messaging/patient_chat_list.html',
                           chats=result['items'],
                           current_page=page,
                           total_pages=total_pages,
                           search_term=search_term,
                           status_filter=status_filter)

@patient_messaging_bp.route('/chat/<int:chat_id>', methods=['GET'])
@login_required
def view_patient_chat(chat_id):
    if not check_patient_authorization(current_user): abort(403)
    patient_id = current_user.id
    page = request.args.get('page', 1, type=int)

    result = get_chat_messages_for_patient(chat_id, patient_id, page, MESSAGES_PER_PAGE)

    if not result['chat_info'] or not result['authorized']:
        flash("Chat not found or you are not authorized to view it.", "warning")
        return redirect(url_for('.list_my_chats'))

    total_message_pages = math.ceil(result['total_messages'] / MESSAGES_PER_PAGE) if MESSAGES_PER_PAGE > 0 and result['total_messages'] > 0 else 0
    
    # Pass current_app.config to the template for MAX_ATTACHMENT_MB (if defined)
    max_attachment_mb = current_app.config.get('MAX_CONTENT_LENGTH', 10 * 1024 * 1024) // (1024 * 1024)


    return render_template('Patient_Portal/Messaging/patient_chat_view.html',
                           chat=result['chat_info'],
                           messages=result['messages'],
                           current_message_page=page,
                           total_message_pages=total_message_pages,
                           chat_id=chat_id,
                           max_attachment_mb=max_attachment_mb)


@patient_messaging_bp.route('/chat/<int:chat_id>/send', methods=['POST'])
@login_required
def send_patient_message(chat_id):
    if not check_patient_authorization(current_user): abort(403)
    patient_id = current_user.id

    message_text = request.form.get('message_text', '').strip()
    attachment_file = request.files.get('attachment')
    attachment_filename_for_db = None; attachment_filetype = None; attachment_size = None

    if not message_text and not (attachment_file and attachment_file.filename):
        flash("Message cannot be empty unless attaching a file.", "warning")
        return redirect(url_for('.view_patient_chat', chat_id=chat_id))
    if not message_text: message_text = ""

    if attachment_file and attachment_file.filename:
        # File size check
        max_size_bytes = current_app.config.get('MAX_CONTENT_LENGTH') # In bytes
        file_length = 0
        file_size_ok = True
        if max_size_bytes:
            try:
                start_pos = attachment_file.tell()
                attachment_file.seek(0, os.SEEK_END); file_length = attachment_file.tell()
                attachment_file.seek(start_pos, os.SEEK_SET)
                if file_length > max_size_bytes:
                    file_size_ok = False
                    max_mb = max_size_bytes // (1024*1024)
                    flash(f"Attachment exceeds maximum size limit ({max_mb}MB).", "danger")
            except Exception as e:
                 current_app.logger.warning(f"Could not accurately determine attachment size: {e}")
                 flash("Could not verify attachment size.", "danger")
                 file_size_ok = False
        
        if not file_size_ok:
             return redirect(url_for('.view_patient_chat', chat_id=chat_id))

        # Save attachment (this uses imported utils now)
        saved_filename, error_msg = save_chat_attachment_pm(attachment_file, patient_id)
        if error_msg:
            flash(f"Attachment error: {error_msg}", "danger")
            return redirect(url_for('.view_patient_chat', chat_id=chat_id))
        
        attachment_filename_for_db = saved_filename # This is the unique, secure filename
        attachment_filetype = attachment_file.content_type
        attachment_size = file_length # Use the pre-checked size

    message_id, error = add_message_from_patient(
        chat_id, patient_id, message_text,
        attachment_filename_for_db, attachment_filetype, attachment_size
    )
    if error:
        flash(f"Failed to send message: {error}", "danger")
    
    return redirect(url_for('.view_patient_chat', chat_id=chat_id))


@patient_messaging_bp.route('/attachment/<int:attachment_id>')
@login_required
def download_patient_attachment(attachment_id):
    if not check_patient_authorization(current_user): abort(403)
    patient_id = current_user.id
    
    # get_attachment_info_for_download_pm now returns just the filename stored in DB
    db_filename = get_attachment_info_for_download_pm(attachment_id, patient_id)

    if not db_filename:
        flash("Attachment not found or you are not authorized to download it.", "danger")
        return redirect(url_for('patient_profile.my_account_dashboard'))

    # UPLOAD_FOLDER_ATTACHMENTS should be an absolute path configured in the app
    directory = current_app.config.get('UPLOAD_FOLDER_ATTACHMENTS')
    if not directory:
        current_app.logger.error("UPLOAD_FOLDER_ATTACHMENTS not configured (patient download).")
        abort(500)
    
    # Log the attempt
    current_app.logger.info(f"Patient {patient_id} attempting to download attachment: {db_filename} from directory: {directory}")

    try:
        # send_from_directory expects the directory and then the filename (not a full path)
        return send_from_directory(directory, db_filename, as_attachment=True)
    except FileNotFoundError:
         current_app.logger.error(f"Patient attachment file NOT FOUND on disk: {os.path.join(directory, db_filename)}")
         abort(404, description="File not found on server.")
    except Exception as e:
         current_app.logger.error(f"Error serving patient attachment {db_filename}: {e}", exc_info=True)
         abort(500, description="Could not serve the attachment.")