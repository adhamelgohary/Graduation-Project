from datetime import datetime, date, time, timedelta

PYTHON_DOW_MAP = {
    0: "Monday",
    1: "Tuesday",
    2: "Wednesday",
    3: "Thursday",
    4: "Friday",
    5: "Saturday",
    6: "Sunday",
}
DB_DOW_MAP = {
    0: "Sunday",
    1: "Monday",
    2: "Tuesday",
    3: "Wednesday",
    4: "Thursday",
    5: "Friday",
    6: "Saturday",
}


def python_dow_to_db_dow(py_dow: int) -> int:
    """Converts Python weekday (0=Monday) to DB weekday (0=Sunday or 1=Sunday depending on DB setup).
    Assuming your DB uses 1=Sunday based on your old code logic (py_dow + 1) % 7?
    Actually, your old code was (py_dow + 1) % 7. Let's stick to that."""
    return (py_dow + 1) % 7


def db_dow_to_python_dow(db_dow: int) -> int:
    return (db_dow - 1 + 7) % 7


def generate_time_slots(start_time, end_time, slot_duration_minutes=30):
    """Generates a list of time objects between start and end."""
    # Convert timedelta to time if necessary
    if isinstance(start_time, timedelta):
        start_time = (datetime.min + start_time).time()
    if isinstance(end_time, timedelta):
        end_time = (datetime.min + end_time).time()

    if not isinstance(start_time, time) or not isinstance(end_time, time):
        return []

    slots = []
    current_dt = datetime.combine(date.min, start_time)
    end_dt_limit = datetime.combine(date.min, end_time)

    while current_dt < end_dt_limit:
        potential_end = current_dt + timedelta(minutes=slot_duration_minutes)
        if potential_end <= end_dt_limit:
            slots.append(current_dt.time())
        current_dt += timedelta(minutes=slot_duration_minutes)

    return slots


def calculate_end_time(start_time, duration_minutes):
    """Calculates end time based on start time and duration."""
    if isinstance(start_time, str):
        try:
            start_time = datetime.strptime(start_time, "%H:%M").time()
        except ValueError:
            start_time = datetime.strptime(start_time, "%H:%M:%S").time()

    start_dt = datetime.combine(date.min, start_time)
    end_dt = start_dt + timedelta(minutes=duration_minutes)
    return end_dt.time()


def format_time_display(time_obj):
    """Formats time for frontend display."""
    if time_obj is None:
        return ""
    if isinstance(time_obj, timedelta):
        total_seconds = int(time_obj.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return time(hours % 24, minutes).strftime("%I:%M %p")
    if isinstance(time_obj, time):
        return time_obj.strftime("%I:%M %p")
    return str(time_obj)
