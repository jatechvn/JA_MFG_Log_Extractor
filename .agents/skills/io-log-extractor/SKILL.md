---
name: io-log-extractor
description: >-
  Extract FW.txt and VPD.txt report files from raw manufacturing test log directories for IO/Chassis units (e.g., SAFVN..., SGFVN...).
  Use this skill whenever asked to filter, extract, or generate FW and VPD log reports for target serial numbers.
---

# Manufacturing Log Extractor Skill (IO & Chassis)

This skill provides step-by-step instructions and automated tool support to extract log report files (`FW.txt` & `VPD.txt` for IO units, `<SN>.txt` for Chassis units) from raw CTP/avocado manufacturing test log directories.

---

## 1. Prerequisites & Unit Type Identification

- **IO Unit (`SAF...`)**: Serial numbers starting with `SAF` (e.g., `SAFVN262883610F`).
  - Generates 2 report files: `FW.txt` and `VPD.txt`.
  - Controller role (`ctrla` / `ctrlb`) is determined by the position of target SN in raw directory name (`[SN1]` = `ctrla`, `[SN2]` = `ctrlb`).
- **IOM RPC73 Unit (`SAF...` with VPD 49 containing `RPC73`)**: Dell ME52XX EBOD Canister.
  - Generates 1 combined report file: `FW_VPD.txt` (139 lines).
  - Canister role (`ctrla` / `ctrlb`) is mapped to Step 2 (`/dev/sg1` vs `/dev/sg2`) and Step 7 (VPD 49 hex dump containing target SN).
- **2U PSU DYJW5 Unit (`PMV...` / `DYJW5`)**: Dell ME4 Power Supply Unit.
  - Generates 1 combined report file: `Controller FW, Drive FW, Serial Number Tracking & Test History.txt` (116 lines).
  - PSU role (`psu0` / `psu1`) is mapped to PCM 1 vs PCM 2, VPD 40/41 hex dump in Step 06 (`write_vpd`), and VPD 60/61 customer validation in Step 07 (`vpd_validation`).
- **Chassis 2U Unit (`SGF...`)**: Serial numbers starting with `SGF` (e.g., `SGFVN26318361A6`).
  - Generates 1 report file: `<target_sn>.txt`.
- **Chassis 4U Unit (`FVB...`)**: Serial numbers starting with `FVB` (e.g., `FVBTL0000E`).
  - Generates 6 report files: `FW.txt`, `GETVPD.txt`, `VER.txt`, `VPD.txt`, `Provisioning State.txt`, `Restore Default.txt`.

---

## 2. Automated Extraction via Script

