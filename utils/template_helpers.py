# utils/template_helpers.py
from datetime import datetime, date, time, timedelta
import logging
from fastapi import Request
from fastapi.templating import Jinja2Templates

# Set up logging
logger = logging.getLogger(__name__)

# --- Global Templates Instance ---
# This centralizes template management so filters are registered once
templates = Jinja2Templates(directory="templates")


# --- Flash Messaging ---
def flash(request: Request, message: str, category: str = "primary"):
    if "_messages" not in request.session:
        request.session["_messages"] = []
    request.session["_messages"].append({"message": message, "category": category})


from functools import partial


def get_flashed_messages(
    request: Request, with_categories: bool = False, category_filter: list = []
):
    messages = request.session.pop("_messages", [])

    if category_filter:
        messages = [m for m in messages if m["category"] in category_filter]

    if with_categories:
        return [(m["category"], m["message"]) for m in messages]

    return [m["message"] for m in messages]


# --- Template Response Override ---
# Intercept TemplateResponse to inject 'current_user' and 'get_flashed_messages'
_original_template_response = templates.TemplateResponse


def auth_template_response(name, context, **kwargs):
    # 'request' is usually in context, or kwargs
    request = context.get("request") or kwargs.get("request")
    if request:
        # Inject current_user if AuthMiddleware set it
        context["current_user"] = getattr(request.state, "user", None)
        # Inject get_flashed_messages handler
        context["get_flashed_messages"] = partial(get_flashed_messages, request)

    return _original_template_response(name, context, **kwargs)


templates.TemplateResponse = auth_template_response

# --- Filter Functions ---


def get_current_year():  # This was also defined as a global later, ensure consistency
    return datetime.now().year


def format_timedelta_as_time(delta, fmt="%I:%M %p"):
    """Custom Jinja filter to format timedelta (from TIME column) as time string."""
    if not isinstance(delta, timedelta):
        if isinstance(delta, time):
            try:
                return delta.strftime(fmt)
            except:
                return str(delta)  # Fallback
        return delta  # Return as is if not timedelta or time

    try:
        # Combine with a minimal date and time to get a datetime object, then format its time part
        if delta.total_seconds() < 0:
            # For negative timedeltas, direct string representation might be best
            # or decide on a specific format like "-HH:MM"
            return str(delta)
        # Create a datetime object at midnight, then add the timedelta
        # This avoids issues with date.min if delta is very large
        dummy_dt = (
            datetime.min.replace(hour=0, minute=0, second=0, microsecond=0) + delta
        )
        return dummy_dt.strftime(fmt)
    except (ValueError, OverflowError, Exception) as e:
        # Optionally log the error:
        # from flask import current_app
        # if current_app:
        #     current_app.logger.warning(f"Error formatting timedelta {delta}: {e}")
        return str(delta)  # Fallback to default string representation on error


def map_status_to_badge_class(status):
    """Maps a status string to a Bootstrap-like background class."""
    if status is None:
        return "secondary"  # Or 'light' for a lighter badge

    status_lower = (
        str(status).lower().strip()
    )  # Ensure it's a string and strip whitespace

    positive_statuses = [
        "approved",
        "approved_user_created",
        "active",
        "completed",
        "confirmed",
        "paid",
    ]
    pending_statuses = [
        "pending",
        "scheduled",
        "rescheduled",
        "pending_payment",
        "processing",
    ]
    negative_statuses = [
        "rejected",
        "inactive",
        "suspended",
        "canceled",
        "no-show",
        "failed",
        "expired",
    ]
    info_statuses = ["pending_info", "info_requested", "on_hold"]  # Example for info

    if status_lower in positive_statuses:
        return "success"
    elif status_lower in pending_statuses:
        return "warning"
    elif status_lower in negative_statuses:
        return "danger"
    elif status_lower in info_statuses:
        return "info"
    else:
        # Default for unknown statuses, could also be 'light' or 'dark'
        return "secondary"


# --- Registration Function ---


def register_template_helpers(templates_obj):
    """Registers custom Jinja filters and globals to a Jinja2Templates object."""

    # Register Filters
    templates_obj.env.filters["timedelta_to_time"] = format_timedelta_as_time
    templates_obj.env.filters["status_badge"] = map_status_to_badge_class

    logger.info("Registered Jinja filters: timedelta_to_time, status_badge")

    # Register Globals
    templates_obj.env.globals["enumerate"] = enumerate
    templates_obj.env.globals["timedelta"] = timedelta
    templates_obj.env.globals["datetime"] = datetime
    templates_obj.env.globals["date"] = date
    templates_obj.env.globals["time"] = time
    templates_obj.env.globals["get_current_year"] = get_current_year
    templates_obj.env.globals["hasattr"] = hasattr

    logger.info(
        "Registered Jinja globals: enumerate, timedelta, datetime, date, time, get_current_year, hasattr"
    )


# Initialize filters on the global instance
register_template_helpers(templates)
