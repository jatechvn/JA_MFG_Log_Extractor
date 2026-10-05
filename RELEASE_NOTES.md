TAG=v1.1.0
TITLE=JA_MFG_Log_Extractor v1.1.0 — Bổ sung hỗ trợ trích xuất IOM RPC73 (FW_VPD.txt)
BODY=
## JA_MFG_Log_Extractor v1.1.0 — Bổ sung hỗ trợ trích xuất IOM RPC73 (FW_VPD.txt)

Bản cập nhật v1.1.0 bổ sung tính năng tự động nhận diện và trích xuất báo cáo tích hợp `FW_VPD.txt` cho dòng sản phẩm **IOM RPC73** (Dell ME52XX EBOD Canister).

### Điểm nhấn chính:
- **Tự động nhận diện IOM RPC73**: Kiểm tra nhận dạng chuỗi `RPC73` trong khối `|0608|VPD 49 (1) - Canister Customer ...` tại bước kiểm thử `vpd_validation`.
- **Trích xuất báo cáo kết hợp `FW_VPD.txt`**:
  1. *Canister Firmware* (Step 02 `check_and_load_fw_test`): Bóc tách 9 dòng thông tin FW Canister theo đúng thiết bị `/dev/sg1` (`ctrla`) hoặc `/dev/sg2` (`ctrlb`).
  2. *FW Match* (Step 02): Trích xuất 30 dòng đối chiếu FW PCD của controller tương ứng.
  3. *VPD 49 Hex Dump* (Step 07 `vpd_validation`): Trích xuất 15 dòng hex dump của Canister Customer VPD (offset `0000:` đến `00a0:`, kết hợp `0360:` và `0370:`), tự động ánh xạ đúng Serial Number của Canister.
  4. *Customer VPD Validation* (Step 07): Trích xuất 83 dòng bảng kiểm thử customer VPD kết thúc tại `result: match` của khối `fru_description`.
- **Định vị Step 2 thông minh**: Tự động chọn đúng bước `check_and_load_fw_test` có chứa thông tin `Canister firmware` (loại trừ các bước kiểm tra phụ).
- **Khớp mẫu tham chiếu 100%**: Đã kiểm chứng khớp chính xác từng byte với file mẫu tham chiếu `FW_VPD - Sample.txt`.

### Cài đặt & Sử dụng:
Giải nén gói `JA_MFG_Log_Extractor_v1.1.0_Windows_x64.zip` và nhấp đúp vào `Chay_Tool_Log.bat`. Xem chi tiết tại `USERGUIDE.md` và `README.md`.
