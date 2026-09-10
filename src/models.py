from datetime import datetime, timezone, date
from sqlalchemy import Column, Integer, String, Text, DateTime, Date, ForeignKey
from sqlalchemy.orm import relationship
from src.database import Base


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


class User(Base):
    """User accounts (Dentists, Reception Staff, Admin)."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=False)
    role = Column(String(20), nullable=False)  # RECEPTIONIST, DENTIST, ADMIN
    specialty = Column(String(100), nullable=True)  # e.g., Orthodontics, Endodontics, General
    created_at = Column(DateTime, default=utc_now, nullable=False)

    appointments = relationship("Appointment", back_populates="dentist", foreign_keys="Appointment.dentist_id")
    treatment_records = relationship("TreatmentRecord", back_populates="dentist", foreign_keys="TreatmentRecord.dentist_id")


class Patient(Base):
    """Patient records with medical history and allergy tracking."""

    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    first_name = Column(String(50), nullable=False, index=True)
    last_name = Column(String(50), nullable=False, index=True)
    phone_number = Column(String(20), unique=True, nullable=False, index=True)
    date_of_birth = Column(Date, nullable=False)
    medical_conditions = Column(Text, nullable=True)  # e.g., Diabetes, Hypertension
    drug_allergies = Column(Text, nullable=True)      # e.g., Penicillin, Aspirin, Sulfa
    created_at = Column(DateTime, default=utc_now, nullable=False)

    appointments = relationship("Appointment", back_populates="patient", cascade="all, delete-orphan")
    treatment_records = relationship("TreatmentRecord", back_populates="patient", cascade="all, delete-orphan")


class Appointment(Base):
    """Scheduled clinic appointments with dentist allocation."""

    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    dentist_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    appointment_time = Column(DateTime, nullable=False, index=True)
    duration_minutes = Column(Integer, default=30, nullable=False)
    treatment_type = Column(String(100), nullable=False)  # e.g., Cleaning, Extraction, Filling, Root Canal
    status = Column(String(20), default="SCHEDULED", nullable=False)  # SCHEDULED, COMPLETED, CANCELLED
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    patient = relationship("Patient", back_populates="appointments")
    dentist = relationship("User", back_populates="appointments", foreign_keys=[dentist_id])
    treatment_records = relationship("TreatmentRecord", back_populates="appointment")


class TreatmentRecord(Base):
    """Detailed clinical treatment log entered by the dentist."""

    __tablename__ = "treatment_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    dentist_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    tooth_number = Column(String(20), nullable=False)  # e.g., "18", "21-24", "Full Mouth"
    treatment_details = Column(Text, nullable=False)
    doctor_notes = Column(Text, nullable=True)
    performed_at = Column(DateTime, default=utc_now, nullable=False)

    patient = relationship("Patient", back_populates="treatment_records")
    dentist = relationship("User", back_populates="treatment_records", foreign_keys=[dentist_id])
    appointment = relationship("Appointment", back_populates="treatment_records")
