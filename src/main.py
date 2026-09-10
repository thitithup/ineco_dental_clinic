from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, Query, status, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from src.config import settings
from src.database import engine, Base, get_db, SessionLocal
from src.models import User, Patient, Appointment, TreatmentRecord
from src.schemas import (
    StandardErrorResponse,
    LoginRequest,
    TokenResponse,
    UserResponse,
    PatientCreate,
    PatientUpdate,
    PatientResponse,
    AppointmentCreate,
    AppointmentResponse,
    AppointmentStatusUpdate,
    ReminderStatusUpdate,
    ReminderMessageResponse,
    TreatmentRecordCreate,
    TreatmentRecordResponse,
)
from src.auth import (
    verify_password,
    create_access_token,
    get_current_user,
    require_roles,
    get_password_hash,
)
from src import crud


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context for DB initialization and demo data seeding."""
    Base.metadata.create_all(bind=engine)

    # Seed default staff and dentists if missing
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.username == "receptionist").first():
            crud.create_user(
                db=db,
                username="receptionist",
                password="DentalPass123!",
                full_name="เจ้าหน้าที่ นงลักษณ์ ต้อนรับดี",
                role="RECEPTIONIST",
            )

        if not db.query(User).filter(User.username == "dr_somchai").first():
            crud.create_user(
                db=db,
                username="dr_somchai",
                password="DentalPass123!",
                full_name="ทพ. สมชาย ใจดี",
                role="DENTIST",
                specialty="Orthodontics (ทันตกรรมจัดฟัน)",
            )

        if not db.query(User).filter(User.username == "dr_kanya").first():
            crud.create_user(
                db=db,
                username="dr_kanya",
                password="DentalPass123!",
                full_name="ทพญ. กัญญา รักษาฟัน",
                role="DENTIST",
                specialty="Endodontics (วิทยารักษารากฟัน)",
            )
    finally:
        db.close()

    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="ระบบบริหารจัดการคลินิกทันตกรรม (Dental Clinic Management System) พร้อมระบบตรวจสอบคิวนัดหมายซ้อนทับ และสิทธิ์การรักษาตาม PDPA",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Custom Exception Handlers ---
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "status": "error",
            "error_code": "VALIDATION_ERROR",
            "message": "Invalid request parameters",
            "details": jsonable_encoder(exc.errors()),
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    code_map = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        422: "UNPROCESSABLE_ENTITY",
    }
    error_code = code_map.get(exc.status_code, "ERROR")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "error_code": error_code,
            "message": exc.detail if isinstance(exc.detail, str) else "An error occurred",
            "details": exc.detail if not isinstance(exc.detail, str) else None,
        },
    )


# --- Health Check ---
@app.get("/health", tags=["System"])
def health_check():
    """Service health verification endpoint."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "timestamp": datetime.now().isoformat(),
    }


# --- Authentication Endpoints ---
@app.post(
    "/api/v1/auth/login",
    response_model=TokenResponse,
    responses={401: {"model": StandardErrorResponse}},
    tags=["Authentication"],
)
def login(login_req: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate user with username and password, returns JWT token."""
    user = crud.get_user_by_username(db, login_req.username)
    if not user or not verify_password(login_req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    token = create_access_token(data={"sub": user.username, "role": user.role})
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        role=user.role,
        full_name=user.full_name,
    )


@app.get("/api/v1/auth/me", response_model=UserResponse, tags=["Authentication"])
def get_current_user_profile(current_user: User = Depends(get_current_user)):
    """Retrieve logged-in user profile details."""
    return current_user


# --- Dentists Directory ---
@app.get("/api/v1/dentists", response_model=List[UserResponse], tags=["Dentists"])
def list_dentists(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all available dentists with specialty information."""
    return crud.get_dentists(db)


# --- Patient Management ---
@app.post(
    "/api/v1/patients",
    response_model=PatientResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {"model": StandardErrorResponse},
        403: {"model": StandardErrorResponse},
    },
    tags=["Patients"],
)
def register_patient(
    patient_data: PatientCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["RECEPTIONIST", "ADMIN"])),
):
    """Register a new patient into the system. Requires RECEPTIONIST or ADMIN role."""
    existing = crud.get_patient_by_phone(db, patient_data.phone_number)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Patient with phone number '{patient_data.phone_number}' already exists.",
        )
    return crud.create_patient(db, patient_data)


