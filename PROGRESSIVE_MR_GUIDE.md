# Progressive MR Creation Guide

## ฟีเจอร์ Progressive MR Creation

ฟีเจอร์ใหม่ที่ช่วยให้ระบบสามารถสร้าง MR ไปยัง branch ถัดไปได้โดยอัตโนมัติหลังจาก merge สำเร็จ

## วิธีการทำงาน

### ขั้นตอนการทำงานของระบบ:

1. **ประมวลผล Intermediate Commits**: สร้าง MRs สำหรับ commits ที่รอการ merge
2. **Monitor MRs**: รอให้ MRs merge สำเร็จ
3. **Progressive Check**: ตรวจสอบ repos ที่ merge สำเร็จแล้ว
4. **สร้าง MRs ถัดไป**: สร้าง MRs ไปยัง branch ถัดไปในลำดับโดยอัตโนมัติ

### ตัวอย่างการทำงาน:

```
สมมติ Branch Flow: [source_branch] → ss-dev → dev2 → sit2

เริ่มต้น:
- [source_branch] → ss-dev: มี 3 commits รอ merge

หลังจาก merge สำเร็จ:
- ระบบจะตรวจสอบว่า ss-dev → dev2 มี commits หรือไม่
- ถ้ามี จะสร้าง MR ss-dev → dev2 โดยอัตโนมัติ

หลังจาก ss-dev → dev2 merge สำเร็จ:
- ระบบจะตรวจสอบว่า dev2 → sit2 มี commits หรือไม่  
- ถ้ามี จะสร้าง MR dev2 → sit2 โดยอัตโนมัติ
```

## การใช้งาน

### เปิดใช้งาน Progressive (Default):
```bash
# Progressive เปิดโดยอัตโนมัติ (source branches จาก config)
./mr-automation.sh --lib-only
./mr-automation.sh --service-only
```

### ปิดใช้งาน Progressive:
```bash
./mr-automation.sh --lib-only --disable-progressive
./mr-automation.sh --service-only --disable-progressive
```

### ใช้กับ Libraries หรือ Services เท่านั้น:
```bash
# Progressive สำหรับ Libraries (intermediate & progressive เปิดโดยอัตโนมัติ)
./mr-automation.sh --lib-only

# Progressive สำหรับ Services (intermediate & progressive เปิดโดยอัตโนมัติ)
./mr-automation.sh --service-only
```

## ข้อดีของ Progressive MR

### 1. **ประหยัดเวลา**
- ไม่ต้องรอรันคำสั่งใหม่หลังจาก merge
- MRs ถูกสร้างโดยอัตโนมัติ

### 2. **ลดความผิดพลาด**
- ไม่ลืมสร้าง MR สำหรับ branch ถัดไป
- ระบบตรวจสอบและสร้างให้อัตโนมัติ

### 3. **เพิ่มประสิทธิภาพ**
- การ deploy ต่อเนื่องได้เร็วขึ้น
- ลดขั้นตอนที่ต้องทำด้วยมือ

## การทำงานกับ Branch Strategies

ระบบรองรับทั้งสอง strategy:

### Strategy A (ms-self-serve, ms-self-serve-batch):
```
[source_branch] → ss-dev → sit2
```
Progressive จะตรวจสอบ:
1. หาก [source_branch] merge เข้า ss-dev แล้ว
2. จะสร้าง MR ss-dev → sit2 (ถ้ามี commits)

### Strategy B (อื่นๆ):
```
[source_branch] → ss-dev → dev2 → sit2
```
Progressive จะตรวจสอบแต่ละขั้นตอน:
1. [source_branch] → ss-dev merge แล้ว → สร้าง ss-dev → dev2
2. ss-dev → dev2 merge แล้ว → สร้าง dev2 → sit2

**หมายเหตุ:** [source_branch] ถูกกำหนดใน config.yaml สำหรับแต่ละ repository

## ตัวอย่าง Output

```
🔄 Processing Intermediate Commits

# ขั้นตอนปกติ
🔍 Processing ms-payment
  [source_branch] → ss-dev: ✅ 5 commits
    🚀 Created MR: [source_branch] → ss-dev

📋 Monitoring merge requests...
✅ MR merged successfully: ms-payment

# Progressive Phase
🔍 ตรวจสอบโอกาสสร้าง MR ต่อเนื่อง...
✅ Created progressive MR for ms-payment: ss-dev → dev2 (3 commits)

📋 Monitoring progressive merge requests...
✅ Progressive MR merged: ms-payment
```

## การ Troubleshooting

### 1. Progressive ไม่ทำงาน
- Progressive เปิดโดยอัตโนมัติใน `--lib-only` และ `--service-only`
- ใช้ `--disable-progressive` เพื่อปิด
- ดู log ว่ามี commits ใน branch ถัดไปหรือไม่

### 2. MR ซ้ำ
- ระบบจะตรวจสอบ MR ที่มีอยู่แล้ว
- ไม่สร้าง MR ซ้ำถ้าข้อมูล source/target เหมือนกัน

### 3. Debug
```bash
./mr-automation.sh --lib-only --log-level=DEBUG
./mr-automation.sh --service-only --log-level=DEBUG
```

## สรุป

Progressive MR Creation ช่วยให้กระบวนการ deployment เป็นแบบ end-to-end โดยอัตโนมัติมากขึ้น ลดการทำงานด้วยมือและเพิ่มประสิทธิภาพของทีม