Run the automated Python script [`extract_mfg_logs.py`](file:///d:/JA_TESTER/LOGS_ANL/extract_mfg_logs.py):

### Cách 1: Chế độ nhập tương tác (Interactive Mode - Khuyên dùng)
Chỉ cần nháy kép chuột vào `Chay_Tool_Log.bat` trong thư mục [`MFG_Log_Extractor_PythonPortable`](file:///d:/JA_TESTER/LOGS_ANL/MFG_Log_Extractor_PythonPortable), chương trình sẽ hỗ trợ thông minh:
```powershell
python d:\JA_TESTER\LOGS_ANL\extract_mfg_logs.py
```
**Quy trình tương tác thông minh**:
1. **[1/3] Input Dir**: Nhập/dán đường dẫn thư mục log đầu vào.
2. **[2/3] Target SN**: Script tự động phân tích tên thư mục input và hiển thị danh sách các SN có sẵn (`[1] SAFVN... (ctrla)` và `[2] SAFVN... (ctrlb)` với IO, hoặc tự chọn SN duy nhất với Chassis). Người dùng chỉ cần gõ `1` hoặc `2` hoặc bấm `Enter` để chọn mặc định `[1]`.
3. **[3/3] Output Base Dir**: Script tự động đề xuất thư mục xuất mặc định chuẩn:
   - Dòng IO (`SAF...`): Mặc định `D:\JA_TESTER\LOGS_ANL\IO`
   - Dòng Chassis (`SGF...`): Mặc định `D:\JA_TESTER\LOGS_ANL\2U`
   - Người dùng chỉ cần nhấn `Enter` để chọn mặc định hoặc dán đường dẫn tùy chỉnh khác.

### Cách 2: Chế độ truyền tham số dòng lệnh (Command Line Arguments)
```powershell
python d:\JA_TESTER\LOGS_ANL\extract_mfg_logs.py --input-dir "<path_to_raw_test_folder>" --target-sn "<TARGET_SN>" --output-dir "<path_to_output_base_folder>"
```

---

## 3. Manual Extraction Algorithm

### Log Line Cleaning (Regex B1)
Apply Regex Find & Replace across log lines:
- **Find**: `^\d{4}-\d{2}-\d{2}.*?(\|\d+\|)`
- **Replace**: `$1`
- Strips timestamps and process info while keeping line markers (e.g. `|0586|`, `|3671|`, `|0250|`).

---

### A. IO Unit Extraction (`SAF...`)

#### Extracting `FW.txt`
1. Locate step directory matching `check_and_load_fw_test` inside `job-*/test-results/` (pick highest step number, e.g. Step 48).
2. Clean `debug.log` lines with Regex B1.
3. Start Marker: `|0586|Component FW <ctrl>:rfwd not in enclosure object.`
4. End Marker: `|0586|Component FW <ctrl>:kmip_bundle_version not in enclosure object.`
5. Copy all lines from Start Marker to End Marker (inclusive) into `FW.txt`.

#### Extracting `VPD.txt`
1. Locate step directory matching `vpd_validation` inside `job-*/test-results/` (e.g. Step 37).
2. Clean `debug.log` lines with Regex B1.
3. **Part 1 Extraction**:
   - Locate anchor B2: `|3737|VPD validation passed for component <ctrl>`
   - Search backwards from B2 to find `|3671|vpd_type 13: ... -> match` (end of Part 1).
   - Search backwards further to find line `|0250|Battery 2 firmware        : Not present`.
   - Start Part 1 from the line immediately following `Battery 2 firmware : Not present` (e.g. `|0180|Sending GEM cmd set_ebodvpd 2...`).
   - Copy lines from start of Part 1 to end of Part 1.
4. Insert 1 blank line.
5. **Part 2 Extraction**:
   - Locate anchor B4: `|3887|Checking <ctrl> customer VPD (ID = 49) ...`
   - Copy downward through all customer VPD attributes until the closing `|4004|-----------------------------------------------------------------------------` separator line following `fru_description`.
6. Append Part 2 to `VPD.txt`.

---

### B. Chassis Unit Extraction (`SGF...`)

1. Locate step directory matching `vpd_validation` inside `job-*/test-results/` (e.g. Step 07).
2. Clean `debug.log` lines with Regex B1.
3. **Step 1**: Find `|0250|Midplane VPD structure`. Copy 3 lines (`Midplane VPD structure`, `Midplane VPD CRC`, `Midplane CPLD`).
4. Insert 1 blank line.
5. **Step 2**: Find `|0608|VPD 18 (1) - Midplane Customer A`. Copy down to the line ending with `z.....`.
6. **Step 3**: Find `|0509|0360:` immediately following Step 2. Copy 2 lines (`|0509|0360:` and `|0509|0370:`).
7. Insert 1 blank line.
8. **Step 4**: Find `|3887|Checking chassis customer VPD`. Copy down to the closing separator `|4004|-----------------------------------------------------------------------------` following `fru_description`.
9. Save combined result into `<target_sn>.txt`.

---

### C. Chassis 4U Unit Extraction (`FVB...`)

Generates 6 report files into `<output_dir>/<target_sn>/`:
1. **`FW.txt`**:
   - Locate step directory matching `check_and_load_fw_test` inside `job-*/test-results/`.
   - Start Marker: `Controller A: ('\nSled 0 Element 0 Firmware :`
   - End Marker: `Drive Enclosure Inband (DEI) Revision :`
   - Strip date/time prefixes (`^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\|.*?\|\d{4}\|`).
2. **`GETVPD.txt` & `VER.txt`** (Timestamp-synchronized pairing):
   - Locate `uut_list_utility_logs.log` in `enc_logs/obmcdump_*/` (or unpack `.tar.gz` archive if needed).
   - Find first `gemcli_getvpd_test_<timestamp>` matching folder date.
   - Extract matching `gemcli_ver_test_<timestamp>` sharing the same timestamp prefix (or adjacent block in same test cycle).
   - Save clean command outputs to `GETVPD.txt` and `VER.txt`.
3. **`VPD.txt`**:
   - Locate step directory matching `vpd_validation` inside `job-*/test-results/`.
   - Start Marker: `|          name           | Oper  | CTP status |`
   - End Marker: Last line starting with `Skipping VPD Check on Validate for ManufacturingDateTime`
   - Keep line-number blocks intact (`|XXXX|...`).
4. **`Restore Default.txt`**:
   - Locate step directory matching `juno_restore_default` inside `job-*/test-results/`.
   - Start Marker: `Verify Factory reset flag state`
   - End Marker: `Factory reset successful using Restore Default command`
   - Keep line-number blocks intact (`|XXXX|...`).
5. **`Provisioning State.txt`**:
   - Locate step directory matching `juno_provisioning_state` inside `job-*/test-results/`.
   - Extract command and output blocks.

---

### D. IOM RPC73 Unit Extraction (`SAF...` with VPD 49 containing `RPC73`)

Generates 1 combined report file: `<output_dir>/<target_sn>/FW_VPD.txt` (139 lines):
1. **Canister Firmware** (Step 02 `check_and_load_fw_test`):
   - Locate step directory matching `check_and_load_fw_test` containing `Canister firmware` (Step 02).
   - Extract 9 lines: from `|0250|Canister firmware` down to `|0250|Canister CPLD` corresponding to target canister (`/dev/sg1` for `ctrla` or `/dev/sg2` for `ctrlb`).
2. **FW Match** (Step 02 `check_and_load_fw_test`):
   - Extract 30 lines (6 blocks) starting at `|0573|FW match: Component: <controller>` through `PCD: <val>`.
3. **VPD 49 Hex Dump** (Step 07 `vpd_validation`):
   - In step `vpd_validation`, find `|0608|VPD 49 (1) - Canister Customer` matching target canister / SN.
   - Extract header + hex lines `0000:` through `00a0:` (13 lines).
   - Append lines `0360:` and `0370:` (2 lines). Total: 15 lines.
4. **Customer VPD Validation** (Step 07 `vpd_validation`):
   - Start Marker: `|3893|Checking <controller> customer VPD (ID = 49) ...`
   - End Marker: `|3993|result: match` of the `fru_description` block. Total: 83 lines.

---

## 4. Verification

Compare output files line-by-line with sample/gold standards using Python:
```python
with open("extracted.txt", "rb") as f1, open("sample.txt", "rb") as f2:
    assert f1.read().replace(b"\r\n", b"\n").strip() == f2.read().replace(b"\r\n", b"\n").strip()
```

