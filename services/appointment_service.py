from datetime import datetime, date, timedelta
import logging
from utils.db_context import db_connection
from utils.media_utils import get_verfied_image_path
from utils.date_utils import (
    python_dow_to_db_dow,
    generate_time_slots,
    calculate_end_time,
    format_time_display,
    db_dow_to_python_dow,
)

logger = logging.getLogger(__name__)


class AppointmentService:

    @staticmethod
    def get_doctor_scheduling_details(doctor_id: int):
        """Fetches doctor details specifically for the scheduling page header."""
        query = """
            SELECT u.user_id, u.first_name, u.last_name, 
                   doc.profile_photo_url,
                   s.name as specialization_name,
                   COALESCE(dept_direct.name, dept_spec.name) as department_name
            FROM users u
            JOIN doctors doc ON u.user_id = doc.user_id
            LEFT JOIN specializations s ON doc.specialization_id = s.specialization_id
            LEFT JOIN departments dept_direct ON doc.department_id = dept_direct.department_id
            LEFT JOIN departments dept_spec ON s.department_id = dept_spec.department_id
            WHERE u.user_id = %s AND u.user_type = 'doctor'
        """
        with db_connection() as cursor:
            cursor.execute(query, (doctor_id,))
            doctor = cursor.fetchone()

        if doctor:
            doctor["profile_image_path"] = get_verfied_image_path(
                doctor["profile_photo_url"], "images/profile_pics/default_avatar.png"
            )
        return doctor

    @staticmethod
    def get_scheduling_setup(doctor_id: int):
        """Fetches locations and working days for a doctor."""
        query = """
            SELECT
                dl.doctor_location_id, dl.location_name, dl.address,
                GROUP_CONCAT(DISTINCT dla.day_of_week ORDER BY dla.day_of_week ASC SEPARATOR ',') as working_days_db_str
            FROM doctor_locations dl
            LEFT JOIN doctor_location_availability dla ON dl.doctor_location_id = dla.doctor_location_id
            WHERE dl.doctor_id = %s AND dl.is_active = TRUE
            GROUP BY dl.doctor_location_id, dl.location_name, dl.address
            ORDER BY dl.is_primary DESC, dl.location_name ASC
        """

        setup = {"locations": [], "all_unique_working_days_db": []}

        with db_connection() as cursor:
            cursor.execute(query, (doctor_id,))
            results = cursor.fetchall()

        unique_days = set()

        for row in results:
            # Parse the comma-separated days
            days_db = []
            if row["working_days_db_str"]:
                try:
                    days_db = [
                        int(d.strip())
                        for d in row["working_days_db_str"].split(",")
                        if d.strip().isdigit()
                    ]
                except ValueError:
                    pass

            if days_db:
                unique_days.update(days_db)
                row["working_days_db"] = days_db
                setup["locations"].append(row)

        setup["all_unique_working_days_db"] = sorted(list(unique_days))
        return setup

    @staticmethod
    def get_available_slots(doctor_id, target_date_str, location_id, slot_interval=30):
        """
        Core logic for finding free slots.
        Considers: Working hours, Existing appointments, Overrides, Daily Caps.
        """
        try:
            target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
            if target_date < date.today():
                return {"error": "Cannot fetch for past dates", "slots": []}
        except ValueError:
            return {"error": "Invalid date format", "slots": []}

        db_dow = python_dow_to_db_dow(target_date.weekday())

        with db_connection() as cursor:
            # 1. Get Base Availability (Working Hours)
            cursor.execute(
                """
                SELECT start_time, end_time FROM doctor_location_availability
                WHERE doctor_location_id = %s AND day_of_week = %s
            """,
                (location_id, db_dow),
            )
            avail_periods = cursor.fetchall()

            if not avail_periods:
                return {"slots": [], "count": 0}

            # Generate all possible slots from working hours
            all_slots = set()
            for period in avail_periods:
                slots = generate_time_slots(
                    period["start_time"], period["end_time"], slot_interval
                )
                all_slots.update(slots)

            if not all_slots:
                return {"slots": [], "count": 0}

            # 2. Fetch Existing Appointments (Conflicts)
            cursor.execute(
                """
                SELECT start_time, end_time FROM appointments
                WHERE doctor_id = %s AND appointment_date = %s AND doctor_location_id = %s
                AND status NOT IN ('canceled', 'rescheduled', 'no-show')
            """,
                (doctor_id, target_date_str, location_id),
            )
            booked = cursor.fetchall()

            # 3. Fetch Overrides (Doctor Time Off)
            cursor.execute(
                """
                SELECT start_time, end_time, is_unavailable FROM doctor_availability_overrides
                WHERE doctor_id = %s AND override_date = %s
                AND (doctor_location_id = %s OR doctor_location_id IS NULL)
            """,
                (doctor_id, target_date_str, location_id),
            )
            overrides = cursor.fetchall()

            # 4. Check Daily Cap
            cursor.execute(
                """
                SELECT max_appointments FROM doctor_location_daily_caps
                WHERE doctor_id = %s AND doctor_location_id = %s AND day_of_week = %s
            """,
                (doctor_id, location_id, db_dow),
            )
            cap_row = cursor.fetchone()

            if cap_row:
                current_count = len(
                    booked
                )  # Approximate check (better to use COUNT query if strict)
                if current_count >= cap_row["max_appointments"]:
                    return {"slots": [], "count": 0, "message": "Daily cap reached"}

        # --- Filtering Logic ---

        # Apply Overrides
        for o in overrides:
            if o["is_unavailable"]:
                # If total block (no times), clear all
                if not o["start_time"] and not o["end_time"]:
                    all_slots.clear()
                    break
                # Remove specific range
                o_start = (
                    (datetime.min + o["start_time"]).time()
                    if isinstance(o["start_time"], timedelta)
                    else o["start_time"]
                )
                o_end = (
                    (datetime.min + o["end_time"]).time()
                    if isinstance(o["end_time"], timedelta)
                    else o["end_time"]
                )

                all_slots = {
                    s
                    for s in all_slots
                    if not (
                        s >= o_start
                        and (
                            datetime.combine(date.min, s)
                            + timedelta(minutes=slot_interval)
                        ).time()
                        <= o_end
                    )
                }

        # Remove Booked Slots
        for b in booked:
            b_start = (
                (datetime.min + b["start_time"]).time()
                if isinstance(b["start_time"], timedelta)
                else b["start_time"]
            )
            b_end = (
                (datetime.min + b["end_time"]).time()
                if isinstance(b["end_time"], timedelta)
                else b["end_time"]
            )

            # Remove any slot that overlaps with a booking
            temp_slots = set()
            for s in all_slots:
                s_end_dt = datetime.combine(date.min, s) + timedelta(
                    minutes=slot_interval
                )
                # Overlap logic: SlotStart < BookEnd AND SlotEnd > BookStart
                if s < b_end and s_end_dt.time() > b_start:
                    pass  # It overlaps, so don't add to temp
                else:
                    temp_slots.add(s)
            all_slots = temp_slots

        sorted_slots = sorted(list(all_slots))
        formatted_slots = [s.strftime("%H:%M") for s in sorted_slots]

        return {"slots": formatted_slots, "count": len(formatted_slots)}

    @staticmethod
    def create_appointment(data: dict, user_id: int):
        """
        Inserts appointment. Assumes validation (availability check) is done by the caller/router
        OR we can re-verify here for safety.
        """
        # Calculate End Time
        end_time_obj = calculate_end_time(
            data["appointment_time"], data["duration_minutes"]
        )

        # Insert
        query = """
            INSERT INTO appointments (
                patient_id, doctor_id, appointment_date, start_time, end_time,
                appointment_type_id, status, reason, doctor_location_id, 
                created_by, updated_by, reschedule_count
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'scheduled', %s, %s, %s, %s, %s)
        """
        params = (
            user_id,
            data["doctor_id"],
            data["appointment_date"],
            data["appointment_time"],
            end_time_obj,
            data["appointment_type_id"],
            data["reason"],
            data["location_id"],
            user_id,
            user_id,
            0,
        )

        with db_connection(commit=True) as cursor:
            cursor.execute(query, params)
            new_id = cursor.lastrowid

            # Optional: Update patient phone if provided
            if data.get("patient_phone"):
                cursor.execute(
                    "UPDATE users SET phone = %s WHERE user_id = %s",
                    (data["patient_phone"], user_id),
                )

        return new_id

    @staticmethod
    def get_appointment_details(appointment_id: int, user_id: int, user_type: str):
        query = """
            SELECT
                a.appointment_id, a.appointment_date, a.start_time, a.end_time,
                apt.type_name as appointment_type_name, 
                a.status, a.reason, a.notes, a.doctor_id, a.patient_id,
                pat_user.first_name as patient_first_name, pat_user.last_name as patient_last_name,
                doc_user.first_name as doctor_first_name, doc_user.last_name as doctor_last_name,
                doc_details.profile_photo_url,
                dl.location_name, dl.address as location_address
            FROM appointments a
            LEFT JOIN appointment_types apt ON a.appointment_type_id = apt.type_id
            JOIN users pat_user ON a.patient_id = pat_user.user_id
            JOIN users doc_user ON a.doctor_id = doc_user.user_id
            JOIN doctors doc_details ON a.doctor_id = doc_details.user_id
            LEFT JOIN doctor_locations dl ON a.doctor_location_id = dl.doctor_location_id
            WHERE a.appointment_id = %s
        """

        # Security check: Append filter based on user role
        params = [appointment_id]
        if user_type == "patient":
            query += " AND a.patient_id = %s"
            params.append(user_id)
        elif user_type == "doctor":
            query += " AND a.doctor_id = %s"
            params.append(user_id)

        with db_connection() as cursor:
            cursor.execute(query, tuple(params))
            appt = cursor.fetchone()

        if appt:
            # Format for display
            appt["display_date"] = appt["appointment_date"].strftime("%A, %B %d, %Y")
            appt["display_start_time"] = format_time_display(appt["start_time"])
            appt["doctor_image_path"] = get_verfied_image_path(
                appt["profile_photo_url"], "images/default_doctor.png"
            )

        return appt

    @staticmethod
    def get_user_appointments(user_id: int, user_type: str):
        base_query = """
            SELECT
                a.appointment_id, a.appointment_date, a.start_time, a.status,
                apt.type_name, 
                doc_user.first_name as doc_first, doc_user.last_name as doc_last,
                pat_user.first_name as pat_first, pat_user.last_name as pat_last
            FROM appointments a
            LEFT JOIN appointment_types apt ON a.appointment_type_id = apt.type_id
            JOIN users doc_user ON a.doctor_id = doc_user.user_id
            JOIN users pat_user ON a.patient_id = pat_user.user_id
        """

        if user_type == "patient":
            base_query += " WHERE a.patient_id = %s"
        elif user_type == "doctor":
            base_query += " WHERE a.doctor_id = %s"
        else:
            return []  # Admin logic not implemented here

        base_query += " ORDER BY a.appointment_date DESC, a.start_time DESC"

        with db_connection() as cursor:
            cursor.execute(base_query, (user_id,))
            results = cursor.fetchall()

        # Post-processing
        for r in results:
            r["display_time"] = format_time_display(r["start_time"])
            # Determine if upcoming or past
            r["category"] = (
                "upcoming"
                if r["appointment_date"] >= date.today()
                and r["status"] not in ["canceled", "completed"]
                else "past"
            )

        return results

    @staticmethod
    def cancel_appointment(appointment_id: int, user_id: int):
        with db_connection(commit=True) as cursor:
            cursor.execute(
                "UPDATE appointments SET status = 'canceled', updated_by = %s WHERE appointment_id = %s",
                (user_id, appointment_id),
            )

    @staticmethod
    def get_appointment_types():
        with db_connection() as cursor:
            cursor.execute(
                "SELECT type_id, type_name, default_duration_minutes FROM appointment_types WHERE is_active = TRUE"
            )
            return cursor.fetchall()
