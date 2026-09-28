# Nhật ký thay đổi (CHANGELOG)

Tất cả các thay đổi đáng chú ý của dự án **JA_MFG_Log_Extractor** sẽ được ghi chép tại tài liệu này.

Định dạng dựa trên [Keep a Changelog](https://keepachangelog.com/vi/1.0.0/),
và tuân thủ chuẩn [Semantic Versioning](https://semver.org/lang/vi/).

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
