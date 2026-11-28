TAG=v1.8.3
TITLE=JA_MFG_Log_Extractor v1.8.3 — Hỗ trợ HPE MSA 2070 iSCSI SFF (S1H44-62001) & SAS LFF (S1H47-62001), 75 Unit Tests
BODY=
## JA_MFG_Log_Extractor v1.8.3 — Hỗ trợ HPE MSA 2070 iSCSI SFF (S1H44-62001) & SAS LFF (S1H47-62001), 75 Unit Tests

Bản cập nhật **v1.8.3** tiếp tục mở rộng hệ sinh thái **HPE MSA 2070** với 2 dòng Chassis mới là **10/25GbE iSCSI SFF (`S1H44-62001`)** và **12Gb SAS LFF (`S1H47-62001`)** theo chuẩn FAIR Section-4 (8 lệnh CLI), nâng tổng số bài kiểm thử tự động lên **75 Unit Tests** đạt 100% tỷ lệ vượt qua.

### 🌟 Điểm nổi bật trong v1.8.3:
- **Hỗ trợ HPE MSA 2070 10/25GbE iSCSI SFF Chassis (`S1H44-62001`)**:
  - Tự động nhận diện PN qua metadata hoặc tên gói log (`Chas S1H44`), `Product ID: MSA 2070 iSCSI`, controller `P61071-001`.
  - Bóc tách 8 lệnh Section-4 với bộ dựng cổng iSCSI chuyên biệt `_render_ports_iscsi_s1h44()` (`Speed(A)`/`Speed(C)` kèm khối 11 trường `Port Details` cho từng cổng), 24 Drive Slots SFF, `show advanced-settings` (26 thuộc tính) và `show certificates` (A & B).
  - Neo dòng `<RESPONSE ...>` trong `_parse_last_xml_command_s1h44()` giúp phân tách chính xác XML `show certificates` sau reset.
- **Hỗ trợ HPE MSA 2070 12Gb SAS LFF Chassis (`S1H47-62001`)**:
  - Tự động nhận diện PN qua metadata hoặc tên gói log (`Chas S1H47`), `Product ID: MSA 2070 SAS`, midplane `P62783-001`, controller `P61073-001`.
  - Bóc tách 8 lệnh Section-4 với bộ dựng cổng SAS 12Gb (`Topo(C)`, `Lanes Expected`, `Active Lanes`, `Disabled Lanes`), 12 Drive Slots LFF (`MSA2070-ENCL-LFF`/`2U12-12Gv3`), `show advanced-settings` và `show certificates` (A & B).
- **Bộ Kiểm Thử Tự Động Toàn Diện (75/75 Unit Tests Pass)**:
  - Bổ sung 16 bài test độc lập trong `tests/test_s1h44_reports.py` (8 tests) và `tests/test_s1h47_reports.py` (8 tests), nâng tổng số test lên 75.
  - Kiểm chứng byte-for-byte 100% SHA256 cho toàn bộ các thiết bị mới và cũ, bảo đảm không có hồi quy.
- **Kiến trúc Module hóa 14 Submodules (`module/`)**:
  - Bổ sung `module/extract_s1h44.py` và `module/extract_s1h47.py` độc lập, bảo toàn tương thích ngược cho entrypoint và CLI arguments.

### 🌐 Phân hệ Kế thừa Toàn vẹn:
- Trích xuất từ xa trực tiếp hoặc qua Indirect Bridge `172.21.168.241` -> `172.19.*.*`.
- Selective Fast Fetch hoàn tất trong 1–3 giây.
- Bảng lọc PASS/FAIL, phân tích Cycle Time, đối soát Golden Sample, và xử lý batch đa luồng.

### Cài đặt & Sử dụng:
Giải nén gói `JA_MFG_Log_Extractor_v1.8.3_Windows_x64.zip`, sao chép `config_sample.json` thành `config.json` nếu chưa có (điền thông tin xác thực SSH/Bridge nếu dùng tính năng Remote), và nhấp đúp vào `Chay_Tool_Log.bat` hoặc thực thi qua dòng lệnh. Giữ lại cấu hình và dữ liệu `reports/` và `downloads/` đang dùng khi cập nhật. Xem chi tiết tại `USERGUIDE.md` và `README.md`.
