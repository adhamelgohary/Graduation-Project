# utils/directory_configs.py
import os
import logging

logger = logging.getLogger(__name__)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
UPLOAD_FOLDER_BASE = os.path.join(BASE_DIR, 'static', 'uploads')

UPLOAD_FOLDER_PROFILE = os.path.join(UPLOAD_FOLDER_BASE, 'profile_pics')
UPLOAD_FOLDER_DOCS = os.path.join(UPLOAD_FOLDER_BASE, 'doctor_docs')
UPLOAD_FOLDER_DEPARTMENTS = os.path.join(UPLOAD_FOLDER_BASE, 'department_images')
# --- ADDED FOR CONDITIONS/DISEASES ---
UPLOAD_FOLDER_CONDITIONS = os.path.join(UPLOAD_FOLDER_BASE, 'condition_images')
# ------------------------------------

ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_DOC_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

def configure_directories(app):
    app.config['STATIC_FOLDER'] = os.path.join(BASE_DIR, 'static')

    app.config['UPLOAD_FOLDER_BASE'] = UPLOAD_FOLDER_BASE
    app.config['UPLOAD_FOLDER_PROFILE'] = UPLOAD_FOLDER_PROFILE
    app.config['UPLOAD_FOLDER_DOCS'] = UPLOAD_FOLDER_DOCS
    app.config['UPLOAD_FOLDER_DEPARTMENTS'] = UPLOAD_FOLDER_DEPARTMENTS
    # --- ADDED FOR CONDITIONS/DISEASES ---
    app.config['UPLOAD_FOLDER_CONDITIONS'] = UPLOAD_FOLDER_CONDITIONS
    # ------------------------------------

    app.config['ALLOWED_IMAGE_EXTENSIONS'] = ALLOWED_IMAGE_EXTENSIONS
    app.config['ALLOWED_DOC_EXTENSIONS'] = ALLOWED_DOC_EXTENSIONS

    upload_dirs = [
        UPLOAD_FOLDER_BASE,
        UPLOAD_FOLDER_PROFILE,
        UPLOAD_FOLDER_DOCS,
        UPLOAD_FOLDER_DEPARTMENTS,
        UPLOAD_FOLDER_CONDITIONS # --- ADDED ---
    ]

    logger.info("--- Configuring Upload Directories ---")
    for dir_path in upload_dirs:
        try:
            os.makedirs(dir_path, exist_ok=True)
            logger.info(f"Ensured directory exists: {dir_path}")
        except OSError as e:
            logger.error(f"Error creating directory '{dir_path}': {e}", exc_info=True)
    logger.info("--- Upload Directory Configuration Complete ---")

# --- Helper to get relative path for DB storage (optional, but good for consistency) ---
def get_relative_upload_path(absolute_filepath, app_config_base_upload_key='UPLOAD_FOLDER_BASE'):
    """
    Generates a path relative to the app's base static upload folder.
    Example: /abs/path/to/static/uploads/condition_images/img.jpg -> uploads/condition_images/img.jpg
    """
    base_static_uploads = current_app.config.get(app_config_base_upload_key)
    if not base_static_uploads:
        logger.error(f"Base upload folder key '{app_config_base_upload_key}' not found in app.config.")
        return None # Or raise an error

    # Ensure both paths are absolute and normalized for correct comparison
    abs_filepath_norm = os.path.normpath(os.path.abspath(absolute_filepath))
    base_static_uploads_norm = os.path.normpath(os.path.abspath(base_static_uploads))

    # Check if the filepath is actually within the base static uploads directory
    if not abs_filepath_norm.startswith(base_static_uploads_norm):
        logger.error(f"Filepath '{abs_filepath_norm}' is not within base upload directory '{base_static_uploads_norm}'. Cannot create relative path.")
        return None # Or raise

    # Get path relative to UPLOAD_FOLDER_BASE
    relative_to_base_uploads = os.path.relpath(abs_filepath_norm, base_static_uploads_norm)
    
    # Construct the path as 'uploads/subdirectory/filename'
    # os.path.join will handle OS-specific separators, then we convert to forward slashes for web URLs
    final_relative_path = os.path.join('uploads', relative_to_base_uploads).replace(os.path.sep, '/')
    
    logger.debug(f"Generated relative path: {final_relative_path} from abs: {abs_filepath_norm}")
    return final_relative_path