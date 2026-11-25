# Hướng dẫn sử dụng JA_MFG_Log_Extractor v1.8.2

Tài liệu hướng dẫn chi tiết các thao tác vận hành, cấu hình kết nối từ xa (Indirect Bridge) và sử dụng công cụ **JA_MFG_Log_Extractor** dành cho kỹ sư kiểm thử (TE), kỹ sư sản xuất (PE), kỹ sư phân tích lỗi (FA) và nhân viên vận hành trạm test.

### Thao tác mới trong v1.8.2

- **Kiến trúc Module hóa (`module/`)**: Phân tách rõ ràng 12 module độc lập (`log_io`, `extract_chassis_5u`, `extract_rpc73`, `extract_psu`, `extract_juno`, `extract_basic`, `extract_p61070`, `extract_s1h41`, `extract_s1h42`, `extract_s1h48`, `extract_s3t80`, `reporting`, `console_style`, `extraction_workflows`, `cli_ui`), bảo toàn tương thích tuyệt đối cho CLI và launcher.
- **Hỗ trợ Dòng Sản phẩm HPE MSA 2070 (FAIR)**:
  - `P61070-001`: Xuất `FW.txt` (5 lệnh chuẩn CLI) và `FW_RAW.md` (bảng Markdown `Versions` 2 cột & dump YAML) từ `test_mfg_restore_default_setting` và `test_restore_defaults_factory_remove_certs`.
  - `S1H41-62001`: Xuất `FW.txt` (6 lệnh chuẩn gồm `show license`, đầy đủ Controller A & B, Ports A & B) và `FW_RAW.md`.
  - `S1H42-62001`: Xuất `FW.txt` (8 lệnh chuẩn gồm `show frus detail`, `show frus secrets detail`, 24 SFF slots, Ports 16Gb và `show advanced-settings`) và `FW_RAW.md`.
  - `S1H48-62001`: Xuất `FW.txt` (8 lệnh chuẩn gồm `show frus detail`, `show frus secrets detail`, 24 SFF slots, Ports SAS 12Gb kèm Lanes và `show advanced-settings`) và `FW_RAW.md`.
  - `S3T80-62001`: Xuất `FW.txt` (7 lệnh chuẩn gồm `show fru secrets detail` / `Midplane Information`, 24 SFF slots, 32Gb ports) và `FW_RAW.md`.
- **Hỗ trợ Dell 5U 7PNTN & Chuẩn hóa IOM 9D57G**:
  - `7PNTN`: Trích xuất Fan Controller FW ở Step 07, Fan VPD 122–126 ở Step 06, chuẩn hóa VPD 260 dòng.
  - `9D57G`: Nhận diện canister qua VPD 49, bảng validation 140 dòng tới sau `fru_description`, hiển thị chuẩn nhãn `IOM 9D57G` theo tên gói log.
- **Tính năng thông minh kế thừa từ v1.7.x**:
  - Sơ đồ 3 Line, chọn nhanh IP/SN từ Clipboard hoặc lịch sử; trong bảng log, `P` chọn PASS, `F` chọn FAIL, `L` chọn mới nhất, `A` chọn tất cả.
  - Hộp thoại chọn file/thư mục Windows native `[B]`/`[F]`, mở nhanh báo cáo trong Explorer `[O]`, copy đường dẫn `[C]`.
  - `--list-only` chỉ xem kết quả không tải log; batch xuất lỗi vào `retry_failed.csv`.

---

## 1. Khởi động chương trình & Cấu hình Kết nối Từ xa (`config.json`)

### 1.1. Khởi động
Nhấp đúp vào tệp tin **`Chay_Tool_Log.bat`**.

Chương trình sẽ tự động kiểm tra môi trường:
- Nếu chạy từ **PowerShell**, **CMD**, hoặc kết nối từ xa (**SSH**, **WinRM**): Chạy trực tiếp trên console hiện tại mà không tạo cửa sổ tiến trình ngầm.
- Nếu double-click từ **Windows Explorer**: Tự động mở trong **Windows Terminal (`wt.exe`)** nếu có, hoặc tiếp tục trên **CMD**.
- Bộ mã hiển thị Unicode UTF-8 (`chcp 65001`) và mã màu ANSI tự động kích hoạt.
- Ưu tiên sử dụng môi trường Python nhúng đi kèm trong thư mục `python_runtime` (đã tích hợp sẵn `paramiko`), hoặc dùng Python hệ thống.

