TAG=v1.0.0
TITLE=JA_MFG_Log_Extractor v1.0.0 — Trích xuất Log CTP Tự Động IO & Chassis 2U/4U
BODY=
## JA_MFG_Log_Extractor v1.0.0 — Trích xuất Log CTP Tự Động IO & Chassis 2U/4U

Bản phát hành chính thức đầu tiên của công cụ trích xuất báo cáo log kiểm thử sản xuất CTP / Avocado dành cho các dòng IO Controller, Chassis 2U và Chassis 4U Juno.

### Điểm nhấn chính:
- **Hỗ trợ 3 dòng sản phẩm chính**:
  - **IO Controller (`SAF...`)**: Trích xuất chuẩn xác `FW.txt` và `VPD.txt` tự động theo vai trò controller `ctrla` / `ctrlb`.
  - **Chassis 2U (`SGF...`)**: Trích xuất báo cáo tổng hợp `<SN>.txt`.
  - **Chassis 4U Juno (`FVB...`)**: Trích xuất đủ 6 file báo cáo tiêu chuẩn: `FW.txt`, `GETVPD.txt`, `VER.txt`, `VPD.txt`, `Restore Default.txt`, `Provisioning State.txt`.
- **Đồng bộ hóa Timestamp**: Ghép cặp chính xác giữa `GETVPD` và `VER` cùng chu kỳ test trong file log tiện ích (`uut_list_utility_logs.log`), hỗ trợ tự động bung file nén `.tar.gz`.
- **Bảo toàn số dòng kiểm toán**: Giữ lại các khối số dòng `|XXXX|` trong `VPD.txt` và `Restore Default.txt` theo đúng quy chuẩn MES.
- **Đường dẫn xuất thông minh**: Tự động lưu vào thư mục SN tương ứng bên trong thư mục mẹ, chống lồng thư mục trùng lặp.
- **Khởi chạy thích ứng Windows**: Tự động mở bằng Windows Terminal (`wt.exe`), PowerShell hoặc CMD.

### Cài đặt & Sử dụng:
Giải nén toàn bộ gói `JA_MFG_Log_Extractor_v1.0.0_Windows_x64.zip` và nhấp đúp vào file `Chay_Tool_Log.bat`. Xem hướng dẫn chi tiết tại `USERGUIDE.md` và `README.md`.
