# คู่มือสถาปัตยกรรมระบบ (System Architecture Manual)
## ระบบบริหารจัดการคลินิกทันตกรรม (Dental Clinic Management System)

---

## 1. ภาพรวมสถาปัตยกรรม (System Architecture Overview)

ระบบ Dental Clinic Management System ถูกออกแบบตามสถาปัตยกรรมแบบ **Layered Architecture & Separation of Concerns** เพื่อรองรับความปลอดภัยตามมาตรฐาน PDPA, ความถูกต้องของคิวนัดหมาย (Collision-free Scheduling), และความเสถียรของข้อมูลเวชระเบียนทันตกรรม

```
+-------------------------------------------------------------------------+
|                              Client Layer                               |
|        (Web Frontend / Mobile App / Swagger UI / Counter Tablet)        |
+------------------------------------+------------------------------------+
                                     |  HTTP / REST (JSON)
                                     v
+-------------------------------------------------------------------------+
|                         FastAPI Gateway Layer                           |
|  - CORS Middleware & Lifespan Seeder                                    |
|  - JWT Bearer Authentication & RBAC Authorization                       |
|  - Global Standard Error Handlers (400, 401, 403, 404, 409, 422, 500)   |
+------------------------------------+------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|                          Business Logic Layer                           |
|  - Anti-Collision Scheduling Engine (Interval Overlap Detection)        |
|  - Patient CRM & Allergy Precaution Tracking                            |
|  - Clinical Treatment Logging & Status Transition Engine                |
+------------------------------------+------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|                   Data Access Layer (SQLAlchemy 2.0)                    |
|  - Models: User, Patient, Appointment, TreatmentRecord                  |
|  - SQLite Database Engine / PostgreSQL Compatible                       |
+-------------------------------------------------------------------------+
```

---

## 2. โครงสร้างฐานข้อมูลและตาราง (Data Dictionary)

### 2.1 ตาราง `users` (ผู้ใช้งานระบบ)
| Field | Type | Constraint | Description |
|---|---|---|---|
| `id` | Integer | Primary Key, Auto Increment | รหัสประจำตัวผู้ใช้ |
| `username` | String(50) | Unique, Index, Not Null | ชื่อผู้ใช้สำหรับล็อกอิน |
| `password_hash` | String(255) | Not Null | รหัสผ่านที่ผ่านการ Hash ด้วย Bcrypt |
| `full_name` | String(100) | Not Null | ชื่อ-นามสกุลจริง |
| `role` | String(20) | Not Null | สิทธิ์: `RECEPTIONIST`, `DENTIST`, `ADMIN` |
| `specialty` | String(100) | Nullable | สาขาความเชี่ยวชาญ (เฉพาะหมอ เช่น จัดฟัน, รักษารากฟัน) |
| `created_at` | DateTime | Default UTC | วันเวลาที่สร้างบัญชี |

### 2.2 ตาราง `patients` (ประวัติคนไข้)
| Field | Type | Constraint | Description |
|---|---|---|---|
| `id` | Integer | Primary Key, Auto Increment | รหัสคนไข้ (HN) |
| `first_name` | String(50) | Index, Not Null | ชื่อจริง |
| `last_name` | String(50) | Index, Not Null | นามสกุล |
| `phone_number` | String(20) | Unique, Index, Not Null | เบอร์โทรศัพท์ (ใช้ค้นหาด่วน) |
| `date_of_birth` | Date | Not Null | วันเดือนปีเกิด |
| `medical_conditions` | Text | Nullable | โรคประจำตัว (เช่น ความดัน, เบาหวาน) |
| `drug_allergies` | Text | Nullable | ประวัติการแพ้ยา (สำคัญสูงสุดด้านความปลอดภัย) |
| `created_at` | DateTime | Default UTC | วันเวลาที่ลงทะเบียน |