### 1.2. Cấu hình Kết nối Từ xa (`config.json`)
Để sử dụng Chế độ `[1]` (Trích xuất trực tiếp từ máy trạm từ xa qua IP + SN), sao chép tệp `config_sample.json` thành `config.json` ngay trong thư mục ứng dụng và điền thông tin xác thực:
```json
{
  "ssh_username": "User",
  "ssh_password": "<Mật_khẩu_trạm_test>",
  "ssh_port": 22,
  "remote_log_path": "C:/Users/User/ctp/logs",
  "default_days": 0,
  "default_latest": 1,
  "connection_mode": "auto",
  "bridge_host": "172.21.168.241",
  "bridge_port": 22,
  "bridge_username": "Checked",
  "bridge_password": "<Mật_khẩu_máy_cầu_nối>",
  "bridge_transport": "auto",
  "bridge_winrm_port": 5985
}
```
> **Lưu ý**: File `config.json` đã được đưa vào `.gitignore` để bảo mật mật khẩu nội bộ. Khi chạy trên máy mạng văn phòng (`172.21.*.*`), chế độ `"connection_mode": "auto"` sẽ tự động đi xuyên qua trạm cầu nối `172.21.168.241` để kết nối tới các trạm test `172.19.*.*`.

---

## 2. Các chế độ làm việc (Menu 1–7)

Khi khởi động, màn hình menu chính hiển thị 7 lựa chọn. Toàn bộ báo cáo phân tích mặc định được lưu tập trung tại **`<Thư_mục_App>/reports/<Target_SN>/`**:

```text
┌─────────────────────────────────────────────────────────────────────┐
│  CÔNG CỤ TRÍCH XUẤT LOG TỰ ĐỘNG (IO, CHASSIS & PSU UNITS) - v1.8.2  │
└─────────────────────────────────────────────────────────────────────┘

Vui lòng chọn chế độ làm việc:
   [1] 🌐 Trích xuất trực tiếp từ Máy Trạm Từ Xa qua IP + SN (Indirect Bridge -> ./reports)
   [2] Trích xuất 1 thư mục / file nén log nội bộ (Single Folder / Archive -> ./reports)
   [3] Quét và trích xuất hàng loạt từ thư mục gốc (Batch Subfolders & Archives -> ./reports)
   [4] Đọc danh sách trích xuất từ file CSV / TXT (Batch CSV Import -> ./reports)
   [5] Tạo file CSV mẫu (mau_danh_sach_log.csv)
   [6] ⏱ Phân tích nhanh Cycle Time & Chẩn đoán lỗi (Cycle Time & Failure Analyzer)
   [7] 🔬 Đối chiếu kết quả với thư mục Golden Sample (Golden Sample Diff Verifier)

   👉 Chọn nhanh số (1-7) hoặc nhấn Enter để chọn [1]:
```

### Chế độ [1]: 🌐 Trích xuất trực tiếp từ Máy Trạm Từ Xa qua IP + SN (Indirect Bridge -> `./reports`)
- **Bước 1**: Chọn trên **Sơ đồ IP 3 Line (`Line 3` │ `Line 2` │ `Line 1`)** hoặc nhập thủ công địa chỉ IP máy trạm test:
  - **Chọn trực quan trên Sơ đồ**: Dùng phím mũi tên `↑` `↓` `←` `→` di chuyển qua 60 trạm trong `Line 3 (.172–.199)`, `Line 2 (.141–.160)`, `Line 1 (.121–.140)` và nhấn `Enter` để chọn.
  - **Gõ tắt 1 octet theo sơ đồ**: `.174` hoặc `174` $\rightarrow$ tự động mở rộng thành `172.19.116.174`
  - **Gõ tắt 2 octet cuối**: `116.174` hoặc `116174` $\rightarrow$ tự động mở rộng thành `172.19.116.174`
  - **IP đầy đủ bất kỳ**: `172.19.116.174`, `172.21.168.241`, v.v.
- **Bước 2**: Nhập 1 hoặc nhiều Serial Number cần lấy báo cáo, phân tách bằng dấu phẩy (hoặc nhấn `Enter` để tự động lấy SN từ Clipboard).
- **Bước 3**: Chọn số lượng bản log mới nhất cần lấy cho mỗi SN (nhấn `Enter` để mặc định lấy `1` bản mới nhất, hoặc nhập `0` để lấy tất cả).
- **Bước 4**: Chọn có lưu lại bản nén `.zip` gốc đầy đủ vào `./downloads/<IP>/` hay không (nhấn `Enter` = Không, chỉ tải chọn lọc **Selective Fast Fetch** và trích xuất thẳng vào `./reports/<SN>/` trong 1–3 giây).
- **Sau khi hoàn tất**:
  - Báo cáo phân tích nằm gọn trong `<App_Dir>/reports/<SN>/` kèm `Cycle_Time_Summary.csv` và `ERROR_SUMMARY.txt` (nếu có lỗi).
  - Nhấn **`[O]`** để mở ngay thư mục báo cáo trong Windows Explorer, **`[R]`** để quay về Menu chính, hoặc **`[Enter]`/`[Q]`** để thoát.

