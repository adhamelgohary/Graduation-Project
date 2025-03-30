# admin_audit.py
# No changes needed - all operations were read-only.

from flask import Blueprint, render_template, request, flash, redirect, url_for, Response, current_app
from flask_login import login_required, current_user
from db import get_db_connection
from math import ceil
# import csv
# import io

admin_audit = Blueprint('admin_audit', __name__)

@admin_audit.route('/admin/audit-logs', methods=['GET'])
@login_required
def index():
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    # --- Get filter parameters ---
    action_type = request.args.get('action_type', 'all')
    user_id_filter = request.args.get('user_id', 'all')
    performed_by_filter = request.args.get('performed_by', 'all')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    search_query = request.args.get('search', '')
    sort_by = request.args.get('sort_by', 'performed_at')
    sort_order = request.args.get('sort_order', 'desc')
    page = request.args.get('page', 1, type=int)
    per_page = 20

    connection = None
    cursor = None
    logs = []
    total_logs = 0
    total_pages = 0
    action_types = []
    admins = []

    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            current_app.logger.error(f"DB connection failed in audit log index")
            raise ConnectionError("DB connection failed")
        cursor = connection.cursor(dictionary=True)

        # --- Build Query (Read-only) ---
        query = """
            SELECT al.log_id, al.user_id, al.action_type, al.action_details,
                   al.target_table, al.target_record_id, al.ip_address,
                   al.performed_by_id, al.performed_at,
                   CONCAT(u1.first_name, ' ', u1.last_name) as user_name,
                   CONCAT(u2.first_name, ' ', u2.last_name) as performed_by_name,
                   u1.username as user_username, u2.username as performed_by_username
            FROM audit_log al
            LEFT JOIN users u1 ON al.user_id = u1.user_id
            JOIN users u2 ON al.performed_by_id = u2.user_id
            WHERE 1=1
        """
        params = []
        where_clauses = []

        # Add filters to query (same as before)
        if action_type != 'all':
            where_clauses.append("al.action_type = %s"); params.append(action_type)
        if user_id_filter != 'all' and user_id_filter.isdigit():
            where_clauses.append("al.user_id = %s"); params.append(int(user_id_filter))
        if performed_by_filter != 'all' and performed_by_filter.isdigit():
            where_clauses.append("al.performed_by_id = %s"); params.append(int(performed_by_filter))
        if date_from:
            where_clauses.append("DATE(al.performed_at) >= %s"); params.append(date_from)
        if date_to:
            where_clauses.append("DATE(al.performed_at) <= %s"); params.append(date_to)
        if search_query:
            where_clauses.append("""(al.action_details LIKE %s OR al.target_table LIKE %s OR
                                    al.target_record_id LIKE %s OR al.ip_address LIKE %s OR
                                    u1.first_name LIKE %s OR u1.last_name LIKE %s OR
                                    u2.first_name LIKE %s OR u2.last_name LIKE %s OR
                                    u1.username LIKE %s OR u2.username LIKE %s)""")
            search_param = f'%{search_query}%'; params.extend([search_param] * 10)

        if where_clauses: query += " AND " + " AND ".join(where_clauses)

        # Construct a simplified count query (avoids selecting all columns for counting)
        count_base_query = query.split("FROM", 1)[1].split("ORDER BY", 1)[0] # Extract FROM...WHERE part
        count_query = f"SELECT COUNT(al.log_id) as total FROM {count_base_query}"
        cursor.execute(count_query, tuple(params)) # Use original params for filtering count

        result = cursor.fetchone()
        total_logs = result['total'] if result else 0
        total_pages = ceil(total_logs / per_page) if total_logs > 0 else 0

        # Add sorting and pagination to the main query
        valid_sort_fields = {'log_id': 'al.log_id', 'user_name': 'user_name',
                             'action_type': 'al.action_type', 'performed_by': 'performed_by_name',
                             'performed_at': 'al.performed_at'}
        sort_field = valid_sort_fields.get(sort_by, 'al.performed_at')
        sort_direction = 'DESC' if sort_order.lower() == 'desc' else 'ASC'
        offset = (page - 1) * per_page
        query += f" ORDER BY {sort_field} {sort_direction} LIMIT %s OFFSET %s"
        # Note: params already includes filters, now add pagination params
        params.extend([per_page, offset])

        cursor.execute(query, tuple(params))
        logs = cursor.fetchall()

        # Get dropdown data (read-only)
        cursor.execute("SELECT DISTINCT action_type FROM audit_log ORDER BY action_type")
        action_types = [row['action_type'] for row in cursor.fetchall()]
        cursor.execute("""SELECT user_id, CONCAT(first_name, ' ', last_name, ' (', username, ')') as name
                          FROM users WHERE user_type = 'admin' ORDER BY name""")
        admins = cursor.fetchall()

    except Exception as e:
        flash(f"Error loading audit logs: {str(e)}", "danger")
        current_app.logger.error(f"Error loading audit logs: {e}")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return render_template('Admin_Portal/AuditLogs/audit_logs.html',
                           logs=logs, total_logs=total_logs, current_page=page,
                           total_pages=total_pages, per_page=per_page, action_types=action_types,
                           admins=admins, filter_action_type=action_type, filter_user_id=user_id_filter,
                           filter_performed_by=performed_by_filter, filter_date_from=date_from,
                           filter_date_to=date_to, search_query=search_query,
                           sort_by=sort_by, sort_order=sort_order)


