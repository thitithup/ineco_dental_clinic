# Dental Clinic Management System (ระบบจัดการคลินิกทันตกรรม)

ระบบหลังบ้านสำหรับคลินิกทันตกรรม พัฒนาตามมาตรฐาน **Ineco Multi-Agent Autonomous SDLC** บน Tech Stack: **Python (FastAPI + SQLAlchemy + SQLite)**

---

## 🌟 ฟีเจอร์หลัก (Core Features)

1. **การจัดการคนไข้ (Patient CRM):**
   - ลงทะเบียนประวัติคนไข้ใหม่ (ชื่อ-นามสกุล, เบอร์โทรศัพท์, วันเกิด, โรคประจำตัว, ประวัติการแพ้ยา)
   - ค้นหาประวัติคนไข้ได้อย่างรวดเร็วด้วยเบอร์โทรศัพท์ หรือ ชื่อ-นามสกุล (Partial search)
   - แจ้งเตือนประวัติแพ้ยาและโรคประจำตัวเพื่อความปลอดภัยสูงสุดในการรักษา

2. **ระบบนัดหมายและตารางตรวจ (Appointment Scheduling):**
   - รองรับทันตแพทย์หลายท่าน พร้อมระบุสาขาความเชี่ยวชาญ (จัดฟัน, รักษารากฟัน, ทันตกรรมทั่วไป ฯลฯ)
   - บันทึกการนัดหมาย: วันเวลา, ทันตแพทย์, หัตถการที่นัด (ขูดหินปูน, อุดฟัน, ถอนฟัน, ฟอกสีฟัน), ระยะเวลา
   - **กฎเหล็ก Anti-Collision Engine:** ป้องกันคิวนัดซ้อนทับกันสำหรับทันตแพทย์ท่านเดียวกันในช่วงเวลาเดียวกัน (Reject ด้วย HTTP 409 Conflict)

3. **บันทึกประวัติการรักษา (Clinical Treatment Logs):**
   - สงวนสิทธิ์เฉพาะทันตแพทย์ผู้รักษา (Dentist role) ในการบันทึกข้อมูล
   - ระบุซี่ฟันที่รักษา (Tooth Number เช่น ซี่ 18, 21-24, หรือ Full Mouth), รายละเอียดหัตถการ และบันทึกของแพทย์ (Doctor Notes)
   - ปรับสถานะนัดหมายเป็น `COMPLETED` อัตโนมัติเมื่อมีการบันทึกประวัติการรักษา

4. **ระบบสิทธิ์และการรักษาความปลอดภัย (Role-Based Access & PDPA):**
   - แบ่งสิทธิ์ชัดเจน:
     - `RECEPTIONIST`: เจ้าหน้าที่เคาน์เตอร์ จัดการลงทะเบียนคนไข้ และนัดหมายคิว
     - `DENTIST`: ทันตแพทย์ ดูตารางนัดหมายและบันทึกประวัติการรักษา
   - การเข้ารหัสรหัสผ่านด้วย Native Bcrypt และระบบยืนยันตัวตนด้วย Bearer JWT Token ตามมาตรฐาน PDPA

---

## 🔑 บัญชีผู้ใช้เริ่มต้นสำหรับทดสอบ (Demo Accounts)

ระบบจะสร้างบัญชีเริ่มต้นให้อัตโนมัติเมื่อเปิดใช้งานครั้งแรก:

| บทบาท (Role) | Username | Password | ชื่อ-นามสกุล | ความเชี่ยวชาญ |
|---|---|---|---|---|
| **RECEPTIONIST** | `receptionist` | `DentalPass123!` | เจ้าหน้าที่ นงลักษณ์ ต้อนรับดี | เคาน์เตอร์ / เวชระเบียน |
| **DENTIST** | `dr_somchai` | `DentalPass123!` | ทพ. สมชาย ใจดี | ทันตกรรมจัดฟัน (Orthodontics) |
| **DENTIST** | `dr_kanya` | `DentalPass123!` | ทพญ. กัญญา รักษาฟัน | วิทยารักษารากฟัน (Endodontics) |

---

## 🚀 การเริ่มต้นใช้งาน (Quick Start)

### วิธีที่ 1: รันด้วย Python Virtual Environment (.venv)

```bash
# 1. เข้าสู่โฟลเดอร์โปรเจกต์
cd dental_clinic

# 2. สร้าง Virtual Environment และเปิดใช้งาน
python3 -m venv .venv
source .venv/bin/activate

# 3. ติดตั้ง Dependencies
pip install -r requirements.txt

# 4. รันระบบเซิร์ฟเวอร์
uvicorn src.main:app --reload --port 8000
```

- ทดสอบเรียกดู API Documentation: [http://localhost:8000/docs](http://localhost:8000/docs)
- ตรวจสอบความพร้อมของระบบ: [http://localhost:8000/health](http://localhost:8000/health)

### วิธีที่ 2: รันด้วย Docker & Docker Compose

```bash
# สั่ง Build และรัน Container ในโหมด Background
docker compose up -d --build

# ดู Log การทำงาน
docker compose logs -f
```

---

## 🧪 การรัน Automated Test Suite

```bash
# รันชุดการทดสอบทั้งหมด 8 เคส
pytest tests/ -v
```