### 2.3 ตาราง `appointments` (คิวนัดหมาย)
| Field | Type | Constraint | Description |
|---|---|---|---|
| `id` | Integer | Primary Key, Auto Increment | รหัสนัดหมาย |
| `patient_id` | Integer | Foreign Key -> `patients.id` | รหัสคนไข้ที่นัด |
| `dentist_id` | Integer | Foreign Key -> `users.id` | รหัสทันตแพทย์ผู้ตรวจ |
| `appointment_time` | DateTime | Index, Not Null | วันเวลาเริ่มต้นนัดหมาย |
| `duration_minutes` | Integer | Default 30, Not Null | ระยะเวลาการรักษา (นาที) |
| `treatment_type` | String(100) | Not Null | หัตถการที่นัด (ขูดหินปูน, ถอนฟัน, อุดฟัน ฯลฯ) |
| `status` | String(20) | Default 'SCHEDULED' | สถานะ: `SCHEDULED`, `COMPLETED`, `CANCELLED` |
| `reminder_status` | String(20) | Default 'PENDING' | สถานะแจ้งเตือน: `PENDING`, `SENT`, `CONFIRMED` |
| `notes` | Text | Nullable | บันทึกเพิ่มเติมของคิวนัด |

### 2.4 ตาราง `treatment_records` (เวชระเบียนบันทึกการรักษา)
| Field | Type | Constraint | Description |
|---|---|---|---|
| `id` | Integer | Primary Key, Auto Increment | รหัสบันทึกการรักษา |
| `appointment_id` | Integer | Foreign Key -> `appointments.id` | นัดหมายที่เกี่ยวข้อง (ถ้ามี) |
| `patient_id` | Integer | Foreign Key -> `patients.id` | คนไข้ที่รับการรักษา |
| `dentist_id` | Integer | Foreign Key -> `users.id` | ทันตแพทย์ผู้ให้การรักษา |
| `tooth_number` | String(20) | Not Null | ซี่ฟันที่ทำ (เช่น 18, 21-24, Full Mouth) |
| `treatment_details` | Text | Not Null | รายละเอียดหัตถการและขั้นตอนการรักษา |
| `doctor_notes` | Text | Nullable | บันทึกติดตามผล / คำแนะนำการดูแลหลังทำ |
| `performed_at` | DateTime | Default UTC | วันเวลาที่ทำหัตถการ |

---

## 3. อัลกอริทึมป้องกันคิวนัดซ้อนทับ (Anti-Collision Algorithm)

หัวใจสำคัญของระบบนัดหมายทันตแพทย์คือ **ห้ามมิให้ทันตแพทย์ท่านเดียวกันมีคิวนัดหมายซ้อนทับกันในช่วงเวลาเดียวกัน**

### หลักการทางคณิตศาสตร์ (Interval Overlap Condition):
ช่วงเวลาใหม่ $A = [Start_A, End_A]$ และช่วงเวลาเดิม $B = [Start_B, End_B]$ จะถือว่าเกิดการซ้อนทับกัน (**Collision**) ก็ต่อเมื่อ:

$$Start_A < End_B \quad \text{AND} \quad End_A > Start_B$$

โดยที่:
- $End = Start + \text{duration\_minutes}$
- คิวนัดหมายเดิมที่มีสถานะ `CANCELLED` จะถูกยกเว้น ไม่นำมาคำนวณการซ้อนทับ
- **Dentist Anti-Collision:** ทันตแพทย์ท่านเดียวกัน ห้ามมีคิวนัดซ้อนทับกันเด็ดขาด (HTTP 409 Conflict)
- **Patient Anti-Collision:** คนไข้ท่านเดียวกัน ห้ามมีคิวนัดซ้อนทับกันข้ามแพทย์ท่านอื่นในเวลาเดียวกันเด็ดขาด (HTTP 409 Conflict)
- **Temporal Constraints:**
  - ห้ามจองคิวนัดหมายย้อนหลังในอดีต (Past Dating)
  - ต้องจองเฉพาะช่วงเวลาทำการของคลินิก: **09:00 - 20:00 น.** เท่านั้น
  - วันเกิดคนไข้ (DOB) ต้องไม่เป็นวันปัจจุบันหรือวันในอนาคต
  - เบอร์โทรศัพท์ต้องเป็นรูปแบบเบอร์โทรศัพท์ของไทย 9-10 หลัก (เช่น 08x-xxx-xxxx, 02-xxx-xxxx)

---

## 4. มาตรฐานความปลอดภัยและการคุ้มครองข้อมูล (Security & PDPA)