@admin_audit.route('/admin/audit-logs/view/<int:log_id>', methods=['GET'])
@login_required
def view_log(log_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    connection = None
    cursor = None
    log = None
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
             current_app.logger.error(f"DB connection failed in view_log {log_id}")
             raise ConnectionError("DB connection failed")
        cursor = connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT al.log_id, al.user_id, al.action_type, al.action_details,
                   al.target_table, al.target_record_id, al.ip_address,
                   al.performed_by_id, al.performed_at,
                   CONCAT(u1.first_name, ' ', u1.last_name) as user_name,
                   u1.username as user_username,
                   u1.email as user_email,
                   CONCAT(u2.first_name, ' ', u2.last_name) as performed_by_name,
                   u2.username as performed_by_username,
                   u2.email as performed_by_email
            FROM audit_log al
            LEFT JOIN users u1 ON al.user_id = u1.user_id
            JOIN users u2 ON al.performed_by_id = u2.user_id
            WHERE al.log_id = %s
        """, (log_id,))
        log = cursor.fetchone()
        if not log:
            flash("Audit log entry not found", "danger")
            return redirect(url_for('admin_audit.index'))
    except Exception as e:
         flash(f"Error loading log details: {str(e)}", "danger")
         current_app.logger.error(f"Error loading log detail {log_id}: {e}")
         return redirect(url_for('admin_audit.index'))
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()
    return render_template('Admin_Portal/AuditLogs/view_log.html', log=log)


@admin_audit.route('/admin/audit-logs/export', methods=['GET'])
@login_required
def export_logs():
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    # Retrieve the same filters as in the index function
    action_type = request.args.get('action_type', 'all')
    user_id_filter = request.args.get('user_id', 'all')
    performed_by_filter = request.args.get('performed_by', 'all')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    search_query = request.args.get('search', '')
    sort_by = request.args.get('sort_by', 'performed_at')
    sort_order = request.args.get('sort_order', 'desc')

    connection = None
    cursor = None
    logs_for_export = []

    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
             current_app.logger.error(f"DB connection failed in audit log export")
             raise ConnectionError("DB connection failed")
        cursor = connection.cursor(dictionary=True)

        # --- Reconstruct the query from index() WITHOUT pagination ---
        query = """
            SELECT al.log_id, al.action_type, al.action_details,
                   al.target_table, al.target_record_id, al.ip_address,
                   al.performed_at,
                   u1.user_id as affected_user_id,
                   CONCAT(u1.first_name, ' ', u1.last_name) as affected_user_name,
                   u1.username as affected_user_username,
                   u2.user_id as performed_by_user_id,
                   CONCAT(u2.first_name, ' ', u2.last_name) as performed_by_name,
                   u2.username as performed_by_username
            FROM audit_log al
            LEFT JOIN users u1 ON al.user_id = u1.user_id
            JOIN users u2 ON al.performed_by_id = u2.user_id
            WHERE 1=1
        """
        params = []
        where_clauses = []
        # --- Add WHERE clauses exactly as in index() function ---
        if action_type != 'all':
            where_clauses.append("al.action_type = %s"); params.append(action_type)
        if user_id_filter != 'all' and user_id_filter.isdigit():
            where_clauses.append("al.user_id = %s"); params.append(int(user_id_filter))
        if performed_by_filter != 'all' and performed_by_filter.isdigit():
            where_clauses.append("al.performed_by_id = %s"); params.append(int(performed_by_filter))
        if date_from:
            where_clauses.append("DATE(al.performed_at) >= %s"); params.append(date_from)
        if date_to:
            where_clauses.append("DATE(al.performed_at) <= %s"); params.append(date_to)
        if search_query:
             where_clauses.append(""" (
                 al.action_details LIKE %s OR al.target_table LIKE %s OR al.target_record_id LIKE %s OR
                 al.ip_address LIKE %s OR u1.first_name LIKE %s OR u1.last_name LIKE %s OR
                 u2.first_name LIKE %s OR u2.last_name LIKE %s OR u1.username LIKE %s OR u2.username LIKE %s
             )""")
             search_param = f'%{search_query}%'
             params.extend([search_param] * 10)

        if where_clauses:
            query += " AND " + " AND ".join(where_clauses)

        # Add sorting
        valid_sort_fields = { # Ensure these match the SELECT aliases/columns
            'log_id': 'al.log_id', 'user_name': 'affected_user_name', 'action_type': 'al.action_type',
            'performed_by': 'performed_by_name', 'performed_at': 'al.performed_at'
        }
        sort_field = valid_sort_fields.get(sort_by, 'al.performed_at')
        sort_direction = 'DESC' if sort_order.lower() == 'desc' else 'ASC'
        query += f" ORDER BY {sort_field} {sort_direction}"

        # Execute query WITHOUT LIMIT/OFFSET
        cursor.execute(query, tuple(params))
        logs_for_export = cursor.fetchall()

        # --- Placeholder for CSV Generation ---
        if not logs_for_export:
            flash("No logs found matching the criteria for export.", "warning")
            # Redirect back to index with filters preserved
            return redirect(url_for('admin_audit.index', **request.args))

        # (Your CSV generation logic using 'csv' and 'io' modules goes here)
        # import csv
        # import io
        # output = io.StringIO()
        # writer = csv.writer(output)
        # # Write header
        # writer.writerow(['Log ID', 'Timestamp', 'Action Type', 'Details', 'Target Table', 'Target ID', 'IP Address', 'Affected User ID', 'Affected User', 'Affected Username', 'Performed By ID', 'Performed By', 'Performed By Username'])
        # # Write data rows
        # for log in logs_for_export:
        #     writer.writerow([
        #         log.get('log_id'), log.get('performed_at'), log.get('action_type'), log.get('action_details'),
        #         log.get('target_table'), log.get('target_record_id'), log.get('ip_address'),
        #         log.get('affected_user_id'), log.get('affected_user_name'), log.get('affected_user_username'),
        #         log.get('performed_by_user_id'), log.get('performed_by_name'), log.get('performed_by_username')
        #     ])
        # output.seek(0)
        # return Response(output, mimetype="text/csv", headers={"Content-Disposition":"attachment;filename=audit_logs.csv"})

        # Remove or comment out this part if CSV export is implemented
        flash("CSV Export functionality needs to be implemented.", "info")
        return redirect(url_for('admin_audit.index', **request.args)) # Redirect back

    except Exception as e:
        flash(f"Error preparing data for export: {str(e)}", "danger")
        current_app.logger.error(f"Error exporting audit logs: {e}")
        return redirect(url_for('admin_audit.index', **request.args)) # Redirect back

    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()