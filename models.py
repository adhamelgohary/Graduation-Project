# models.py
from sqlalchemy import (
    Column,
    Integer,
    String,
    TIMESTAMP,
    Text,
    ForeignKey,
    text,
    Date,
    Time,
    DateTime,
    Numeric,
)
from sqlalchemy.dialects.mysql import ENUM, TINYINT, INTEGER, DECIMAL
from sqlalchemy.orm import relationship
from db import Base


class Users(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, nullable=False)
    username = Column(String(50, "utf8mb4_bin"), nullable=False, unique=True)
    email = Column(String(100, "utf8mb4_bin"), nullable=False, unique=True)
    password = Column(String(255, "utf8mb4_bin"), nullable=False)
    first_name = Column(String(50, "utf8mb4_bin"), nullable=False)
    last_name = Column(String(50, "utf8mb4_bin"), nullable=False)
    user_type = Column(ENUM("patient", "doctor", "admin"), nullable=False)
    phone = Column(String(30, "utf8mb4_bin"))
    country = Column(String(50, "utf8mb4_bin"), server_default=text("'United States'"))
    profile_picture = Column(String(255, "utf8mb4_bin"))
    account_status = Column(
        ENUM("active", "inactive", "suspended", "pending"),
        server_default=text("'active'"),
    )
    created_at = Column(TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
    )

    # --- Relationships ---
    # use uselist=False for 1-to-1 relationships
    doctor_profile = relationship("Doctors", back_populates="user", uselist=False)
    patient_profile = relationship("Patients", back_populates="user", uselist=False)
    admin_profile = relationship("Admins", back_populates="user", uselist=False)

    # --- Business Logic Properties (Old User Class logic) ---
    @property
    def is_active(self):
        return self.account_status == "active"

    @property
    def is_authenticated(self):
        return True

    @property
    def is_doctor(self):
        return self.user_type == "doctor"

    @property
    def is_patient(self):
        return self.user_type == "patient"

    @property
    def is_admin(self):
        return self.user_type == "admin"

    @property
    def is_fully_verified_doctor(self):
        if not self.is_doctor or not self.doctor_profile:
            return False
        return self.doctor_profile.verification_status == "approved"

    @property
    def doctor_needs_info(self):
        if not self.is_doctor or not self.doctor_profile:
            return False
        return self.doctor_profile.verification_status == "pending_info"


class Admins(Base):
    __tablename__ = "admins"
    user_id = Column(
        Integer, ForeignKey("users.user_id"), nullable=False, primary_key=True
    )
    admin_level = Column(ENUM("super", "regular"), server_default=text("'regular'"))

    user = relationship("Users", back_populates="admin_profile")


class Doctors(Base):
    __tablename__ = "doctors"
    user_id = Column(
        Integer, ForeignKey("users.user_id"), nullable=False, primary_key=True
    )
    specialization_id = Column(Integer, nullable=False)
    license_number = Column(String(50, "utf8mb4_bin"))
    license_state = Column(String(50, "utf8mb4_bin"))
    license_expiration = Column(Date)
    npi_number = Column(String(20, "utf8mb4_bin"))
    medical_school = Column(String(100, "utf8mb4_bin"))
    graduation_year = Column(Integer)
    certifications = Column(Text(collation="utf8mb4_bin"))
    accepting_new_patients = Column(TINYINT(1), server_default=text("'1'"))
    biography = Column(Text(collation="utf8mb4_bin"))
    profile_photo_url = Column(String(255, "utf8mb4_bin"))
    clinic_address = Column(Text(collation="utf8mb4_bin"))
    verification_status = Column(
        ENUM("pending", "approved", "rejected", "pending_info"),
        server_default=text("'pending'"),
    )
    approval_date = Column(DateTime)
    updated_at = Column(DateTime, nullable=False)
    department_id = Column(Integer)

    user = relationship("Users", back_populates="doctor_profile")


