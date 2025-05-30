# routes/patient/patient_trackers.py (new file)

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
import os
import json
from datetime import datetime
from db import get_db_connection # Assuming you have this
from utils.directory_configs import get_relative_path_for_db

patient_tracker_bp = Blueprint('patient_tracker_bp', __name__, url_prefix='/patient/trackers')

# Mapping from URL tracker name to a more descriptive name and localStorage key
TRACKER_CONFIG = {
    'joint_health': {'name': 'Joint Health Tracker', 'localStorageKey': 'jointHealthTracker'},
    'kyphosis': {'name': 'Kyphosis Tracker', 'localStorageKey': 'kyphosisTracker'},
    'scoliosis': {'name': 'Scoliosis Tracker', 'localStorageKey': 'scoliosisTracker'}, # Assuming spinetracker.html is for scoliosis
    'lumbar_herniated_disc': {'name': 'Lumbar Herniated Disc Tracker', 'localStorageKey': 'herniatedDiscTracker'}
}

@patient_tracker_bp.route('/submit/<string:tracker_url_name>', methods=['POST'])
@login_required
def submit_tracker_data(tracker_url_name):
    if tracker_url_name not in TRACKER_CONFIG:
        return jsonify({'success': False, 'message': 'Invalid tracker type specified.'}), 400

    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data received.'}), 400

        patient_id = current_user.id # Assuming current_user has an 'id' attribute for patient_id
        entry_type = data.get('type', 'unknown').capitalize() # 'daily', 'weekly', 'monthly' -> 'Daily', 'Weekly', 'Monthly'
        entry_date_str = data.get('date') or data.get('weekOf') or data.get('monthOf') or datetime.now().strftime('%Y-%m-%d')
        
        # Ensure entry_date_str is just the date part for filename consistency
        try:
            entry_date_obj = datetime.strptime(entry_date_str.split('T')[0], '%Y-%m-%d')
            filename_date_str = entry_date_obj.strftime('%Y%m%d')
        except ValueError:
            filename_date_str = datetime.now().strftime('%Y%m%d') # Fallback

        config = TRACKER_CONFIG[tracker_url_name]
        base_document_type = config['name']
        
        document_type_full = f"{base_document_type} - {entry_type} Entry"
        document_name = f"{base_document_type} - {entry_type} - {filename_date_str}"

        # Define file storage path
        reports_upload_folder = current_app.config['UPLOAD_FOLDER_PATIENT_REPORTS']
        patient_specific_folder = os.path.join(reports_upload_folder, str(patient_id))
        os.makedirs(patient_specific_folder, exist_ok=True)

        # Sanitize filename components
        safe_tracker_name = tracker_url_name.replace(" ", "_")
        safe_entry_type = entry_type.lower()
        report_filename = f"{safe_tracker_name}_{safe_entry_type}_{filename_date_str}_{datetime.now().strftime('%H%M%S')}.json"
        absolute_file_path = os.path.join(patient_specific_folder, report_filename)

        # Save the data as a JSON file
        with open(absolute_file_path, 'w') as f:
            json.dump(data, f, indent=4)
        
        # Get relative path for DB
        # Pass the specific base key if your get_relative_path_for_db is flexible,
        # or ensure it calculates relative to UPLOAD_FOLDER_BASE correctly
        relative_file_path = get_relative_path_for_db(absolute_file_path) 
        if not relative_file_path:
            current_app.logger.error(f"Could not generate relative path for {absolute_file_path}")
            return jsonify({'success': False, 'message': 'Error processing file path.'}), 500

        # Save to database
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = """
            INSERT INTO patient_medical_reports 
            (patient_id, document_name, document_type, report_format, file_path, submission_date, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        # Use current datetime for submission_date
        submission_time = datetime.now()
        notes_content = data.get('notes', '') # Get notes from the submitted data if available

        cursor.execute(sql, (
            patient_id, 
            document_name, 
            document_type_full, 
            'json', # report_format
            relative_file_path, 
            submission_time,
            notes_content 
        ))
        conn.commit()
        
        current_app.logger.info(f"Patient {patient_id} submitted report: {document_name}, path: {relative_file_path}")
        return jsonify({'success': True, 'message': 'Report submitted successfully.'})

    except Exception as e:
        current_app.logger.error(f"Error submitting tracker data for {tracker_url_name}: {e}", exc_info=True)
        if 'conn' in locals() and conn.is_connected():
            conn.rollback()
        return jsonify({'success': False, 'message': f'An internal error occurred: {str(e)}'}), 500
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conn' in locals() and conn.is_connected(): conn.close()

# Remember to register this blueprint in your main app factory
# In __init__.py or app.py:
# from routes.patient.patient_trackers import patient_tracker_bp
# app.register_blueprint(patient_tracker_bp)