@app.get("/api/v1/patients", response_model=List[PatientResponse], tags=["Patients"])
def search_patients(
    query: Optional[str] = Query(None, description="Search term matching first name, last name, or phone"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Search or list patients. Accessible by RECEPTIONIST, DENTIST, and ADMIN."""
    return crud.search_patients(db, query_str=query, skip=skip, limit=limit)


@app.get(
    "/api/v1/patients/{patient_id}",
    response_model=PatientResponse,
    responses={404: {"model": StandardErrorResponse}},
    tags=["Patients"],
)
def get_patient_details(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve full patient demographic, medical history, and drug allergies."""
    patient = crud.get_patient_by_id(db, patient_id)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient ID {patient_id} not found.",
        )
    return patient


@app.put(
    "/api/v1/patients/{patient_id}",
    response_model=PatientResponse,
    responses={
        404: {"model": StandardErrorResponse},
        409: {"model": StandardErrorResponse},
    },
    tags=["Patients"],
)
def update_patient_info(
    patient_id: int,
    patient_data: PatientUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["RECEPTIONIST", "ADMIN"])),
):
    """Update patient info. Requires RECEPTIONIST or ADMIN role."""
    if patient_data.phone_number:
        existing = crud.get_patient_by_phone(db, patient_data.phone_number)
        if existing and existing.id != patient_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Phone number '{patient_data.phone_number}' is already registered to another patient.",
            )

    updated = crud.update_patient(db, patient_id, patient_data)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient ID {patient_id} not found.",
        )
    return updated


# --- Appointment Scheduling & Anti-Collision ---
@app.post(
    "/api/v1/appointments",
    response_model=AppointmentResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"model": StandardErrorResponse},
        409: {"model": StandardErrorResponse},
    },
    tags=["Appointments"],
)
def schedule_appointment(
    appt_data: AppointmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["RECEPTIONIST", "ADMIN"])),
):
    """
    Schedule an appointment with collision prevention.
    Rejects overlapping bookings for the same dentist.
    """
    # 1. Verify Patient exists
    patient = crud.get_patient_by_id(db, appt_data.patient_id)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient ID {appt_data.patient_id} does not exist.",
        )

    # 2. Verify Dentist exists and has role DENTIST
    dentist = crud.get_user_by_id(db, appt_data.dentist_id)
    if not dentist or dentist.role != "DENTIST":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dentist ID {appt_data.dentist_id} not found or is not a qualified dentist.",
        )

    # 3. Collision Detection Check (Strict Rule)
    is_collision = crud.check_dentist_collision(
        db=db,
        dentist_id=appt_data.dentist_id,
        start_time=appt_data.appointment_time,
        duration_minutes=appt_data.duration_minutes,
    )
    if is_collision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Dentist '{dentist.full_name}' already has an overlapping appointment "
                f"at {appt_data.appointment_time.isoformat()} for duration {appt_data.duration_minutes} mins."
            ),
        )

    # 4. Patient Collision Detection Check (Prevent double-booking patient)
    is_patient_conflict = crud.check_patient_collision(
        db=db,
        patient_id=appt_data.patient_id,
        start_time=appt_data.appointment_time,
        duration_minutes=appt_data.duration_minutes,
    )
    if is_patient_conflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Patient '{patient.first_name} {patient.last_name}' already has an overlapping appointment "
                f"scheduled at this time ({appt_data.appointment_time.isoformat()})."
            ),
        )

    return crud.create_appointment(db, appt_data)