class Patients(Base):
    __tablename__ = "patients"
    user_id = Column(
        Integer, ForeignKey("users.user_id"), nullable=False, primary_key=True
    )
    date_of_birth = Column(Date, nullable=False)
    gender = Column(
        ENUM("male", "female", "other", "prefer_not_to_say", "unknown"),
        nullable=False,
        server_default=text("'unknown'"),
    )
    blood_type = Column(
        ENUM("A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-", "Unknown"),
        server_default=text("'Unknown'"),
    )
    height_cm = Column(DECIMAL(5, 2))
    weight_kg = Column(DECIMAL(5, 2))
    insurance_provider_id = Column(Integer)
    insurance_policy_number = Column(String(50, "utf8mb4_bin"))
    insurance_group_number = Column(String(50, "utf8mb4_bin"))
    insurance_expiration = Column(Date)
    marital_status = Column(
        ENUM("single", "married", "divorced", "widowed", "separated", "other")
    )
    occupation = Column(String(100, "utf8mb4_bin"))
    updated_at = Column(
        DateTime, server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
    )

    user = relationship("Users", back_populates="patient_profile")


class Allergies(Base):
    __tablename__ = "allergies"
    allergy_id = Column(Integer, nullable=False, primary_key=True)
    allergy_name = Column(String(100, "utf8mb4_bin"), nullable=False)
    allergy_type = Column(
        ENUM("medication", "food", "environmental", "other"), nullable=False
    )
    created_at = Column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )


class AppointmentFollowups(Base):
    __tablename__ = "appointment_followups"
    followup_id = Column(Integer, nullable=False, primary_key=True)
    appointment_id = Column(Integer, nullable=False)
    followup_status = Column(
        ENUM("pending", "contacted", "resolved", "ignored"),
        nullable=False,
        server_default=text("'pending'"),
    )
    notes = Column(Text(collation="utf8mb4_bin"))
    created_at = Column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )
    updated_by = Column(Integer)


class AppointmentTypes(Base):
    __tablename__ = "appointment_types"
    type_id = Column(Integer, nullable=False, primary_key=True)
    type_name = Column(String(100, "utf8mb4_bin"), nullable=False)
    default_duration_minutes = Column(
        Integer, nullable=False, server_default=text("'30'")
    )
    description = Column(Text(collation="utf8mb4_bin"))
    is_active = Column(TINYINT(1), nullable=False, server_default=text("'1'"))
    created_at = Column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )


class Appointments(Base):
    __tablename__ = "appointments"
    appointment_id = Column(Integer, nullable=False, primary_key=True)
    patient_id = Column(Integer, nullable=False)
    doctor_id = Column(Integer, nullable=False)
    appointment_date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    appointment_type_id = Column(Integer)
    status = Column(
        ENUM("scheduled", "completed", "canceled", "no-show", "rescheduled"),
        server_default=text("'scheduled'"),
    )
    reschedule_count = Column(Integer, nullable=False, server_default=text("'0'"))
    reason = Column(Text(collation="utf8mb4_general_ci"))
    notes = Column(Text(collation="utf8mb4_general_ci"))
    check_in_time = Column(DateTime)
    start_treatment_time = Column(DateTime)
    end_treatment_time = Column(DateTime)
    doctor_location_id = Column(
        Integer, comment="FK to doctor_locations.doctor_location_id"
    )
    is_active = Column(TINYINT(1), nullable=False, server_default=text("'1'"))
    created_at = Column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )
    created_by = Column(Integer, nullable=False)
    updated_by = Column(Integer)


class AuditLog(Base):
    __tablename__ = "audit_log"
    log_id = Column(Integer, nullable=False, primary_key=True)
    user_id = Column(Integer)
    action_type = Column(String(50, "utf8mb4_bin"), nullable=False)
    target_table = Column(String(100, "utf8mb4_bin"))
    target_record_id = Column(String(100, "utf8mb4_bin"))
    action_details = Column(Text(collation="utf8mb4_bin"))
    performed_by_id = Column(Integer)
    performed_at = Column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    ip_address = Column(String(45, "utf8mb4_bin"))


