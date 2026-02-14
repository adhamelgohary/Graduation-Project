from contextlib import contextmanager
from db import get_db_connection
import logging

logger = logging.getLogger(__name__)

@contextmanager
def db_connection(commit=False):
    """
    Yields a dictionary cursor from existing sync connection.
    Automatically closes connection and cursor when done.
    """
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to get database connection")
        raise ConnectionError("Failed to get database connection")
    
    cursor = conn.cursor(dictionary=True , buffered=True)
    try:
        yield cursor
        if commit:
            conn.commit()
    except Exception as e:
        if commit:
            conn.rollback()
        logger.error(f"Error in database operation: {e}")
        raise e
    finally:
        cursor.close()
        if conn.is_connected():
            conn.close()