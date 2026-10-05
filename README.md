# JA_MFG_Log_Extractor

![Version](https://img.shields.io/badge/version-1.3.1-blue)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-brightgreen)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-Proprietary-orange)

**JA_MFG_Log_Extractor** là công cụ tự động hóa chuyên dụng phục vụ dây chuyền sản xuất công nghiệp, chuyên trích xuất, phân tích và chuẩn hóa các tệp tin báo cáo kiểm thử từ cây log raw của hệ thống kiểm thử tự động CTP / Avocado.

---

## 🎯 Chủng loại thiết bị hỗ trợ

| Chủng loại | Tiền tố SN / Dấu hiệu | File báo cáo xuất ra | Mô tả |
| :--- | :--- | :--- | :--- |
| **PSU 2U & 5U** | `PMV...` / `DYJW5` / `0R4C4` | `Controller FW, Drive FW, Serial Number Tracking & Test History.txt` | Bóc tách tích hợp 4 phần từ Step 06 (`PCM firmware`, `VPD 40/41 hex diff`) và Step 07 (`VPD 60/61 hex dump`, `Customer VPD validation`). Tự động nhận diện 2U (`DYJW5`) vs 5U (`0R4C4`), tự động phân định `psu0` (PCM 1) hoặc `psu1` (PCM 2). |
| **IO Controller chuẩn** | `SAF...` | `FW.txt`, `VPD.txt` | Tự động phân tích vai trò `ctrla` / `ctrlb` dựa theo thứ tự xuất hiện của SN trong tên thư mục. |
| **IOM RPC73** | `SAF...` (VPD 49 chứa `RPC73`) | `FW_VPD.txt` | Tự động nhận diện Canister ME52XX EBOD, bóc tách tích hợp 4 phần từ Step 02 (`Canister firmware`, `FW match`) và Step 07 (`VPD 49 hex dump`, `Customer VPD validation`). |
| **Chassis 2U** | `SGF...` | `<Target_SN>.txt` | Tổng hợp 4 khối dữ liệu VPD (Midplane, CPLD, Customer VPD hex dump, fru_description). |
| **Chassis 4U (Juno)** | `FVB...` | `FW.txt`, `GETVPD.txt`, `VER.txt`, `VPD.txt`, `Restore Default.txt`, `Provisioning State.txt` | Bộ 6 báo cáo toàn diện, đồng bộ timestamp mili-giây giữa GETVPD và VER, bảo toàn khối số dòng `\|XXXX\|`. |

---

## 🚀 Tính năng nổi bật

- ⚡ **Khởi chạy thông minh & Tương thích Remote (WinRM / SSH)**:
  - Khi chạy từ CLI / PowerShell / WinRM / SSH: Chạy trực tiếp tại shell hiện tại mà không tạo cửa sổ ngầm.
  - Khi Double-click từ File Explorer: Tự động khởi chạy trong **Windows Terminal (`wt.exe`)** nếu có, hoặc tiếp tục trên **CMD**.
  - Xử lý an toàn khi stdin bị redirect/pipe, không gặp lỗi EOFError.
- 🔍 **Đa chế độ làm việc**:
  1. **Single Folder Mode**: Nhập đường dẫn thư mục log 1 máy, tự động quét và đề xuất danh sách SN để chọn 1-chạm.
  2. **Batch Subfolders Scan**: Quét đệ quy toàn bộ thư mục mẹ, tự động bóc tách hàng loạt trạm test.
  3. **Batch CSV Import**: Nạp danh sách từ file CSV hoặc TXT để xử lý tự động trong nền.
  4. **CSV Template Generator**: Xuất file CSV mẫu chuẩn ngay tại thư mục công cụ.
- 📁 **Định tuyến thư mục xuất thông minh**:
  - Mặc định xuất vào: `<Thư mục mẹ>/<Target_SN>/`.
  - Cơ chế **Anti-nesting guard**: Ngăn chặn tuyệt đối việc lồng 2 lần tên SN nếu thư mục mẹ đã mang tên SN.
  - Hỗ trợ đường dẫn dài Windows (`\\?\` UNC & local) vượt mốc 260 ký tự `MAX_PATH`.
- 📦 **Tự động bung nén log nội bộ**: Tự động phát hiện và trích xuất dữ liệu từ các file nén `.tar.gz` trong thư mục `enc_logs/`.

---

## 💻 Hướng dẫn sử dụng

### Cách 1: Chạy trực tiếp (Khuyên dùng trên Windows)
Chỉ cần nhấp đúp vào file:
```cmd
Chay_Tool_Log.bat
```
Công cụ sẽ tự động mở giao diện điều khiển màu ANSI và hiển thị menu tương tác.

### Cách 2: Chạy qua dòng lệnh (CLI / Scripting)
```powershell
# Chế độ tương tác qua Python:
python extract_mfg_logs.py

# Chế độ dòng lệnh trực tiếp:
python extract_mfg_logs.py --input-dir "D:\Path\To\Raw_Log" --target-sn "PMV1104029G007D" --output-dir "D:\Path\To\Output"
```

---

## 📁 Cấu trúc dự án

```text
JA_MFG_Log_Extractor/
├── extract_mfg_logs.py      # Mã nguồn chính của công cụ
├── Chay_Tool_Log.bat        # Trình khởi chạy thích ứng Windows
├── mau_danh_sach_log.csv    # File CSV mẫu cho chế độ xử lý hàng loạt
├── requirements.txt         # Khai báo phụ thuộc (Zero-dependency)
├── ABOUT.txt                # Thông tin phiên bản & bản quyền
├── README.md                # Tài liệu tổng quan
├── CHANGELOG.md             # Lịch sử các phiên bản
├── USERGUIDE.md             # Hướng dẫn sử dụng chi tiết
├── RELEASE_NOTES.md         # Ghi chú phát hành
├── .agents/skills/          # Bộ kỹ năng AI Antigravity tích hợp
└── dist/                    # Bản đóng gói phát hành (Portable ZIP)
```

---

## 📄 Bản quyền

Bản quyền thuộc về **JA-Tech System / Foxconn CESBG Vietnam** (C) 2026.
