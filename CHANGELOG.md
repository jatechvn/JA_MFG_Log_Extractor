# Nhật ký thay đổi (CHANGELOG)

Tất cả các thay đổi đáng chú ý của dự án **JA_MFG_Log_Extractor** sẽ được ghi chép tại tài liệu này.

Định dạng dựa trên [Keep a Changelog](https://keepachangelog.com/vi/1.0.0/),
và tuân thủ chuẩn [Semantic Versioning](https://semver.org/lang/vi/).

---

## [v1.6.0] - 2026-10-15

### 🚀 Nâng cấp & Tính năng mới
- **Chạy Trực tiếp & Trích xuất Từ xa qua Liên kết Gián tiếp (`Indirect Bridge` — Menu `[1]` / `--ip` & `--sn`)**:
  - Tích hợp trọn vẹn phân hệ kết nối từ xa và cầu nối gián tiếp (`module/bridge.py`, `module/remote_fetcher.py`, `module/winrm_socket.py`, `module/winrm_bridge.ps1`, `module/config.py`, `module/ip_utils.py`) từ hệ sinh thái `seagate_log_downloader`.
  - Cho phép chạy trực tiếp trên máy kỹ sư dải mạng văn phòng (`172.21.*.*`), tự động định tuyến trực tiếp hoặc qua trạm cầu nối Jump-Host (`172.21.168.241` / `172.19.208.133`) tới toàn bộ trạm kiểm thử (`172.19.*.*`) qua kênh SSH `direct-tcpip` kèm cơ chế dự phòng tự động sang WinRM TCP Proxy.
  - Hỗ trợ nhập nhanh IP rút gọn 2 octet (`116.174` hoặc `116174` $\rightarrow$ `172.19.116.174`), tìm kiếm 1 hoặc nhiều Serial Number cùng lúc (`SN1, SN2`), và giới hạn số bản test mới nhất (`--latest`).
  - **Cơ chế Selective Fast Fetch**: Chỉ nén và tải các file văn bản nhẹ cần thiết cho phân tích (`debug.log`, `results.json`, `*.log`, `ctp_log_metadata.yaml`, `job.log`, `enc_logs/*`), tự động loại bỏ các thư mục nặng (`serial_logs/`, `sysinfo/`, `.journal.sqlite`, `results.html`), giúp tải và trích xuất hoàn tất chỉ trong **1–3 giây** và tự động dọn sạch thư mục tạm (hỗ trợ đường dẫn dài `\\?\` trên Windows).
  - Hỗ trợ cờ `--keep-raw-zip` để lưu thêm bản `.zip` đầy đủ của thư mục log vào `<App_Dir>/downloads/<IP>/` khi cần lưu trữ nguyên bản.
- **Lưu Báo cáo Tập trung trong Thư mục Ứng dụng (`<App_Dir>/reports/`)**:
  - Quy hoạch toàn bộ đường dẫn xuất mặc định của mọi chế độ (Remote IP+SN, Single Folder/Archive, Batch Subfolders, CSV Import, Cycle Time) về `<App_Dir>/reports/<Target_SN>/` và `<App_Dir>/reports/Cycle_Time_Summary.csv`.
- **Nâng cấp Bóc tách Log Lỗi VPD (`VPD rendering failed`)**:
  - Bổ sung cơ chế nhận diện điểm kết thúc dự phòng trong `extract_vpd()` và `extract_chassis_vpd()` khi bước `vpd_validation` bị dừng sớm bởi lỗi `VPD rendering failed` (ví dụ `EC(30005) VPD rendering failed for chassis FRU-REV`), đảm bảo vẫn xuất được báo cáo phần dữ liệu VPD đã chạy, cảnh báo `WARN` và tự động sinh `ERROR_SUMMARY.txt`.
- **Đóng gói Sẵn sàng Chạy (Self-Contained Portable Runtime)**:
  - Tích hợp sẵn `paramiko`, `cryptography`, `bcrypt`, `pynacl`, `cffi` cùng các thư viện chuẩn cần thiết vào `python_runtime` Portable.

---

## [v1.5.0] - 2026-10-14

### 🚀 Nâng cấp & Tính năng mới (Group 1 & Group 2)
- **Phân tích Cycle Time & Test Metadata Tự động + Xuất `Cycle_Time_Summary.csv` (Menu `[5]` / `--cycle-time`)**:
  - Tự động trích xuất `Test duration` (Wall-clock Cycle Time từ file `<unit>.log`), thời gian chạy Avocado (`results.json`), `Start_Time`, `End_Time`, `Station_ID`, `Employee_ID`, `Part_Number`, `Script_Name` và số lượng bước test (`Total`, `Pass`, `Fail`, `Error`, `Skip`).
  - Hiển thị trực tiếp cột `Cycle Time` trên bảng kết quả console sau mỗi lần trích xuất đơn lẻ hoặc hàng loạt.
  - Tự động xuất bảng tổng hợp `Cycle_Time_Summary.csv` (mã hóa `utf-8-sig` mở trực tiếp bằng Excel) phục vụ báo cáo hiệu suất dây chuyền (PE/IE).
  - Bổ sung chế độ chuyên biệt `[5]` trên Menu và cờ `--cycle-time` để quét nhanh thời gian test hàng loạt mà không cần trích xuất toàn bộ báo cáo FW/VPD.
- **Đọc Trực tiếp File Nén Log (`.zip`, `.tar.gz`, `.tgz`, `.tar.xz`)**:
  - Cho phép truyền trực tiếp đường dẫn file nén log vào cả chế độ đơn lẻ, quét thư mục hàng loạt và file CSV mà không cần giải nén thủ công ra ổ cứng.
  - Cơ chế **Selective Unpacking** chỉ giải nén các file log/metadata cần thiết vào bộ nhớ tạm và tự động bỏ qua các thư mục nặng không dùng đến (`serial_logs/`, `sysinfo/`, `.journal.sqlite`, `results.html`), giúp rút ngắn thời gian đọc file nén xuống chỉ còn 1–3 giây và tự động dọn sạch thư mục tạm sau khi xử lý.
  - Bổ sung thư viện chuẩn `lzma` và `bz2` vào `python_runtime` di động để giải nén trực tiếp các gói `obmcdump_*.tar.xz` của dòng 4U Juno.
- **Kiểm tra Toàn vẹn Báo cáo (Sanity & Completeness Guard)**:
  - Tự động kiểm tra số lượng file báo cáo kỳ vọng theo từng dòng sản phẩm (1 file cho 2U Chassis/PSU/RPC73, 2 file cho IO/5U Dell, 6 file cho 4U Juno) và đảm bảo dung lượng > 0 byte.
  - Tự động quét nội dung báo cáo để cảnh báo sớm (`WARN`) nếu xuất hiện các dòng `result: mismatch`, `-> mismatch`, `| FAIL |`, hoặc `FW mismatch`.
- **Tự động Chẩn đoán Nguyên nhân Lỗi (`ERROR_SUMMARY.txt` & `--diagnose`)**:
  - Khi phát hiện bước kiểm thử bị `FAIL` hoặc `ERROR` trong `results.json` (hoặc khi có cảnh báo mismatch / cờ `--diagnose`), công cụ tự động trích xuất tên bước lỗi, thời gian chạy, `fail_reason` và 15 dòng log lỗi cuối cùng từ `debug.log` của bước đó để ghi ra file `ERROR_SUMMARY.txt`.
- **Hộp thoại Chọn Thư mục/File Windows Gốc (`[B]` / `[F]`) & Phím tắt Sau Trích xuất (`[O]` / `[R]`)**:
  - Tại mọi bước nhập đường dẫn, hỗ trợ gõ `B` (chọn thư mục) hoặc `F` (chọn file nén `.zip`/`.tar.gz`) để mở hộp thoại Windows Explorer gốc thông qua PowerShell `.NET System.Windows.Forms` (hoạt động 100% trên Python Portable không cần `tkinter`).
  - Sau khi trích xuất xong, hiển thị thanh tác vụ nhanh: nhấn `[O]` mở ngay thư mục báo cáo vừa xuất trong Windows Explorer, `[R]` quay lại Menu chính để làm tiếp máy khác, hoặc `[Enter/Q]` để thoát.
- **Công cụ Đối soát Mẫu Chuẩn Golden Sample (Menu `[6]` / `--verify-sample`)**:
  - Đối chiếu tự động 100% Byte-for-Byte giữa thư mục báo cáo vừa trích xuất và thư mục mẫu chuẩn (Golden Sample) theo mã băm `SHA256`, dung lượng byte và số dòng; tự động in `unified_diff` nếu có bất kỳ dòng nào sai khác.
- **Xử lý Hàng loạt Đa luồng (`--workers`, mặc định 4 luồng)**:
  - Tích hợp hàng đợi đa luồng (`queue.Queue` + `threading.Thread`) kèm khóa đồng bộ hiển thị console (`_PRINT_LOCK`), tăng tốc độ trích xuất hàng loạt qua CSV hoặc quét thư mục mẹ lên gấp 3–4 lần.

---

## [v1.4.0] - 2026-10-13

### 🚀 Nâng cấp & Tính năng mới
- **Bổ sung hỗ trợ dòng Chassis Dell 5U84 (Part Number W47DG)**:
  - Tự động nhận diện cấu hình kiểm thử Dell 5U Chassis qua tên thư mục hoặc log chứa `W47DG`, `5U_Dell`, `5U84ENC`, `5U84NPCM`, `ASSY,CHAS,RKMNT,5U`.
  - Phân định thông minh giữa Chassis 2U tiêu chuẩn (`SGF...` xuất ra `<SN>.txt`) và Chassis 5U Dell (`SGF...` xuất ra bộ đôi `FW.txt` và `VPD.txt`).
  - Trích xuất chuẩn xác 100% byte-for-byte theo mẫu xuất xưởng của Dell 5U:
    1. **FW.txt** (21 dòng):
       - Khối 1: Thông tin Midplane VPD structure (`0x13`), CRC (`0xAA7722D1`), CPLD (`0x20`) trích xuất từ Step 02 (`check_and_load_fw_test` với expander firmware `6.0.0.54`).
       - Khối 2: 8 dòng firmware Sled 1 & Sled 2 Element 0..3 (`6.0.0.54`).
       - Khối 3: 8 dòng SAS addresses expander sắp xếp chuẩn từ `exp:0` đến `exp:7` từ Step 07 (`vpd_validation`).
    2. **VPD.txt** (216 dòng):
       - Section 1: VPD 16 (1) Midplane A hex dump (`0000:` đến `00c0:`) từ Step 07 với độ rộng chuẩn 71 ký tự.
       - Section 2: Reading customer VPD ID = 18 hex dump (`0000:` đến `00b0:`) từ Step 07.
       - Sections 3-10: 8 khối bảng hex diff Canister VPD 48 của các expander `exp:0` đến `exp:7` từ Step 06 (`write_vpd`), được chuẩn hóa header và địa chỉ hex (`0000:` đến `0070:` cho exp:0, `0000:` đến `0050:` cho exp:1..7).
       - Sections 11-17: 7 khối kết quả lệnh và so sánh `set_midplanevpd 2` đến `set_midplanevpd 8` từ Step 07.
       - Section 18: Bảng Customer VPD validation table đầy đủ từ `name: part_number` đến dòng `result: match` của `fru_description` (`ASSY,CHAS,RKMNT,5U84NPCM`).
- **Nâng cấp Cơ chế Nhận diện & Trích xuất Hàng loạt**:
  - Tích hợp nhận diện `Chassis 5U` vào bảng thống kê tổng hợp batch kết quả.
  - Cập nhật kịch bản mẫu CSV (`mau_danh_sach_log.csv`) bổ sung cấu hình dòng 5U Dell (`W47DG`).
  - Đảm bảo tính tương thích hồi quy 100% đối với toàn bộ các dòng sản phẩm hiện hữu (IO Controller chuẩn, IOM RPC73, Chassis 2U, Chassis 4U Juno, PSU 2U DYJW5, PSU 5U 0R4C4).

---

## [v1.3.1] - 2026-10-06

### 🚀 Nâng cấp & Tính năng mới
- **Tương thích Thực thi Từ xa & Môi trường Headless (WinRM / SSH / CI)**:
  - Nâng cấp kịch bản khởi chạy `Chay_Tool_Log.bat`: Tự động nhận diện phiên làm việc từ xa (WinRM, SSH, PowerShell Remoting, non-interactive CI), thực thi trực tiếp tại console hiện tại mà không tạo cửa sổ process ngầm bị cô lập (`start ""`).
  - Loại bỏ hoàn toàn sự cố thoát đột ngột (zero output) khi chạy `.\Chay_Tool_Log.bat` qua WinRM/SSH trên máy trạm Windows Server/Windows 10/11 xưởng.
  - Tự động bỏ qua lệnh `pause` khi chạy có tham số CLI hoặc trong phiên remote/không có desktop session (`SESSIONNAME`).
- **Xử lý An toàn Dòng Nhập Stdin & Ngăn ngừa EOFError**:
  - Tích hợp hàm `safe_input` và kiểm tra `sys.stdin.isatty()` cho cơ chế chọn phím nhanh `get_single_key_choice`.
  - Hỗ trợ truyền dữ liệu qua đường ống (piped input, vd: `echo 4 | Chay_Tool_Log.bat`), tự động chọn mặc định khi gặp EOF mà không crash.
- **Tách biệt và Chuẩn hóa Cấu trúc Dự án**:
  - Di chuyển toàn bộ mã nguồn, tài liệu, kịch bản đóng gói và lịch sử Git sang workspace phát triển chuyên dụng (`D:\OS-Software\OneDrive\OpenClaw_Workspace\JA_PROJECT\PROJECT_PY\JA_MFG_Log_Extractor`).
  - Giải phóng thư mục dữ liệu sản xuất `D:\JA_TESTER\LOGS_ANL`, chỉ lưu trữ dữ liệu log thô và báo cáo trích xuất theo đúng nghiệp vụ kiểm thử.

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
