# your_project/routes/api/user_alerts.py (or in an existing API blueprint)
from flask import Blueprint, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from db import get_db_connection # Adjust import
import logging # Import logging

# Configure logger for this module
logger = logging.getLogger(__name__)


user_alerts_bp = Blueprint('user_alerts', __name__, url_prefix='/api/user-alerts')

def format_time_left(td):
    """Formats a timedelta into a human-readable string like 'X hours, Y minutes'."""
    if not isinstance(td, timedelta) or td.total_seconds() < 0:
        return "Now or Past"

    days = td.days
    hours, remainder = divmod(td.seconds, 3600)
    minutes, _ = divmod(remainder, 60)

    parts = []
    if days > 0:
        parts.append(f"{days} day{'s' if days > 1 else ''}")
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours > 1 else ''}")
    if minutes > 0 or (not parts and hours == 0 and days == 0) : # Show minutes if it's the only unit or if < 1hr
        parts.append(f"{minutes} min{'s' if minutes > 1 else ''}")
    
    if not parts: # Less than a minute
        return "Soon"
        
    return ", ".join(parts) + " left"


@user_alerts_bp.route('/upcoming-appointments-alert')
@login_required
def upcoming_appointments_alert():
    conn = None
    cursor = None
    alerts = []
    now = datetime.now()
    in_24_hours = now + timedelta(hours=24)

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Base query to select necessary fields
        query_base = """
            SELECT 
                a.appointment_id,
                a.appointment_date,
                a.start_time,
                apt.type_name as appointment_type,
                dl.location_name
            FROM appointments a
            LEFT JOIN appointment_types apt ON a.appointment_type_id = apt.type_id
            LEFT JOIN doctor_locations dl ON a.doctor_location_id = dl.doctor_location_id
            WHERE 
                a.status IN ('scheduled', 'confirmed') 
                AND CONCAT(a.appointment_date, ' ', a.start_time) >= %s
                AND CONCAT(a.appointment_date, ' ', a.start_time) <= %s
        """
        
        params = [now.strftime('%Y-%m-%d %H:%M:%S'), in_24_hours.strftime('%Y-%m-%d %H:%M:%S')]

        if current_user.user_type == 'patient':
            query = query_base + " AND a.patient_id = %s ORDER BY a.appointment_date, a.start_time ASC"
            params.append(current_user.id)
        elif current_user.user_type == 'doctor':
            query = query_base + " AND a.doctor_id = %s ORDER BY a.appointment_date, a.start_time ASC"
            params.append(current_user.id)
        else:
            # Admins or other types might not need this alert, or need a different one
            return jsonify({"upcoming_alerts": []})

        cursor.execute(query, tuple(params))
        appointments = cursor.fetchall()

        for appt in appointments:
            # Combine date and time from DB into a datetime object
            # start_time from DB might be timedelta, convert to time if so
            appt_start_time = appt['start_time']
            if isinstance(appt_start_time, timedelta):
                # Convert timedelta to time
                total_seconds = int(appt_start_time.total_seconds())
                h = (total_seconds // 3600) % 24
                m = (total_seconds % 3600) // 60
                s = total_seconds % 60
                appt_start_time = time(h,m,s)
            
            if isinstance(appt['appointment_date'], datetime): # if date is already datetime
                appt_datetime_start = datetime.combine(appt['appointment_date'].date(), appt_start_time)
            elif isinstance(appt['appointment_date'], date): # if date is date object
                appt_datetime_start = datetime.combine(appt['appointment_date'], appt_start_time)
            else: # Should not happen if DB schema is correct
                logger.warning(f"Unexpected appointment_date type: {type(appt['appointment_date'])} for appt ID {appt['appointment_id']}")
                continue


            if appt_datetime_start > now: # Only include future appointments
                time_left_delta = appt_datetime_start - now
                alerts.append({
                    "appointment_id": appt['appointment_id'],
                    "type": appt.get('appointment_type', 'Appointment'),
                    "location": appt.get('location_name', 'N/A'),
                    "datetime_iso": appt_datetime_start.isoformat(), # For JS to parse
                    "time_left_str": format_time_left(time_left_delta),
                    "time_left_seconds": time_left_delta.total_seconds() # For JS countdown
                })
        
        logger.debug(f"Upcoming alerts for user {current_user.id}: {alerts}")
        return jsonify({"upcoming_alerts": alerts})

    except mysql.connector.Error as err:
        logger.error(f"Database error fetching upcoming appointment alerts for user {current_user.id}: {err}", exc_info=True)
        return jsonify({"error": "Database error"}), 500
    except Exception as e:
        logger.error(f"Unexpected error fetching upcoming appointment alerts for user {current_user.id}: {e}", exc_info=True)
        return jsonify({"error": "An unexpected error occurred"}), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

# Register this blueprint in your main app factory (e.g., __init__.py)
# from .routes.api.user_alerts import user_alerts_bp # Adjust path
# app.register_blueprint(user_alerts_bp)