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

    # 5.4 Book Dr. Kanya at the same overlapping time (10:15) -> Should succeed because different dentist
    res_other_dentist = client.post(
        "/api/v1/appointments",
        json={
            "patient_id": patient_id,
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
