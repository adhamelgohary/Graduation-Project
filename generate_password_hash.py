# generate_user_hash.py
from werkzeug.security import generate_password_hash

# The password you want to set
new_password_plain = "Adham@patient" # Case-sensitive, ensure it matches exactly

# The username or email of the user whose password you want to update
# You'll use this in your WHERE clause
user_identifier_for_sql = "Adham" # Or the user's email, e.g., 'adham@example.com'

# Generate the hash
hashed_password = generate_password_hash(new_password_plain)

print(f"Plain password: {new_password_plain}")
print(f"Hashed password: {hashed_password}")
print("\n--- SQL UPDATE Statement ---")
print(f"UPDATE users SET password = '{hashed_password}' WHERE username = '{user_identifier_for_sql}';")
print("# OR, if identifying by email:")
print(f"# UPDATE users SET password = '{hashed_password}' WHERE email = 'user_email@example.com';")
print("\nIMPORTANT: Always back up your database before running manual UPDATE statements.")