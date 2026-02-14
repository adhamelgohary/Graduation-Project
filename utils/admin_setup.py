from sqladmin import Admin, ModelView
from db import engine
from models import (
    Users,
    Doctors,
    Patients,
    Admins,
    Departments,
    Specializations,
    Appointments,
    VaccinationRecords,
    NutritionGuides,
    EducationalContent,
    PendingRegistrations,
    InsuranceProviders,
)


class UserAdmin(ModelView, model=Users):
    column_list = [
        Users.user_id,
        Users.username,
        Users.email,
        Users.user_type,
        Users.account_status,
    ]
    can_delete = False
    name = "User"
    name_plural = "Users"
    icon = "fa-solid fa-user"


class DoctorAdmin(ModelView, model=Doctors):
    column_list = [Doctors.user_id, Doctors.verification_status]
    name = "Doctor"
    name_plural = "Doctors"
    icon = "fa-solid fa-user-doctor"


class PatientAdmin(ModelView, model=Patients):
    column_list = [Patients.user_id, Patients.date_of_birth, Patients.gender]
    name = "Patient"
    name_plural = "Patients"
    icon = "fa-solid fa-hospital-user"


class AdminAdmin(ModelView, model=Admins):
    column_list = [Admins.user_id, Admins.admin_level]
    name = "Admin"
    name_plural = "Admins"
    icon = "fa-solid fa-user-shield"


class DepartmentAdmin(ModelView, model=Departments):
    column_list = [Departments.department_id, Departments.name]
    name = "Department"
    name_plural = "Departments"
    icon = "fa-solid fa-building-medical"


class SpecializationAdmin(ModelView, model=Specializations):
    column_list = [
        Specializations.specialization_id,
        Specializations.name,
        Specializations.department_id,
    ]
    name = "Specialization"
    name_plural = "Specializations"
    icon = "fa-solid fa-stethoscope"


class AppointmentAdmin(ModelView, model=Appointments):
    column_list = [
        Appointments.appointment_id,
        Appointments.patient_id,
        Appointments.doctor_id,
        Appointments.status,
    ]
    name = "Appointment"
    name_plural = "Appointments"
    icon = "fa-solid fa-calendar-check"


class VaccinationAdmin(ModelView, model=VaccinationRecords):
    column_list = [
        VaccinationRecords.record_id,
        VaccinationRecords.patient_id,
        VaccinationRecords.vaccine_name,
    ]
    name = "Vaccination Record"
    name_plural = "Vaccination Records"
    icon = "fa-solid fa-syringe"


class NutritionAdmin(ModelView, model=NutritionGuides):
    column_list = [
        NutritionGuides.guide_id,
        NutritionGuides.patient_id,
        NutritionGuides.title,
    ]
    name = "Nutrition Guide"
    name_plural = "Nutrition Guides"
    icon = "fa-solid fa-apple-whole"


class EducationAdmin(ModelView, model=EducationalContent):
    column_list = [
        EducationalContent.content_id,
        EducationalContent.title,
        EducationalContent.category,
    ]
    name = "Educational Content"
    name_plural = "Educational Content"
    icon = "fa-solid fa-book-medical"


class PendingRegAdmin(ModelView, model=PendingRegistrations):
    column_list = [
        PendingRegistrations.registration_id,
        PendingRegistrations.username,
        PendingRegistrations.status,
    ]
    name = "Pending Registration"
    name_plural = "Pending Registrations"
    icon = "fa-solid fa-user-clock"


class InsuranceAdmin(ModelView, model=InsuranceProviders):
    column_list = [InsuranceProviders.id, InsuranceProviders.provider_name]
    name = "Insurance Provider"
    name_plural = "Insurance Providers"
    icon = "fa-solid fa-id-card"


def setup_admin(app):
    admin = Admin(app, engine, title="Health Guide DB Admin", base_url="/admin_db")

    # Register all views
    admin.add_view(UserAdmin)
    admin.add_view(DoctorAdmin)
    admin.add_view(PatientAdmin)
    admin.add_view(AdminAdmin)
    admin.add_view(DepartmentAdmin)
    admin.add_view(SpecializationAdmin)
    admin.add_view(AppointmentAdmin)
    admin.add_view(VaccinationAdmin)
    admin.add_view(NutritionAdmin)
    admin.add_view(EducationAdmin)
    admin.add_view(PendingRegAdmin)
    admin.add_view(InsuranceAdmin)

    return admin
