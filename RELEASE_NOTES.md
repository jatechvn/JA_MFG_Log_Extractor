TAG=v1.8.0
TITLE=JA_MFG_Log_Extractor v1.8.0 — Kiến trúc Module hóa, Hỗ trợ HPE MSA 2070 (P61070/S1H41/S3T80), Dell 5U 7PNTN & IOM 9D57G
BODY=
## JA_MFG_Log_Extractor v1.8.0 — Kiến trúc Module hóa, Hỗ trợ HPE MSA 2070 (P61070/S1H41/S3T80), Dell 5U 7PNTN & IOM 9D57G

Bản cập nhật lớn **v1.8.0** đánh dấu bước chuyển mình quan trọng của hệ thống với kiến trúc module hóa toàn diện (`module/`), mở rộng khả năng trích xuất chuyên sâu cho 3 dòng thiết bị **HPE MSA 2070** theo chuẩn FAIR (`P61070-001`, `S1H41-62001`, `S3T80-62001`), hỗ trợ **Dell 5U PN 7PNTN**, chuẩn hóa **IOM 9D57G**, đồng thời mở rộng bộ kiểm thử tự động lên **43 Unit Tests** đạt 100% tỷ lệ vượt qua.

### 🌟 Điểm nổi bật trong v1.8.0:
- **Kiến trúc Module hóa Tinh gọn (`module/`)**:
  - Tách mã nguồn nguyên khối thành 10 module độc lập chuyên trách (`log_io`, `extract_basic`, `extract_chassis_5u`, `extract_rpc73`, `extract_psu`, `extract_juno`, `extract_p61070`, `extract_s1h41`, `extract_s3t80`, `extraction_workflows`, `reporting`, `cli_ui`, `console_style`).
  - Bảo toàn 100% tương thích ngược caller entrypoint và CLI arguments.
- **Hỗ trợ 3 Dòng Thiết bị HPE MSA 2070 (Chuẩn FAIR)**:
  - **IO Controller `P61070-001`**: Trích xuất 5 lệnh Section 4 FAIR (`show firmware-bundles`, `show system`, `show frus detail`, `show configuration` giữ bảng `Versions` 2 cột A & B độc lập, lọc riêng target SN, và `show certificates` sau reset cuối). Sinh bộ đôi `FW.txt` (định dạng CLI sạch) và `FW_RAW.md` (bảng Markdown `Versions` 2 cột kèm dump YAML).
  - **Chassis FC LFF `S1H41-62001`**: Trích xuất 6 lệnh Section 5 FAIR gồm `show firmware-bundles all` (XML cuối có trạng thái `Active/Default`), `show system`, `show license`, `show frus detail`, `show configuration` (giữ đủ 2 controller A & B, bảng `Versions` và `PSU Versions` 2 cột, Ports A & B kèm `Speed(C)`, Disks/Slots/Pools/FRUs), và `show certificates` (cả A & B). Sinh `FW.txt` và `FW_RAW.md`.
  - **Chassis 32Gb FC SFF `S3T80-62001`**: Trích xuất 7 lệnh Section 4 FAIR gồm `show firmware-bundles`, `show system`, `show license`, `show fru detail`, `show fru secrets detail` (`Midplane Information`), `show configuration` (24 drive slots SFF, Ports 32Gb kèm `Speed(A)`/`Speed(C)`), và `show certificates`. Sinh `FW.txt` và `FW_RAW.md`.
- **Hỗ trợ Dell 5U PN `7PNTN`**:
  - Trích xuất `FW.txt` (31 dòng: bổ sung 5 cặp Fan Controller từ Step 07 trước Sled) và `VPD.txt` (260 dòng: VPD 16 đến 0090, VPD 18 đến 00a0 + 0360/0370, WWN, Customer VPD 18, Fan VPD 122–126 và Canister VPD 48 từ Step 06).
- **Chuẩn hóa IOM `9D57G` & RPC73**:
  - Nhận diện canister qua VPD 49; với log mã `|3898|`, chọn canister theo SN trong VPD 49, PN `RPC73` và `9D57G` lấy bảng validation đến hết dấu phân cách sau `fru_description` (140 dòng), bảo toàn CRLF cuối file.
  - Hiển thị nhãn dòng sản phẩm `IOM 9D57G` trong banner, bảng kết quả và CSV khi tên gói mang mã `9D57G`.
- **Kiểm thử Toàn diện (43/43 Unit Tests Pass)**:
  - 43 bài test tự động kiểm chứng 100% byte-for-byte SHA256 cho toàn bộ các thiết bị mới và cũ, bảo đảm không có hồi quy.
- **Tích hợp XML Parser vào Python Runtime Nhúng**:
  - Bổ sung thư viện chuẩn `xml` vào `python_runtime` Portable giúp chạy trơn tru độc lập trên mọi máy trạm Windows.

### 🌐 Phân hệ Kế thừa Toàn vẹn:
- Trích xuất từ xa trực tiếp hoặc qua Indirect Bridge `172.21.168.241` -> `172.19.*.*`.
- Selective Fast Fetch hoàn tất trong 1–3 giây.
- Bảng lọc PASS/FAIL, phân tích Cycle Time, đối soát Golden Sample, và xử lý batch đa luồng.

### Cài đặt & Sử dụng:
Giải nén gói `JA_MFG_Log_Extractor_v1.8.0_Windows_x64.zip`, sao chép `config_sample.json` thành `config.json` nếu chưa có (điền thông tin xác thực SSH/Bridge nếu dùng tính năng Remote), và nhấp đúp vào `Chay_Tool_Log.bat` hoặc thực thi qua dòng lệnh. Giữ lại cấu hình và dữ liệu `reports/` và `downloads/` đang dùng khi cập nhật. Xem chi tiết tại `USERGUIDE.md` và `README.md`.