class ChatMessages(Base):
    __tablename__ = "chat_messages"
    message_id = Column(Integer, nullable=False, primary_key=True)
    chat_id = Column(Integer, nullable=False)
    sender_type = Column(ENUM("doctor", "patient", "system"), nullable=False)
    sender_id = Column(Integer, nullable=False)
    message_text = Column(Text(collation="utf8mb4_general_ci"), nullable=False)
    has_attachment = Column(TINYINT(1), server_default=text("'0'"))
    sent_at = Column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    read_at = Column(TIMESTAMP)
    is_deleted = Column(TINYINT(1), server_default=text("'0'"))


class Chats(Base):
    __tablename__ = "chats"
    chat_id = Column(Integer, nullable=False, primary_key=True)
    patient_id = Column(Integer, nullable=False)
    doctor_id = Column(Integer, nullable=False)
    start_time = Column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    end_time = Column(TIMESTAMP)
    status = Column(
        ENUM("active", "closed", "pending"), server_default=text("'active'")
    )
    subject = Column(String(255, "utf8mb4_general_ci"))
    created_at = Column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )


class Conditions(Base):
    __tablename__ = "conditions"
    condition_id = Column(Integer, nullable=False, primary_key=True)
    condition_name = Column(String(100, "utf8mb4_bin"), nullable=False)
    description = Column(Text(collation="utf8mb4_bin"))
    icd_code = Column(String(20, "utf8mb4_bin"))
    urgency_level = Column(
        ENUM("low", "medium", "high", "emergency"),
        nullable=False,
        server_default=text("'medium'"),
    )
    condition_type = Column(ENUM("common", "rare", "chronic", "acute"))
    age_relevance = Column(String(100, "utf8mb4_bin"))
    gender_relevance = Column(
        ENUM("all", "male", "female"), server_default=text("'all'")
    )
    specialist_type = Column(String(100, "utf8mb4_bin"))
    self_treatable = Column(TINYINT(1), server_default=text("'0'"))
    typical_duration = Column(String(100, "utf8mb4_bin"))
    educational_content = Column(Text(collation="utf8mb4_bin"))
    overview = Column(Text(collation="utf8mb4_bin"))
    regular_symptoms_text = Column(Text(collation="utf8mb4_bin"))
    emergency_symptoms_text = Column(Text(collation="utf8mb4_bin"))
    risk_factors_text = Column(Text(collation="utf8mb4_bin"))
    treatment_protocols_text = Column(Text(collation="utf8mb4_bin"))
    symptoms_text = Column(Text(collation="utf8mb4_bin"))
    causes_text = Column(Text(collation="utf8mb4_bin"))
    complications_text = Column(Text(collation="utf8mb4_bin"))
    testing_details = Column(Text(collation="utf8mb4_bin"))
    diagnosis_details = Column(Text(collation="utf8mb4_bin"))
    condition_image_filename = Column(String(500, "utf8mb4_bin"))
    condition_video_filename = Column(String(500, "utf8mb4_bin"))
    testing_type_id = Column(Integer)
    diagnosis_type_id = Column(Integer)
    department_id = Column(Integer)
    is_active = Column(TINYINT(1), nullable=False, server_default=text("'1'"))
    created_at = Column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )


class Departments(Base):
    __tablename__ = "departments"
    department_id = Column(Integer, nullable=False, primary_key=True)
    name = Column(String(100, "utf8mb4_bin"), nullable=False)
    description = Column(Text(collation="utf8mb4_bin"))
    image_filename = Column(String(255, "utf8mb4_bin"))
    created_at = Column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at = Column(DateTime)


