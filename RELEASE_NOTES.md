TAG=v1.8.2
TITLE=JA_MFG_Log_Extractor v1.8.2 — Hỗ trợ HPE MSA 2070 12Gb SAS SFF (S1H48-62001) & 59 Unit Tests
BODY=
## JA_MFG_Log_Extractor v1.8.2 — Hỗ trợ HPE MSA 2070 12Gb SAS SFF (S1H48-62001) & 59 Unit Tests

Bản cập nhật **v1.8.2** hoàn thiện thêm hệ sinh thái dòng sản phẩm **HPE MSA 2070** với việc bổ sung parser chuyên biệt cho **Chassis 12Gb SAS SFF (`S1H48-62001`)** theo chuẩn FAIR Section-4 (8 lệnh CLI kèm bộ dựng cổng SAS chuyên biệt), đồng thời mở rộng bộ kiểm thử tự động lên **59 Unit Tests** đạt tỷ lệ vượt qua 100%.

### 🌟 Điểm nổi bật trong v1.8.2:
- **Hỗ trợ HPE MSA 2070 12Gb SAS SFF Chassis (`S1H48-62001`)**:
  - Tự động nhận diện PN qua metadata hoặc tên thư mục log (`Chas S1H48`).
  - Bóc tách đầy đủ 8 lệnh Section-4: `show firmware-bundles`, `show system`, `show license`, `show frus detail`, `show frus secrets detail` (`Midplane Information`), `show configuration` (bộ dựng cổng SAS 12Gb: `Topo(C)`, `Lanes Expected`, `Active Lanes`, `Disabled Lanes` không có `Speed(C)`/SFP, 24 SFF slots), `show advanced-settings` (26 thuộc tính chuẩn, hỗ trợ dict & XML fallback), và `show certificates` sau reset cuối cùng (cả 2 controller A & B).
  - Xuất bộ đôi báo cáo chuẩn: `FW.txt` (định dạng CLI sạch) và `FW_RAW.md` (bảng Markdown `Versions` 2 cột kèm dump YAML).
  - Xác thực chéo target SN qua midplane, SKU, chassis midplane, fru-tlasn, và fru-oemsn.
- **Bộ Kiểm Thử Tự Động Toàn Diện (59/59 Unit Tests Pass)**:
  - Bổ sung 8 bài test độc lập trong `tests/test_s1h48_reports.py`, nâng tổng số test lên 59.
  - Kiểm chứng byte-for-byte 100% SHA256 cho toàn bộ các thiết bị mới và cũ, bảo đảm không có hồi quy.
- **Kiến trúc Module hóa 12 Submodules (`module/`)**:
  - Submodule `module/extract_s1h48.py` độc lập, bảo toàn tương thích ngược cho entrypoint và CLI arguments.

### 🌐 Phân hệ Kế thừa Toàn vẹn:
- Trích xuất từ xa trực tiếp hoặc qua Indirect Bridge `172.21.168.241` -> `172.19.*.*`.
- Selective Fast Fetch hoàn tất trong 1–3 giây.
- Bảng lọc PASS/FAIL, phân tích Cycle Time, đối soát Golden Sample, và xử lý batch đa luồng.

### Cài đặt & Sử dụng:
Giải nén gói `JA_MFG_Log_Extractor_v1.8.2_Windows_x64.zip`, sao chép `config_sample.json` thành `config.json` nếu chưa có (điền thông tin xác thực SSH/Bridge nếu dùng tính năng Remote), và nhấp đúp vào `Chay_Tool_Log.bat` hoặc thực thi qua dòng lệnh. Giữ lại cấu hình và dữ liệu `reports/` và `downloads/` đang dùng khi cập nhật. Xem chi tiết tại `USERGUIDE.md` và `README.md`.
