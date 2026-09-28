# Hướng dẫn sử dụng JA_MFG_Log_Extractor v1.0.0

Tài liệu hướng dẫn chi tiết các thao tác vận hành, cấu hình và sử dụng công cụ **JA_MFG_Log_Extractor** dành cho kỹ sư kiểm thử (TE), kỹ sư sản xuất (PE) và nhân viên vận hành trạm test.

---

## 1. Khởi động chương trình

Nhấp đúp vào tệp tin **`Chay_Tool_Log.bat`**.

Chương trình sẽ tự động kiểm tra môi trường:
- Nếu máy có **Windows Terminal (`wt.exe`)**, công cụ sẽ mở trên giao diện Terminal hiện đại.
- Nếu không có, sẽ tự động chuyển tiếp qua **PowerShell** hoặc **Command Prompt (CMD)** với bộ mã Unicode UTF-8 (`chcp 65001`) và mã màu ANSI.
- Ưu tiên sử dụng môi trường Python nhúng đi kèm trong thư mục `python_runtime` (nếu có), hoặc dùng Python có sẵn trong biến môi trường Windows.

---

## 2. Các chế độ làm việc

Khi khởi động, màn hình menu chính hiển thị 4 lựa chọn:

```text
┌─────────────────────────────────────────────────────────────────────┐
│     CÔNG CỤ TRÍCH XUẤT LOG TỰ ĐỘNG (IO & CHASSIS UNITS) - v1.0.0    │
└─────────────────────────────────────────────────────────────────────┘

Vui lòng chọn chế độ làm việc:
   [1] Trích xuất 1 thư mục log đơn lẻ (Single Folder Mode)
   [2] Quét và trích xuất hàng loạt từ thư mục gốc (Batch Subfolders Scan)
   [3] Đọc danh sách trích xuất từ file CSV / TXT (Batch CSV Import)
   [4] Tạo file CSV mẫu (mau_danh_sach_log.csv)

   👉 Chọn nhanh số (1-4) hoặc nhấn Enter để chọn [1]:
```

### Chế độ [1]: Trích xuất 1 thư mục log đơn lẻ (Single Folder Mode)
- **Bước 1**: Dán hoặc nhập đường dẫn thư mục log raw vào ô nhập. Hỗ trợ kéo thả thư mục vào cửa sổ console.
- **Bước 2**: Công cụ tự động phân tích tên thư mục:
  - Nếu là **IO (`SAF...`)**: Hiển thị danh sách các SN tìm thấy kèm vai trò controller (`[1] SAFVN... (ctrla)`, `[2] SAFVN... (ctrlb)`). Chỉ cần nhấn số `1`, `2` hoặc bấm `Enter` để chọn số `1`.
  - Nếu là **Chassis 2U (`SGF...`)** hoặc **Chassis 4U (`FVB...`)**: Tự động nhận diện SN duy nhất, nhấn `Enter` để tiếp tục.
- **Bước 3**: Nhập thư mục xuất báo cáo (hoặc nhấn `Enter` để sử dụng mặc định là thư mục mang tên `<Target_SN>` trong thư mục mẹ của log).

### Chế độ [2]: Quét và trích xuất hàng loạt (Batch Subfolders Scan)
- Áp dụng khi bạn có một thư mục cha chứa nhiều thư mục con của nhiều máy test khác nhau.
- Chỉ cần nhập đường dẫn thư mục cha, công cụ sẽ tự động duyệt cây thư mục đệ quy, nhận diện toàn bộ các phiên test hợp lệ và trích xuất đồng loạt toàn bộ các máy.
- Báo cáo kết quả tổng kết hiển thị theo bảng thống kê chi tiết số máy thành công và thất bại.

### Chế độ [3]: Đọc danh sách trích xuất từ file CSV / TXT (Batch CSV Import)
- Phù hợp cho việc tự động hóa theo danh sách chỉ định từ MES hoặc hệ thống quản lý.
- Cấu trúc file CSV gồm 3 cột:
  ```csv
  LogPath,TargetSN,OutputDir
  D:\LOGS\rbod_fin2_test_uut0_TD214_SAFVN2628836122_SAFVN262883610F_20260717-053125,SAFVN262883610F,
  D:\LOGS\juno_fin2_test_uut0_J024X1-995_FVBTL0000E_20260912-154742,FVBTL0000E,
  ```
  *(Cột `TargetSN` và `OutputDir` có thể để trống để công cụ tự động nhận diện).*

### Chế độ [4]: Tạo file CSV mẫu
- Tự động tạo tệp `mau_danh_sach_log.csv` chuẩn định dạng ngay trong thư mục công cụ.

---

## 3. Quy cách tệp tin báo cáo sinh ra

### A. Đối với IO Controller (`SAF...`):
- `FW.txt`: Bóc tách thông tin firmware của controller tương ứng (`ctrla` hoặc `ctrlb`), từ khóa mở đầu `Component FW <ctrl>:rfwd` đến `kmip_bundle_version`.
- `VPD.txt`: Bóc tách 2 phần gồm bảng cấu trúc ebodvpd (`gem ebodvpd 2`) và bảng chi tiết linh kiện khách hàng (`Checking <ctrl> customer VPD ID = 49`).

### B. Đối với Chassis 2U (`SGF...`):
- `<SN>.txt`: Tổng hợp 4 khối tiêu chuẩn: Cấu trúc Midplane VPD, Midplane CRC/CPLD, Mã hex Customer VPD và thông tin `fru_description`.

### C. Đối với Chassis 4U Juno (`FVB...`):
- `FW.txt`: Thông tin firmware controller A và controller B đã làm sạch biến thời gian.
- `GETVPD.txt`: Nội dung lệnh `gemcli getvpd` đã ghép nối đúng chu kỳ test.
- `VER.txt`: Nội dung lệnh `gemcli ver` có cùng tiền tố timestamp với GETVPD.
- `VPD.txt`: Bảng kiểm định VPD bắt đầu từ tiêu đề `name | Oper | CTP status` đến dòng kết thúc `Skipping VPD Check...`, giữ nguyên tiền tố số dòng `|XXXX|`.
- `Restore Default.txt`: Quá trình reset mặc định từ `Verify Factory reset flag state` đến `Factory reset successful`, giữ tiền tố `|XXXX|`.
- `Provisioning State.txt`: Trạng thái provisioning của hệ thống.

---

## 4. Xử lý sự cố thường gặp (Troubleshooting)

1. **Lỗi đường dẫn quá dài (> 260 ký tự)**:
   - Công cụ đã tích hợp cơ chế tiền tố mở rộng `\\?\` của Windows. Người dùng không cần cấu hình thêm Registry.
2. **Không thấy file `uut_list_utility_logs.log`**:
   - Nếu thư mục log chỉ có file nén `obmcdump_*.tar.gz`, công cụ sẽ tự động giải nén trong bộ nhớ tạm thời mà không yêu cầu cài đặt thêm phần mềm nén ngoài như 7-Zip hay WinRAR.
