import mysql.connector
from faker import Faker
import random
from datetime import datetime, timedelta
# DO NOT use hashlib for real passwords. Use bcrypt or Argon2.
# import hashlib # We will insert plain text passwords for this script ONLY.
import sys
import os

# --- Configuration ---
# !! IMPORTANT: Replace with your actual database credentials !!
DB_CONFIG = {
    'host': 'localhost',
    'user': 'your_db_user',
    'password': 'your_db_password',
    'database': 'your_database_name'
}
NUM_DOCTORS = 20
NUM_PATIENTS = 20
STARTING_USER_ID = 1
# --- End Configuration ---

# --- Database Connection (Import from db.py Recommended) ---
try:
    # Assumes db.py is in the parent directory or accessible via PYTHONPATH
    from db import get_db_connection
    print("Successfully imported get_db_connection from db.py")
except ImportError:
    print("Warning: Could not import get_db_connection from db.py.")
    print("Using direct DB_CONFIG connection instead.")
    # Fallback to direct connection if import fails
    def get_db_connection():
        """Establishes a database connection using configuration."""
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            return conn
        except mysql.connector.Error as err:
            print(f"Error connecting to database using DB_CONFIG: {err}")
            sys.exit(1) # Exit if connection fails
# --- End Database Connection ---

fake = Faker()

def get_existing_ids(conn, table_name, id_column_name):
    """Fetches a list of existing IDs from a given table."""
    ids = []
    cursor = None
    try:
        cursor = conn.cursor()
        query = f"SELECT {id_column_name} FROM {table_name}"
        cursor.execute(query)
        results = cursor.fetchall()
        ids = [row[0] for row in results]
    except mysql.connector.Error as err:
        print(f"Error fetching IDs from {table_name}: {err}")
    finally:
        if cursor:
            cursor.close()
    if not ids:
        print(f"Warning: No IDs found in table '{table_name}'.")
    return ids

def ensure_insurance_providers(conn, providers_to_ensure):
    """Checks for specific providers and inserts if missing. Returns their IDs."""
    provider_ids = {}
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        placeholders = ','.join(['%s'] * len(providers_to_ensure))
        query_select = f"SELECT id, provider_name FROM insurance_providers WHERE provider_name IN ({placeholders})"
        cursor.execute(query_select, tuple(providers_to_ensure))
        existing = {row['provider_name']: row['id'] for row in cursor.fetchall()}
        provider_ids.update(existing)

        missing_providers = [p for p in providers_to_ensure if p not in existing]

        if missing_providers:
            print(f"Inserting missing insurance providers: {missing_providers}")
            sql_insert = "INSERT INTO insurance_providers (provider_name, is_active) VALUES (%s, %s)"
            insert_data = [(name, True) for name in missing_providers]
            cursor.executemany(sql_insert, insert_data)
            conn.commit() # Commit after inserting providers

            cursor.execute(query_select, tuple(missing_providers))
            newly_inserted = {row['provider_name']: row['id'] for row in cursor.fetchall()}
            provider_ids.update(newly_inserted)

    except mysql.connector.Error as err:
        print(f"Error ensuring insurance providers: {err}")
        conn.rollback()
    finally:
        if cursor:
            cursor.close()
    return provider_ids


