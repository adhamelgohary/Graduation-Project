# utils/directory_configs.py
import os
import logging
from flask import current_app # Import current_app for get_relative_upload_path

logger = logging.getLogger(__name__)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
UPLOAD_FOLDER_BASE = os.path.join(BASE_DIR, 'static', 'uploads')

UPLOAD_FOLDER_PROFILE = os.path.join(UPLOAD_FOLDER_BASE, 'profile_pics')
UPLOAD_FOLDER_DOCS = os.path.join(UPLOAD_FOLDER_BASE, 'doctor_docs')
UPLOAD_FOLDER_DEPARTMENTS = os.path.join(UPLOAD_FOLDER_BASE, 'department_images')
UPLOAD_FOLDER_CONDITIONS = os.path.join(UPLOAD_FOLDER_BASE, 'condition_images')
UPLOAD_FOLDER_CONDITION_VIDEOS = os.path.join(UPLOAD_FOLDER_BASE, 'condition_videos') # <-- NEW FOLDER
UPLOAD_FOLDER_ATTACHMENTS = os.path.join(UPLOAD_FOLDER_BASE, 'chat_attachments') # For messaging

ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_DOC_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'} # For doctor docs
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'mov', 'avi', 'wmv', 'mkv', 'webm'} # <-- NEW VIDEO EXTENSIONS
ALLOWED_ATTACHMENT_EXTENSIONS = { # For chat
    'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'doc', 'docx', 'txt', 'xls', 'xlsx', 'ppt', 'pptx', 'mp4', 'mov'
}


def configure_directories(app):
    app.config['STATIC_FOLDER'] = os.path.join(BASE_DIR, 'static')

    app.config['UPLOAD_FOLDER_BASE'] = UPLOAD_FOLDER_BASE
    app.config['UPLOAD_FOLDER_PROFILE'] = UPLOAD_FOLDER_PROFILE
    app.config['UPLOAD_FOLDER_DOCS'] = UPLOAD_FOLDER_DOCS
    app.config['UPLOAD_FOLDER_DEPARTMENTS'] = UPLOAD_FOLDER_DEPARTMENTS
    app.config['UPLOAD_FOLDER_CONDITIONS'] = UPLOAD_FOLDER_CONDITIONS
    app.config['UPLOAD_FOLDER_CONDITION_VIDEOS'] = UPLOAD_FOLDER_CONDITION_VIDEOS # <-- NEW
    app.config['UPLOAD_FOLDER_ATTACHMENTS'] = UPLOAD_FOLDER_ATTACHMENTS # <-- NEW (if not already there)


    app.config['ALLOWED_IMAGE_EXTENSIONS'] = ALLOWED_IMAGE_EXTENSIONS
    app.config['ALLOWED_DOC_EXTENSIONS'] = ALLOWED_DOC_EXTENSIONS
    app.config['ALLOWED_VIDEO_EXTENSIONS'] = ALLOWED_VIDEO_EXTENSIONS # <-- NEW
    app.config['ALLOWED_ATTACHMENT_EXTENSIONS'] = ALLOWED_ATTACHMENT_EXTENSIONS # <-- NEW


    upload_dirs = [
        UPLOAD_FOLDER_BASE,
        UPLOAD_FOLDER_PROFILE,
        UPLOAD_FOLDER_DOCS,
        UPLOAD_FOLDER_DEPARTMENTS,
        UPLOAD_FOLDER_CONDITIONS,
        UPLOAD_FOLDER_CONDITION_VIDEOS, # <-- NEW
        UPLOAD_FOLDER_ATTACHMENTS      # <-- NEW
    ]

    logger.info("--- Configuring Upload Directories ---")
    for dir_path in upload_dirs:
        try:
            os.makedirs(dir_path, exist_ok=True)
            logger.info(f"Ensured directory exists: {dir_path}")
        except OSError as e:
            logger.error(f"Error creating directory '{dir_path}': {e}", exc_info=True)
    logger.info("--- Upload Directory Configuration Complete ---")

# Helper to get relative path for DB storage
def get_relative_upload_path(absolute_filepath, app_config_base_upload_key='UPLOAD_FOLDER_BASE'):
    # This function uses current_app, so it must be called within an app context
    if not current_app:
        logger.error("get_relative_upload_path called outside of application context.")
        # In a real scenario, this might raise an error or return a specific failure indicator
        # For now, to prevent crashes if called incorrectly during setup (though it shouldn't be):
        return absolute_filepath # Fallback to absolute, though not ideal for DB

    base_static_uploads = current_app.config.get(app_config_base_upload_key)
    if not base_static_uploads:
        logger.error(f"Base upload folder key '{app_config_base_upload_key}' not found in app.config.")
        return None

    abs_filepath_norm = os.path.normpath(os.path.abspath(absolute_filepath))
    base_static_uploads_norm = os.path.normpath(os.path.abspath(base_static_uploads))

    if not abs_filepath_norm.startswith(base_static_uploads_norm):
        logger.error(f"Filepath '{abs_filepath_norm}' is not within base upload directory '{base_static_uploads_norm}'.")
        return None

    relative_to_base_uploads = os.path.relpath(abs_filepath_norm, base_static_uploads_norm)
    final_relative_path = os.path.join('uploads', relative_to_base_uploads).replace(os.path.sep, '/')
    
    logger.debug(f"Generated relative path: {final_relative_path} from abs: {abs_filepath_norm}")
    return final_relative_path