class Diagnoses(Base):
    __tablename__ = "diagnoses"
    diagnosis_id = Column(Integer, nullable=False, primary_key=True)
    patient_id = Column(Integer, nullable=False)
    doctor_id = Column(Integer)
    diagnosis_date = Column(Date, nullable=False)
    diagnosis_code = Column(String(20, "utf8mb4_bin"))
    diagnosis_name = Column(String(100, "utf8mb4_bin"), nullable=False)
    diagnosis_type = Column(
        ENUM("preliminary", "differential", "final", "working"),
        server_default=text("'final'"),
    )
    description = Column(Text(collation="utf8mb4_bin"))
    treatment_details = Column(Text(collation="utf8mb4_bin"))
    notes = Column(Text(collation="utf8mb4_bin"))
    treatment_plan = Column(Text(collation="utf8mb4_bin"))
    follow_up_required = Column(TINYINT(1), server_default=text("'0'"))
    follow_up_date = Column(Date)
    follow_up_type = Column(String(50, "utf8mb4_bin"))
    severity = Column(
        ENUM("mild", "moderate", "severe", "critical", "unknown"),
        server_default=text("'unknown'"),
    )
    prognosis = Column(Text(collation="utf8mb4_bin"))
    is_chronic = Column(TINYINT(1), server_default=text("'0'"))
    is_resolved = Column(TINYINT(1), server_default=text("'0'"))
    resolved_date = Column(Date)
    created_at = Column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )
    created_by = Column(Integer, nullable=False)
    updated_by = Column(Integer)


class DiagnosisTypes(Base):
    __tablename__ = "diagnosis_types"
    diagnosis_type_id = Column(Integer, nullable=False, primary_key=True)
    name = Column(String(100, "utf8mb4_bin"), nullable=False)
    description = Column(Text(collation="utf8mb4_bin"))
    created_at = Column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class DietPlanFoodItems(Base):
    __tablename__ = "diet_plan_food_items"
    item_id = Column(Integer, nullable=False, primary_key=True)
    meal_id = Column(Integer, nullable=False)
    food_name = Column(String(100, "utf8mb4_general_ci"), nullable=False)
    serving_size = Column(String(50, "utf8mb4_general_ci"), nullable=False)
    calories = Column(Integer)
    protein_grams = Column(DECIMAL(6, 2))
    carbs_grams = Column(DECIMAL(6, 2))
    fat_grams = Column(DECIMAL(6, 2))
    notes = Column(Text(collation="utf8mb4_general_ci"))
    alternatives = Column(Text(collation="utf8mb4_general_ci"))
    created_at = Column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )


class DietPlanMeals(Base):
    __tablename__ = "diet_plan_meals"
    meal_id = Column(Integer, nullable=False, primary_key=True)
    plan_id = Column(Integer, nullable=False)
    meal_name = Column(String(100, "utf8mb4_general_ci"), nullable=False)
    meal_type = Column(
        ENUM("breakfast", "lunch", "dinner", "snack", "other"), nullable=False
    )
    protein_grams = Column(Integer)
    time_of_day = Column(Time)
    description = Column(Text(collation="utf8mb4_general_ci"))
    calories = Column(Integer)
    carbs_grams = Column(Integer)
    fat_grams = Column(Integer)
    fiber_grams = Column(Integer)
    sodium_mg = Column(Integer)
    created_at = Column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )


class DietPlans(Base):
    __tablename__ = "diet_plans"
    plan_id = Column(Integer, nullable=False, primary_key=True)
    plan_name = Column(String(100, "utf8mb4_general_ci"), nullable=False)
    description = Column(Text(collation="utf8mb4_general_ci"))
    plan_type = Column(
        ENUM(
            "standard", "custom", "medical", "weight_loss", "weight_gain", "maintenance"
        ),
        nullable=False,
    )
    calories = Column(Integer)
    protein_grams = Column(Integer)
    carbs_grams = Column(Integer)
    fat_grams = Column(Integer)
    fiber_grams = Column(Integer)
    sodium_mg = Column(Integer)
    is_public = Column(TINYINT(1), server_default=text("'0'"))
    creator_id = Column(Integer)
    target_conditions = Column(Text(collation="utf8mb4_general_ci"))
    created_at = Column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )
    updated_by = Column(Integer)


