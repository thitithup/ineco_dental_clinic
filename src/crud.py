from datetime import datetime, timedelta, date, timezone
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from src.models import User, Patient, Appointment, TreatmentRecord
from src.schemas import PatientCreate, PatientUpdate, AppointmentCreate, TreatmentRecordCreate
from src.auth import get_password_hash


# --- User & Dentist Operations ---
def get_user_by_username(db: Session, username: str) -> Optional[User]:
    """Retrieve user by username."""
    return db.query(User).filter(User.username == username).first()


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    """Retrieve user by ID."""
    return db.query(User).filter(User.id == user_id).first()


def get_dentists(db: Session) -> List[User]:
    """Retrieve all dentist accounts with specialty details."""
    return db.query(User).filter(User.role == "DENTIST").order_by(User.full_name).all()


def create_user(
    db: Session,
    username: str,
    password: str,
    full_name: str,
    role: str,
    specialty: Optional[str] = None
) -> User:
    """Create a new user account with hashed password."""
    hashed = get_password_hash(password)
    user = User(
        username=username,
        password_hash=hashed,
        full_name=full_name,
        role=role,
        specialty=specialty
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# --- Patient Operations ---
def get_patient_by_id(db: Session, patient_id: int) -> Optional[Patient]:
    """Retrieve patient by ID."""
    return db.query(Patient).filter(Patient.id == patient_id).first()


def get_patient_by_phone(db: Session, phone_number: str) -> Optional[Patient]:
    """Retrieve patient by exact phone number."""
    return db.query(Patient).filter(Patient.phone_number == phone_number).first()


def search_patients(
    db: Session,
    query_str: Optional[str] = None,
    skip: int = 0,
    limit: int = 50
) -> List[Patient]:
    """Search patients by name or phone number with partial matching."""
    q = db.query(Patient)
    if query_str and query_str.strip():
        term = f"%{query_str.strip()}%"
        q = q.filter(
            or_(
                Patient.first_name.ilike(term),
                Patient.last_name.ilike(term),
                Patient.phone_number.like(term)
            )
        )
    return q.order_by(Patient.first_name, Patient.last_name).offset(skip).limit(limit).all()


def create_patient(db: Session, patient_data: PatientCreate) -> Patient:
    """Register a new patient."""
    patient = Patient(
        first_name=patient_data.first_name.strip(),
        last_name=patient_data.last_name.strip(),
        phone_number=patient_data.phone_number.strip(),
        date_of_birth=patient_data.date_of_birth,
        medical_conditions=patient_data.medical_conditions,
        drug_allergies=patient_data.drug_allergies
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


def update_patient(db: Session, patient_id: int, patient_update: PatientUpdate) -> Optional[Patient]:
    """Update patient demographic and medical records."""
    patient = get_patient_by_id(db, patient_id)
    if not patient:
        return None

    update_dict = patient_update.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        if value is not None and isinstance(value, str):
            value = value.strip()
        setattr(patient, key, value)

    db.commit()
    db.refresh(patient)
    return patient


# --- Appointment Operations & Anti-Collision Engine ---
def check_dentist_collision(
    db: Session,
    dentist_id: int,
    start_time: datetime,
    duration_minutes: int,
    exclude_appointment_id: Optional[int] = None
) -> bool:
    """
    Check if a dentist has an overlapping appointment.
    Rule: Two intervals [S1, E1] and [S2, E2] overlap if: S1 < E2 and E1 > S2.
    """
    new_start = start_time
    new_end = start_time + timedelta(minutes=duration_minutes)

    # Search window around requested time to ensure high performance
    window_start = new_start - timedelta(hours=12)
    window_end = new_end + timedelta(hours=12)

    query = db.query(Appointment).filter(
        Appointment.dentist_id == dentist_id,
        Appointment.status != "CANCELLED",
        Appointment.appointment_time >= window_start,
        Appointment.appointment_time <= window_end
    )

    if exclude_appointment_id:
        query = query.filter(Appointment.id != exclude_appointment_id)

    candidates = query.all()
    for appt in candidates:
        existing_start = appt.appointment_time
        existing_end = existing_start + timedelta(minutes=appt.duration_minutes)

        # Collision detection interval check
        if new_start < existing_end and new_end > existing_start:
            return True  # Collision detected

    return False


def create_appointment(db: Session, appt_data: AppointmentCreate) -> Appointment:
    """Create a new appointment record."""
    appt = Appointment(
        patient_id=appt_data.patient_id,
        dentist_id=appt_data.dentist_id,
        appointment_time=appt_data.appointment_time,
        duration_minutes=appt_data.duration_minutes,
        treatment_type=appt_data.treatment_type,
        notes=appt_data.notes,
        status="SCHEDULED"
    )
    db.add(appt)
    db.commit()
    db.refresh(appt)
    return appt


def get_appointment_by_id(db: Session, appointment_id: int) -> Optional[Appointment]:
    """Retrieve appointment by ID with joined relationships."""
    return db.query(Appointment).filter(Appointment.id == appointment_id).first()


def get_appointments(
    db: Session,
    dentist_id: Optional[int] = None,
    patient_id: Optional[int] = None,
    target_date: Optional[date] = None
) -> List[Appointment]:
    """Filter appointments by dentist, patient, or date."""
    query = db.query(Appointment)
    if dentist_id:
        query = query.filter(Appointment.dentist_id == dentist_id)
    if patient_id:
        query = query.filter(Appointment.patient_id == patient_id)
    if target_date:
        day_start = datetime.combine(target_date, datetime.min.time())
        day_end = datetime.combine(target_date, datetime.max.time())
        query = query.filter(
            Appointment.appointment_time >= day_start,
            Appointment.appointment_time <= day_end
        )
    return query.order_by(Appointment.appointment_time).all()


def update_appointment_status(db: Session, appointment_id: int, new_status: str) -> Optional[Appointment]:
    """Update appointment status (SCHEDULED, COMPLETED, CANCELLED)."""
    appt = get_appointment_by_id(db, appointment_id)
    if not appt:
        return None
    appt.status = new_status
    db.commit()
    db.refresh(appt)
    return appt


# --- Treatment Record Operations ---
def create_treatment_record(
    db: Session,
    record_data: TreatmentRecordCreate,
    dentist_id: int
) -> TreatmentRecord:
    """Create treatment record for a patient logged by the treating dentist."""
    record = TreatmentRecord(
        appointment_id=record_data.appointment_id,
        patient_id=record_data.patient_id,
        dentist_id=dentist_id,
        tooth_number=record_data.tooth_number,
        treatment_details=record_data.treatment_details,
        doctor_notes=record_data.doctor_notes
    )
    db.add(record)

    # Automatically mark associated appointment as COMPLETED if linked
    if record_data.appointment_id:
        appt = get_appointment_by_id(db, record_data.appointment_id)
        if appt and appt.status != "CANCELLED":
            appt.status = "COMPLETED"

    db.commit()
    db.refresh(record)
    return record


def get_treatment_records_by_patient(db: Session, patient_id: int) -> List[TreatmentRecord]:
    """Retrieve full clinical treatment history for a patient."""
    return db.query(TreatmentRecord).filter(
        TreatmentRecord.patient_id == patient_id
    ).order_by(TreatmentRecord.performed_at.desc()).all()