def insert_users():
    """
    Inserts sample users and UPDATES the doctors/patients records
    created by the database trigger.
    """
    conn = get_db_connection()
    if not conn:
        print("Failed to establish database connection. Exiting.")
        return

    cursor = conn.cursor()
    user_id_counter = STARTING_USER_ID
    inserted_users = 0
    updated_doctors = 0
    updated_patients = 0

    try:
        print("Fetching existing Department, Specialization, and Insurance Provider IDs...")
        department_ids = get_existing_ids(conn, 'departments', 'department_id')
        specialization_ids = get_existing_ids(conn, 'specializations', 'specialization_id')
        sample_providers = ["BlueCross", "Aetna", "Cigna", "UnitedHealthcare", "Medicare", "Medicaid", "SampleCare"]
        insurance_provider_id_map = ensure_insurance_providers(conn, sample_providers)
        insurance_provider_ids = list(insurance_provider_id_map.values()) + [None]

        if not department_ids:
            print("Error: Cannot proceed without Department IDs for doctors.")
            return
        if not specialization_ids:
            print("Error: Cannot proceed without Specialization IDs for doctors.")
            return
        if not insurance_provider_id_map:
             print("Warning: Could not fetch or insert Insurance Provider IDs.")


        # --- SQL Statements ---
        # INSERT for users remains the same
        sql_insert_user = """
            INSERT INTO users
            (user_id, username, email, password, first_name, last_name, user_type,
             phone, country, account_status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        # *** CHANGED: UPDATE statement for doctors ***
        sql_update_doctor = """
            UPDATE doctors
            SET specialization_id = %s,
                department_id = %s,
                license_number = %s,
                license_state = %s,
                license_expiration = %s,
                npi_number = %s,
                medical_school = %s,
                graduation_year = %s,
                accepting_new_patients = %s,
                clinic_address = %s,
                verification_status = %s,
                approval_date = %s
                -- Add other columns from doctors table to update if needed
            WHERE user_id = %s
        """

        # *** CHANGED: UPDATE statement for patients ***
        sql_update_patient = """
            UPDATE patients
            SET date_of_birth = %s,
                gender = %s,
                blood_type = %s,
                insurance_provider_id = %s,
                insurance_policy_number = %s,
                insurance_group_number = %s,
                marital_status = %s,
                occupation = %s
                -- Add other columns from patients table to update if needed
            WHERE user_id = %s
        """

        # --- Insert Doctors ---
        print(f"\n--- Inserting {NUM_DOCTORS} Doctors ---")
        for i in range(NUM_DOCTORS):
            first_name = fake.first_name()
            last_name = fake.last_name()
            username = f"{first_name[0].lower()}{last_name.lower()}{random.randint(1,99)}"
            email = f"{username}@healthcenter.doc"
            password = f"Pass_{last_name}!" # Example INSECURE plain text password
            phone = fake.phone_number()
            country = random.choice(['United States', 'Canada', 'United Kingdom'])
            account_status = 'active'
            user_type = 'doctor' # This will trigger the DB trigger
            now = datetime.now()

            user_data = (
                user_id_counter, username, email, password, first_name, last_name, user_type,
                phone, country, account_status, now, now
            )

            try:
                # Step 1: Insert the user (trigger runs automatically after this)
                cursor.execute(sql_insert_user, user_data)
                print(f"  Inserted user: {user_id_counter} - Dr. {first_name} {last_name} ({username})")
                inserted_users += 1 # Count user insertion here

                # Step 2: Prepare data for UPDATE
                spec_id = random.choice(specialization_ids)
                dept_id = random.choice(department_ids)
                license_num = f"DOC-{random.randint(10000, 99999)}"
                license_state = fake.state_abbr()
                license_exp = fake.future_date(end_date="+5y")
                npi_num = str(random.randint(1000000000, 1999999999))
                med_school = fake.company() + " Medical School"
                grad_year = fake.random_int(min=datetime.now().year - 40, max=datetime.now().year - 4)
                accepting = random.choice([True, False])
                clinic_addr = fake.address().replace('\n', ', ')
                verif_status = 'approved' # Override trigger's default 'pending'
                approval_dt = fake.past_datetime(start_date="-3y")

                # Data tuple for the UPDATE statement (user_id is last for WHERE clause)
                doctor_update_data = (
                    spec_id, dept_id, license_num, license_state,
                    license_exp, npi_num, med_school, grad_year,
                    accepting, clinic_addr, verif_status, approval_dt,
                    user_id_counter # WHERE user_id = ?
                )

                # Step 3: Execute the UPDATE for the doctors table
                cursor.execute(sql_update_doctor, doctor_update_data)
                print(f"    -> Updated doctor record for user {user_id_counter}")
                updated_doctors += 1 # Count doctor update

                user_id_counter += 1 # Increment user ID for the next user

            except mysql.connector.Error as user_err:
                print(f"  ERROR processing user {username} ({email}): {user_err}")
                if user_err.errno == 1062: # Duplicate user entry
                     print("    -> Skipping this user due to duplicate username or email.")
                     # Need to increment counter even if skipped to avoid ID reuse attempts
                     user_id_counter += 1
                     continue # Skip to next iteration
                else:
                     # For other errors during user insert or doctor update, raise them
                     # to trigger the main rollback
                     conn.rollback() # Rollback current transaction state
                     print("Rolled back transaction due to error.")
                     raise user_err # Re-raise to be caught by outer handler


        # --- Insert Patients ---
        print(f"\n--- Inserting {NUM_PATIENTS} Patients ---")
        for i in range(NUM_PATIENTS):
            first_name = fake.first_name()
            last_name = fake.last_name()
            username = f"{first_name.lower()}.{last_name.lower()}{random.randint(1,999)}"
            email = f"{username}@email.com"
            password = f"{last_name}{random.randint(10,99)}?" # Example INSECURE plain text password
            phone = fake.phone_number()
            country = random.choice(['United States', 'Canada', 'United Kingdom', 'Mexico'])
            account_status = 'active'
            user_type = 'patient' # This will trigger the DB trigger
            now = datetime.now()

            user_data = (
                user_id_counter, username, email, password, first_name, last_name, user_type,
                phone, country, account_status, now, now
            )

            try:
                # Step 1: Insert the user (trigger runs automatically after this)
                cursor.execute(sql_insert_user, user_data)
                print(f"  Inserted user: {user_id_counter} - {first_name} {last_name} ({username})")
                inserted_users += 1 # Count user insertion here

                # Step 2: Prepare data for UPDATE
                dob = fake.date_of_birth(minimum_age=0, maximum_age=90)
                gender = random.choice(['male', 'female', 'other', 'prefer_not_to_say'])
                blood_type = random.choice(['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-', 'Unknown'])
                provider_id = random.choice(insurance_provider_ids)
                policy_number = f"{random.choice(['BS', 'AE', 'CI', 'UH', 'MC', 'MD', 'SC'])}{random.randint(10000000, 99999999)}" if provider_id else None
                group_number = f"GRP{random.randint(1000, 9999)}" if provider_id else None
                marital = random.choice(['single', 'married', 'divorced', 'widowed', 'other', None])
                occupation = fake.job() if random.random() > 0.1 else None

                # Data tuple for the UPDATE statement (user_id is last for WHERE clause)
                patient_update_data = (
                    dob, gender, blood_type, provider_id,
                    policy_number, group_number, marital, occupation,
                    user_id_counter # WHERE user_id = ?
                )

                # Step 3: Execute the UPDATE for the patients table
                cursor.execute(sql_update_patient, patient_update_data)
                print(f"    -> Updated patient record for user {user_id_counter}")
                updated_patients += 1 # Count patient update

                user_id_counter += 1 # Increment user ID for the next user

            except mysql.connector.Error as user_err:
                 print(f"  ERROR processing user {username} ({email}): {user_err}")
                 if user_err.errno == 1062: # Duplicate user entry
                     print("    -> Skipping this user due to duplicate username or email.")
                     user_id_counter += 1
                     continue
                 else:
                     conn.rollback() # Rollback current transaction state
                     print("Rolled back transaction due to error.")
                     raise user_err # Re-raise

        # --- Commit changes ---
        conn.commit()
        print("\n--- Success! ---")
        print(f"Inserted {inserted_users} total users.")
        print(f"Updated {updated_doctors} doctor records.")
        print(f"Updated {updated_patients} patient records.")
        print(f"Next available user_id would be {user_id_counter}")

    except mysql.connector.Error as err:
        # This catches errors not handled within the loops (like connection issues)
        # or errors re-raised from within the loops
        print(f"\n--- Database Error Occurred During Operation ---")
        print(f"Error: {err}")
        print("Attempting to rollback changes...")
        try:
            if conn.is_connected(): # Check before rollback
                conn.rollback()
                print("Rollback successful.")
            else:
                print("Connection lost, cannot rollback.")
        except Exception as roll_err:
            print(f"Rollback failed: {roll_err}")
    except Exception as e:
        print(f"\n--- An Unexpected Error Occurred ---")
        print(f"Error: {e}")
        print("Attempting to rollback changes...")
        try:
            if conn.is_connected():
                conn.rollback()
                print("Rollback successful.")
            else:
                 print("Connection lost, cannot rollback.")
        except Exception as roll_err:
            print(f"Rollback failed: {roll_err}")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
            # print("Database connection closed.")

# --- Main execution ---
if __name__ == "__main__":
    print("Starting sample user insertion script (UPDATE mode)...")
    insert_users()
    print("Script finished.")