1. **Role-Based Access Control (RBAC):**
   - การลงทะเบียนคนไข้ และการจองคิวนัดหมาย สงวนสิทธิ์เฉพาะบทบาท `RECEPTIONIST` และ `ADMIN`
   - การบันทึกเวชระเบียนการรักษา (Treatment Record) สงวนสิทธิ์เฉพาะบทบาท `DENTIST` เท่านั้น
2. **การปกป้องรหัสผ่าน:**
   - เข้ารหัสด้วย `Bcrypt` พร้อม Random Salt ก่อนจัดเก็บลงฐานข้อมูล ไม่มีการเก็บ Plaintext Password
3. **การเข้าถึง API ด้วย JWT:**
   - ใช้ JSON Web Token (HS256) พร้อมอายุการใช้งานจำกัด (Access Token Expiration)
   - ป้องกันการเข้าถึงข้อมูลประวัติการรักษาและข้อมูลส่วนบุคคลของคนไข้โดยไม่ได้รับอนุญาต

---

## 5. รายการ API Endpoints (API Reference)

| Method | Endpoint | Allowed Roles | Description | Response Codes |
|---|---|---|---|---|
| `GET` | `/health` | Public | ตรวจสอบสถานะการทำงานของระบบ | 200 |
| `POST` | `/api/v1/auth/login` | Public | ล็อกอินเพื่อรับ Bearer JWT Token | 200, 401 |
| `GET` | `/api/v1/auth/me` | Authenticated | ดูข้อมูลโปรไฟล์ของผู้ใช้ปัจจุบัน | 200, 401 |
| `GET` | `/api/v1/dentists` | Authenticated | รายชื่อทันตแพทย์ทั้งหมดพร้อมความเชี่ยวชาญ | 200, 401 |
| `POST` | `/api/v1/patients` | RECEPTIONIST, ADMIN | ลงทะเบียนคนไข้ใหม่ | 201, 403, 409 |
| `GET` | `/api/v1/patients` | All Authenticated | ค้นหาคนไข้ตามชื่อ หรือ เบอร์โทรศัพท์ | 200, 401 |
| `GET` | `/api/v1/patients/{id}` | All Authenticated | ดูประวัติและข้อมูลสุขภาพคนไข้ | 200, 404 |
| `PUT` | `/api/v1/patients/{id}` | RECEPTIONIST, ADMIN | ปรับปรุงข้อมูลส่วนตัว/โรคประจำตัวคนไข้ | 200, 403, 409 |
| `POST` | `/api/v1/appointments` | RECEPTIONIST, ADMIN | จองคิวนัดหมาย (พร้อมระบบเช็กคิวซ้อนทับ) | 201, 403, 404, 409 |
| `GET` | `/api/v1/appointments` | All Authenticated | ตรวจสอบตารางนัดหมาย (กรองตามวัน/แพทย์) | 200, 401 |
| `PATCH`| `/api/v1/appointments/{id}/status` | All Authenticated | ปรับสถานะนัดหมาย (SCHEDULED, COMPLETED, CANCELLED) | 200, 404 |
| `POST` | `/api/v1/treatments` | DENTIST | บันทึกประวัติการรักษาและระบุซี่ฟัน | 201, 403, 404 |
| `GET` | `/api/v1/treatments/patient/{id}` | All Authenticated | ดูประวัติการรักษาทั้งหมดของคนไข้ | 200, 404 |
| `GET` | `/api/v1/reminders/upcoming` | RECEPTIONIST, ADMIN | ดึงคิวนัดหมายล่วงหน้าและสร้างข้อความแจ้งเตือน SMS/LINE | 200, 403 |
| `PATCH`| `/api/v1/appointments/{id}/reminder-status` | RECEPTIONIST, ADMIN | ปรับสถานะการเตือน (PENDING, SENT, CONFIRMED) | 200, 403, 404 |

---

## 6. ระบบเตรียมข้อความแจ้งเตือนนัดหมาย (Appointment Reminder Service)

ระบบถูกออกแบบมาเพื่อลดอัตราการไม่มาตามนัด (No-show rate) ของคนไข้ โดยมีหลักการทำงานดังนี้:

1. **การดึงคิวล่วงหน้า (Target Date Filtering):**
   - ค่าเริ่มต้นจะค้นหาคิวนัดหมายของ "วันพรุ่งนี้" (`date.today() + 1 day`) ที่มีสถานะ `SCHEDULED`
   - สามารถระบุวันที่อื่น หรือกรองสถานะการส่งข้อความ (`reminder_status`) ได้
