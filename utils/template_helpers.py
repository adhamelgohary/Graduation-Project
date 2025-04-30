# utils/template_helpers.py
from datetime import datetime, date, time, timedelta

# --- Filter Functions ---

def format_timedelta_as_time(delta, fmt='%I:%M %p'):
    """Custom Jinja filter to format timedelta (from TIME column) as time string."""
    if not isinstance(delta, timedelta):
        if isinstance(delta, time):
            try: return delta.strftime(fmt)
            except: return str(delta) # Fallback
        return delta

    try:
        # Combine with a minimal date and time to get a datetime object, then format its time part
        # Handle potential large negative timedeltas if necessary
        if delta.total_seconds() < 0:
             # Decide how to display negative time (e.g., "-HH:MM", or default string)
             return str(delta) # Example: return default string representation
        dummy_dt = datetime.combine(date.min, time.min) + delta
        return dummy_dt.strftime(fmt)
    except (ValueError, OverflowError, Exception) as e:
        # Log error maybe? from flask import current_app; current_app.logger.warning(...)
        return str(delta) # Fallback to default string representation on error

def map_status_to_badge_class(status):
    """Maps a status string to a Bootstrap-like background class."""
    if status is None:
        return 'secondary'
    status_lower = str(status).lower()
    if status_lower in ['approved', 'approved_user_created', 'active', 'completed', 'confirmed']: # Added more "positive" statuses
        return 'success'
    elif status_lower in ['pending', 'scheduled', 'rescheduled']: # Added more "pending/neutral"
        return 'warning'
    elif status_lower in ['rejected', 'inactive', 'suspended', 'canceled', 'no-show']: # Added more "negative"
        return 'danger'
    elif status_lower == 'info_requested': # Keeping this distinct if needed visually
        return 'info'
    else:
        return 'secondary'

# --- Registration Function ---

def register_template_helpers(app):
    """Registers custom Jinja filters and globals."""

    # Register Filters
    app.jinja_env.filters['timedelta_to_time'] = format_timedelta_as_time
    app.jinja_env.filters['status_badge'] = map_status_to_badge_class
    app.logger.info("Registered Jinja filters: timedelta_to_time, status_badge")

    # Register Globals
    app.jinja_env.globals['enumerate'] = enumerate
    app.jinja_env.globals['timedelta'] = timedelta
    app.jinja_env.globals['datetime'] = datetime
    app.jinja_env.globals['date'] = date # Add date if needed
    app.jinja_env.globals['time'] = time # Add time if needed
    app.logger.info("Registered Jinja globals: enumerate, timedelta, datetime, date, time")