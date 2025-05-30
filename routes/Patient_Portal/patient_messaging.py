# routes/Patient_Portal/patient_messaging.py

import mysql.connector
from flask import (
    Blueprint, render_template, request, flash, redirect, url_for,
    jsonify, current_app, abort, session, has_app_context
)
from flask_login import login_required, current_user
# import os # No longer needed
from db import get_db_connection
from datetime import datetime, date, time, timedelta
import math
import logging

module_logger = logging.getLogger(__name__)

try:
    from utils.auth_helpers import check_patient_authorization
    module_logger.info("Successfully imported check_patient_authorization.")
except ImportError as e:
    module_logger.error(f"CRITICAL: Failed to import check_patient_authorization: {e}. Using basic fallback.", exc_info=True)
    def check_patient_authorization(user):
        module_logger.warning("FALLBACK: check_patient_authorization called.")
        return user.is_authenticated and hasattr(user, 'user_type') and user.user_type == 'patient'

patient_messaging_bp = Blueprint(
    'patient_messaging',
    __name__,
    url_prefix='/patient/messages',
    template_folder='../../templates'
)

MESSAGES_PER_PAGE = 20
CHATS_PER_PAGE = 15

def get_patient_chats(patient_id, page, per_page, search_term=None, status_filter=None):
    conn = None; cursor = None; offset = (page - 1) * per_page
    result = {'items': [], 'total': 0}
    log = current_app.logger if has_app_context() else module_logger
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        sql_select = """SELECT SQL_CALC_FOUND_ROWS c.chat_id, c.subject, c.status, c.updated_at,
                        d.user_id as doctor_user_id, d_user.first_name as doctor_first_name, d_user.last_name as doctor_last_name,
                        (SELECT COUNT(*) FROM chat_messages cm WHERE cm.chat_id = c.chat_id AND cm.read_at IS NULL AND cm.sender_id != %s AND cm.sender_type = 'doctor') as unread_count,
                        (SELECT cm_last.message_text FROM chat_messages cm_last WHERE cm_last.chat_id = c.chat_id ORDER BY cm_last.sent_at DESC LIMIT 1) as last_message_snippet"""
        sql_from = " FROM chats c JOIN doctors d ON c.doctor_id = d.user_id JOIN users d_user ON d.user_id = d_user.user_id"
        sql_where = " WHERE c.patient_id = %s"; params = [patient_id, patient_id]

        if search_term:
            search_like = f"%{search_term}%"
            sql_where += " AND (c.subject LIKE %s OR d_user.first_name LIKE %s OR d_user.last_name LIKE %s OR CONCAT(d_user.first_name, ' ', d_user.last_name) LIKE %s)"
            params.extend([search_like, search_like, search_like, search_like])
        if status_filter and status_filter in ['active', 'pending', 'closed']:
            sql_where += " AND c.status = %s"; params.append(status_filter)

        sql_order = " ORDER BY c.status = 'active' DESC, c.status = 'pending' DESC, unread_count DESC, c.updated_at DESC";
        sql_limit = " LIMIT %s OFFSET %s"; params.extend([per_page, offset])
        query = f"{sql_select}{sql_from}{sql_where}{sql_order}{sql_limit}"
        
        cursor.execute(query, tuple(params)); result['items'] = cursor.fetchall()
        cursor.execute("SELECT FOUND_ROWS() as total"); total_row = cursor.fetchone()
        result['total'] = total_row['total'] if total_row else 0
    except Exception as e:
        log.error(f"Error fetching chats for patient {patient_id}: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return result

def get_chat_messages_for_patient(chat_id, patient_user_id, page, per_page):
    conn = None; cursor = None; offset = (page - 1) * per_page
    result = {'chat_info': None, 'messages': [], 'total_messages': 0, 'authorized': False}
    log = current_app.logger if has_app_context() else module_logger
    db_conn_for_mark = None
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

        query_messages = """SELECT SQL_CALC_FOUND_ROWS cm.* 
                            FROM chat_messages cm
                            WHERE cm.chat_id = %s AND cm.is_deleted = FALSE ORDER BY cm.sent_at ASC LIMIT %s OFFSET %s"""
        cursor.execute(query_messages, (chat_id, per_page, offset)); result['messages'] = cursor.fetchall()
        cursor.execute("SELECT FOUND_ROWS() as total"); total_row = cursor.fetchone()
        result['total_messages'] = total_row['total'] if total_row else 0

        if result['messages']:
            # Use a separate connection for marking messages to avoid transaction conflicts
            # if the main connection is in a transaction for reading.
            # However, if get_db_connection always returns new connections, this is fine.
            # If using a pooled connection, ensure it's handled correctly.
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
        if db_conn_for_mark and db_conn_for_mark.is_connected(): db_conn_for_mark.close() # Close the separate connection
    return result

def mark_messages_as_read_pm(chat_id, reader_user_id, db_connection):
    cursor = None
    log = current_app.logger if has_app_context() else module_logger
    try:
        if not db_connection or not db_connection.is_connected():
            log.error("Mark messages read (patient) failed: Invalid DB connection provided.")
            return False
        
        # Ensure autocommit is suitable or manage transaction explicitly if needed for this operation
        # For a single UPDATE, if autocommit is True on the passed connection, it's fine.
        # If autocommit is False, the caller of mark_messages_as_read_pm or this function needs to commit.
        # Here, we assume the passed db_connection might have autocommit=False, so we commit.

        original_autocommit = db_connection.autocommit # Store original state
        db_connection.autocommit = True # Temporarily set to True for this simple update

        cursor = db_connection.cursor()
        query = "UPDATE chat_messages SET read_at = NOW() WHERE chat_id = %s AND sender_id != %s AND sender_type = 'doctor' AND read_at IS NULL"
        cursor.execute(query, (chat_id, reader_user_id))
        
        # No explicit commit needed if autocommit was set to True for this operation
        # if cursor.rowcount > 0 and not db_connection.autocommit: # CORRECTED: access as attribute
        #     db_connection.commit() # This commit would apply if autocommit was False

        db_connection.autocommit = original_autocommit # Restore original autocommit state

        return True
    except Exception as e:
        log.error(f"Error marking messages as read (patient) chat {chat_id}, user {reader_user_id}: {e}", exc_info=True)
        # Do not rollback here, let the caller handle its connection's transaction state if necessary
        return False
    finally:
        if cursor: cursor.close()
        # The passed-in db_connection is managed (closed) by its original creator/caller.

def add_message_from_patient(chat_id, patient_id, message_text):
    conn = None; cursor = None
    log = current_app.logger if has_app_context() else module_logger
    try:
        conn = get_db_connection(); conn.start_transaction(); cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM chats WHERE chat_id = %s AND patient_id = %s AND status = 'active'", (chat_id, patient_id))
        if not cursor.fetchone():
            log.warning(f"Patient {patient_id} attempted to send message to inactive/unauthorized chat {chat_id}")
            return None, "Cannot send message to this chat. It may be closed or you are not a participant."

        sql_msg = "INSERT INTO chat_messages (chat_id, sender_id, sender_type, message_text, has_attachment, sent_at) VALUES (%s, %s, 'patient', %s, FALSE, NOW())"
        cursor.execute(sql_msg, (chat_id, patient_id, message_text))
        message_id = cursor.lastrowid
        if not message_id: raise mysql.connector.Error("Failed to insert patient message, no message_id returned.")
        
        # CORRECTED: Removed 'last_message_at' assuming it's not in 'chats' table or 'updated_at' is sufficient
        sql_update_chat = "UPDATE chats SET updated_at = NOW() WHERE chat_id = %s"
        cursor.execute(sql_update_chat, (chat_id,))
        conn.commit()
        return message_id, None
    except mysql.connector.Error as db_err:
        if conn and conn.in_transaction: conn.rollback() # Ensure rollback if in transaction
        log.error(f"DB error adding patient message to chat {chat_id}: {db_err}", exc_info=True)
        return None, f"Database error: {db_err.msg}"
    except Exception as e:
        if conn and conn.in_transaction: conn.rollback() # Ensure rollback
        log.error(f"Unexpected error adding patient message to chat {chat_id}: {e}", exc_info=True)
        return None, "An unexpected error occurred."
    finally:
        if cursor: cursor.close()
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
    chat_statuses = ['active', 'pending', 'closed'] 

    return render_template('Patient_Portal/Messaging/patient_chat_list.html',
                           chats=result['items'],
                           current_page=page,
                           total_pages=total_pages,
                           search_term=search_term,
                           status_filter=status_filter,
                           chat_statuses=chat_statuses)

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
    
    return render_template('Patient_Portal/Messaging/patient_chat_view.html',
                           chat=result['chat_info'],
                           messages=result['messages'],
                           current_message_page=page,
                           total_message_pages=total_message_pages,
                           chat_id=chat_id)


@patient_messaging_bp.route('/chat/<int:chat_id>/send', methods=['POST'])
@login_required
def send_patient_message(chat_id):
    if not check_patient_authorization(current_user): 
        return jsonify({"success": False, "message": "Unauthorized"}), 403 # Return JSON for AJAX
        
    patient_id = current_user.id
    message_text = request.form.get('message_text', '').strip()
    
    if not message_text:
        return jsonify({"success": False, "message": "Message text cannot be empty."}), 400

    message_id, error = add_message_from_patient(chat_id, patient_id, message_text)
    
    if error:
        return jsonify({"success": False, "message": f"Failed to send message: {error}"}), 500
    
    # For AJAX, good to return the newly created message data
    # For now, just success. Client can re-fetch or this can be enhanced.
    # Fetching the message again to return full details
    new_message_data = None
    if message_id:
        conn_temp = None; cursor_temp = None
        try:
            conn_temp = get_db_connection()
            cursor_temp = conn_temp.cursor(dictionary=True)
            cursor_temp.execute("SELECT * FROM chat_messages WHERE message_id = %s", (message_id,))
            new_message_data = cursor_temp.fetchone()
            if new_message_data and isinstance(new_message_data.get('sent_at'), datetime): # Format datetime for JSON
                 new_message_data['sent_at'] = new_message_data['sent_at'].isoformat()

        except Exception as e:
            module_logger.error(f"Error fetching newly sent message {message_id}: {e}")
        finally:
            if cursor_temp: cursor_temp.close()
            if conn_temp and conn_temp.is_connected(): conn_temp.close()

    return jsonify({
        "success": True, 
        "message": "Message sent successfully.", 
        "message_id": message_id,
        "new_message_data": new_message_data # Client can use this to append to UI
    })