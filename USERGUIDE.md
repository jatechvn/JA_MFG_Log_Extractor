# Hướng dẫn sử dụng JA_MFG_Log_Extractor v1.6.0

Tài liệu hướng dẫn chi tiết các thao tác vận hành, cấu hình kết nối từ xa (Indirect Bridge) và sử dụng công cụ **JA_MFG_Log_Extractor** dành cho kỹ sư kiểm thử (TE), kỹ sư sản xuất (PE), kỹ sư phân tích lỗi (FA) và nhân viên vận hành trạm test.

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
│  CÔNG CỤ TRÍCH XUẤT LOG TỰ ĐỘNG (IO, CHASSIS & PSU UNITS) - v1.6.0  │
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
- **Bước 1**: Nhập địa chỉ IP máy trạm test. Hỗ trợ 3 định dạng:
  - Rút gọn 2 octet có dấu chấm: `116.174` $\rightarrow$ tự động mở rộng thành `172.19.116.174`
  - Rút gọn 6 chữ số liền: `116174` $\rightarrow$ tự động mở rộng thành `172.19.116.174`
  - IP đầy đủ: `172.19.116.174`
- **Bước 2**: Nhập 1 hoặc nhiều Serial Number cần lấy báo cáo, phân tách bằng dấu phẩy (ví dụ: `SGFVN2633836284` hoặc `PMV1104546G0017, PMV1104546G002E`).
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
- **IOM RPC73 (`SAF...` có VPD 49 chứa 'RPC73')**: `FW_VPD.txt` (139 dòng).
- **Chassis 5U Dell (`SGF...` / `W47DG` / `5U84`)**: `FW.txt` (21 dòng), `VPD.txt` (216 dòng).
- **Chassis 2U (`SGF...`)**: `<SN>.txt`.
- **Chassis 4U Juno (`FVB...`)**: Bộ 6 file (`FW.txt`, `GETVPD.txt`, `VER.txt`, `VPD.txt`, `Restore Default.txt`, `Provisioning State.txt`).
- **PSU 2U & 5U (`PMV...` / `DYJW5` / `0R4C4`)**: `Controller FW, Drive FW, Serial Number Tracking & Test History.txt` (116 dòng).
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