### Chế độ [2]: Trích xuất 1 thư mục / file nén log nội bộ (`-> ./reports`)
- Dán đường dẫn thư mục log, đường dẫn file nén (`.zip`, `.tar.gz`, `.tgz`, `.tar.xz`), hoặc nhập trực tiếp IP trạm test (`116.174` -> tự động chuyển sang chế độ Remote).
- **Mẹo nhanh**: Gõ **`B`** để mở cửa sổ chọn thư mục Windows, hoặc gõ **`F`** để mở cửa sổ chọn file nén `.zip`/`.tar.gz`.
- Nhấn `Enter` ở bước chọn thư mục xuất để lưu mặc định vào **`<App_Dir>/reports/<Target_SN>`**.

### Chế độ [3]: Quét và trích xuất hàng loạt (Batch Subfolders & Archives `-> ./reports`)
- Áp dụng khi bạn có một thư mục cha chứa nhiều thư mục log con hoặc các file `.zip` log của nhiều máy test.
- Công cụ tự động duyệt đệ quy, trích xuất song song đa luồng (mặc định 4 luồng) vào `<App_Dir>/reports/<Target_SN>/`, hiển thị bảng tổng hợp kèm `Cycle Time` và xuất file **`<App_Dir>/reports/Cycle_Time_Summary.csv`**.

### Chế độ [4]: Đọc danh sách trích xuất từ file CSV / TXT (Batch CSV Import `-> ./reports`)
- Hỗ trợ cả đường dẫn thư mục lẫn đường dẫn file `.zip` / `.tar.gz` trong cột `LogPath`. Nếu để trống `OutputBaseDir`, báo cáo sẽ tự động lưu vào `<App_Dir>/reports/<Target_SN>/`.

### Chế độ [5]: Tạo file CSV mẫu
- Tự động tạo tệp `mau_danh_sach_log.csv` chuẩn định dạng ngay trong thư mục công cụ.

### Chế độ [6]: ⏱ Phân tích nhanh Cycle Time & Chẩn đoán lỗi (Cycle Time & Failure Analyzer)
- Quét siêu tốc 1 thư mục log, file `.zip` hoặc cả thư mục mẹ để lấy thông tin thời gian kiểm thử (`Total Cycle Time`, `Avocado Active Time`, `Part_Number`, `Station_ID`, `Employee_ID`, `Pass/Fail/Skip`) và xuất bảng **`<App_Dir>/reports/Cycle_Time_Summary.csv`**.

### Chế độ [7]: 🔬 Đối chiếu kết quả với thư mục Golden Sample (Golden Sample Diff Verifier)
- Kiểm tra đối chứng 100% Byte-for-Byte giữa thư mục báo cáo vừa trích xuất và thư mục mẫu chuẩn (Golden Sample) theo mã băm **SHA256**, kích thước byte, số dòng và `unified_diff`.

---

## 3. Quy cách tệp tin báo cáo sinh ra (`<App_Dir>/reports/<Target_SN>/`)

