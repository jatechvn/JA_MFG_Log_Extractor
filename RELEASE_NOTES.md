TAG=v1.4.0
TITLE=JA_MFG_Log_Extractor v1.4.0 — Hỗ trợ Chassis Dell 5U84 (PN W47DG) & Đồng bộ định dạng xuất xưởng
BODY=
## JA_MFG_Log_Extractor v1.4.0 — Hỗ trợ Chassis Dell 5U84 (PN W47DG) & Đồng bộ định dạng xuất xưởng

Bản cập nhật v1.4.0 chính thức bổ sung hỗ trợ dòng Chassis Dell 5U84 (Part Number W47DG), mở rộng phạm vi trích xuất lên 7 chủng loại thiết bị và chuẩn hóa 100% byte-for-byte theo mẫu báo cáo xuất xưởng của Dell.

### Điểm nhấn chính:
- **Hỗ trợ Chassis Dell 5U84 (PN W47DG)**: Tự động phân định Chassis 5U Dell với Chassis 2U tiêu chuẩn, bóc tách chính xác bộ đôi file báo cáo `FW.txt` (21 dòng) và `VPD.txt` (216 dòng).
- **Trích xuất FW.txt chính xác 100%**: Thu thập cấu trúc Midplane VPD structure (`0x13`), CRC (`0xAA7722D1`), CPLD (`0x20`) từ Step 02 với firmware expander `6.0.0.54`, 8 dòng firmware Sled 1 & Sled 2 Element 0..3, và 8 địa chỉ SAS expander (`exp:0` đến `exp:7`) từ Step 07.
- **Trích xuất VPD.txt toàn diện**: Kết hợp chính xác 18 phân đoạn gồm VPD 16 Midplane A hex dump, Customer VPD 18 hex dump, 8 bảng Canister VPD 48 hex diff (`exp:0..7`) từ Step 06 (`write_vpd`), 7 khối kết quả lệnh `set_midplanevpd 2..8` và bảng Customer VPD validation table đầy đủ từ Step 07.
- **Tương thích Hồi quy Tuyệt đối**: Bảo toàn độ chính xác và tương thích trên toàn bộ các dòng IO Controller chuẩn, IOM RPC73, Chassis 2U, Chassis 4U Juno, PSU 2U DYJW5 và PSU 5U 0R4C4.
- **Cập nhật Kịch bản Mẫu & Thống kê**: Tích hợp chủng loại `Chassis 5U` vào bảng kết quả tổng hợp batch và file CSV mẫu `mau_danh_sach_log.csv`.

### Cài đặt & Sử dụng:
Giải nén gói `JA_MFG_Log_Extractor_v1.4.0_Windows_x64.zip` và nhấp đúp vào `Chay_Tool_Log.bat` hoặc thực thi qua dòng lệnh. Xem chi tiết tại `USERGUIDE.md` và `README.md`.