2. **แม่แบบข้อความแจ้งเตือนอัตโนมัติ (Template Generator):**
   - ข้อความถูกประกอบขึ้นอย่างเป็นระบบ:
     `เรียนคุณ {patient_name} {CLINIC_NAME} ขอแจ้งเตือนนัดหมาย {treatment_type} กับ {dentist_name} ในวันที่ {DD/MM/YYYY} เวลา {HH:MM} น. หากต้องการเลื่อนนัดกรุณาโทร {CLINIC_PHONE}`
3. **วงจรสถานะการแจ้งเตือน (Reminder Status Lifecycle):**
   - `PENDING` (รอดำเนินการ - ค่าเริ่มต้นเมื่อจองนัด)
   - `SENT` (ส่งข้อความไปยังคนไข้แล้ว)
   - `CONFIRMED` (คนไข้ตอบรับยืนยันเวลาเรียบร้อยแล้ว)

---

## 7. ขอบเขตการทดสอบและผลลัพธ์ (Testing Scope & Verification Results)

ระบบได้รับการทดสอบความถูกต้องอย่างเข้มงวดตามมาตรฐาน **Automated Integration & Edge-Case Testing** โดยแยกสภาพแวดล้อมออกจากฐานข้อมูลจริงอย่างสมบูรณ์

### 7.1 กลยุทธ์การทดสอบ (Testing Strategy & Environment Isolation)
- **In-Memory Test Database:** ชุดทดสอบทั้งหมดรันบน SQLite หน่วยความจำเสมือน (`sqlite:///:memory:` ร่วมกับ `StaticPool`) ข้อมูลจำลองจะถูกสร้างและทำลายทิ้งทันทีเมื่อสิ้นสุดการรัน ไม่มีการเขียนทับหรือปะปนกับฐานข้อมูล `dental_clinic.db` จริงของคลินิก
- **Isolated Virtual Environment:** รันการทดสอบภายใต้ Virtual Environment ประจำโปรเจกต์ (`.venv`)
- **Automated CI/CD Quality Gate:** รันการทดสอบ 15 เคสโดยอัตโนมัติบน GitHub Actions ทุกครั้งที่มีการ Commit / Pull Request โค้ดใหม่

---

### 7.2 ตารางสรุปขอบเขตเคสทดสอบ (15 Test Cases Matrix)

