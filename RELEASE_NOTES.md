TAG=v1.7.0
TITLE=JA_MFG_Log_Extractor v1.7.0 — Chọn log theo kết quả, sơ đồ IP và thao tác nhanh
BODY=
## JA_MFG_Log_Extractor v1.7.0 — Chọn log theo kết quả, sơ đồ IP và thao tác nhanh

Bản cập nhật **v1.7.0** bổ sung chọn log theo PASS/FAIL, sơ đồ IP 3 Line, gợi ý Clipboard/lịch sử và thao tác nhanh khi phân tích log tại `<App_Dir>/reports/`.

### Thay đổi trong v1.7.0
- Chọn `P`/`F` chỉ lấy gói có kết quả phù hợp; không có gói khớp thì yêu cầu chọn lại. Hỗ trợ `L`, `A` và dải số.
- Bảng co cho terminal 80 cột, dùng danh sách khi cửa sổ hẹp hơn. Thời gian kết thúc dựa trên mtime của file, không phải xác nhận độc lập từ MES.
- Sơ đồ 3 Line, IP rút gọn, gợi ý Clipboard và lịch sử 5 IP/SN gần nhất; `[O]` mở báo cáo, `[C]` copy đường dẫn.
- Tái sử dụng SSH trên cùng máy, fail-fast theo host và xuất `retry_failed.csv` khi batch lỗi.
- `--list-only` không tải log và không cập nhật history; unit test cô lập history để bảo toàn dữ liệu thật.
- Launcher và tài liệu đồng bộ v1.7.0. PSU 2U giữ dòng hex `00a0:` trong báo cáo 117 dòng.

### Điểm nhấn chính:
- **Chạy Trực tiếp & Trích xuất Từ xa qua Liên kết Gián tiếp (Menu `[1]` / `--ip` & `--sn`)**:
  - Tự động định tuyến kết nối trực tiếp hoặc qua cầu nối Jump-Host (`172.21.168.241` / `172.19.208.133`) tới các trạm kiểm thử (`172.19.*.*`) bằng kênh SSH `direct-tcpip` và cơ chế tự động chuyển đổi dự phòng sang WinRM TCP Proxy (`winrm_bridge.ps1`).
  - Hỗ trợ nhập nhanh IP rút gọn 2 octet (`116.174` hoặc `116174` $\rightarrow$ `172.19.116.174`), tìm kiếm nhiều Serial Number cùng lúc (`SN1, SN2`), và giới hạn số bản test mới nhất (`--latest 1`).
  - **Selective Fast Fetch**: Chỉ nén và tải các file văn bản nhẹ cần thiết cho phân tích (`debug.log`, `results.json`, `*.log`, `ctp_log_metadata.yaml`, `job.log`, `enc_logs/*`), bỏ qua `serial_logs/`, `sysinfo/`, `.journal.sqlite`, `results.html`, giúp quá trình tải và trích xuất hoàn tất chỉ trong **1–3 giây** và tự động dọn sạch file tạm. Hỗ trợ cờ `--keep-raw-zip` nếu muốn lưu thêm bản `.zip` đầy đủ vào `<App_Dir>/downloads/<IP>/`.
- **Lưu Báo cáo Tập trung trong Thư mục Ứng dụng (`<App_Dir>/reports/`)**:
  - Toàn bộ báo cáo trích xuất của mọi chế độ làm việc (Remote IP+SN, Local Folder/Archive, Batch Scan, CSV Import, Cycle Time) mặc định được lưu gọn gàng vào `<App_Dir>/reports/<Target_SN>/` và `<App_Dir>/reports/Cycle_Time_Summary.csv`.
- **Nâng cấp Bóc tách Log Lỗi VPD (`VPD rendering failed`)**:
  - Tự động xử lý các bản log kiểm thử bị dừng giữa chừng tại bước `vpd_validation` (ví dụ `EC(30005) VPD rendering failed for chassis FRU-REV`), vẫn trích xuất đầy đủ phần dữ liệu VPD hiện có, gắn cờ cảnh báo `WARN` và tự động sinh báo cáo chẩn đoán lỗi `ERROR_SUMMARY.txt`.
- **Đóng gói Sẵn sàng Chạy (Self-Contained Portable Runtime)**:
  - Tích hợp sẵn `paramiko`, `cryptography`, `bcrypt`, `pynacl` cùng các thư viện chuẩn cần thiết vào `python_runtime` Portable — chạy ngay trên mọi máy Windows không cần cài đặt Python hay thư viện ngoài.

### Cài đặt & Sử dụng:
Giải nén gói `JA_MFG_Log_Extractor_v1.7.0_Windows_x64.zip`, sao chép `config_sample.json` thành `config.json` nếu chưa có (điền thông tin xác thực SSH/Bridge nếu dùng tính năng Remote), và nhấp đúp vào `Chay_Tool_Log.bat` hoặc thực thi qua dòng lệnh. Giữ lại cấu hình và dữ liệu reports/downloads đang dùng khi cập nhật. Xem chi tiết tại `USERGUIDE.md` và `README.md`.
