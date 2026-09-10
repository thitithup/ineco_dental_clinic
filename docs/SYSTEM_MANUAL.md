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
- หากตรวจพบการชนกัน ระบบจะปฏิเสธการจองทันทีด้วยรหัส **HTTP 409 Conflict** พร้อมข้อความแจ้งเตือนที่ชัดเจน

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