class DoctorAvailabilityOverrides(Base):
    __tablename__ = "doctor_availability_overrides"
    override_id = Column(Integer, nullable=False, primary_key=True)
    doctor_id = Column(Integer, nullable=False)
    doctor_location_id = Column(Integer)
    override_date = Column(Date, nullable=False)
    start_time = Column(Time)
    end_time = Column(Time)
    is_unavailable = Column(TINYINT(1), nullable=False, server_default=text("'1'"))
    reason = Column(String(255, "utf8mb4_general_ci"))
    created_at = Column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )


class DoctorDocuments(Base):
    __tablename__ = "doctor_documents"
    document_id = Column(Integer, nullable=False, primary_key=True)
    doctor_id = Column(Integer, nullable=False)
    document_type = Column(
        ENUM("license", "certification", "identity", "education", "other"),
        nullable=False,
    )
    file_name = Column(String(255, "utf8mb4_bin"), nullable=False)
    file_path = Column(String(255, "utf8mb4_bin"), nullable=False)
    file_size = Column(Integer, nullable=False)
    upload_date = Column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class DoctorLocationAvailability(Base):
    __tablename__ = "doctor_location_availability"
    location_availability_id = Column(Integer, nullable=False, primary_key=True)
    doctor_location_id = Column(Integer, nullable=False)
    day_of_week = Column(TINYINT, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    created_at = Column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )


class DoctorLocationDailyCaps(Base):
    __tablename__ = "doctor_location_daily_caps"
    cap_id = Column(Integer, nullable=False, primary_key=True)
    doctor_id = Column(Integer, nullable=False)
    doctor_location_id = Column(Integer, nullable=False)
    day_of_week = Column(TINYINT, nullable=False)
    max_appointments = Column(INTEGER, nullable=False)
    created_at = Column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )


class DoctorLocations(Base):
    __tablename__ = "doctor_locations"
    doctor_location_id = Column(Integer, nullable=False, primary_key=True)
    doctor_id = Column(Integer, nullable=False)
    location_name = Column(String(255, "utf8mb4_bin"), nullable=False)
    address = Column(Text(collation="utf8mb4_bin"), nullable=False)
    city = Column(String(100, "utf8mb4_bin"))
    state = Column(String(50, "utf8mb4_bin"))
    zip_code = Column(String(20, "utf8mb4_bin"))
    country = Column(String(50, "utf8mb4_bin"), server_default=text("'United States'"))
    phone_number = Column(String(20, "utf8mb4_bin"))
    is_primary = Column(TINYINT(1), server_default=text("'0'"))
    is_active = Column(TINYINT(1), server_default=text("'1'"))
    notes = Column(Text(collation="utf8mb4_bin"))
    created_at = Column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )
    google_maps_link = Column(String(1024, "utf8mb4_bin"))


class DoctorReviews(Base):
    __tablename__ = "doctor_reviews"
    review_id = Column(Integer, nullable=False, primary_key=True)
    doctor_id = Column(Integer, nullable=False)
    reviewer_id = Column(Integer, nullable=False)
    review_date = Column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    action = Column(
        ENUM("viewed", "approved", "rejected", "info_requested"), nullable=False
    )
    notes = Column(Text(collation="utf8mb4_bin"))


class FoodItemLibrary(Base):
    __tablename__ = "food_item_library"
    food_item_id = Column(Integer, nullable=False, primary_key=True)
    item_name = Column(String(255, "utf8mb4_general_ci"), nullable=False)
    serving_size = Column(String(100, "utf8mb4_general_ci"), nullable=False)
    calories = Column(Integer)
    protein_grams = Column(DECIMAL(10, 2))
    carbs_grams = Column(DECIMAL(10, 2))
    fat_grams = Column(DECIMAL(10, 2))
    fiber_grams = Column(DECIMAL(10, 2))
    sodium_mg = Column(Integer)
    notes = Column(Text(collation="utf8mb4_general_ci"))
    is_active = Column(TINYINT(1), server_default=text("'1'"))
    creator_id = Column(Integer)
    created_at = Column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )


class InsuranceProviders(Base):
    __tablename__ = "insurance_providers"
    id = Column(Integer, nullable=False, primary_key=True)
    provider_name = Column(String(255, "utf8mb4_bin"), nullable=False)
    description = Column(Text(collation="utf8mb4_bin"))
    is_active = Column(TINYINT(1), server_default=text("'1'"))
    created_at = Column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )


