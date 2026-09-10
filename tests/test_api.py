from datetime import datetime, date, timezone, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from src.database import Base, get_db
from src.main import app
from src.models import User
from src import crud
from src.auth import create_access_token

# Setup in-memory SQLite for test isolation
TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    try:
        # Seed test users
        crud.create_user(
            db=db,
            username="receptionist_test",
            password="DentalPass123!",
            full_name="เจ้าหน้าที่ ทดสอบ",
            role="RECEPTIONIST",
        )
        crud.create_user(
            db=db,
            username="dentist_somchai",
            password="DentalPass123!",
            full_name="ทพ. สมชาย ใจดี",
            role="DENTIST",
            specialty="Orthodontics",
        )
        crud.create_user(
            db=db,
            username="dentist_kanya",
            password="DentalPass123!",
            full_name="ทพญ. กัญญา รักษาฟัน",
            role="DENTIST",
            specialty="Endodontics",
        )
    finally:
        db.close()
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def client():
    return TestClient(app)


def get_token(client: TestClient, username: str, password: str = "DentalPass123!") -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


# --- 1. Health & System Check ---
def test_health_check(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "Dental Clinic" in data["service"]


# --- 2. Authentication & Authorization Tests ---
def test_login_invalid_credentials(client):
    res = client.post(
        "/api/v1/auth/login",
        json={"username": "receptionist_test", "password": "WrongPassword"},
    )
    assert res.status_code == 401
    assert res.json()["error_code"] == "UNAUTHORIZED"


def test_login_and_me_profile(client):
    token = get_token(client, "receptionist_test")
    res = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["username"] == "receptionist_test"
    assert data["role"] == "RECEPTIONIST"


# --- 3. Dentists Directory Tests ---
def test_list_dentists(client):
    token = get_token(client, "receptionist_test")
    res = client.get(
        "/api/v1/dentists",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    dentists = res.json()
    assert len(dentists) >= 2
    names = [d["full_name"] for d in dentists]
    assert "ทพ. สมชาย ใจดี" in names
    assert "ทพญ. กัญญา รักษาฟัน" in names


# --- 4. Patient Management Tests ---
def test_patient_registration_and_search(client):
    rec_token = get_token(client, "receptionist_test")

    # 4.1 Register patient
    patient_payload = {
        "first_name": "สมศักดิ์",
        "last_name": "รักฟัน",
        "phone_number": "0812345678",
        "date_of_birth": "1990-05-20",
        "medical_conditions": "ความดันโลหิตสูง",
        "drug_allergies": "แพ้ยา Penicillin",
    }
    res = client.post(
        "/api/v1/patients",
        json=patient_payload,
        headers={"Authorization": f"Bearer {rec_token}"},
    )
    assert res.status_code == 201
    p_data = res.json()
    assert p_data["first_name"] == "สมศักดิ์"
    assert p_data["drug_allergies"] == "แพ้ยา Penicillin"
    patient_id = p_data["id"]

    # 4.2 Duplicate phone number conflict
    dup_res = client.post(
        "/api/v1/patients",
        json=patient_payload,
        headers={"Authorization": f"Bearer {rec_token}"},
    )
    assert dup_res.status_code == 409
    assert dup_res.json()["error_code"] == "CONFLICT"

    # 4.3 Search patient by phone number
    search_res = client.get(
        "/api/v1/patients?query=0812345678",
        headers={"Authorization": f"Bearer {rec_token}"},
    )
    assert search_res.status_code == 200
    results = search_res.json()
    assert len(results) >= 1
    assert results[0]["id"] == patient_id

    # 4.4 Search patient by name
    name_search = client.get(
        "/api/v1/patients?query=สมศักดิ์",
        headers={"Authorization": f"Bearer {rec_token}"},
    )
    assert name_search.status_code == 200
    assert len(name_search.json()) >= 1

    # 4.5 Get patient details
    detail_res = client.get(
        f"/api/v1/patients/{patient_id}",
        headers={"Authorization": f"Bearer {rec_token}"},
    )
    assert detail_res.status_code == 200
    assert detail_res.json()["medical_conditions"] == "ความดันโลหิตสูง"


def test_dentist_cannot_register_patient_role_enforcement(client):
    # DENTIST role should not have permission to register patients
    dentist_token = get_token(client, "dentist_somchai")
    res = client.post(
        "/api/v1/patients",
        json={
            "first_name": "กมล",
            "last_name": "มีสุข",
            "phone_number": "0899999999",
            "date_of_birth": "1995-01-01",
        },
        headers={"Authorization": f"Bearer {dentist_token}"},
    )
    assert res.status_code == 403
    assert res.json()["error_code"] == "FORBIDDEN"


# --- 5. Appointment Scheduling & Strict Anti-Collision Tests ---
def test_appointment_booking_and_anti_collision(client):
    rec_token = get_token(client, "receptionist_test")

    # Get dentist ID for Somchai
    dentists_res = client.get("/api/v1/dentists", headers={"Authorization": f"Bearer {rec_token}"})
    dentists = dentists_res.json()
    somchai = next(d for d in dentists if "สมชาย" in d["full_name"])
    kanya = next(d for d in dentists if "กัญญา" in d["full_name"])

    # Create another patient for testing
    patient_res = client.post(
        "/api/v1/patients",
        json={
            "first_name": "วิภา",
            "last_name": "สุขเกษม",
            "phone_number": "0855555555",
            "date_of_birth": "1992-08-15",
        },
        headers={"Authorization": f"Bearer {rec_token}"},
    )
    patient_id = patient_res.json()["id"]

    # 5.1 Book first appointment with Dr. Somchai: 10:00 to 10:30 (30 mins)
    base_time = datetime(2026, 11, 20, 10, 0, 0)
    appt1_payload = {
        "patient_id": patient_id,
        "dentist_id": somchai["id"],
        "appointment_time": base_time.isoformat(),
        "duration_minutes": 30,
        "treatment_type": "ขูดหินปูน (Scaling)",
        "notes": "นัดตรวจฟันประจำปี",
    }
    res1 = client.post(
        "/api/v1/appointments",
        json=appt1_payload,
        headers={"Authorization": f"Bearer {rec_token}"},
    )
    assert res1.status_code == 201
    appt1_id = res1.json()["id"]

    # 5.2 Attempt to book overlapping appointment for Dr. Somchai at 10:15 (COLLISION!)
    overlap_time = datetime(2026, 11, 20, 10, 15, 0)
    res_conflict = client.post(
        "/api/v1/appointments",
        json={
            "patient_id": patient_id,
            "dentist_id": somchai["id"],
            "appointment_time": overlap_time.isoformat(),
            "duration_minutes": 30,
            "treatment_type": "อุดฟัน (Filling)",
        },
        headers={"Authorization": f"Bearer {rec_token}"},
    )
    assert res_conflict.status_code == 409
    assert res_conflict.json()["error_code"] == "CONFLICT"
    assert "already has an overlapping appointment" in res_conflict.json()["message"]

    # 5.3 Book non-overlapping appointment for Dr. Somchai at 10:30 (starts right after 1st ends)
    consecutive_time = datetime(2026, 11, 20, 10, 30, 0)
    res_consecutive = client.post(
        "/api/v1/appointments",
        json={
            "patient_id": patient_id,
            "dentist_id": somchai["id"],
            "appointment_time": consecutive_time.isoformat(),
            "duration_minutes": 30,
            "treatment_type": "ฟอกสีฟัน (Bleaching)",
        },
        headers={"Authorization": f"Bearer {rec_token}"},
    )
    assert res_consecutive.status_code == 201

    # 5.4 Book Dr. Kanya at the same time (10:15) for a DIFFERENT patient -> Succeeds because different dentist
    p2_res = client.post(
        "/api/v1/patients",
        json={
            "first_name": "ประสิทธิ์",
            "last_name": "ใจดี",
            "phone_number": "0819998877",
            "date_of_birth": "1985-03-15",
        },
        headers={"Authorization": f"Bearer {rec_token}"},
    )
    assert p2_res.status_code == 201
    patient2_id = p2_res.json()["id"]

    res_other_dentist = client.post(
        "/api/v1/appointments",
        json={
            "patient_id": patient2_id,
            "dentist_id": kanya["id"],
            "appointment_time": overlap_time.isoformat(),
            "duration_minutes": 30,
            "treatment_type": "รักษารากฟัน (Root Canal)",
        },
        headers={"Authorization": f"Bearer {rec_token}"},
    )
    assert res_other_dentist.status_code == 201


# --- 6. Treatment Record Tests (Clinical Logs) ---
def test_treatment_record_creation_and_history(client):
    rec_token = get_token(client, "receptionist_test")
    dentist_token = get_token(client, "dentist_somchai")

    # Get patient
    patient_res = client.get("/api/v1/patients?query=วิภา", headers={"Authorization": f"Bearer {rec_token}"})
    patient = patient_res.json()[0]

    # Get Dr. Somchai's appointments
    appt_res = client.get(
        f"/api/v1/appointments?patient_id={patient['id']}",
        headers={"Authorization": f"Bearer {rec_token}"},
    )
    appts = appt_res.json()
    target_appt = appts[0]

    # 6.1 Receptionist attempts to create treatment record -> 403 Forbidden
    rec_treatment_res = client.post(
        "/api/v1/treatments",
        json={
            "appointment_id": target_appt["id"],
            "patient_id": patient["id"],
            "tooth_number": "18",
            "treatment_details": "ถอนฟันคุดกรามบนขวา",
        },
        headers={"Authorization": f"Bearer {rec_token}"},
    )
    assert rec_treatment_res.status_code == 403

    # 6.2 Dentist creates treatment record -> 201 Created
    dentist_treatment_res = client.post(
        "/api/v1/treatments",
        json={
            "appointment_id": target_appt["id"],
            "patient_id": patient["id"],
            "tooth_number": "18",
            "treatment_details": "ผ่าฟันคุด กรอตัดฟันและเย็บ 2 เข็ม",
            "doctor_notes": "นัดตัดไหมในอีก 7 วัน คนไข้แผลแห้งดี ไม่พบอาการบวมผิดปกติ",
        },
        headers={"Authorization": f"Bearer {dentist_token}"},
    )
    assert dentist_treatment_res.status_code == 201
    treatment_data = dentist_treatment_res.json()
    assert treatment_data["tooth_number"] == "18"
    assert "ผ่าฟันคุด" in treatment_data["treatment_details"]

    # 6.3 Verify appointment status transitioned to COMPLETED automatically
    updated_appt_res = client.get(
        f"/api/v1/appointments?patient_id={patient['id']}",
        headers={"Authorization": f"Bearer {dentist_token}"},
    )
    completed_appt = next(a for a in updated_appt_res.json() if a["id"] == target_appt["id"])
    assert completed_appt["status"] == "COMPLETED"

    # 6.4 Verify treatment history by patient ID
    history_res = client.get(
        f"/api/v1/treatments/patient/{patient['id']}",
        headers={"Authorization": f"Bearer {dentist_token}"},
    )
    assert history_res.status_code == 200
    history = history_res.json()
    assert len(history) >= 1
    assert history[0]["tooth_number"] == "18"


# --- 7. Appointment Reminder Service Tests ---
def test_appointment_reminder_service(client):
    rec_token = get_token(client, "receptionist_test")
    dentist_token = get_token(client, "dentist_somchai")

    # 7.1 Dentist role should be forbidden from accessing reminders (receptionist/admin only)
    forbidden_res = client.get(
        "/api/v1/reminders/upcoming",
        headers={"Authorization": f"Bearer {dentist_token}"},
    )
    assert forbidden_res.status_code == 403

    # 7.2 Create a patient and schedule an appointment for a specific target date
    patient_res = client.post(
        "/api/v1/patients",
        json={
            "first_name": "ธนกร",
            "last_name": "มั่งมี",
            "phone_number": "0861112233",
            "date_of_birth": "1988-12-10",
        },
        headers={"Authorization": f"Bearer {rec_token}"},
    )
    assert patient_res.status_code == 201
    patient = patient_res.json()

    dentists_res = client.get("/api/v1/dentists", headers={"Authorization": f"Bearer {rec_token}"})
    somchai = next(d for d in dentists_res.json() if "สมชาย" in d["full_name"])

    target_dt = datetime(2026, 12, 1, 14, 0, 0)
    target_date_str = target_dt.strftime("%Y-%m-%d")

    appt_res = client.post(
        "/api/v1/appointments",
        json={
            "patient_id": patient["id"],
            "dentist_id": somchai["id"],
            "appointment_time": target_dt.isoformat(),
            "duration_minutes": 45,
            "treatment_type": "ตรวจสุขภาพฟันและขูดหินปูน",
        },
        headers={"Authorization": f"Bearer {rec_token}"},
    )
    assert appt_res.status_code == 201
    appt = appt_res.json()
    assert appt["reminder_status"] == "PENDING"

    # 7.3 Fetch upcoming reminders for target date
    reminders_res = client.get(
        f"/api/v1/reminders/upcoming?date={target_date_str}",
        headers={"Authorization": f"Bearer {rec_token}"},
    )
    assert reminders_res.status_code == 200
    reminders = reminders_res.json()
    assert len(reminders) >= 1
    my_reminder = next(r for r in reminders if r["appointment_id"] == appt["id"])

    # Verify generated reminder message
    assert "เรียนคุณ ธนกร มั่งมี" in my_reminder["message_text"]
    assert "ตรวจสุขภาพฟันและขูดหินปูน" in my_reminder["message_text"]
    assert "ทพ. สมชาย ใจดี" in my_reminder["message_text"]
    assert "14:00" in my_reminder["message_text"]
    assert "02-123-4567" in my_reminder["message_text"]
    assert my_reminder["phone_number"] == "0861112233"
    assert my_reminder["reminder_status"] == "PENDING"

    # 7.4 Update reminder status to SENT
    patch_res = client.patch(
        f"/api/v1/appointments/{appt['id']}/reminder-status",
        json={"reminder_status": "SENT"},
        headers={"Authorization": f"Bearer {rec_token}"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["reminder_status"] == "SENT"

    # 7.5 Filter reminders by status=SENT
    sent_reminders = client.get(
        f"/api/v1/reminders/upcoming?date={target_date_str}&reminder_status=SENT",
        headers={"Authorization": f"Bearer {rec_token}"},
    ).json()
    assert any(r["appointment_id"] == appt["id"] for r in sent_reminders)

    # 7.6 Filter reminders by status=PENDING (should no longer include appt)
    pending_reminders = client.get(
        f"/api/v1/reminders/upcoming?date={target_date_str}&reminder_status=PENDING",
        headers={"Authorization": f"Bearer {rec_token}"},
    ).json()
    assert not any(r["appointment_id"] == appt["id"] for r in pending_reminders)

    # 7.7 Update status to CONFIRMED
    confirm_res = client.patch(
        f"/api/v1/appointments/{appt['id']}/reminder-status",
        json={"reminder_status": "CONFIRMED"},
        headers={"Authorization": f"Bearer {rec_token}"},
    )
    assert confirm_res.status_code == 200
    assert confirm_res.json()["reminder_status"] == "CONFIRMED"


# --- 8. Comprehensive Edge-Case & Data Validation Tests ---
def test_patient_dob_in_future_rejected(client):
    """Ensure date of birth in the future or today is rejected (422 Unprocessable Entity)."""
    rec_token = get_token(client, "receptionist_test")
    future_date = (date.today() + timedelta(days=5)).isoformat()
    res = client.post(
        "/api/v1/patients",
        json={
            "first_name": "อนาคต",
            "last_name": "ยังไม่เกิด",
            "phone_number": "0891234567",
            "date_of_birth": future_date,
        },
        headers={"Authorization": f"Bearer {rec_token}"},
    )
    assert res.status_code == 422
    assert "Date of birth cannot be today or in the future" in str(res.json())


def test_patient_invalid_phone_format_rejected(client):
    """Ensure non-Thai phone number formats are rejected."""
    rec_token = get_token(client, "receptionist_test")
    for invalid_phone in ["1234567890", "abcdefghijk", "081234567x"]:
        res = client.post(
            "/api/v1/patients",
            json={
                "first_name": "ทดสอบ",
                "last_name": "เบอร์ผิด",
                "phone_number": invalid_phone,
                "date_of_birth": "1995-01-01",
            },
            headers={"Authorization": f"Bearer {rec_token}"},
        )
        assert res.status_code == 422
        assert "Phone number must be a valid Thai telephone format" in str(res.json())


def test_appointment_in_the_past_rejected(client):
    """Ensure appointments scheduled in the past are rejected."""
    rec_token = get_token(client, "receptionist_test")
    past_time = datetime(2020, 1, 1, 10, 0, 0).isoformat()
    res = client.post(
        "/api/v1/appointments",
        json={
            "patient_id": 1,
            "dentist_id": 2,
            "appointment_time": past_time,
            "duration_minutes": 30,
            "treatment_type": "ตรวจฟัน",
        },
        headers={"Authorization": f"Bearer {rec_token}"},
    )
    assert res.status_code == 422
    assert "Appointment time cannot be scheduled in the past" in str(res.json())


def test_appointment_outside_operating_hours_rejected(client):
    """Ensure appointments outside clinic hours (09:00 - 20:00) are rejected."""
    rec_token = get_token(client, "receptionist_test")
    early_time = datetime(2026, 11, 20, 3, 0, 0).isoformat()  # 03:00 AM
    late_time = datetime(2026, 11, 20, 22, 0, 0).isoformat()  # 10:00 PM

    for t in [early_time, late_time]:
        res = client.post(
            "/api/v1/appointments",
            json={
                "patient_id": 1,
                "dentist_id": 2,
                "appointment_time": t,
                "duration_minutes": 30,
                "treatment_type": "ตรวจฟัน",
            },
            headers={"Authorization": f"Bearer {rec_token}"},
        )
        assert res.status_code == 422
        assert "clinic operating hours" in str(res.json())


def test_patient_double_booking_collision_rejected(client):
    """Ensure the SAME patient cannot have overlapping appointments across DIFFERENT dentists."""
    rec_token = get_token(client, "receptionist_test")

    dentists = client.get("/api/v1/dentists", headers={"Authorization": f"Bearer {rec_token}"}).json()
    somchai = next(d for d in dentists if "สมชาย" in d["full_name"])
    kanya = next(d for d in dentists if "กัญญา" in d["full_name"])

    # Create distinct patient for this test
    p_res = client.post(
        "/api/v1/patients",
        json={
            "first_name": "คนไข้",
            "last_name": "คิวชน",
            "phone_number": "0898765432",
            "date_of_birth": "1993-07-20",
        },
        headers={"Authorization": f"Bearer {rec_token}"},
    )
    assert p_res.status_code == 201
    patient_id = p_res.json()["id"]

    # Book Dr. Somchai at 11:00 - 11:30
    appt_time = datetime(2026, 11, 25, 11, 0, 0).isoformat()
    res1 = client.post(
        "/api/v1/appointments",
        json={
            "patient_id": patient_id,
            "dentist_id": somchai["id"],
            "appointment_time": appt_time,
            "duration_minutes": 30,
            "treatment_type": "จัดฟัน",
        },
        headers={"Authorization": f"Bearer {rec_token}"},
    )
    assert res1.status_code == 201

    # Attempt to book Dr. Kanya for the SAME patient at 11:15 (overlap)
    overlap_time = datetime(2026, 11, 25, 11, 15, 0).isoformat()
    res2 = client.post(
        "/api/v1/appointments",
        json={
            "patient_id": patient_id,
            "dentist_id": kanya["id"],
            "appointment_time": overlap_time,
            "duration_minutes": 30,
            "treatment_type": "รักษารากฟัน",
        },
        headers={"Authorization": f"Bearer {rec_token}"},
    )
    assert res2.status_code == 409
    assert "already has an overlapping appointment scheduled" in res2.json()["message"]


def test_expired_and_malformed_jwt_token_rejected(client):
    """Ensure malformed or expired JWT tokens are rejected with 401 Unauthorized."""
    # Malformed token
    res_malformed = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer this.is.an.invalid.token"},
    )
    assert res_malformed.status_code == 401
    assert res_malformed.json()["error_code"] == "UNAUTHORIZED"

    # Expired token (created with negative expiration delta)
    expired_token = create_access_token(
        data={"sub": "receptionist_test", "role": "RECEPTIONIST"},
        expires_delta=timedelta(minutes=-30)
    )
    res_expired = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert res_expired.status_code == 401
    assert res_expired.json()["error_code"] == "UNAUTHORIZED"


