# Release Notes - Config-Based Source Branches & Progressive MR Enhancement

## 🚀 Major Features Added

### 1. **Separated Commands for Libraries and Services**
ตอนนี้สามารถแยกการประมวลผล libraries และ services ได้:

```bash
# Libraries เท่านั้น (source branches จาก config)
./mr-automation.sh --lib-only

# Services เท่านั้น (source branches จาก config)
./mr-automation.sh --service-only

# ทั้งหมด - ใช้ main deployment command
./mr-automation.sh --target=all
```

### 2. **Progressive MR Creation** ⭐ NEW!
ฟีเจอร์ใหม่ที่สร้าง MR ไปยัง branch ถัดไปโดยอัตโนมัติหลังจาก merge สำเร็จ:

- **เปิดโดยอัตโนมัติ**: Progressive MR creation เปิดใช้งานโดย default
- **สร้าง MRs ต่อเนื่อง**: หลังจาก MR merge สำเร็จ ระบบจะตรวจสอบและสร้าง MR ไปยัง branch ถัดไปอัตโนมัติ
- **ประหยัดเวลา**: ไม่ต้องรอรันคำสั่งใหม่หลังจาก merge
- **ลดความผิดพลาด**: ไม่ลืมสร้าง MR สำหรับ branch ถัดไป

```bash
# เปิด Progressive (default)
./mr-automation.sh --lib-only
./mr-automation.sh --service-only

# ปิด Progressive
./mr-automation.sh --lib-only --disable-progressive
./mr-automation.sh --service-only --disable-progressive
```

### 3. **Enhanced Auto-Merge System** 🛠️
ปรับปรุงระบบ auto-merge ให้แข็งแกร่งขึ้นมาก:

- **หลายวิธีการ**: มีหลายวิธีในการ enable auto-merge
- **การ Retry อัตโนมัติ**: ระบบจะ retry หาก method แรกล้มเหลว
- **ตรวจสอบละเอียด**: ตรวจสอบสถานะ MR และ Pipeline อย่างครอบคลุม
- **Detailed Logging**: แสดงสาเหตุที่ชัดเจนเมื่อ auto-merge ล้มเหลว
- **Manual Fallback**: แสดง URL ของ MRs ที่ต้อง merge ด้วยมือ

### 4. **Better Error Handling and Reporting**
- ✅ รายงานสาเหตุที่ auto-merge ล้มเหลว
- ✅ แสดง URL ของ MRs ที่ต้อง merge ด้วยมือ
- ✅ คำแนะนำในการแก้ไขปัญหา
- ✅ Improved logging และ debugging

## 🎯 การใช้งานใหม่

### แยกการทำงานระหว่าง Libraries และ Services:
```bash
# Libraries (explore-go, proto) - source branches จาก config
./mr-automation.sh --lib-only

# Services (ms-bff-go, ms-bbff-go, ms-payment, etc.) - source branches จาก config
./mr-automation.sh --service-only
```

### Progressive MR Creation:
```bash
# แบบ Progressive (แนะนำ) - เปิดโดยอัตโนมัติ
./mr-automation.sh --lib-only
./mr-automation.sh --service-only

# แบบเดิม (ไม่ Progressive)
./mr-automation.sh --lib-only --disable-progressive
./mr-automation.sh --service-only --disable-progressive
```

### Debug และ Troubleshooting:
```bash
# Debug mode
./mr-automation.sh --lib-only --log-level=DEBUG
./mr-automation.sh --service-only --log-level=DEBUG

# Dry run
./mr-automation.sh --lib-only --dry-run
./mr-automation.sh --service-only --dry-run
```

## 📋 ตัวอย่างการทำงาน

### Progressive MR Flow:
```
1. เริ่มต้น: [source_branch] → ss-dev (มี 3 commits)
   ✅ สร้าง MR และ merge สำเร็จ

2. Progressive Phase: ตรวจสอบ ss-dev → dev2
   ✅ พบ 3 commits ใหม่ → สร้าง MR อัตโนมัติ
   ✅ MR merge สำเร็จ

3. Progressive Phase: ตรวจสอบ dev2 → sit2  
   ✅ พบ 3 commits ใหม่ → สร้าง MR อัตโนมัติ
   ✅ MR merge สำเร็จ

🎉 Deployment สมบูรณ์โดยไม่ต้องรอหรือรันคำสั่งใหม่!

หมายเหตุ: [source_branch] ถูกกำหนดใน config.yaml สำหรับแต่ละ repository
```

