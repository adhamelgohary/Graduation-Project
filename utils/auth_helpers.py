# utils/auth_helpers.py (or add to existing utils file)
from flask_login import current_user

def check_patient_authorization(user):
    """Checks if the user is an authenticated patient."""
    if not user or not user.is_authenticated:
        return False
    # Check the user_type attribute exists before comparing
    return getattr(user, 'user_type', None) == 'patient'

def check_doctor_authorization(user):
     """Checks if the user is an authenticated doctor."""
     if not user or not user.is_authenticated: return False
     return getattr(user, 'user_type', None) == 'doctor'

# Add other roles (admin) if needed