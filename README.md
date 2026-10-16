# JA_MFG_Log_Extractor

![Version](https://img.shields.io/badge/version-1.6.0-blue)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-brightgreen)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-Proprietary-orange)

**JA_MFG_Log_Extractor** là công cụ tự động hóa chuyên dụng phục vụ dây chuyền sản xuất công nghiệp, chuyên kết nối trực tiếp hoặc qua cầu nối gián tiếp (Indirect Bridge) tới các trạm kiểm thử để trích xuất, phân tích Cycle Time, chẩn đoán lỗi và chuẩn hóa các tệp tin báo cáo kiểm thử từ hệ thống kiểm thử tự động CTP / Avocado. Toàn bộ báo cáo phân tích được lưu tập trung tại thư mục `<App_Dir>/reports/`.

---

## 🎯 Chủng loại thiết bị hỗ trợ

| Chủng loại | Tiền tố SN / Dấu hiệu | File báo cáo xuất ra (`reports/<SN>/`) | Mô tả |
| :--- | :--- | :--- | :--- |
| **Chassis 5U Dell** | `SGF...` / `W47DG` / `5U84` | `FW.txt`, `VPD.txt` | Dell 5U84 Chassis (PN W47DG). Trích xuất `FW.txt` (21 dòng: Midplane VPD 0x13, CRC, CPLD, 8 firmware Element 0..3, 8 địa chỉ SAS expander) và `VPD.txt` (216 dòng: VPD 16, VPD 18, 8 khối Canister VPD 48 hex diff, 7 khối set_midplanevpd 2..8, Customer VPD validation). |
| **PSU 2U & 5U** | `PMV...` / `DYJW5` / `0R4C4` | `Controller FW, Drive FW, Serial Number Tracking & Test History.txt` | Bóc tách tích hợp 4 phần từ Step 06 (`PCM firmware`, `VPD 40/41 hex diff`) và Step 07 (`VPD 60/61 hex dump`, `Customer VPD validation`). Tự động nhận diện 2U (`DYJW5`) vs 5U (`0R4C4`), tự động phân định `psu0` (PCM 1) hoặc `psu1` (PCM 2). |
| **IO Controller chuẩn** | `SAF...` | `FW.txt`, `VPD.txt` | Tự động phân tích vai trò `ctrla` / `ctrlb` dựa theo thứ tự xuất hiện của SN trong tên thư mục. |
| **IOM RPC73** | `SAF...` (VPD 49 chứa `RPC73`) | `FW_VPD.txt` | Tự động nhận diện Canister ME52XX EBOD, bóc tách tích hợp 4 phần từ Step 02 (`Canister firmware`, `FW match`) và Step 07 (`VPD 49 hex dump`, `Customer VPD validation`). |
| **Chassis 2U** | `SGF...` | `<Target_SN>.txt` | Tổng hợp 4 khối dữ liệu VPD (Midplane, CPLD, Customer VPD hex dump, fru_description). |
| **Chassis 4U (Juno)** | `FVB...` | `FW.txt`, `GETVPD.txt`, `VER.txt`, `VPD.txt`, `Restore Default.txt`, `Provisioning State.txt` | Bộ 6 báo cáo toàn diện, đồng bộ timestamp mili-giây giữa GETVPD và VER, bảo toàn khối số dòng `\|XXXX\|`. |

---

## 🚀 Tính năng nổi bật (v1.6.0)

- 🌐 **Trích xuất Trực tiếp Từ xa qua Liên kết Gián tiếp (Indirect Bridge `172.21.168.241` $\rightarrow$ `172.19.*.*`)**:
  - Chạy trực tiếp trên máy kỹ sư (`172.21.*.*`), tự động định tuyến trực tiếp hoặc qua trạm cầu nối Jump-Host (`172.21.168.241` / `172.19.208.133`) tới các trạm test (`172.19.*.*`) bằng SSH `direct-tcpip` kèm cơ chế fallback tự động sang WinRM TCP Proxy.
  - Hỗ trợ nhập nhanh IP rút gọn 2 octet (`116.174` hoặc `116174` $\rightarrow$ `172.19.116.174`), tìm kiếm 1 hoặc nhiều Serial Number (`SN1, SN2`), và lọc số bản chạy mới nhất (`--latest`).
  - Cơ chế **Selective Fast Fetch**: Chỉ nén và tải các file log/metadata nhẹ cần cho phân tích (`debug.log`, `results.json`, `*.log`, `ctp_log_metadata.yaml`, `job.log`, `enc_logs/*`), hoàn tất trích xuất từ xa trong **1–3 giây**. Hỗ trợ cờ `--keep-raw-zip` để lưu thêm bản `.zip` gốc vào `downloads/<IP>/`.
- 📂 **Lưu Báo cáo Tập trung trong Thư mục Ứng dụng (`<App_Dir>/reports/`)**:
  - Mọi chế độ trích xuất (Remote IP+SN, Local Folder/Archive, Batch Scan, CSV Import, Cycle Time) mặc định xuất báo cáo vào `<App_Dir>/reports/<Target_SN>/` và `<App_Dir>/reports/Cycle_Time_Summary.csv`.
- ⏱ **Phân tích Cycle Time & Xuất Báo cáo Excel (`Cycle_Time_Summary.csv`)**:
  - Tự động đọc `Test duration` (Wall-clock Cycle Time từ `<unit>.log`), thời gian thực thi Avocado (`results.json`), `Start_Time`, `End_Time`, `Station_ID`, `Employee_ID`, `Part_Number`, `Script_Name`, và số bước `Pass/Fail/Skip`.
- 🗜 **Đọc Trực tiếp File Nén (`.zip`, `.tar.gz`, `.tgz`, `.tar.xz`)**:
  - Hỗ trợ truyền trực tiếp file nén log đầu vào mà không cần giải nén thủ công.
- 🛡 **Kiểm tra Toàn vẹn (Sanity Guard) & Tự động Chẩn đoán Lỗi (`ERROR_SUMMARY.txt`)**:
  - Tự động kiểm tra số lượng file báo cáo kỳ vọng, dung lượng > 0 byte và cảnh báo sớm khi có dòng `result: mismatch`, `VPD rendering failed`, hoặc `| FAIL |`.
  - Khi phát hiện bước test `FAIL`/`ERROR` trong `results.json`, tự động trích xuất nguyên nhân và 15 dòng lỗi cuối trong `debug.log` ra file `ERROR_SUMMARY.txt`.
- 🪟 **Hộp thoại Chọn File/Folder Windows (`[B]`/`[F]`) & Phím tắt Sau Trích xuất (`[O]`/`[R]`)**:
  - Gõ `B` (chọn thư mục) hoặc `F` (chọn file nén `.zip`/`.tar.gz`) để mở hộp thoại Windows Explorer gốc.
  - Sau khi hoàn tất, nhấn `[O]` để mở ngay thư mục kết quả trong Explorer hoặc `[R]` để quay lại Menu chính.
- 🔬 **Đối soát Mẫu Chuẩn Golden Sample (`--verify-sample` / Menu `[7]`) & Đa luồng (`--workers 4`)**:
  - Đối chiếu 100% Byte-for-Byte (SHA256, số dòng, unified diff) với thư mục mẫu chuẩn.
  - Xử lý hàng loạt đa luồng (`--workers 4`) tăng tốc độ trích xuất batch gấp 3–4 lần.

---

## 💻 Hướng dẫn sử dụng

### Cách 1: Chạy trực tiếp (Khuyên dùng trên Windows)
Chỉ cần nhấp đúp vào file:
```cmd
Chay_Tool_Log.bat
```
Công cụ sẽ tự động mở giao diện điều khiển màu ANSI và hiển thị 7 chế độ làm việc tương tác (mặc định `[1]` là Trích xuất trực tiếp từ máy trạm từ xa qua IP + SN).

### Cách 2: Chạy qua dòng lệnh (CLI / Scripting)
```powershell
# Chế độ tương tác qua Python:
python extract_mfg_logs.py

# Trích xuất trực tiếp từ trạm test từ xa (qua Indirect Bridge) vào ./reports/<SN>/:
python extract_mfg_logs.py --ip 116.174 --sn SGFVN2633836284 --latest 1

# Trích xuất từ xa và giữ lại bản nén .zip đầy đủ trong ./downloads/<IP>/:
python extract_mfg_logs.py --ip 116.172 --sn PMV1104546G0017 --latest 1 --keep-raw-zip

# Trích xuất từ thư mục hoặc file nén .zip nội bộ kèm đối soát Golden Sample:
python extract_mfg_logs.py --input-dir "D:\Logs\unit_log.zip" --verify-sample "D:\Sample_Dir"

# Quét nhanh Cycle Time & xuất báo cáo Excel CSV vào ./reports/Cycle_Time_Summary.csv:
python extract_mfg_logs.py --cycle-time --batch-dir "D:\JA_TESTER\LOGS_ANL\IO"

# Trích xuất hàng loạt đa luồng (4 workers) từ file CSV:
python extract_mfg_logs.py --csv-file mau_danh_sach_log.csv --workers 4
```

---

## 📁 Cấu trúc dự án

```text
JA_MFG_Log_Extractor/
├── extract_mfg_logs.py      # Mã nguồn chính của công cụ (CLI + Engine trích xuất)
├── module/                  # Phân hệ kết nối từ xa, Indirect Bridge & Selective Fetch
│   ├── bridge.py            # Cầu nối SSH direct-tcpip & WinRM TCP Proxy fallback
│   ├── remote_fetcher.py    # Tìm kiếm & tải chọn lọc siêu tốc qua SFTP/PowerShell
│   ├── config.py            # Cấu hình kết nối & đọc config.json
│   ├── ip_utils.py          # Chuẩn hóa IP rút gọn (116.174 / 116174 -> 172.19.116.174)
│   ├── winrm_socket.py      # Socket-like adapter cho WinRM Bridge
│   └── winrm_bridge.ps1     # Kịch bản PowerShell TCP Bridge trên trạm trung gian
├── config_sample.json       # Mẫu cấu hình kết nối từ xa (sao chép thành config.json)
├── Chay_Tool_Log.bat        # Trình khởi chạy thích ứng Windows
├── mau_danh_sach_log.csv    # File CSV mẫu cho chế độ xử lý hàng loạt
├── requirements.txt         # Khai báo phụ thuộc (paramiko>=3.0.0)
├── reports/                 # Thư mục lưu tập trung toàn bộ báo cáo phân tích & CSV
├── downloads/               # Thư mục lưu file nén .zip gốc khi bật --keep-raw-zip
├── ABOUT.txt                # Thông tin phiên bản & bản quyền
├── README.md                # Tài liệu tổng quan
├── CHANGELOG.md             # Lịch sử các phiên bản
├── USERGUIDE.md             # Hướng dẫn sử dụng chi tiết
├── RELEASE_NOTES.md         # Ghi chú phát hành
└── dist/                    # Bản đóng gói phát hành (Portable ZIP)
```

---

## 📄 Bản quyền

Bản quyền thuộc về **JA-Tech System / Foxconn CESBG Vietnam** (C) 2026.
