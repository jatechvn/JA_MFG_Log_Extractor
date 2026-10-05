TAG=v1.3.0
TITLE=JA_MFG_Log_Extractor v1.3.0 — Bổ sung hỗ trợ trích xuất PSU 5U 0R4C4 & Sửa lỗi Batch Scan
BODY=
## JA_MFG_Log_Extractor v1.3.0 — Bổ sung hỗ trợ trích xuất PSU 5U 0R4C4 & Sửa lỗi Batch Scan

Bản cập nhật v1.3.0 bổ sung tính năng tự động nhận diện và trích xuất báo cáo tích hợp `Controller FW, Drive FW, Serial Number Tracking & Test History.txt` cho cả 2 dòng sản phẩm nguồn Dell ME4: **PSU 2U DYJW5** và **PSU 5U 0R4C4**, đồng thời khắc phục triệt để lỗi quét thư mục hàng loạt (Batch Subfolders Scan).

### Điểm nhấn chính:
- **Bổ sung hỗ trợ PSU 5U 0R4C4**: Tự động nhận diện dòng nguồn 5U (Part Number `0R4C4`, FRU Description `PWR SPLY,5U,ME4`, I2C bus 32 addr=15h/17h), bóc tách chính xác 116 dòng cho cả `psu0` (PCM 1) và `psu1` (PCM 2) khớp 100% byte-for-byte với mẫu chuẩn.
- **Tự động nhận diện động chủng loại PSU**: Giao diện và bảng thống kê hiển thị chính xác tên dòng: `PSU 5U (0R4C4)` vs `PSU 2U (DYJW5)`.
- **Khắc phục lỗi quét Batch Subfolders Scan**: Điều chỉnh logic nhận diện thư mục log trực tiếp để tránh việc thư mục mẹ bị nhận nhầm là trạm log đơn lẻ, cho phép quét tự động toàn bộ thư mục test PSU 5U.
- **Cập nhật mẫu CSV**: Thêm log mẫu PSU 5U vào `mau_danh_sach_log.csv`.

### Cài đặt & Sử dụng:
Giải nén gói `JA_MFG_Log_Extractor_v1.3.0_Windows_x64.zip` và nhấp đúp vào `Chay_Tool_Log.bat`. Xem chi tiết tại `USERGUIDE.md` và `README.md`.