- **IO Controller chuẩn (`SAF...`)**: `FW.txt`, `VPD.txt`.
- **IO HPE MSA (`P61070-001`)**: nhận diện theo PN trong metadata hoặc tên gói log (kèm SN 10 ký tự như `1VAD4YB000`/`1VAD4YB007`, `2MXD2YG0S0`/`2MXD2YG0S2`). Sinh 2 tệp `FW.txt` (định dạng MSA CLI theo Section 4 FAIR) và `FW_RAW.md` (dữ liệu thô `key: value` + bảng Markdown 2 cột `Versions`). Gồm đúng 5 lệnh: `# show firmware-bundles`, `# show system`, `# show frus detail`, `# show configuration` (giữ bảng `Versions` 2 cột A & B sạch không dính cột, các phần còn lại lọc riêng Controller/IOM/Expander/Ports/FRU của SN đích) từ step `test_mfg_restore_default_setting`, và `# show certificates` sau reset cuối cùng từ step `test_restore_defaults_factory_remove_certs` kèm đúng dòng trạng thái thật trong log.
- **IOM RPC73 / 9D57G (`SAF...` có VPD 49 chứa 'RPC73')**: Dòng SP ưu tiên PN trong tên gói log. Báo cáo `FW_VPD.txt`. Với log dùng mã `|3898|`, chọn canister theo SN trong VPD 49: PN `RPC73` và `9D57G` lấy bảng validation đến hết dấu phân cách sau `fru_description` (140 dòng theo mẫu hiện hành), giữ CRLF ở cuối file. Log kiểu cũ giữ báo cáo 139 dòng.
- **Chassis 5U Dell (`SGF...` / `W47DG` / `5U84`)**: `FW.txt` (21 dòng), `VPD.txt` (216 dòng).
- **Chassis 5U Dell (`7PNTN`)**: nhận diện theo PN trong metadata hoặc tên gói log. `FW.txt` (31 dòng) thêm 5 cặp Fan Controller từ step 07 trước phần Sled. `VPD.txt` (260 dòng theo mẫu) lấy VPD 16 đến `0090`, VPD 18 đến `00a0` rồi thêm `0360`/`0370`, WWN và các nhóm Customer VPD 18 từ step 07. Từ step 06 lấy cột trái `0000:`–`0050:` của cả 8 Canister VPD 48 và 5 Fan VPD `122–126`, giữ offset. Các mã của Customer VPD được giữ nguyên. Nếu dữ liệu bắt buộc thiếu hoặc mâu thuẫn, công cụ báo lỗi trước khi ghi báo cáo.
- **Chassis HPE MSA (`S1H41-62001`)**: nhận diện theo PN trong metadata hoặc tên gói log (kèm SN 10 ký tự như `1VAD4ZB004`, `ACVD1DW001`). Sinh 2 tệp `FW.txt` (định dạng MSA CLI theo Section 5 FAIR) và `FW_RAW.md` (dữ liệu thô `key: value` + bảng Markdown 2 cột `Versions` và `PSU Versions`). Gồm đúng 6 lệnh: `# show firmware-bundles all` (XML cuối có trạng thái `Active/Default` từ `test_rbod_rfwd` hoặc fallback `test_restore_default_factory_firmware`), `# show system`, `# show license`, `# show frus detail`, `# show configuration` (giữ đủ 2 controller A & B, bảng `Versions` và `PSU Versions` 2 cột không dính nhau, Ports A & B có `Speed(C)`, Disks/Slots/Disk Groups/Pools/Enclosures/FRUs) từ `test_mfg_restore_default_setting`, và `# show certificates` sau reset cuối cùng (cả 2 controller A & B) từ `test_restore_defaults_factory_remove_certs`.
- **Chassis HPE MSA (`S1H42-62001`)**: nhận diện theo PN trong metadata hoặc tên gói log (kèm SN 10 ký tự như `1VAD4ZB031`, `2MXD3DG09F`). Sinh 2 tệp `FW.txt` (định dạng MSA CLI theo Section 4 FAIR) và `FW_RAW.md` (dữ liệu thô `key: value` + bảng Markdown 2 cột `Versions` và `PSU Versions`). Gồm đúng 8 lệnh: `# show firmware-bundles`, `# show system`, `# show license`, `# show frus detail`, `# show frus secrets detail` (`Midplane Information`), `# show configuration` (đầy đủ 2 controller A & B, bảng `Versions` và `PSU Versions` 2 cột không dính nhau, Ports A & B kèm `Speed(A)`/`Speed(C)` 16Gb, 24 Drive Slots SFF, `MSA2070-ENCL-SFF`/`2U24-12Gv3`), `# show certificates` sau reset cuối cùng (cả 2 controller A & B) từ `test_restore_defaults_factory_remove_certs`, và `# show advanced-settings` (26 thuộc tính chuẩn từ `test_mfg_restore_default_setting`).
- **Chassis HPE MSA (`S1H48-62001`)**: nhận diện theo PN trong metadata hoặc tên gói log (kèm SN 10 ký tự như `1VAD4ZB02C`, `2MXD3DG0BS`). Sinh 2 tệp `FW.txt` (định dạng MSA CLI theo Section 4 FAIR) và `FW_RAW.md` (dữ liệu thô `key: value` + bảng Markdown 2 cột `Versions` và `PSU Versions`). Gồm đúng 8 lệnh tương tự `S1H42-62001` (`# show firmware-bundles` đến `# show advanced-settings`), với `Product ID: MSA 2070 SAS`, controller `P61073-001`, Ports A & B chuẩn SAS 12Gb (`Topo(C)`, `Lanes Expected`, `Active Lanes`, `Disabled Lanes`, không có `Speed(C)`/SFP) và 24 Drive Slots SFF.
- **Chassis HPE MSA (`S3T80-62001`)**: nhận diện theo PN trong metadata hoặc tên gói log (kèm SN 10 ký tự như `1VAD4ZB02Z`, `ACVD23W00X`). Sinh 2 tệp `FW.txt` (định dạng MSA CLI theo Section 4 FAIR) và `FW_RAW.md` (dữ liệu thô `key: value` + bảng Markdown 2 cột `Versions` và `PSU Versions`). Gồm đúng 7 lệnh: `# show firmware-bundles`, `# show system`, `# show license`, `# show fru detail`, `# show fru secrets detail` (`Midplane Information`), `# show configuration` (đầy đủ 2 controller A & B, bảng `Versions` và `PSU Versions` 2 cột không dính nhau, Ports A & B kèm `Speed(A)`/`Speed(C)`, 24 Drive Slots SFF, `MSA2070-ENCL-SFF`/`2U24-12Gv3`) từ `test_mfg_restore_default_setting`, và `# show certificates` sau reset cuối cùng (cả 2 controller A & B) từ `test_restore_defaults_factory_remove_certs`.
- **Chassis 2U (`SGF...`)**: `<SN>.txt`.
- **Chassis 4U Juno (`FVB...`)**: Bộ 6 file (`FW.txt`, `GETVPD.txt`, `VER.txt`, `VPD.txt`, `Restore Default.txt`, `Provisioning State.txt`).
- **PSU 2U & 5U (`PMV...` / `DYJW5` / `0R4C4`)**: `Controller FW, Drive FW, Serial Number Tracking & Test History.txt` (117 dòng cho 2U `DYJW5` / 116 dòng cho 5U `0R4C4`).
- **Báo cáo Phụ trợ & Chẩn đoán Tự động**:
  - **`reports/Cycle_Time_Summary.csv`**: Chứa 24 cột thống kê thời gian test, trạm test, nhân viên và trạng thái từng máy.
  - **`reports/<SN>/ERROR_SUMMARY.txt`**: Tự động sinh ra khi máy test có bước `FAIL`/`ERROR`, dừng giữa chừng (`VPD rendering failed`), hoặc có cảnh báo `mismatch`.

