# utils/directory_configs.py
import os

# Determine the absolute path to the project directory
# Assumes this file is inside 'utils', which is at the project root or one level down.
# Adjust '..' if your structure is different (e.g., if utils is inside an 'app' folder)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

UPLOAD_FOLDER_BASE = os.path.join(BASE_DIR, 'static', 'uploads')
UPLOAD_FOLDER_PROFILE = os.path.join(UPLOAD_FOLDER_BASE, 'profile_pics')
UPLOAD_FOLDER_DOCS = os.path.join(UPLOAD_FOLDER_BASE, 'doctor_docs')

# Allowed extensions (can also be defined here or kept in app.py config)
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_DOC_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'} # Adjusted based on your original app.py

def configure_directories(app):
    """Sets upload folder paths in Flask app config and creates directories."""
    app.config['UPLOAD_FOLDER_PROFILE'] = UPLOAD_FOLDER_PROFILE
    app.config['UPLOAD_FOLDER_DOCS'] = UPLOAD_FOLDER_DOCS

    # Add extension configs if moved here
    app.config['ALLOWED_IMAGE_EXTENSIONS'] = ALLOWED_IMAGE_EXTENSIONS
    app.config['ALLOWED_DOC_EXTENSIONS'] = ALLOWED_DOC_EXTENSIONS

    # Ensure upload directories exist
    try:
        os.makedirs(app.config['UPLOAD_FOLDER_PROFILE'], exist_ok=True)
        os.makedirs(app.config['UPLOAD_FOLDER_DOCS'], exist_ok=True)
        app.logger.info(f"Upload directories ensured/created:")
        app.logger.info(f" - Profiles: {app.config['UPLOAD_FOLDER_PROFILE']}")
        app.logger.info(f" - Docs: {app.config['UPLOAD_FOLDER_DOCS']}")
    except OSError as e:
        app.logger.error(f"Error creating upload directories: {e}", exc_info=True)
        # Decide if this is a critical error that should stop the app
        # raise OSError(f"Could not create required upload directories: {e}") from e