| หมวดหมู่ | ชื่อฟังก์ชันทดสอบ | ประเภทการทดสอบ | วัตถุประสงค์และการตรวจสอบ | ผลลัพธ์ |
|---|---|---|---|:---:|
| **System** | `test_health_check` | Health & Liveness | ตรวจสอบสถานะความพร้อมของ API Service (`/health`) | **PASS** |
| **Security** | `test_login_invalid_credentials` | Negative Security | ปฏิเสธการล็อกอินด้วยรหัสผ่านผิดทันทีด้วย `401 Unauthorized` | **PASS** |
| **Security** | `test_login_and_me_profile` | Authentication | ออก Token สำเร็จและดึงข้อมูลโปรไฟล์ผู้ใช้ตนเอง (`/me`) | **PASS** |
| **Directory** | `test_list_dentists` | Functional | ดึงรายชื่อทันตแพทย์ทั้งหมดพร้อมสาขาความเชี่ยวชาญ | **PASS** |
| **CRM** | `test_patient_registration_and_search` | Functional & Integrity | ลงทะเบียนคนไข้, ป้องกันเบอร์ซ้ำ (`409`), ค้นหาด่วนด้วยชื่อและเบอร์ | **PASS** |
| **RBAC** | `test_dentist_cannot_register_patient_role_enforcement` | Access Control | ป้องกันทันตแพทย์ลงทะเบียนคนไข้ตามหลัก Least Privilege (`403`) | **PASS** |
| **Scheduling** | `test_appointment_booking_and_anti_collision` | Core Business Logic | ตรวจจับคิวนัดซ้อนทับของหมอคนเดิม (`409`), จองคิวต่อเนื่อง (`201`), จองหมอคนละท่านในเวลาเดียวกัน (`201`) | **PASS** |
| **Clinical** | `test_treatment_record_creation_and_history` | Business Automation | เคาน์เตอร์ห้ามบันทึกการรักษา (`403`), หมอบันทึกระบุซี่ฟัน (`201`), อัปเดตสถานะนัดหมายเป็น `COMPLETED` อัตโนมัติ | **PASS** |
| **Reminder** | `test_appointment_reminder_service` | Communication Service | หมอเข้าถึงไม่ได้ (`403`), ดึงคิวนัดล่วงหน้า, สร้างข้อความ SMS/LINE อัตโนมัติ, ปรับสถานะ `PENDING` $\rightarrow$ `SENT` $\rightarrow$ `CONFIRMED` | **PASS** |
| **Data Validation**| `test_patient_dob_in_future_rejected` | Boundary Validation | ปฏิเสธวันเกิดคนไข้ในอนาคตหรือวันปัจจุบัน (`422 Unprocessable Entity`) | **PASS** |
| **Data Validation**| `test_patient_invalid_phone_format_rejected` | Regex Validation | ปฏิเสธเบอร์โทรศัพท์ที่ไม่ได้รูปแบบไทย 9-10 หลัก (`422 Unprocessable Entity`) | **PASS** |
| **Temporal** | `test_appointment_in_the_past_rejected` | Temporal Integrity | ปฏิเสธการจองคิวนัดหมายย้อนหลังในอดีต (`422 Unprocessable Entity`) | **PASS** |
| **Temporal** | `test_appointment_outside_operating_hours_rejected` | Business Hours | ปฏิเสธการจองคิวนอกเวลาทำการ 09:00 - 20:00 น. (`422 Unprocessable Entity`) | **PASS** |
| **Scheduling** | `test_patient_double_booking_collision_rejected` | Dual Anti-Collision | ป้องกันคนไข้คนเดิมจองนัดซ้อนทับข้ามหมอท่านอื่นในเวลาเดียวกัน (`409 Conflict`) | **PASS** |
| **Security** | `test_expired_and_malformed_jwt_token_rejected` | Token Degradation | ปฏิเสธ Token ปลอมแปลง หรือ Token ที่หมดอายุการใช้งาน (`401 Unauthorized`) | **PASS** |

---

### 7.3 บันทึกผลการรันการทดสอบจริง (Execution Log Output)

```bash
$ .venv/bin/pytest tests/ -v
============================= test session starts ==============================
platform darwin -- Python 3.12.9, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/tititab/Documents/Codes/Software House/dental_clinic
plugins: anyio-4.15.1
collected 15 items

tests/test_api.py::test_health_check PASSED                              [  6%]
tests/test_api.py::test_login_invalid_credentials PASSED                 [ 13%]
tests/test_api.py::test_login_and_me_profile PASSED                      [ 20%]
tests/test_api.py::test_list_dentists PASSED                             [ 26%]
tests/test_api.py::test_patient_registration_and_search PASSED           [ 33%]
tests/test_api.py::test_dentist_cannot_register_patient_role_enforcement PASSED [ 40%]
tests/test_api.py::test_appointment_booking_and_anti_collision PASSED    [ 46%]
tests/test_api.py::test_treatment_record_creation_and_history PASSED     [ 53%]
tests/test_api.py::test_appointment_reminder_service PASSED              [ 60%]
tests/test_api.py::test_patient_dob_in_future_rejected PASSED            [ 66%]
tests/test_api.py::test_patient_invalid_phone_format_rejected PASSED     [ 73%]
tests/test_api.py::test_appointment_in_the_past_rejected PASSED          [ 80%]
tests/test_api.py::test_appointment_outside_operating_hours_rejected PASSED [ 86%]
tests/test_api.py::test_patient_double_booking_collision_rejected PASSED [ 93%]
tests/test_api.py::test_expired_and_malformed_jwt_token_rejected PASSED  [100%]

======================== 15 passed in 4.48s ========================
```

---

### 7.4 สถานะการรันบนระบบ CI/CD (GitHub Actions)
- **Workflow:** `.github/workflows/ci.yml`
- **สถานะล่าสุด:** [![CI Status](https://img.shields.io/badge/CI%2FCD-Passed%20100%25-brightgreen)](https://github.com/thitithup/ineco_dental_clinic/actions)
- **อัตราความสำเร็จ:** 100% (15/15 Passed ทั้ง Unit/Integration Tests และ Docker Image Build)