---

## 4. Chạy trực tiếp qua dòng lệnh (CLI / PowerShell / WinRM / SSH)

### Các cờ lệnh Kết nối Từ xa (Remote Indirect Bridge):
- `--ip <IP>`: Địa chỉ IP máy trạm test (vd: `116.174`, `116174`, hoặc `172.19.116.174`).
- `--sn <SN1,SN2>`: Một hoặc nhiều Serial Number cần tìm và trích xuất.
- `--latest <N>`: Chỉ lấy `N` bản log mới nhất của mỗi SN (mặc định đọc từ `config.json`: `1`).
- `--days <D>`: Chỉ tìm log trong `D` ngày gần nhất (`0` = không giới hạn).
- `--keep-raw-zip`: Lưu thêm bản `.zip` đầy đủ của thư mục log vào `<App_Dir>/downloads/<IP>/`.
- `--connection <auto|direct|bridge>`: Chế độ kết nối (mặc định: `auto`).
- `--bridge-transport <auto|ssh|winrm>`: Giao thức cầu nối (mặc định: `auto`).

### Các cờ lệnh Nội bộ & Batch:
- `--input-dir <log_dir_or_zip> [--target-sn <sn>] [--output-dir <out_dir>]`: Trích xuất 1 thư mục hoặc file nén `.zip`/`.tar.gz` (mặc định xuất vào `./reports`).
- `--batch-dir <thư_mục_gốc>`: Quét và trích xuất đa luồng tất cả log con / file nén vào `./reports`.
- `--csv-file <đường_dẫn_csv>`: Chạy hàng loạt đa luồng theo file CSV/TXT.
- `--workers <số_luồng>`: Số luồng xử lý song song khi chạy batch (mặc định: `4`).
- `--cycle-time`: Chỉ phân tích nhanh Cycle Time & Test Metadata và xuất `./reports/Cycle_Time_Summary.csv`.
- `--verify-sample <thư_mục_sample>`: Đối chiếu 100% Byte-for-Byte (SHA256) kết quả trích xuất với thư mục mẫu chuẩn.
- `--diagnose`: Bắt buộc tạo báo cáo chẩn đoán `ERROR_SUMMARY.txt`.
