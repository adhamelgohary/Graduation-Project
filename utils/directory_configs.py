# utils/directory_configs.py
import os
import logging

logger = logging.getLogger(__name__)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATIC_FOLDER_ABS = os.path.join(BASE_DIR, "static")
UPLOAD_FOLDER_BASE = os.path.join(STATIC_FOLDER_ABS, "uploads")

UPLOAD_FOLDER_PROFILE = os.path.join(UPLOAD_FOLDER_BASE, "profile_pics")
UPLOAD_FOLDER_DOCS = os.path.join(UPLOAD_FOLDER_BASE, "doctor_docs")
UPLOAD_FOLDER_DEPARTMENTS = os.path.join(UPLOAD_FOLDER_BASE, "department_images")
UPLOAD_FOLDER_CONDITIONS = os.path.join(UPLOAD_FOLDER_BASE, "condition_images")
UPLOAD_FOLDER_CONDITION_VIDEOS = os.path.join(UPLOAD_FOLDER_BASE, "condition_videos")
UPLOAD_FOLDER_ATTACHMENTS = os.path.join(UPLOAD_FOLDER_BASE, "chat_attachments")
UPLOAD_FOLDER_PATIENT_REPORTS = os.path.join(UPLOAD_FOLDER_BASE, "patient_reports")
UPLOAD_FOLDER_VACCINE_CATEGORY_IMAGES = os.path.join(
    UPLOAD_FOLDER_BASE, "vaccine_category_images"
)

ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
ALLOWED_DOC_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "doc", "docx"}
ALLOWED_VIDEO_EXTENSIONS = {"mp4", "mov", "avi", "wmv", "mkv", "webm"}
ALLOWED_REPORT_EXTENSIONS = {"json", "pdf"}
ALLOWED_ATTACHMENT_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "gif",
    "webp",
    "pdf",
    "doc",
    "docx",
    "txt",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    "mp4",
    "mov",
}


def configure_directories(app=None):
    """
    Ensures all necessary upload directories exist.
    Optional 'app' argument for FastAPI app context if needed.
    """
    upload_dirs = [
        UPLOAD_FOLDER_BASE,
        UPLOAD_FOLDER_PROFILE,
        UPLOAD_FOLDER_DOCS,
        UPLOAD_FOLDER_DEPARTMENTS,
        UPLOAD_FOLDER_CONDITIONS,
        UPLOAD_FOLDER_CONDITION_VIDEOS,
        UPLOAD_FOLDER_ATTACHMENTS,
        UPLOAD_FOLDER_PATIENT_REPORTS,
        UPLOAD_FOLDER_VACCINE_CATEGORY_IMAGES,
    ]

    logger.info("--- Configuring Upload Directories ---")
    for dir_path in upload_dirs:
        try:
            os.makedirs(dir_path, exist_ok=True)
            logger.info(f"Ensured directory exists: {dir_path}")
        except OSError as e:
            logger.error(f"Error creating directory '{dir_path}': {e}", exc_info=True)

    if app:
        # For FastAPI, you can store these in app.state if needed
        app.state.UPLOAD_FOLDER_BASE = UPLOAD_FOLDER_BASE
        app.state.UPLOAD_FOLDER_PROFILE = UPLOAD_FOLDER_PROFILE
        app.state.UPLOAD_FOLDER_DOCS = UPLOAD_FOLDER_DOCS
        app.state.UPLOAD_FOLDER_DEPARTMENTS = UPLOAD_FOLDER_DEPARTMENTS
        app.state.UPLOAD_FOLDER_CONDITIONS = UPLOAD_FOLDER_CONDITIONS
        app.state.UPLOAD_FOLDER_CONDITION_VIDEOS = UPLOAD_FOLDER_CONDITION_VIDEOS
        app.state.UPLOAD_FOLDER_ATTACHMENTS = UPLOAD_FOLDER_ATTACHMENTS
        app.state.UPLOAD_FOLDER_PATIENT_REPORTS = UPLOAD_FOLDER_PATIENT_REPORTS
        app.state.UPLOAD_FOLDER_VACCINE_CATEGORY_IMAGES = (
            UPLOAD_FOLDER_VACCINE_CATEGORY_IMAGES
        )
        app.state.ALLOWED_IMAGE_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS
        app.state.ALLOWED_DOC_EXTENSIONS = ALLOWED_DOC_EXTENSIONS
        app.state.ALLOWED_VIDEO_EXTENSIONS = ALLOWED_VIDEO_EXTENSIONS
        app.state.ALLOWED_REPORT_EXTENSIONS = ALLOWED_REPORT_EXTENSIONS
        app.state.ALLOWED_ATTACHMENT_EXTENSIONS = ALLOWED_ATTACHMENT_EXTENSIONS

    logger.info("--- Upload Directory Configuration Complete ---")


def get_relative_path_for_db(absolute_filepath):
    """
    Returns the path relative to the static folder for storage in the DB.
    """
    try:
        abs_filepath_norm = os.path.normpath(os.path.abspath(absolute_filepath))
        static_folder_abs_norm = os.path.normpath(STATIC_FOLDER_ABS)
    except Exception as e:
        logger.error(
            f"Error normalizing paths: {absolute_filepath} or {STATIC_FOLDER_ABS}. Error: {e}"
        )
        return None

    if not abs_filepath_norm.startswith(static_folder_abs_norm):
        logger.error(
            f"Filepath '{abs_filepath_norm}' is not within the static directory '{static_folder_abs_norm}'."
        )
        return None

    relative_to_static = os.path.relpath(abs_filepath_norm, static_folder_abs_norm)
    final_relative_path = relative_to_static.replace(os.path.sep, "/")
    logger.debug(
        f"Generated relative path (for DB/url_for): {final_relative_path} from abs: {abs_filepath_norm}"
    )
    return final_relative_path
