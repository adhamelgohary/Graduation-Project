from flask import Blueprint, render_template, request, session, flash, redirect, url_for
from flask_login import login_required, current_user
from db import get_db_connection

admin_audit = Blueprint('admin_audit', __name__)

@admin_audit.route('/admin/audit-logs', methods=['GET'])
@login_required
def index():
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    
    # Get filter parameters
    action_type = request.args.get('action_type', 'all')
    user_id = request.args.get('user_id', 'all')
    performed_by = request.args.get('performed_by', 'all')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    search_query = request.args.get('search', '')
    sort_by = request.args.get('sort_by', 'performed_at')
    sort_order = request.args.get('sort_order', 'desc')
    
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    # Base query without filters
    query = """
        SELECT al.log_id, al.user_id, al.action_type, al.action_details, 
               al.performed_by_id, al.performed_at,
               CONCAT(u1.first_name, ' ', u1.last_name) as user_name,
               CONCAT(u2.first_name, ' ', u2.last_name) as performed_by_name
        FROM audit_log al
        LEFT JOIN users u1 ON al.user_id = u1.user_id
        LEFT JOIN users u2 ON al.performed_by_id = u2.user_id
        WHERE 1=1
    """
    
    # Initialize parameters list
    params = []
    
    # Add filters to query
    if action_type != 'all':
        query += " AND al.action_type = %s"
        params.append(action_type)
    
    if user_id != 'all' and user_id.isdigit():
        query += " AND al.user_id = %s"
        params.append(int(user_id))
    
    if performed_by != 'all' and performed_by.isdigit():
        query += " AND al.performed_by_id = %s"
        params.append(int(performed_by))
    
    if date_from:
        query += " AND DATE(al.performed_at) >= %s"
        params.append(date_from)
    
    if date_to:
        query += " AND DATE(al.performed_at) <= %s"
        params.append(date_to)
    
    if search_query:
        query += """ AND (
            al.action_details LIKE %s OR 
            u1.first_name LIKE %s OR 
            u1.last_name LIKE %s OR 
            u2.first_name LIKE %s OR 
            u2.last_name LIKE %s
        )"""
        search_param = f'%{search_query}%'
        params.extend([search_param, search_param, search_param, search_param, search_param])
    
    # Add sorting
    valid_sort_fields = {
        'log_id': 'al.log_id',
        'user_name': 'user_name',
        'action_type': 'al.action_type',
        'performed_by': 'performed_by_name',
        'performed_at': 'al.performed_at'
    }
    
    sort_field = valid_sort_fields.get(sort_by, 'al.performed_at')
    sort_direction = 'DESC' if sort_order.lower() == 'desc' else 'ASC'
    
    query += f" ORDER BY {sort_field} {sort_direction}"
    
    # Add pagination
    page = int(request.args.get('page', 1))
    per_page = 20
    offset = (page - 1) * per_page
    
    count_query = f"SELECT COUNT(*) as total FROM ({query}) as filtered_logs"
    cursor.execute(count_query, tuple(params))
    total_logs = cursor.fetchone()['total']
    
    query += " LIMIT %s OFFSET %s"
    params.extend([per_page, offset])
    
    # Execute query
    cursor.execute(query, tuple(params))
    logs = cursor.fetchall()
    
    # Get action types for filter dropdown
    cursor.execute("SELECT DISTINCT action_type FROM audit_log ORDER BY action_type")
    action_types = [row['action_type'] for row in cursor.fetchall()]
    
    # Get admin users for filter dropdown
    cursor.execute("""
        SELECT user_id, CONCAT(first_name, ' ', last_name) as name 
        FROM users 
        WHERE user_type = 'admin'
        ORDER BY name
    """)
    admins = cursor.fetchall()
    
    cursor.close()
    connection.close()
    
    total_pages = (total_logs + per_page - 1) // per_page
    
    return render_template('Admin_Portal/AuditLogs/audit_logs.html', 
                           logs=logs,
                           total_logs=total_logs,
                           current_page=page,
                           total_pages=total_pages,
                           action_types=action_types,
                           admins=admins,
                           filter_action_type=action_type,
                           filter_user_id=user_id,
                           filter_performed_by=performed_by,
                           filter_date_from=date_from,
                           filter_date_to=date_to,
                           search_query=search_query,
                           sort_by=sort_by,
                           sort_order=sort_order)

@admin_audit.route('/admin/audit-logs/view/<int:log_id>', methods=['GET'])
@login_required
def view_log(log_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT al.log_id, al.user_id, al.action_type, al.action_details, 
               al.performed_by_id, al.performed_at,
               CONCAT(u1.first_name, ' ', u1.last_name) as user_name,
               u1.username as user_username,
               u1.email as user_email,
               CONCAT(u2.first_name, ' ', u2.last_name) as performed_by_name,
               u2.username as performed_by_username,
               u2.email as performed_by_email
        FROM audit_log al
        LEFT JOIN users u1 ON al.user_id = u1.user_id
        LEFT JOIN users u2 ON al.performed_by_id = u2.user_id
        WHERE al.log_id = %s
    """, (log_id,))
    
    log = cursor.fetchone()
    
    if not log:
        flash("Audit log entry not found", "danger")
        return redirect(url_for('admin_audit.index'))
    
    cursor.close()
    connection.close()
    
    return render_template('Admin_Portal/AuditLogs/view_log.html', log=log)

@admin_audit.route('/admin/audit-logs/export', methods=['GET'])
@login_required
def export_logs():
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    
    # Retrieve the same filters as in the index function
    action_type = request.args.get('action_type', 'all')
    user_id = request.args.get('user_id', 'all')
    performed_by = request.args.get('performed_by', 'all')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    search_query = request.args.get('search', '')
    sort_by = request.args.get('sort_by', 'performed_at')
    sort_order = request.args.get('sort_order', 'desc')
    
    # Implement CSV export logic here (similar to the index query but without pagination)
    # This is a placeholder for the CSV export functionality
    
    flash("Export functionality will be implemented in a future release", "info")
    return redirect(url_for('admin_audit.index', 
                           action_type=action_type,
                           user_id=user_id,
                           performed_by=performed_by,
                           date_from=date_from,
                           date_to=date_to,
                           search_query=search_query,
                           sort_by=sort_by,
                           sort_order=sort_order))