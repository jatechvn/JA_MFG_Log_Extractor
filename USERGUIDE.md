# Hướng dẫn sử dụng JA_MFG_Log_Extractor v1.3.1

Tài liệu hướng dẫn chi tiết các thao tác vận hành, cấu hình và sử dụng công cụ **JA_MFG_Log_Extractor** dành cho kỹ sư kiểm thử (TE), kỹ sư sản xuất (PE) và nhân viên vận hành trạm test.

---

## 1. Khởi động chương trình

Nhấp đúp vào tệp tin **`Chay_Tool_Log.bat`**.

Chương trình sẽ tự động kiểm tra môi trường:
- Nếu chạy từ **PowerShell**, **CMD**, hoặc kết nối từ xa (**SSH**, **WinRM**): Chạy trực tiếp trên console hiện tại mà không tạo cửa sổ tiến trình ngầm.
- Nếu double-click từ **Windows Explorer**: Tự động mở trong **Windows Terminal (`wt.exe`)** nếu có, hoặc tiếp tục trên **CMD**.
- Bộ mã hiển thị Unicode UTF-8 (`chcp 65001`) và mã màu ANSI tự động kích hoạt.
- Ưu tiên sử dụng môi trường Python nhúng đi kèm trong thư mục `python_runtime` (nếu có), hoặc dùng Python có sẵn trong biến môi trường Windows.

---

## 2. Các chế độ làm việc

Khi khởi động, màn hình menu chính hiển thị 4 lựa chọn:

```text
┌─────────────────────────────────────────────────────────────────────┐
│  CÔNG CỤ TRÍCH XUẤT LOG TỰ ĐỘNG (IO, CHASSIS & PSU UNITS) - v1.3.1  │
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
  - Nếu là **PSU 2U/5U (`PMV...`)**: Hiển thị danh sách các SN tìm thấy kèm vị trí PSU (`[1] PMV... (psu0 / PCM 1)`, `[2] PMV... (psu1 / PCM 2)`).
  - Nếu là **IO (`SAF...`)** hoặc **IOM RPC73**: Hiển thị danh sách các SN tìm thấy kèm vai trò controller (`[1] SAFVN... (ctrla)`, `[2] SAFVN... (ctrlb)`). Chỉ cần nhấn số `1`, `2` hoặc bấm `Enter` để chọn số `1`.
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
  D:\LOGS\jbod_cto_test_uut0_9D57G_SAFVN2640836553_SAFVN264083654F_20261001-063641,SAFVN2640836553,
  D:\LOGS\juno_fin2_test_uut0_J024X1-995_FVBTL0000E_20260912-154742,FVBTL0000E,
  ```
  *(Cột `TargetSN` và `OutputDir` có thể để trống để công cụ tự động nhận diện).*

### Chế độ [4]: Tạo file CSV mẫu
- Tự động tạo tệp `mau_danh_sach_log.csv` chuẩn định dạng ngay trong thư mục công cụ.

---

## 3. Quy cách tệp tin báo cáo sinh ra

### A. Đối với IO Controller chuẩn (`SAF...`):
- `FW.txt`: Bóc tách thông tin firmware của controller tương ứng (`ctrla` hoặc `ctrlb`), từ khóa mở đầu `Component FW <ctrl>:rfwd` đến `kmip_bundle_version`.
- `VPD.txt`: Bóc tách 2 phần gồm bảng cấu trúc ebodvpd (`gem ebodvpd 2`) và bảng chi tiết linh kiện khách hàng (`Checking <ctrl> customer VPD ID = 49`).

### B. Đối với IOM RPC73 (`SAF...` có VPD 49 chứa 'RPC73'):
- Tự động nhận diện và tạo duy nhất 1 tệp tin báo cáo tổng hợp: **`FW_VPD.txt`** (139 dòng) gồm 4 phần:
  1. *Canister Firmware*: 9 dòng thông tin FW Canister (`Canister firmware` ... `Canister CPLD`) từ Step 02 (`check_and_load_fw_test`) theo đúng controller (`/dev/sg1` cho `ctrla` hoặc `/dev/sg2` cho `ctrlb`).
  2. *FW Match*: 30 dòng đối chiếu FW PCD của controller tương ứng từ Step 02.
  3. *VPD 49 Hex Dump*: 15 dòng hex dump của Canister Customer VPD từ Step 07 (`vpd_validation`) gồm header, offset `0000:` đến `00a0:`, và 2 dòng `0360:` / `0370:`, khớp với Serial Number của Canister.
  4. *Customer VPD Validation*: 83 dòng bảng kiểm thử customer VPD từ Step 07 kết thúc tại `result: match` của khối `fru_description`.

