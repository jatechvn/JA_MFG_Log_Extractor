# Nhật ký thay đổi (CHANGELOG)

Tất cả các thay đổi đáng chú ý của dự án **JA_MFG_Log_Extractor** sẽ được ghi chép tại tài liệu này.

Định dạng dựa trên [Keep a Changelog](https://keepachangelog.com/vi/1.0.0/),
và tuân thủ chuẩn [Semantic Versioning](https://semver.org/lang/vi/).

---

## [v1.3.0] - 2026-10-05

### 🚀 Nâng cấp & Tính năng mới
- **Bổ sung hỗ trợ dòng PSU 5U 0R4C4 (Dell ME4)**:
  - Tự động nhận diện dòng nguồn 5U (Part Number `0R4C4`, FRU Description `PWR SPLY,5U,ME4`, bus=32 addr=15h/17h).
  - Trích xuất báo cáo kết hợp hoàn chỉnh `Controller FW, Drive FW, Serial Number Tracking & Test History.txt` (đúng 116 dòng) cho cả `PMV...` psu0 (PCM 1) và psu1 (PCM 2) với độ chính xác 100% byte-for-byte.
  - Phân loại và hiển thị linh hoạt dòng sản phẩm trên giao diện console và bảng tổng hợp: `PSU 5U (0R4C4)` vs `PSU 2U (DYJW5)`.
- **Sửa lỗi quét thư mục hàng loạt (Batch Folder Scan Fix)**:
  - Khắc phục sự cố bộ nhận diện thư mục log trực tiếp khiến `scan_parent_folder_for_logs` nhận nhầm thư mục mẹ là trạm log đơn lẻ do tìm kiếm đệ quy `test-results`.
  - Hỗ trợ quét tự động trơn tru toàn bộ danh mục test log 5U PSU và các dòng thiết bị khác.
- **Cập nhật File CSV Mẫu**:
  - Bổ sung đường dẫn mẫu của cả PSU 5U (`0R4C4`) và PSU 2U (`DYJW5`) vào file CSV mẫu (`mau_danh_sach_log.csv`).

---

## [v1.2.0] - 2026-10-05

### 🚀 Nâng cấp & Tính năng mới
- **Bổ sung hỗ trợ dòng 2U PSU DYJW5 (Dell ME4)**:
  - Tự động nhận diện cấu hình kiểm thử PSU DYJW5 qua tên thư mục chứa `DYJW5` hoặc qua cấu hình `sn_pn_dict` / `psu0` / `PCM 1` trong Step 07.
  - Tự động phân định `psu0` (PCM 1) hoặc `psu1` (PCM 2) tương ứng với từng Serial Number mục tiêu (`PMV1104029G...`).
  - Trích xuất báo cáo kết hợp hoàn chỉnh `Controller FW, Drive FW, Serial Number Tracking & Test History.txt` (116 dòng) khớp 100% byte-for-byte với mẫu xuất xưởng:
    1. **PCM Firmware & VPD CRC** (Step 06 `write_vpd`): 6 dòng thông tin firmware, cấu trúc VPD và mã băm CRC của cả 2 bộ PCM 1 & PCM 2.
    2. **VPD Raw Hex Dump** (Step 06 `write_vpd`): Bóc tách bảng hex dump từ bảng so sánh sau nạp VPD (VPD 40 cho `psu0` hoặc VPD 41 cho `psu1`), trích xuất dải offset `0000:` đến `0050:`.
    3. **Customer VPD Hex Dump** (Step 07 `vpd_validation`): Trích xuất bảng hex dump VPD 60 (cho `psu0`) hoặc VPD 61 (cho `psu1`), trích xuất dải offset `0000:` đến `0090:`, phân cách dòng trắng và dải `0360:` đến `0390:`.
    4. **Customer VPD Validation Table** (Step 07 `vpd_validation`): 84 dòng bảng kiểm thử customer VPD từ `Checking psu0/psu1 customer VPD` đến dòng `result: match` của thuộc tính `fru_description`.
- **Nâng cấp Regex Nhận diện Serial Number**:
  - Bổ sung nhận diện tiền tố Serial Number dòng PSU (`PM[A-Z0-9]{10,}`), cho phép tự động quét và nhận diện đồng thời cả 2 Serial Number PSU (`psu0` và `psu1`) trong tên thư mục log.
  - Hỗ trợ menu chọn nhanh 1-chạm hiển thị rõ `(psu0 / PCM 1)` và `(psu1 / PCM 2)`.

---

## [v1.1.0] - 2026-10-05

### 🚀 Nâng cấp & Tính năng mới
- **Bổ sung hỗ trợ dòng IOM RPC73**:
  - Tự động nhận diện loại log IOM RPC73 khi khối `|0608|VPD 49 (1) - Canister Customer ...` trong bước `vpd_validation` chứa chuỗi `RPC73`.
  - Tự động bóc tách và tạo báo cáo tích hợp `FW_VPD.txt` gồm 4 phần chuẩn:
    1. **Canister Firmware**: Bóc tách 9 dòng thông tin Canister firmware (từ `Canister firmware` đến `Canister CPLD`) trong Step 2 (`check_and_load_fw_test`) theo đúng bộ điều khiển `ctrla` (`/dev/sg1`) hoặc `ctrlb` (`/dev/sg2`).
    2. **FW Match**: Bóc tách 30 dòng (6 khối) đối chiếu firmware PCD trong Step 2 theo đúng component controller tương ứng.
    3. **VPD 49 Hex Dump**: Trích xuất 15 dòng hex dump của Canister Customer VPD trong Step 7 (`vpd_validation`) gồm header, dải offset `0000:` đến `00a0:`, và 2 dòng `0360:` / `0370:`, tự động ánh xạ đúng Serial Number của canister.
    4. **Customer VPD Validation**: Trích xuất 83 dòng bảng kiểm thử customer VPD trong Step 7 kết thúc tại `|3993|result: match` của khối `fru_description`.
- **Cơ chế định vị Step 2 thông minh**:
  - Tự động quét và chọn đúng bước `check_and_load_fw_test` có chứa thông tin `Canister firmware` (Step 02), loại trừ các bước kiểm tra FW phụ không chứa log canister.
- **Tự động nhận diện Controller từ VPD 49**:
  - Cho phép xác định vai trò `ctrla` / `ctrlb` trực tiếp từ dữ liệu Serial Number nhúng trong hex dump của VPD 49, đảm bảo độ chính xác tuyệt đối ngay cả khi cấu trúc tên thư mục bị thay đổi.

---

## [v1.0.0] - 2026-09-29

### 🚀 Nâng cấp & Tính năng mới
- **Hỗ trợ toàn diện 3 dòng sản phẩm**:
  - **IO Controller (`SAF...`)**: Tự động nhận diện vai trò `ctrla` / `ctrlb` dựa theo vị trí SN trong tên thư mục log raw. Trích xuất chính xác `FW.txt` và `VPD.txt`.
  - **Chassis 2U (`SGF...`)**: Trích xuất file báo cáo tổng hợp `<SN>.txt` gồm 4 khối chuẩn (Midplane structure, Midplane VPD, Customer VPD hex dump và fru_description).
  - **Chassis 4U Juno (`FVB...`)**: Trích xuất bộ 6 file báo cáo tiêu chuẩn: `FW.txt`, `GETVPD.txt`, `VER.txt`, `VPD.txt`, `Restore Default.txt`, `Provisioning State.txt`.
- **Đồng bộ hóa Timestamp & Ghép cặp chu kỳ test**:
  - Lệnh `GETVPD` và `VER` trong log 4U được ghép cặp chính xác theo cùng chu kỳ test (sai lệch miligiây) thông qua định danh `gemcli_*__test_<timestamp>`.
  - Tự động bóc tách và giải nén file log tiện ích `uut_list_utility_logs.log` trực tiếp từ file nén `.tar.gz` trong thư mục `enc_logs/obmcdump_*/`.
- **Bảo toàn khối số dòng kiểm toán (`|XXXX|`)**:
  - Hỗ trợ lưu giữ nguyên vẹn tiền tố số dòng ở đầu các file `VPD.txt` và `Restore Default.txt` phục vụ đối soát MES.
- **Định tuyến đường dẫn xuất báo cáo thông minh (Smart Export Routing)**:
  - Tự động lưu file vào thư mục mang tên "SN tương ứng" bên trong thư mục mẹ của log đầu vào (`<Parent_Dir>/<Target_SN>/`).
  - Tích hợp cơ chế phát hiện và chống lồng lặp 2 lần tên SN (`Anti-nesting guard`).
  - Hỗ trợ đường dẫn Windows siêu dài (`\\?\` prefix) vượt qua giới hạn 260 ký tự `MAX_PATH`.
- **Giao diện đa chế độ & Trình khởi chạy 1-chạm**:
  - Cung cấp 4 chế độ làm việc: Xử lý đơn lẻ, Quét tự động cây thư mục cha, Nhập danh sách từ CSV/TXT, và Tạo file CSV mẫu.
  - File khởi chạy `Chay_Tool_Log.bat` thông minh tự động thích ứng: Windows Terminal (`wt.exe`) ➔ PowerShell ➔ CMD.

### 🐛 Sửa lỗi & Tối ưu hóa
- Xử lý tương thích đa dạng cấu trúc thư mục kiểm thử: `latest/test-results`, `job-*/test-results`, hoặc `test-results` trực tiếp.
- Khắc phục triệt để lỗi đường dẫn bị lệch cấp thư mục khi input truyền vào thư mục con `latest` hoặc `job-*`.
- Đảm bảo 100% khớp từng byte đối soát với mẫu tiêu chuẩn xuất xưởng.

### 📦 Phát hành
- Đồng bộ version `1.0.0+1` trên toàn bộ hệ sinh thái: `extract_mfg_logs.py`, `Chay_Tool_Log.bat`, `ABOUT.txt`, `README.md`, `CHANGELOG.md`, `USERGUIDE.md`, `RELEASE_NOTES.md`.