class MessageAttachments(Base):
    __tablename__ = "message_attachments"
    attachment_id = Column(Integer, nullable=False, primary_key=True)
    message_id = Column(Integer, nullable=False)
    file_name = Column(String(255, "utf8mb4_general_ci"), nullable=False)
    file_type = Column(String(100, "utf8mb4_general_ci"), nullable=False)
    file_size = Column(Integer, nullable=False)
    file_path = Column(String(255, "utf8mb4_general_ci"), nullable=False)
    uploaded_at = Column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class PatientAllergies(Base):
    __tablename__ = "patient_allergies"
    patient_id = Column(Integer, nullable=False, primary_key=True)
    allergy_id = Column(Integer, nullable=False, primary_key=True)
    severity = Column(
        ENUM("mild", "moderate", "severe", "unknown"), server_default=text("'unknown'")
    )
    reaction_description = Column(Text(collation="utf8mb4_bin"))
    diagnosed_date = Column(Date)
    notes = Column(Text(collation="utf8mb4_bin"))
    created_at = Column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )


class PatientMedicalReports(Base):
    __tablename__ = "patient_medical_reports"
    report_id = Column(Integer, nullable=False, primary_key=True)
    patient_id = Column(Integer, nullable=False)
    document_name = Column(String(255, "utf8mb4_general_ci"), nullable=False)
    document_type = Column(String(100, "utf8mb4_general_ci"), nullable=False)
    report_format = Column(
        String(10, "utf8mb4_general_ci"), server_default=text("'json'")
    )
    file_path = Column(String(512, "utf8mb4_general_ci"), nullable=False)
    submission_date = Column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    notes = Column(Text(collation="utf8mb4_general_ci"))


class PatientSymptoms(Base):
    __tablename__ = "patient_symptoms"
    patient_symptom_id = Column(Integer, nullable=False, primary_key=True)
    patient_id = Column(Integer, nullable=False)
    symptom_id = Column(Integer, nullable=False)
    reported_date = Column(Date, nullable=False)
    onset_date = Column(Date)
    severity = Column(String(50, "utf8mb4_bin"))
    duration = Column(String(50, "utf8mb4_bin"))
    frequency = Column(ENUM("constant", "intermittent", "occasional", "rare"))
    triggers = Column(Text(collation="utf8mb4_bin"))
    alleviating_factors = Column(Text(collation="utf8mb4_bin"))
    worsening_factors = Column(Text(collation="utf8mb4_bin"))
    notes = Column(Text(collation="utf8mb4_bin"))
    reported_by = Column(Integer, nullable=False)
    created_at = Column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )


class PatientVaccinations(Base):
    __tablename__ = "patient_vaccinations"
    patient_vaccination_id = Column(Integer, nullable=False, primary_key=True)
    patient_id = Column(Integer, nullable=False)
    vaccine_id = Column(Integer, nullable=False)
    administration_date = Column(Date, nullable=False)
    dose_number = Column(String(20, "utf8mb4_general_ci"))
    lot_number = Column(String(50, "utf8mb4_general_ci"))
    administered_by_id = Column(Integer)
    notes = Column(Text(collation="utf8mb4_general_ci"))
    created_at = Column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )


class PendingRegistrations(Base):
    __tablename__ = "pending_registrations"
    id = Column(Integer, nullable=False, primary_key=True)
    email = Column(String(100, "utf8mb4_bin"), nullable=False)
    first_name = Column(String(50, "utf8mb4_bin"), nullable=False)
    last_name = Column(String(50, "utf8mb4_bin"), nullable=False)
    username = Column(String(50, "utf8mb4_bin"), nullable=False)
    phone = Column(String(20, "utf8mb4_bin"))
    country = Column(String(50, "utf8mb4_bin"))
    user_type_requested = Column(ENUM("doctor"), nullable=False)
    specialization_id = Column(Integer)
    license_number = Column(String(50, "utf8mb4_bin"))
    license_state = Column(String(50, "utf8mb4_bin"))
    license_expiration = Column(Date)
    date_submitted = Column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    status = Column(
        ENUM("pending", "approved_user_created", "rejected"),
        nullable=False,
        server_default=text("'pending'"),
    )
    user_id = Column(Integer)
    processed_by = Column(Integer)
    date_processed = Column(DateTime)
    notes = Column(Text(collation="utf8mb4_bin"))
    department_id = Column(Integer)
    password = Column(String(255, "utf8mb4_bin"))


