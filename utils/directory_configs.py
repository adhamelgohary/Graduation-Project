# utils/directory_configs.py
import os
import logging

# Get logger instance
logger = logging.getLogger(__name__)

# Determine the absolute path to the project directory
# Assumes this file is inside 'utils', and 'utils' is directly under the project root.
# If 'utils' is inside 'app', change '..' to '../..'.
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# --- Base Upload Folder ---
# All uploads will go into subdirectories under static/uploads/
UPLOAD_FOLDER_BASE = os.path.join(BASE_DIR, 'static', 'uploads')

# --- Specific Upload Folders ---
UPLOAD_FOLDER_PROFILE = os.path.join(UPLOAD_FOLDER_BASE, 'profile_pics')
UPLOAD_FOLDER_DOCS = os.path.join(UPLOAD_FOLDER_BASE, 'doctor_docs')
UPLOAD_FOLDER_DEPARTMENTS = os.path.join(UPLOAD_FOLDER_BASE, 'department_images') # <-- ADDED
# Add more specific upload folders as needed
# UPLOAD_FOLDER_CONDITIONS = os.path.join(UPLOAD_FOLDER_BASE, 'condition_images') # Example

# --- Relative Paths for Database/URL Generation ---
# These paths are relative to the STATIC folder, used by url_for()
# Example: static/uploads/profile_pics/ -> uploads/profile_pics/
# Note: os.path.relpath requires the base path (STATIC_FOLDER) which isn't
# known until the app context is available. We'll construct these inside
# the configure function or calculate them where needed.
# A common pattern is to store the full path in config and derive the relative path later.

# --- Allowed Extensions ---
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_DOC_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'} # Kept your reduced set

def configure_directories(app):
    """
    Sets upload folder paths and allowed extensions in Flask app config.
    Ensures the directories exist.
    """
    app.config['STATIC_FOLDER'] = os.path.join(BASE_DIR, 'static') # Define base static folder if not already set

    # Store ABSOLUTE paths in config for direct use by os functions
    app.config['UPLOAD_FOLDER_BASE'] = UPLOAD_FOLDER_BASE
    app.config['UPLOAD_FOLDER_PROFILE'] = UPLOAD_FOLDER_PROFILE
    app.config['UPLOAD_FOLDER_DOCS'] = UPLOAD_FOLDER_DOCS
    app.config['UPLOAD_FOLDER_DEPARTMENTS'] = UPLOAD_FOLDER_DEPARTMENTS # <-- ADDED

    # Store allowed extensions
    app.config['ALLOWED_IMAGE_EXTENSIONS'] = ALLOWED_IMAGE_EXTENSIONS
    app.config['ALLOWED_DOC_EXTENSIONS'] = ALLOWED_DOC_EXTENSIONS

    # List all upload directories to create
    upload_dirs = [
        UPLOAD_FOLDER_BASE,
        UPLOAD_FOLDER_PROFILE,
        UPLOAD_FOLDER_DOCS,
        UPLOAD_FOLDER_DEPARTMENTS # <-- ADDED
    ]

    logger.info("--- Configuring Upload Directories ---")
    for dir_path in upload_dirs:
        try:
            os.makedirs(dir_path, exist_ok=True)
            logger.info(f"Ensured directory exists: {dir_path}")
        except OSError as e:
            logger.error(f"Error creating directory '{dir_path}': {e}", exc_info=True)
            # Optionally raise an error to stop app startup if directories are critical
            # raise OSError(f"Could not create required upload directory '{dir_path}': {e}") from e
    logger.info("--- Upload Directory Configuration Complete ---")