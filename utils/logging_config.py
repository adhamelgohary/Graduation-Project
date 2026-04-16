import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s - %(message)s"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def setup_logging(app):
    log_level = logging.getLevelName(os.environ.get("LOG_LEVEL", "INFO"))

    app.logger.setLevel(log_level)
    app.logger.handlers.clear()

    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "app.log"), maxBytes=10 * 1024 * 1024, backupCount=5
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    app.logger.addHandler(file_handler)

    error_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "error.log"), maxBytes=10 * 1024 * 1024, backupCount=5
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    app.logger.addHandler(error_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    app.logger.addHandler(console_handler)

    app.logger.info(f"Logging initialized at {datetime.utcnow().isoformat()}Z")


def log_user_activity(user_id, action, details=None, ip_address=None):
    logger = logging.getLogger("activity")
    activity_log = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "user_id": user_id,
        "action": action,
        "details": details or {},
        "ip_address": ip_address,
    }
    with open(os.path.join(LOG_DIR, "activity.log"), "a") as f:
        f.write(f"{activity_log}\n")
    logging.getLogger("activity").info(f"USER_ACTIVITY: {activity_log}")


def log_security_event(event_type, user_id=None, ip_address=None, details=None):
    logger = logging.getLogger("security")
    security_log = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "event_type": event_type,
        "user_id": user_id,
        "ip_address": ip_address,
        "details": details or {},
    }
    with open(os.path.join(LOG_DIR, "security.log"), "a") as f:
        f.write(f"{security_log}\n")
    logging.getLogger("security").warning(f"SECURITY_EVENT: {security_log}")


def log_api_request(
    method, path, status_code, duration_ms, user_id=None, ip_address=None
):
    logger = logging.getLogger("access")
    access_log = [
        datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        method,
        path,
        str(status_code),
        f"{duration_ms:.2f}ms",
    ]
    logger.info(" ".join(access_log))


def log_database_query(query_type, table, duration_ms, rows_affected=0, error=None):
    logger = logging.getLogger("database")
    db_log = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "query_type": query_type,
        "table": table,
        "duration_ms": duration_ms,
        "rows_affected": rows_affected,
        "error": str(error) if error else None,
    }
    logger.info(f"DB_QUERY: {db_log}")
