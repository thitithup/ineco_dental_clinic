import re
from datetime import datetime, date, timezone
from typing import Optional, List, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator


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

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        clean = v.strip().replace("-", "").replace(" ", "")
        if not re.match(r"^0[0-9]{8,9}$", clean):
            raise ValueError("Phone number must be a valid Thai telephone format (9-10 digits starting with 0)")
        return clean

    @field_validator("date_of_birth")
    @classmethod
    def validate_dob(cls, v: date) -> date:
        if v >= date.today():
            raise ValueError("Date of birth cannot be today or in the future")
        return v


class PatientUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None
    date_of_birth: Optional[date] = None
    medical_conditions: Optional[str] = None
    drug_allergies: Optional[str] = None

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean = v.strip().replace("-", "").replace(" ", "")
            if not re.match(r"^0[0-9]{8,9}$", clean):
                raise ValueError("Phone number must be a valid Thai telephone format (9-10 digits starting with 0)")
            return clean
        return v

    @field_validator("date_of_birth")
    @classmethod
    def validate_dob(cls, v: Optional[date]) -> Optional[date]:
        if v is not None and v >= date.today():
            raise ValueError("Date of birth cannot be today or in the future")
        return v


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

    @field_validator("appointment_time")
    @classmethod
    def validate_appointment_time(cls, v: datetime) -> datetime:
        now = datetime.now(v.tzinfo) if v.tzinfo else datetime.now()
        if v < now:
            raise ValueError("Appointment time cannot be scheduled in the past")

        if v.hour < 9 or v.hour >= 20:
            raise ValueError("Appointment must be scheduled during clinic operating hours (09:00 - 20:00)")
        return v


class AppointmentStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(SCHEDULED|COMPLETED|CANCELLED)$")


class ReminderStatusUpdate(BaseModel):
    reminder_status: str = Field(..., pattern="^(PENDING|SENT|CONFIRMED)$")


class AppointmentResponse(BaseModel):
    id: int
    patient_id: int
    dentist_id: int
    appointment_time: datetime
    duration_minutes: int
    treatment_type: str
    status: str
    reminder_status: str = "PENDING"
    notes: Optional[str] = None
    created_at: datetime
    patient: Optional[PatientResponse] = None
    dentist: Optional[UserResponse] = None

    model_config = ConfigDict(from_attributes=True)


class ReminderMessageResponse(BaseModel):
    appointment_id: int
    patient_id: int
    patient_name: str
    phone_number: str
    dentist_name: str
    appointment_time: datetime
    treatment_type: str
    reminder_status: str
    message_text: str

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
