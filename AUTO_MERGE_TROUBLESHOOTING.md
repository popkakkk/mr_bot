# Auto-Merge Troubleshooting Guide

## การแก้ไขปัญหา Auto-Merge

เมื่อเจอข้อผิดพลาด auto-merge ที่ไม่ทำงาน ระบบได้รับการปรับปรุงเพื่อจัดการกับปัญหาต่างๆ:

### ปัญหาที่พบบ่อย

1. **Response Code 405 (Method Not Allowed)**
   - สาเหตุ: GitLab API ไม่อนุญาตให้ merge ในขณะนั้น
   - วิธีแก้: ระบบจะลองวิธีการอื่น อัตโนมัติ

2. **Response Code 406 (Not Acceptable)**  
   - สาเหตุ: MR มี merge conflicts หรือเงื่อนไขอื่นไม่เป็นไปตาม
   - วิธีแก้: ตรวจสอบและแก้ conflicts ที่ GitLab UI

3. **Pipeline Status Issues**
   - สาเหตุ: Pipeline ยังไม่เสร็จหรือล้มเหลว
   - วิธีแก้: ระบบจะรอ pipeline เสร็จแล้วลองใหม่

### วิธีการที่ระบบใช้ในการแก้ไข

#### 1. Enhanced Auto-Merge Process
```
1. ตรวจสอบสถานะ MR (state, merge_status)
2. ลองวิธีการหลัก (GitLab API merge endpoint)
3. หากล้มเหลว ลองวิธีการสำรอง:
   - Python-gitlab library method
   - Monitor pipeline และ retry
   - Direct merge (หาก pipeline สำเร็จ)
   - Alternative API endpoints
```

#### 2. Detailed Logging
ระบบจะบันทึกข้อมูลเพิ่มเติมเมื่อ auto-merge ล้มเหลว:
- สถานะ MR ปัจจุบัน
- สถานะ Pipeline  
- สาเหตุที่ไม่สามารถ merge ได้
- คำแนะนำในการแก้ไข

#### 3. Manual Merge Fallback
หาก auto-merge ล้มเหลวทั้งหมด:
- ระบบจะแสดง URL ของ MRs ที่ต้อง merge ด้วยมือ
- ผู้ใช้สามารถ merge ที่ GitLab UI ได้

### การใช้งาน Commands ใหม่

#### แยก Libraries และ Services
```bash
# สำหรับ libraries เท่านั้น (source branches จาก config)
./mr-automation.sh --lib-only

# สำหรับ services เท่านั้น (source branches จาก config)
./mr-automation.sh --service-only

# สำหรับ deployment ปกติ
./mr-automation.sh --target=all
```

#### การ Debug
```bash
# เปิด debug logging เพื่อดูรายละเอียดการทำงาน
./mr-automation.sh --lib-only --log-level=DEBUG
./mr-automation.sh --service-only --log-level=DEBUG

# ทดสอบโดยไม่ทำการเปลี่ยนแปลงจริง
./mr-automation.sh --lib-only --dry-run
./mr-automation.sh --service-only --dry-run
```

### เมื่อ Auto-Merge ยังไม่ทำงาน

1. **ตรวจสอบที่ GitLab UI**
   - เปิด MR ใน GitLab
   - ดูว่ามี merge conflicts หรือไม่
   - ตรวจสอบสถานะ Pipeline

2. **Manual Merge**
   - กดปุ่ม "Merge" ที่ GitLab UI
   - หรือใช้ force-merge command:
   ```bash
   ./mr-automation.sh --force-merge="repo:mr_id"
   ```

3. **ตรวจสอบ Log**
   - ดู log file: `mr_automation.log`
   - หาสาเหตุที่ auto-merge ล้มเหลว

### การปรับปรุงที่เพิ่มขึ้น

1. **ตรวจสอบ MR Status อย่างละเอียด**
2. **หลายวิธีการในการ Enable Auto-Merge**  
3. **การ Retry อัตโนมัติ**
4. **Logging ที่ครอบคลุมมากขึ้น**
5. **คำแนะนำสำหรับการแก้ไขปัญหา**

### สรุป

ระบบใหม่จะช่วยลดปัญหา auto-merge ที่ไม่ทำงานอย่างมาก และให้ข้อมูลที่ชัดเจนขึ้นเมื่อเกิดปัญหา ทำให้สามารถแก้ไขได้ง่ายขึ้น