### C. Đối với Chassis 2U (`SGF...`):
- `<SN>.txt`: Tổng hợp 4 khối tiêu chuẩn: Cấu trúc Midplane VPD, Midplane CRC/CPLD, Mã hex Customer VPD và thông tin `fru_description`.

### D. Đối với Chassis 4U Juno (`FVB...`):
- `FW.txt`: Thông tin firmware controller A và controller B đã làm sạch biến thời gian.
- `GETVPD.txt`: Nội dung lệnh `gemcli getvpd` đã ghép nối đúng chu kỳ test.
- `VER.txt`: Nội dung lệnh `gemcli ver` có cùng tiền tố timestamp với GETVPD.
- `VPD.txt`: Bảng kiểm định VPD bắt đầu từ tiêu đề `name | Oper | CTP status` đến dòng kết thúc `Skipping VPD Check...`, giữ nguyên tiền tố số dòng `|XXXX|`.
- `Restore Default.txt`: Quá trình reset mặc định từ `Verify Factory reset flag state` đến `Factory reset successful`, giữ tiền tố `|XXXX|`.
- `Provisioning State.txt`: Trạng thái provisioning của hệ thống.

### E. Đối với 2U PSU DYJW5 (`PMV...` / `DYJW5`):
- Tự động nhận diện và tạo duy nhất 1 tệp tin báo cáo tổng hợp: **`Controller FW, Drive FW, Serial Number Tracking & Test History.txt`** (116 dòng) gồm 4 phần:
  1. *PCM Firmware & VPD CRC*: 6 dòng thông tin firmware, cấu trúc VPD và mã CRC của cả 2 bộ nguồn PCM 1 và PCM 2 từ Step 06 (`write_vpd`).
  2. *VPD Raw Hex Dump*: 7 dòng hex dump từ bảng đối soát sau nạp VPD (VPD 40 cho `psu0` hoặc VPD 41 cho `psu1`), dải offset `0000:` đến `0050:` từ Step 06.
  3. *Customer VPD Hex Dump*: 16 dòng hex dump của VPD 60 (cho `psu0`) hoặc VPD 61 (cho `psu1`) từ Step 07 (`vpd_validation`) gồm offset `0000:` đến `0090:`, dòng phân cách trống và dải `0360:` đến `0390:`.
  4. *Customer VPD Validation Table*: 84 dòng bảng kiểm thử customer VPD từ Step 07 kết thúc tại `result: match` của khối `fru_description`.

---

## 4. Chạy trực tiếp qua dòng lệnh (CLI / PowerShell / WinRM / SSH)

Công cụ hỗ trợ đầy đủ các tham số dòng lệnh phục vụ tự động hóa và điều khiển từ xa:

### Các cờ lệnh (Options):
- `--help`: Xem danh sách tham số hướng dẫn.
- `--csv-file <đường_dẫn_csv>`: Chạy hàng loạt theo file CSV/TXT tự động (headless/background).
- `--batch-dir <thư_mục_gốc>`: Tự động quét và trích xuất tất cả log con bên trong thư mục gốc.
- `--input-dir <log_dir> --target-sn <sn> [--output-dir <out_dir>]`: Trích xuất trực tiếp 1 unit cụ thể.
- `--generate-csv-template`: Tự động tạo tệp `mau_danh_sach_log.csv`.

### Ví dụ chạy từ xa qua WinRM / PowerShell:
```powershell
Set-Location 'D:\MFG_Log_Extractor_PythonPortable'
.\Chay_Tool_Log.bat --csv-file mau_danh_sach_log.csv
```
Khi chạy có tham số hoặc trong phiên SSH/WinRM, công cụ tự động vô hiệu hóa lệnh tạm dừng (`pause`) để không làm nghẽn tiến trình tự động hóa.

---

## 5. Xử lý sự cố thường gặp (Troubleshooting)

1. **Lỗi đường dẫn quá dài (> 260 ký tự)**:
   - Công cụ đã tích hợp cơ chế tiền tố mở rộng `\\?\` của Windows. Người dùng không cần cấu hình thêm Registry.
2. **Không thấy file `uut_list_utility_logs.log`**:
   - Nếu thư mục log chỉ có file nén `obmcdump_*.tar.gz`, công cụ sẽ tự động giải nén trong bộ nhớ tạm thời mà không yêu cầu cài đặt thêm phần mềm nén ngoài như 7-Zip hay WinRAR.
3. **Phân biệt Controller cho IOM RPC73**:
   - Công cụ tự động đối soát Serial Number nhúng trực tiếp trong hex dump của VPD 49 để định danh chính xác Canister A (`ctrla`) và Canister B (`ctrlb`).
