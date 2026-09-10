from datetime import datetime, date
from typing import Optional, List, Any
from pydantic import BaseModel, Field, ConfigDict


class StandardErrorResponse(BaseModel):
    """Standardized error contract."""

    status: str = "error"
    error_code: str
    message: str
    details: Optional[Any] = None


# --- Authentication Schemas ---
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    full_name: str


class UserResponse(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    specialty: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# --- Patient Schemas ---
class PatientCreate(BaseModel):
    first_name: str = Field(..., min_length=2, max_length=50)
    last_name: str = Field(..., min_length=2, max_length=50)
    phone_number: str = Field(..., min_length=9, max_length=20)
    date_of_birth: date
    medical_conditions: Optional[str] = None
    drug_allergies: Optional[str] = None


class PatientUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None
    date_of_birth: Optional[date] = None
    medical_conditions: Optional[str] = None
    drug_allergies: Optional[str] = None


class PatientResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    phone_number: str
    date_of_birth: date
    medical_conditions: Optional[str] = None
    drug_allergies: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Appointment Schemas ---
class AppointmentCreate(BaseModel):
    patient_id: int
    dentist_id: int
    appointment_time: datetime
    duration_minutes: int = Field(default=30, ge=15, le=240)
    treatment_type: str = Field(..., min_length=2)
    notes: Optional[str] = None


class AppointmentStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(SCHEDULED|COMPLETED|CANCELLED)$")


class AppointmentResponse(BaseModel):
    id: int
    patient_id: int
    dentist_id: int
    appointment_time: datetime
    duration_minutes: int
    treatment_type: str
    status: str
    notes: Optional[str] = None
    created_at: datetime
    patient: Optional[PatientResponse] = None
    dentist: Optional[UserResponse] = None

    model_config = ConfigDict(from_attributes=True)


# --- Treatment Record Schemas ---
class TreatmentRecordCreate(BaseModel):
    appointment_id: Optional[int] = None
    patient_id: int
    tooth_number: str = Field(..., description="e.g. 18, 21-24, or Full Mouth")
    treatment_details: str = Field(..., min_length=3)
    doctor_notes: Optional[str] = None


class TreatmentRecordResponse(BaseModel):
    id: int
    appointment_id: Optional[int] = None
    patient_id: int
    dentist_id: int
    tooth_number: str
    treatment_details: str
    doctor_notes: Optional[str] = None
    performed_at: datetime

    model_config = ConfigDict(from_attributes=True)
