# utils/template_helpers.py
from datetime import datetime, date, time, timedelta
# No need to import 'builtins' for hasattr as it's a standard built-in function
# and Flask/Jinja usually make these accessible or you pass the function itself.

# --- Filter Functions ---

def get_current_year(): # This was also defined as a global later, ensure consistency
    return datetime.now().year

def format_timedelta_as_time(delta, fmt='%I:%M %p'):
    """Custom Jinja filter to format timedelta (from TIME column) as time string."""
    if not isinstance(delta, timedelta):
        if isinstance(delta, time):
            try:
                return delta.strftime(fmt)
            except:
                return str(delta) # Fallback
        return delta # Return as is if not timedelta or time

    try:
        # Combine with a minimal date and time to get a datetime object, then format its time part
        if delta.total_seconds() < 0:
             # For negative timedeltas, direct string representation might be best
             # or decide on a specific format like "-HH:MM"
             return str(delta)
        # Create a datetime object at midnight, then add the timedelta
        # This avoids issues with date.min if delta is very large
        dummy_dt = datetime.min.replace(hour=0, minute=0, second=0, microsecond=0) + delta
        return dummy_dt.strftime(fmt)
    except (ValueError, OverflowError, Exception) as e:
        # Optionally log the error:
        # from flask import current_app
        # if current_app:
        #     current_app.logger.warning(f"Error formatting timedelta {delta}: {e}")
        return str(delta) # Fallback to default string representation on error

def map_status_to_badge_class(status):
    """Maps a status string to a Bootstrap-like background class."""
    if status is None:
        return 'secondary' # Or 'light' for a lighter badge

    status_lower = str(status).lower().strip() # Ensure it's a string and strip whitespace

    positive_statuses = ['approved', 'approved_user_created', 'active', 'completed', 'confirmed', 'paid']
    pending_statuses = ['pending', 'scheduled', 'rescheduled', 'pending_payment', 'processing']
    negative_statuses = ['rejected', 'inactive', 'suspended', 'canceled', 'no-show', 'failed', 'expired']
    info_statuses = ['pending_info', 'info_requested', 'on_hold'] # Example for info

    if status_lower in positive_statuses:
        return 'success'
    elif status_lower in pending_statuses:
        return 'warning'
    elif status_lower in negative_statuses:
        return 'danger'
    elif status_lower in info_statuses:
        return 'info'
    else:
        # Default for unknown statuses, could also be 'light' or 'dark'
        return 'secondary'

# --- Registration Function ---

def register_template_helpers(app):
    """Registers custom Jinja filters and globals."""

    # Register Filters
    app.jinja_env.filters['timedelta_to_time'] = format_timedelta_as_time
    app.jinja_env.filters['status_badge'] = map_status_to_badge_class
    if app.logger: # Check if logger is available (it should be)
        app.logger.info("Registered Jinja filters: timedelta_to_time, status_badge")

    # Register Globals
    # These make Python objects/functions directly usable in templates without passing them from views
    app.jinja_env.globals['enumerate'] = enumerate
    app.jinja_env.globals['timedelta'] = timedelta
    app.jinja_env.globals['datetime'] = datetime # Allows using datetime.strptime etc. in templates if needed
    app.jinja_env.globals['date'] = date
    app.jinja_env.globals['time'] = time
    app.jinja_env.globals['get_current_year'] = get_current_year # Makes the function callable
    
    # --- ADD HASATTR TO JINJA GLOBALS ---
    app.jinja_env.globals['hasattr'] = hasattr

    if app.logger:
        app.logger.info("Registered Jinja globals: enumerate, timedelta, datetime, date, time, get_current_year, hasattr")