@app.get(
    "/api/v1/appointments",
    response_model=List[AppointmentResponse],
    tags=["Appointments"],
)
def list_appointments(
    dentist_id: Optional[int] = Query(None, description="Filter by dentist ID"),
    patient_id: Optional[int] = Query(None, description="Filter by patient ID"),
    date_str: Optional[date] = Query(None, alias="date", description="Filter by date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List appointments.
    Dentists automatically filter to their own appointments if dentist_id is not specified.
    """
    target_dentist_id = dentist_id
    if current_user.role == "DENTIST" and target_dentist_id is None:
        target_dentist_id = current_user.id

    return crud.get_appointments(
        db,
        dentist_id=target_dentist_id,
        patient_id=patient_id,
        target_date=date_str,
    )


@app.patch(
    "/api/v1/appointments/{appointment_id}/status",
    response_model=AppointmentResponse,
    responses={404: {"model": StandardErrorResponse}},
    tags=["Appointments"],
)
def update_appointment_status(
    appointment_id: int,
    status_update: AppointmentStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update appointment status (SCHEDULED, COMPLETED, CANCELLED)."""
    appt = crud.update_appointment_status(db, appointment_id, status_update.status)
    if not appt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment ID {appointment_id} not found.",
        )
    return appt


# --- Treatment Records (Clinical Logs) ---
@app.post(
    "/api/v1/treatments",
    response_model=TreatmentRecordResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        403: {"model": StandardErrorResponse},
        404: {"model": StandardErrorResponse},
    },
    tags=["Treatment Records"],
)
def record_treatment(
    treatment_data: TreatmentRecordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["DENTIST"])),
):
    """
    Log clinical treatment record.
    Restricted strictly to DENTIST role.
    """
    # 1. Validate patient exists
    patient = crud.get_patient_by_id(db, treatment_data.patient_id)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient ID {treatment_data.patient_id} not found.",
        )

    # 2. If appointment_id is given, check validity
    if treatment_data.appointment_id:
        appt = crud.get_appointment_by_id(db, treatment_data.appointment_id)
        if not appt:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Appointment ID {treatment_data.appointment_id} not found.",
            )

    return crud.create_treatment_record(
        db=db,
        record_data=treatment_data,
        dentist_id=current_user.id,
    )


@app.get(
    "/api/v1/treatments/patient/{patient_id}",
    response_model=List[TreatmentRecordResponse],
    tags=["Treatment Records"],
)
def get_patient_treatment_history(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve full clinical treatment records for a patient."""
    patient = crud.get_patient_by_id(db, patient_id)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient ID {patient_id} not found.",
        )
    return crud.get_treatment_records_by_patient(db, patient_id)


# --- Appointment Reminder Service (SMS / LINE) ---
@app.get(
    "/api/v1/reminders/upcoming",
    response_model=List[ReminderMessageResponse],
    tags=["Reminders"],
)
def get_upcoming_reminders(
    target_date: Optional[date] = Query(None, alias="date", description="Target appointment date (defaults to tomorrow)"),
    reminder_status: Optional[str] = Query(None, pattern="^(PENDING|SENT|CONFIRMED)$", description="Filter by reminder status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["RECEPTIONIST", "ADMIN"])),
):
    """
    Retrieve upcoming appointments and generate personalized SMS/LINE reminder messages.
    Defaults to appointments scheduled for tomorrow.
    """
    return crud.get_upcoming_reminders(
        db=db,
        target_date=target_date,
        reminder_status=reminder_status,
    )


@app.patch(
    "/api/v1/appointments/{appointment_id}/reminder-status",
    response_model=AppointmentResponse,
    responses={404: {"model": StandardErrorResponse}},
    tags=["Reminders"],
)
def update_appointment_reminder_status(
    appointment_id: int,
    status_update: ReminderStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["RECEPTIONIST", "ADMIN"])),
):
    """Update appointment reminder status (PENDING, SENT, CONFIRMED)."""
    appt = crud.update_appointment_reminder_status(
        db=db,
        appointment_id=appointment_id,
        reminder_status=status_update.reminder_status,
    )
    if not appt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment ID {appointment_id} not found.",
        )
    return appt