## 🆕 Options ใหม่

| Option | Description | Default |
|--------|-------------|---------|
| `--lib-only` | ประมวลผลเฉพาะ libraries (intermediate & progressive by default) | false |
| `--service-only` | ประมวลผลเฉพาะ services (intermediate & progressive by default) | false |
| `--disable-progressive` | ปิด Progressive MR creation | false |

### 🆕 Config-Based Source Branches
Source branches are now configured per repository in `config.yaml`:

```yaml
branch_strategies:
  strategy_a:
    repos: [ms-self-serve, ms-self-serve-batch]
    source_branch: sprint5/all
    flow: [sprint5/all, sit3]
  strategy_b:
    repos: [explore-go, proto, ...]
    source_branch: ss/sprint5/all
    flow: [ss/sprint5/all, sit3]
```

## 🔧 การแก้ไขปัญหา Auto-Merge

เมื่อเจอปัญหา "auto merged ทำงานไม่ได้" ระบบใหม่จะ:

1. **ลองหลายวิธีการ**: API หลัก, python-gitlab library, alternative APIs
2. **ตรวจสอบสาเหตุ**: merge conflicts, pipeline status, MR state
3. **รายงานรายละเอียด**: แสดงสาเหตุและวิธีแก้ไข
4. **Manual Fallback**: แสดง URL สำหรับ merge ด้วยมือ

ดู [AUTO_MERGE_TROUBLESHOOTING.md](AUTO_MERGE_TROUBLESHOOTING.md) สำหรับรายละเอียดเพิ่มเติม

## 📖 เอกสารเพิ่มเติม

- [PROGRESSIVE_MR_GUIDE.md](PROGRESSIVE_MR_GUIDE.md) - คู่มือ Progressive MR Creation
- [AUTO_MERGE_TROUBLESHOOTING.md](AUTO_MERGE_TROUBLESHOOTING.md) - แก้ไขปัญหา Auto-Merge
- [README.md](README.md) - คู่มือการใช้งานหลัก

## ✅ การทดสอบ

ระบบได้รับการทดสอบแล้วกับ:
- ✅ Libraries-only processing (explore-go, proto)
- ✅ Services-only processing (ms-bff-go, ms-bbff-go, ms-payment, ms-self-serve, ms-self-serve-batch)
- ✅ Progressive MR creation
- ✅ Enhanced auto-merge system
- ✅ Error handling และ fallback mechanisms

## 🚀 ความได้เปรียบ

1. **ประหยัดเวลา**: ไม่ต้องรอรันคำสั่งใหม่หลังจาก merge
2. **ลดความผิดพลาด**: ระบบจัดการทุกอย่างอัตโนมัติ
3. **เพิ่มความน่าเชื่อถือ**: auto-merge ทำงานได้ดีขึ้นมาก
4. **ยืดหยุ่นมากขึ้น**: แยกการทำงาน libraries/services ได้
5. **ง่ายต่อ Debug**: logging และ error reporting ที่ดีขึ้น

---

**สรุปการเปลี่ยนแปลงใหม่**: 
- 🚀 **ไม่ต้องใส่ `--sprint` อีกแล้ว**: Source branches อ่านจาก config.yaml แทน
- 🎯 **แต่ละ repo มี source branch ต่างกันได้**: กำหนดใน config per strategy
- 📦 **แยกการทำงานระหว่าง lib repo และ service ได้**: `--lib-only` และ `--service-only`
- 🔄 **Progressive MR ที่สร้าง MR ไปยัง branch ถัดไปโดยอัตโนมัติ**: หลังจาก merge สำเร็จ
- ⚙️ **Configuration-driven approach**: เปลี่ยน source branch ได้ที่ config file เท่านั้น 🎉