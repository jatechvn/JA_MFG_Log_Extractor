TAG=v1.2.0
TITLE=JA_MFG_Log_Extractor v1.2.0 — Bổ sung hỗ trợ trích xuất 2U PSU DYJW5
BODY=
## JA_MFG_Log_Extractor v1.2.0 — Bổ sung hỗ trợ trích xuất 2U PSU DYJW5

Bản cập nhật v1.2.0 bổ sung tính năng tự động nhận diện và trích xuất báo cáo tích hợp `Controller FW, Drive FW, Serial Number Tracking & Test History.txt` cho dòng sản phẩm **2U PSU DYJW5** (Dell ME4 Power Supply Unit).

### Điểm nhấn chính:
- **Tự động nhận diện 2U PSU DYJW5**: Quét nhận dạng chuỗi `DYJW5` và cấu hình `sn_pn_dict` / `psu0` / `PCM 1` tại Step 06 (`write_vpd`) và Step 07 (`vpd_validation`).
- **Phân định bộ nguồn thông minh**: Tự động ánh xạ Serial Number mục tiêu (`PMV1104029G...`) thành `psu0` (PCM 1) hoặc `psu1` (PCM 2).
- **Trích xuất báo cáo kết hợp hoàn chỉnh (116 dòng)**:
  1. *PCM Firmware & VPD CRC* (Step 06 `write_vpd`): 6 dòng thông tin firmware, cấu trúc VPD và mã CRC của cả 2 bộ PCM 1 & PCM 2.
  2. *VPD Raw Hex Dump* (Step 06 `write_vpd`): 7 dòng hex dump từ bảng đối soát sau nạp VPD (VPD 40 cho `psu0` hoặc VPD 41 cho `psu1`), dải offset `0000:` đến `0050:`.
  3. *Customer VPD Hex Dump* (Step 07 `vpd_validation`): 16 dòng hex dump của VPD 60 (cho `psu0`) hoặc VPD 61 (cho `psu1`) gồm offset `0000:` đến `0090:`, phân cách dòng trắng và dải `0360:` đến `0390:`.
  4. *Customer VPD Validation Table* (Step 07 `vpd_validation`): 84 dòng bảng kiểm thử customer VPD từ Step 07 kết thúc tại `result: match` của khối `fru_description`.
- **Khớp mẫu tham chiếu 100%**: Đã kiểm chứng khớp chính xác từng byte với file mẫu tham chiếu `Controller FW, Drive FW, Serial Number Tracking & Test History.txt`.

### Cài đặt & Sử dụng:
Giải nén gói `JA_MFG_Log_Extractor_v1.2.0_Windows_x64.zip` và nhấp đúp vào `Chay_Tool_Log.bat`. Xem chi tiết tại `USERGUIDE.md` và `README.md`.
