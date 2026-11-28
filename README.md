# JA_MFG_Log_Extractor

![Version](https://img.shields.io/badge/version-1.8.3-blue)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-brightgreen)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-Proprietary-orange)

**JA_MFG_Log_Extractor** là công cụ tự động hóa chuyên dụng phục vụ dây chuyền sản xuất công nghiệp, chuyên kết nối trực tiếp hoặc qua cầu nối gián tiếp (Indirect Bridge) tới các trạm kiểm thử để trích xuất, phân tích Cycle Time, chẩn đoán lỗi và chuẩn hóa các tệp tin báo cáo kiểm thử từ hệ thống kiểm thử tự động CTP / Avocado. Toàn bộ báo cáo phân tích được lưu tập trung tại thư mục `<App_Dir>/reports/`.

---

## 🎯 Chủng loại thiết bị hỗ trợ

| Chủng loại | Tiền tố SN / Dấu hiệu | File báo cáo xuất ra (`reports/<SN>/`) | Mô tả |
| :--- | :--- | :--- | :--- |
| **Chassis 5U Dell (W47DG)** | `SGF...` / `W47DG` / `5U84` | `FW.txt`, `VPD.txt` | Dell 5U84 Chassis (PN W47DG). Trích xuất `FW.txt` (21 dòng: Midplane VPD structure/CRC/CPLD từ step 07 `vpd_validation`, 8 firmware Element 0..3, 8 địa chỉ SAS expander) và `VPD.txt` (216 dòng: VPD 16, VPD 18, 8 khối Canister VPD 48 hex diff, 7 khối set_midplanevpd 2..8, Customer VPD validation). |
| **Chassis 5U Dell (7PNTN)** | `SGF...` / `7PNTN` | `FW.txt`, `VPD.txt` | Dell 5U Chassis (PN 7PNTN). Trích xuất `FW.txt` (31 dòng: bổ sung 5 cặp Fan Controller từ step 07 trước Sled) và `VPD.txt` (260 dòng: VPD 16 đến 0090, VPD 18 đến 00a0 + 0360/0370, WWN, Customer VPD 18, cùng Fan VPD 122–126 và Canister VPD 48 từ step 06). |
| **HPE MSA IO Controller** | `P61070-001` (`1VAD4YB...`, `2MXD2YG...`) | `FW.txt`, `FW_RAW.md` | HPE MSA 2070 FC Controller theo Section 4 FAIR. Xuất `FW.txt` (chuẩn CLI 5 lệnh không dính cột) và `FW_RAW.md` (bảng Markdown `Versions` 2 cột và dump YAML lọc theo SN đích). |
| **HPE MSA Chassis LFF** | `S1H41-62001` (`1VAD4ZB...`, `ACVD1DW...`) | `FW.txt`, `FW_RAW.md` | HPE MSA 2070 FC LFF Chassis theo Section 5 FAIR. Xuất `FW.txt` (đầy đủ 6 lệnh chuẩn, show license, 2 Controller A & B, Ports A & B có `Speed(C)`) và `FW_RAW.md`. |
| **HPE MSA Chassis 16Gb SFF** | `S1H42-62001` (`1VAD4ZB...`, `2MXD3DG...`) | `FW.txt`, `FW_RAW.md` | HPE MSA 2070 16Gb FC SFF Chassis theo Section 4 FAIR. Xuất `FW.txt` (8 lệnh chuẩn gồm `show frus secrets detail`, 24 SFF slots, 16Gb FC ports, `show advanced-settings`) và `FW_RAW.md`. |
| **HPE MSA Chassis 10/25GbE iSCSI SFF** | `S1H44-62001` (`1VAD4ZB...`, `2MXD43G...`) | `FW.txt`, `FW_RAW.md` | HPE MSA 2070 10/25GbE iSCSI SFF Chassis theo Section 4 FAIR. Xuất `FW.txt` (8 lệnh chuẩn, controller `P61071-001`, ports iSCSI kèm `Port Details` 11 trường, 24 SFF slots, `show advanced-settings`) và `FW_RAW.md`. |
| **HPE MSA Chassis 12Gb SAS LFF** | `S1H47-62001` (`1VAD4ZB...`, `2MXD3DG...`) | `FW.txt`, `FW_RAW.md` | HPE MSA 2070 12Gb SAS LFF Chassis theo Section 4 FAIR. Xuất `FW.txt` (8 lệnh chuẩn, midplane `P62783-001`, controller `P61073-001`, ports SAS 12Gb kèm Lanes, 12 LFF slots, `show advanced-settings`) và `FW_RAW.md`. |
| **HPE MSA Chassis 12Gb SAS SFF** | `S1H48-62001` (`1VAD4ZB...`, `2MXD3DG...`) | `FW.txt`, `FW_RAW.md` | HPE MSA 2070 12Gb SAS SFF Chassis theo Section 4 FAIR. Xuất `FW.txt` (8 lệnh chuẩn, controller P61073-001, ports SAS 12Gb kèm Lanes, 24 SFF slots, `show advanced-settings`) và `FW_RAW.md`. |
| **HPE MSA Chassis 32Gb SFF** | `S3T80-62001` (`1VAD4ZB...`, `ACVD23W...`) | `FW.txt`, `FW_RAW.md` | HPE MSA 2070 32Gb FC SFF Chassis theo Section 4 FAIR. Xuất `FW.txt` (7 lệnh chuẩn gồm `show fru secrets detail` / `Midplane Information`, 24 SFF slots, 32Gb ports) và `FW_RAW.md`. |
| **PSU 2U & 5U** | `PMV...` / `DYJW5` / `0R4C4` | `Controller FW, Drive FW, Serial Number Tracking & Test History.txt` | Bóc tách tích hợp 4 phần từ Step 06 (`PCM firmware`, `VPD 40/41 hex diff`) và Step 07 (`VPD 60/61 hex dump`, `Customer VPD validation`). Tự động nhận diện 2U (`DYJW5` 117 dòng) vs 5U (`0R4C4` 116 dòng), phân định `psu0` (PCM 1) hoặc `psu1` (PCM 2). |
| **IO Controller chuẩn** | `SAF...` | `FW.txt`, `VPD.txt` | Tự động phân tích vai trò `ctrla` / `ctrlb` dựa theo thứ tự xuất hiện của SN trong tên thư mục. |
| **IOM RPC73 / 9D57G** | `SAF...` (VPD 49 chứa `RPC73` / `9D57G`) | `FW_VPD.txt` | Nhận diện Canister ME52XX EBOD. Với log `|3898|`, chọn canister theo SN trong VPD 49; PN `RPC73` và `9D57G` lấy bảng validation đến sau `fru_description` (140 dòng), hiển thị nhãn `IOM 9D57G` theo tên gói log. Log cũ giữ 139 dòng. |
| **Chassis 2U** | `SGF...` | `<Target_SN>.txt` | Tổng hợp 4 khối dữ liệu VPD (Midplane, CPLD, Customer VPD hex dump, fru_description). |
| **Chassis 4U (Juno)** | `FVB...` | `FW.txt`, `GETVPD.txt`, `VER.txt`, `VPD.txt`, `Restore Default.txt`, `Provisioning State.txt` | Bộ 6 báo cáo toàn diện, đồng bộ timestamp mili-giây giữa GETVPD và VER, bảo toàn khối số dòng `\|XXXX\|`. |

---

## 🚀 Tính năng nổi bật (v1.8.3)

- ⚡ **Bổ sung Hỗ trợ HPE MSA 2070 iSCSI SFF (`S1H44-62001`) & SAS LFF (`S1H47-62001`)**:
  - `S1H44-62001`: Hỗ trợ toàn diện 8 lệnh FAIR Section-4 (`Product ID: MSA 2070 iSCSI`, controller `P61071-001`), bộ dựng cổng iSCSI chuyên biệt kèm `Port Details` 11 trường và 24 SFF slots.
  - `S1H47-62001`: Hỗ trợ toàn diện 8 lệnh FAIR Section-4 (`Product ID: MSA 2070 SAS`, midplane `P62783-001`, controller `P61073-001`), ports SAS 12Gb kèm Lanes và 12 LFF slots.
  - Xuất bộ đôi báo cáo: `FW.txt` (định dạng CLI sạch) và `FW_RAW.md` (bảng Markdown `Versions` 2 cột & dump YAML).
- 🧪 **Mở rộng Bộ Kiểm Thử Tự Động Toàn Diện (75 Unit Tests)**:
  - Bổ sung 16 unit tests độc lập trong `tests/test_s1h44_reports.py` và `tests/test_s1h47_reports.py`, nâng tổng số lên 75 tests vượt qua 100% byte-for-byte SHA256.
- 🏗 **Kiến trúc Module hóa Tinh gọn 14 Submodules (`module/`)**:
  - Tách biệt rõ ràng 14 submodule chuyên biệt: `log_io`, `extract_chassis_5u`, `extract_rpc73`, `extract_psu`, `extract_juno`, `extract_basic`, `extract_p61070`, `extract_s1h41`, `extract_s1h42`, `extract_s1h44`, `extract_s1h47`, `extract_s1h48`, `extract_s3t80`, `reporting`, `console_style`, `extraction_workflows`, `cli_ui`.
  - Giữ vững 100% khả năng tương thích ngược cho launcher và CLI entrypoint `extract_mfg_logs.py`.
- 🎯 **Mở rộng Dell 5U PN 7PNTN & Chuẩn hóa IOM 9D57G**:
  - Dell 5U `7PNTN`: Trích xuất Fan Controller FW (Step 07), Fan VPD 122–126 (Step 06), chuẩn hóa bố cục VPD 260 dòng.
  - IOM `9D57G`: Nhận diện canister qua VPD 49, giữ bảng validation 140 dòng tới sau `fru_description`, hiển thị chuẩn nhãn `IOM 9D57G` theo tên gói log.
- 🧪 **Bộ Kiểm Thử Tự Động Toàn Diện (43 Unit Tests)**:
  - Mở rộng từ 11 tests lên 43 unit tests kiểm chứng từng byte tất cả các dòng thiết bị và các ca hồi quy.
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
Công cụ sẽ tự động mở giao diện điều khiển màu ANSI và hiển thị các chế độ làm việc tương tác (mặc định `[1]` là Trích xuất trực tiếp từ máy trạm từ xa qua IP + SN).

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
├── extract_mfg_logs.py      # Entrypoint chính (CLI args + dispatch)
├── module/                  # Hệ thống submodule chuyên biệt
│   ├── log_io.py            # Quản lý đọc/ghi, giải nén stream & đường dẫn log
│   ├── extract_basic.py     # Parser cho IO tiêu chuẩn (SAF...) & Chassis 2U
│   ├── extract_chassis_5u.py# Parser cho Dell 5U W47DG & 7PNTN
│   ├── extract_rpc73.py     # Parser cho IOM RPC73 & 9D57G
│   ├── extract_psu.py       # Parser cho PSU 2U DYJW5 & 5U 0R4C4
│   ├── extract_juno.py      # Parser cho Chassis 4U Juno
│   ├── extract_p61070.py    # Parser cho HPE MSA 2070 FC Controller P61070-001
│   ├── extract_s1h41.py     # Parser cho HPE MSA 2070 FC LFF Chassis S1H41-62001
│   ├── extract_s1h42.py     # Parser cho HPE MSA 2070 16Gb FC SFF Chassis S1H42-62001
│   ├── extract_s1h44.py     # Parser cho HPE MSA 2070 10/25GbE iSCSI SFF Chassis S1H44-62001
│   ├── extract_s1h47.py     # Parser cho HPE MSA 2070 12Gb SAS LFF Chassis S1H47-62001
│   ├── extract_s1h48.py     # Parser cho HPE MSA 2070 12Gb SAS SFF Chassis S1H48-62001
│   ├── extract_s3t80.py     # Parser cho HPE MSA 2070 32Gb FC SFF Chassis S3T80-62001
│   ├── extraction_workflows.py # Điều phối quy trình trích xuất (Local, Remote, Batch)
│   ├── reporting.py         # Tổng hợp báo cáo, Cycle Time, Golden Sample diff & chẩn đoán
│   ├── cli_ui.py            # Giao diện tương tác terminal, menu & dialogs
│   ├── console_style.py     # Định nghĩa mã màu ANSI console
│   ├── bridge.py            # Cầu nối SSH direct-tcpip & WinRM TCP Proxy fallback
│   ├── remote_fetcher.py    # Tìm kiếm & tải chọn lọc siêu tốc qua SFTP
│   ├── config.py            # Cấu hình kết nối & đọc config.json
│   ├── ip_utils.py          # Chuẩn hóa IP rút gọn (116.174 / 116174 -> 172.19.116.174)
│   ├── winrm_socket.py      # Socket-like adapter cho WinRM Bridge
│   └── winrm_bridge.ps1     # Kịch bản PowerShell TCP Bridge trên trạm trung gian
├── tests/                   # Bộ 75 kiểm thử tự động toàn diện
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