class Specializations(Base):
    __tablename__ = "specializations"
    specialization_id = Column(Integer, nullable=False, primary_key=True)
    name = Column(String(100, "utf8mb4_bin"), nullable=False)
    description = Column(Text(collation="utf8mb4_bin"))
    department_id = Column(Integer)
    created_at = Column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )


class Symptoms(Base):
    __tablename__ = "symptoms"
    symptom_id = Column(Integer, nullable=False, primary_key=True)
    symptom_name = Column(String(100, "utf8mb4_bin"), nullable=False)
    description = Column(Text(collation="utf8mb4_bin"))
    body_area = Column(String(50, "utf8mb4_bin"))
    icd_code = Column(String(20, "utf8mb4_bin"))
    common_causes = Column(Text(collation="utf8mb4_bin"))
    severity_scale = Column(String(255, "utf8mb4_bin"))
    symptom_category = Column(ENUM("common", "rare", "emergency", "chronic"))
    age_relevance = Column(String(100, "utf8mb4_bin"))
    gender_relevance = Column(
        ENUM("all", "male", "female"), server_default=text("'all'")
    )
    question_text = Column(Text(collation="utf8mb4_bin"))
    follow_up_questions = Column(Text(collation="utf8mb4_bin"))
    created_at = Column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )


class TestingTypes(Base):
    __tablename__ = "testing_types"
    testing_type_id = Column(Integer, nullable=False, primary_key=True)
    name = Column(String(100, "utf8mb4_bin"), nullable=False)
    description = Column(Text(collation="utf8mb4_bin"))
    created_at = Column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class Vaccines(Base):
    __tablename__ = "vaccines"
    vaccine_id = Column(Integer, nullable=False, primary_key=True)
    category_id = Column(Integer, nullable=False)
    vaccine_name = Column(String(255, "utf8mb4_bin"), nullable=False)
    abbreviation = Column(String(50, "utf8mb4_bin"))
    diseases_prevented = Column(Text(collation="utf8mb4_bin"), nullable=False)
    recommended_for = Column(Text(collation="utf8mb4_bin"))
    benefits = Column(Text(collation="utf8mb4_bin"))
    timing_schedule = Column(Text(collation="utf8mb4_bin"))
    number_of_doses = Column(String(50, "utf8mb4_bin"))
    booster_information = Column(Text(collation="utf8mb4_bin"))
    vaccine_type = Column(String(100, "utf8mb4_bin"))
    administration_route = Column(String(100, "utf8mb4_bin"))
    common_side_effects = Column(Text(collation="utf8mb4_bin"))
    contraindications_precautions = Column(Text(collation="utf8mb4_bin"))
    storage_requirements = Column(Text(collation="utf8mb4_bin"))
    manufacturer = Column(String(255, "utf8mb4_bin"))
    notes = Column(Text(collation="utf8mb4_bin"))
    created_at = Column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )
    is_active = Column(TINYINT(1), nullable=False, server_default=text("'1'"))


class VaccineCategories(Base):
    __tablename__ = "vaccine_categories"
    category_id = Column(Integer, nullable=False, primary_key=True)
    category_name = Column(String(100, "utf8mb4_bin"), nullable=False)
    description = Column(Text(collation="utf8mb4_bin"))
    target_group = Column(String(100, "utf8mb4_bin"))
    image_filename = Column(String(255, "utf8mb4_bin"))
    is_active = Column(TINYINT(1), nullable=False, server_default=text("'1'"))
    created_at = Column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )
