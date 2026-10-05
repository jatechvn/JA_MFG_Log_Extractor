TAG=v1.3.1
TITLE=JA_MFG_Log_Extractor v1.3.1 — Hỗ trợ thực thi CLI Remote (WinRM/SSH) & Tách biệt không gian lưu trữ
BODY=
## JA_MFG_Log_Extractor v1.3.1 — Hỗ trợ thực thi CLI Remote (WinRM/SSH) & Tách biệt không gian lưu trữ

Bản cập nhật v1.3.1 hoàn thiện khả năng điều khiển tự động hóa từ xa qua mạng (WinRM, SSH, PowerShell Remoting, non-interactive CI), khắc phục triệt để lỗi process bị cô lập, đồng thời di chuyển và chuẩn hóa cấu trúc dự án độc lập với thư mục dữ liệu kiểm thử.

### Điểm nhấn chính:
- **Tương thích Thực thi Từ xa & CLI**: Trình khởi chạy `Chay_Tool_Log.bat` tự động phát hiện phiên remote (WinRM / SSH / không có `SESSIONNAME`) hoặc các lệnh có đối số CLI để thực thi trực tiếp tại console hiện tại mà không tạo cửa sổ process ngầm bị cô lập (`start ""`).
- **Tự động hóa không gián đoạn**: Bỏ qua lệnh `pause` khi chạy từ xa hoặc qua tham số CLI (`--help`, `--csv-file`, `--batch-dir`, `--input-dir`), giúp kịch bản tự động hóa và remote CI chạy trơn tru mà không bị nghẽn tiến trình.
- **Xử lý An toàn Stdin (Pipes / Non-TTY)**: Tích hợp hàm `safe_input` và kiểm tra `sys.stdin.isatty()`, bảo đảm các luồng dữ liệu truyền qua pipe hoặc chạy ngầm không bị crash bởi lỗi EOFError.
- **Tách biệt Không gian Dự án & Dữ liệu Log**: Di chuyển toàn bộ mã nguồn, tài liệu, kịch bản build và kho lưu trữ Git về workspace dự án riêng biệt (`D:\OS-Software\OneDrive\OpenClaw_Workspace\JA_PROJECT\PROJECT_PY\JA_MFG_Log_Extractor`), giải phóng thư mục `D:\JA_TESTER\LOGS_ANL` để chỉ chứa dữ liệu log và báo cáo kiểm thử.

### Cài đặt & Sử dụng:
Giải nén gói `JA_MFG_Log_Extractor_v1.3.1_Windows_x64.zip` và nhấp đúp vào `Chay_Tool_Log.bat` hoặc thực thi qua dòng lệnh. Xem chi tiết tại `USERGUIDE.md` và `README.md`.
