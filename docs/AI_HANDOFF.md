# AI Handoff — 2026-10-15 (JA_MFG_Log_Extractor v1.6.0)

## Summary of Changes (v1.6.0)
1. **Direct Local Execution with Indirect Bridge (`module/`)**:
   - Ported and integrated `module/bridge.py`, `module/remote_fetcher.py`, `module/winrm_socket.py`, `module/winrm_bridge.ps1`, `module/config.py`, `module/local_config.py`, `module/ip_utils.py`, `module/path_utils.py`, `module/log_finder.py`, `module/exceptions.py` from `seagate_log_downloader`.
   - Supports connecting from `172.21.*.*` workstation directly or via dual-NIC Jump-Host Bridge `172.21.168.241` (`172.19.208.133`) to `172.19.*.*` test stations using SSH `direct-tcpip` with automatic WinRM TCP Proxy fallback (`winrm_bridge.ps1`).
   - Added **Selective Fast Fetch** in `module/remote_fetcher.py`: packages only analysis-relevant text/metadata files (`debug.log`, `results.json`, `*.log`, `ctp_log_metadata.yaml`, `job.log`, `enc_logs/*`), skipping heavy `serial_logs/`, `sysinfo/`, `.journal.sqlite`, `results.html`, completing remote fetch + extraction in 1–3 seconds.
   - Added `--keep-raw-zip` flag to optionally save full raw `.zip` archives in `<App_Dir>/downloads/<IP>/`.
2. **Centralized Analysis Reports (`<App_Dir>/reports/`)**:
   - All extraction modes (Remote IP+SN, Local Single Folder/Archive, Batch Scan, CSV Import, Cycle Time) now default to saving extracted reports inside `<App_Dir>/reports/<Target_SN>/` and `<App_Dir>/reports/Cycle_Time_Summary.csv`.
3. **Graceful Extraction on Aborted VPD Validation**:
   - Added fallback end-marker detection (`vpd rendering failed` / `fail_reason`) in `extract_vpd()` and `extract_chassis_vpd()` and warning detection in `validate_extracted_reports()`, ensuring failed runs (such as `EC(30005) VPD rendering failed for chassis FRU-REV`) still produce partial VPD reports + `ERROR_SUMMARY.txt` + `Cycle_Time_Summary.csv` warnings.
4. **Portable Runtime & Clean Project Structure**:
   - Removed the redundant `MFG_Log_Extractor_PythonPortable/` folder since `dist/` already holds the complete unpacked portable build alongside `JA_MFG_Log_Extractor_v1.6.0_Windows_x64.zip`.
   - `build.bat` automatically preserves `dist/python_runtime` across builds, and root `Chay_Tool_Log.bat` automatically uses `dist/python_runtime/python.exe`.

## Independent verification of pending v1.7.0 — 2026-11-02

- Preserved the existing dirty upgrade worktree. Verification details and reproducible evidence: ../verify_20261102_v170/REPORT.md.
- Supplied unit tests: 6/6 pass. Actual seven manufacturing cases: source and unpacked embedded runtime match all 14 reports; Dell 5U matches separate sample exactly. PSU 2U intentionally adds a raw-log-backed 00a0 hex row (117 lines).
- Actual bridge listing works for .172 and .174; .172 matches the walkthrough's five packages. The unpacked ZIP launcher also passed live --list-only on .172.
- ZIP integrity, source/module parity, checksum and version manifest verified. SHA256: 367ebd8d87abf16df77f1d07406aeba4c8070c52e28463165aedcecff99026ac.
- Confirmed remaining defects: P/F with no matching status falls back to the opposite newest run; table overflows 80-column terminals; launcher and key packaged documentation still say v1.6.0; supplied list-only unit test writes the real recent history file because HISTORY_FILE is not isolated.
- No application fixes, rebuild, commit, publication or Drive sync performed. Explorer/actual clipboard and full interactive/remote-download flow remain unverified; end time is filesystem mtime rather than independent MES acknowledgement.

## Four v1.7.0 fixes completed — 2026-11-02

- Fixed empty P/F selection to re-prompt, narrow-terminal table overflow, stale v1.6.0 launcher/document metadata and list-only/unit-test history writes.
- Nine unit tests pass, including P/F no-match cancellation, 20–140 column width checks and existing/absent history. Real history bytes unchanged by test discovery.
- Seven actual log cases through source and candidate embedded runtime match all 14 previously verified reports. Packaged launcher live --list-only on .172 succeeds, finds five packages and preserves seeded local history.
- Verified package installed into dist with updated manifest/checksum. Runtime/data and all unmodified ZIP members retained; previous source/docs/package/replaced dist files backed up (path in ../verify_20261102_v170/four_fixes/backup_path.txt).
- New ZIP SHA256: e924357c3f2908230b0e97924e5a714aa17104cc9399b6f9c593cdcee80d0bf9.
- Detailed evidence: ../verify_20261102_v170/four_fixes/FIX_REPORT.md. No commit, GitHub publication or Drive sync. Native Explorer/physical keyboard and Clipboard remain unverified.

## W47DG FW Midplane correction (v1.7.1) — 2026-11-03

- User corrected the source contract: FW.txt Midplane structure/CRC/CPLD must come from Step 07 vpd_validation, never Step 02. Historical sample/skill statements using 0x13 and AA7722D1 are superseded for these three fields; do not restore them to regain old sample parity.
- extract_chassis_5u_midplane_validation reads a complete Step 07 block dynamically and rejects missing/incomplete status. The real SGFVN26418364D7 raw log lines 107–109 give 0x14 / 0x4BC5F496 / 0x20.
- 11 unit tests pass; source and extracted-package runtimes pass seven actual cases. Only W47DG structure/CRC bytes differ from old FW sample; other FW bytes, VPD.txt and twelve reports from other product cases are unchanged. Integration probe rejects missing Step 07 despite valid Step 02.
- Synchronized v1.7.1 across source, launcher, docs, and packaged `dist/JA_MFG_Log_Extractor_v1.7.1_Windows_x64.zip` (SHA256: `24c9d174780f7c263b2f98f7d324e40525d74ebbfb8630133a050872ae8936b4`).
- Details/corrected reports: ../verify_20261103_w47dg/REPORT.md and source/5u/SGFVN26418364D7/FW.txt under that verification directory. Original production reports/Sample unchanged.

## Dell 5U PN 7PNTN — 2026-11-12

- The Dell 5U extractor now selects the 7PNTN layout by PN. Step 07 supplies Fan firmware and the WWN pair matching both TWI buses; step 06 supplies left-column Fan VPD 122–126. Selected log codes are stripped; Customer VPD codes and final separator are kept.
- Source and unpacked ZIP runtime both match `reports/SGFVN26428364DE_sample` exactly (FW: 31 lines/1,749 bytes; VPD: 259 lines/16,784 bytes). Sixteen unit tests pass; seven prior cases retain all 14 verified report hashes, including corrected W47DG v1.7.1.
- Missing Fan offset `0050` is rejected before either report is written. Evidence and isolated verification ZIP are in ../verify_20261112_7pntn/. Existing raw, sample, reports, `config_sample.json` changes and `dist` were preserved. No live bridge test or release in this scope.

## Live bridge verification for 7PNTN — 2026-11-12

- Connected by SSH through bridge `172.21.168.241` to Linux station `172.19.116.172`. Of nine runs for `SGFVN26428364DE`, selected only `jbod_cto_test_uut0_7PNTN_SGFVN26428364DE_20261024-074325` (station status PASS).
- The app's remote extraction flow downloaded that exact run via read-only SFTP (remote precompression disabled). Its `FW.txt` (31 lines, 1,749 bytes) and `VPD.txt` (259 lines, 16,784 bytes) both match the independent sample byte-for-byte. Production history was unchanged.
- Reproducer: ../verify_20261112_7pntn/verify_live_bridge.py. Evidence and generated reports: ../verify_20261112_7pntn/live_bridge_u13zy3u_/results.json. No release or `dist` change.

## Revised 7PNTN VPD layout — 2026-11-12

- The current sample supersedes the 259-line VPD layout. For 7PNTN only: VPD 16 ends at `0090`; VPD 18 keeps `0000`–`00a0` and `0360`/`0370`; all eight Canister VPD 48 blocks preserve offsets `0000`–`0050`; Customer VPD 18 fields are selected and ordered to match the sample. W47DG output is unchanged.
- Source, unpacked ZIP runtime and live SSH bridge/SFTP all produce exact sample bytes: FW 31 lines/1,749 bytes (unchanged), VPD 260 lines/16,376 bytes. Seventeen unit tests passed; seven prior cases retained all 14 hashes. Missing Fan/Canister `0050` and Customer VPD `0370` are rejected before writing reports.
- Evidence, reproducible checks and isolated ZIP: ../verify_20261112_7pntn_vpd_update/REPORT.md. Raw, sample, production reports, config changes, and `dist` were preserved. No release.

## 9D57G revised RPC73 layout — 2026-11-13

- The revised Step 07 `|3898|` validation layout selects the canister by the serial bytes in VPD 49 and confirms the same serial in the paired validation table. Output ends after the `revision` separator with CRLF. Older RPC73 layout remains unchanged.
- `SAFVN26468368FF` matches the golden FW_VPD report from source and the isolated ZIP runtime (103 lines / 5,229 bytes). `SAFVN26468368ED` from the same run selects `ctrla` with the correct SN. 19 tests pass; all 14 legacy reports and both 7PNTN report hashes are unchanged.
- Evidence: ../verify_20261113_9d57g/REPORT.md. Existing sample, raw, reports, config changes and `dist` preserved; no live bridge or release.

## PN RPC73 full Customer VPD layout — 2026-11-17

- New-style `|3898|` logs now retain validation through `fru_description` for PN `RPC73` only. PN `9D57G` still stops at `revision`; legacy `|3893|` output remains unchanged.
- `SAFVN26468368F7` matches the sample byte-for-byte (140 lines / 8,320 bytes); sibling `SAFVN26468368F5` selects the correct `ctrlb`. 20 unit tests pass, and 17 baseline report hashes remain unchanged across seven legacy cases plus 9D57G and 7PNTN.
- Source CLI evidence: ../verify_20261117_rpc73/REPORT.md. No bridge, package rebuild or release in this scope.

## AI navigation and module split plan — 2026-11-18

- Added repository [rules](../AGENTS.md), [source map](AI_CONTEXT.md) and navigation guides for [modules](../module/README.md) and [tests](../tests/README.md). [USERGUIDE.md](../USERGUIDE.md) remains the functional reference; no duplicate specification was added.
- [Module split plan](MODULE_SPLIT_PLAN.md) defines responsibility boundaries and per-phase acceptance checks. No Python code was moved. Existing parser, config and untracked test changes remain in the worktree.
- The read-only optimizer audit now maps all 18 source files and both module/test directories, with no stale or ambiguous references. With `-SpecPath USERGUIDE.md`, the navigation heuristic is 97.5/100; the scanner did not run tests. Root `AGENTS.md` is unignored locally so the shared guide can be tracked.

## I/O behavior baseline — 2026-11-18

- Captured behavior on HEAD `0939fa9` plus pending worktree changes, without committing. [Baseline report](../verify_20261118_io_baseline/REPORT.md) links the CLI help, API/caller inventory, per-case exits and SHA-256 manifest, and rerun command.
- 20 unit tests passed; 11 real directory runs retained 19 reports, and a real W47DG ZIP matched its directory run. Safe ZIP/TAR fixtures cover long paths, filtering, malformed ZIP and temporary cleanup; verified CRLF and final newline behavior.
- No application code or runtime data changed. This is a source CLI baseline; native UI, packaged runtime, and live bridge were not exercised. Stage 1 can use `capture.py --compare` followed by an isolated ZIP smoke test. Archive path containment is a separate review item, not a behavior validated here.

## Stage 1: shared log I/O — 2026-11-18

- Moved 15 helpers to [module/log_io.py](../module/log_io.py), keeping names available through the old entrypoint. The only function-body change was adjusting the non-frozen app root for the module's new location. Parser, CLI and transport logic remain in place.
- Baseline comparison passed for all 12 CLI runs (21 report hashes), 20 unit tests and ZIP/TAR, long path, CRLF and cleanup probes. Isolated ZIP smoke passed for W47DG through embedded Python and 7PNTN through the launcher with packaged default report paths.
- [Stage 1 evidence](../verify_20261118_log_io_split/REPORT.md) includes the ZIP and commands. No live bridge, UI, archive security change, build in `dist`, or release. Next planned code move is the W47DG/7PNTN parser family.

## Stage 2: W47DG/7PNTN parser — 2026-11-18

- Moved nine Dell 5U functions to [module/extract_chassis_5u.py](../module/extract_chassis_5u.py) and the shared package PN helper to `module/log_io.py`. Existing entrypoint imports and function bodies were preserved; the 7PNTN test now patches `find_step_dir` in the module that owns the parser.
- 20 unit tests, 12 CLI runs and 21 report hashes matched baseline. Missing W47DG Step 07 CRC and three missing 7PNTN offsets still failed before report writes. Isolated ZIP verified W47DG via embedded Python and 7PNTN via BAT.
- [Evidence and candidate ZIP](../verify_20261118_chassis5u_split/REPORT.md). No release, live bridge or `dist` change. Next family is RPC73/9D57G.

## Stage 2: RPC73/9D57G parser — 2026-11-18

- Moved five IOM parser functions and the validation marker to [module/extract_rpc73.py](../module/extract_rpc73.py) without changing their bodies. The old imports remain available and the entrypoint still owns dispatch and report writing.
- 20 unit tests passed; baseline comparison matched 12 CLI runs and 21 report hashes. An isolated ZIP matched RPC73 legacy, 9D57G, and both new RPC73 canisters using embedded Python or the BAT launcher.
- [Evidence and candidate ZIP](../verify_20261118_rpc73_split/REPORT.md). No release, live bridge or `dist` change. Next family is PSU.

## Stage 2 — PSU parser — 2026-11-18

- Moved the four PSU 2U DYJW5 and 5U 0R4C4 parser functions to [module/extract_psu.py](../module/extract_psu.py). All function bodies and both DYJW5 compatibility aliases were preserved. The entrypoint still dispatches and writes the report.
- All 20 unit tests, 12 CLI runs and 21 report hashes matched baseline. The isolated ZIP selected both PCMs for each model, with all four hashes matching pre-refactor output and matching CLI help through embedded Python and BAT.
- The 2U historical sample differs only by the current report's `00a0:` row. The saved 5U PCM 1 report matches byte for byte. [Verification and ZIP](../verify_20261118_psu_split/REPORT.md). Next parser is Juno 4U.

## Stage 2 — Juno 4U parser — 2026-11-18

- Moved `extract_chassis_4u_logs()` to [module/extract_juno.py](../module/extract_juno.py). The original entrypoint import, function body, GETVPD/VER pairing and six-report contract were preserved.
- Baseline matched 20 unit tests, 12 CLI runs and 21 report hashes. The isolated ZIP matched the six `FVBTL0000E` sample files from both the raw directory and the raw ZIP with nested `enc_logs` tar.xz. The six `FVBTL0000R` reports matched pre-refactor hashes and the saved current reference.
- [Verification and candidate ZIP](../verify_20261118_juno_split/REPORT.md). Verification scope was local CLI on Windows. Next parser group is IO and Chassis 2U.

## Stage 2 — IO and Chassis 2U parsers — 2026-11-18

- Moved `extract_fw()`, `extract_vpd()` and `extract_chassis_vpd()` to [module/extract_basic.py](../module/extract_basic.py). The function bodies and old imports were preserved. Controller selection, file I/O and dispatch stay in the caller.
- Baseline matched 20 unit tests, 12 CLI runs and 21 report hashes. The isolated ZIP verified both TD214 controllers and the NP0W0 2U report through embedded Python and BAT, with both folder and archive inputs exercised.
- The original NP0W0 ZIP fails before parsing because it contains a `latest` symlink and `latest/` descendants. Previous and current packages reproduce WinError 183. A staging copy omitting just that symlink matches the 2U reference bytes. [Verification and candidate ZIP](../verify_20261118_basic_split/REPORT.md).
- Stage 2 is complete. Stage 3 starts with `module/reporting.py`.

## Stage 3 — reporting module — 2026-11-18

- Moved seven cycle-time, validation, diagnostic, golden comparison and CSV functions to [module/reporting.py](../module/reporting.py). Shared [console_style.py](../module/console_style.py) owns the original ANSI class. Original imports, function bodies and CLI workflow remain available.
- All 20 unit tests, 12 baseline CLI runs and 21 report hashes matched. Additional reporting parity verified three CSVs, two diagnostics, three batch reports and five CLI outputs from source and the isolated ZIP through embedded Python and BAT. The optimizer audit maps 26/26 sources.
- [Reporting evidence and candidate ZIP](../verify_20261118_reporting_split/REPORT.md). The successful Windows ZIP run used a shorter staging path for embedded dependency imports. Next phase starts with the local path in `module/extraction_workflows.py`.

## Stage 3 — local extraction workflow — 2026-11-18

- Moved `process_single_extraction()` and `determine_controller()` to [module/extraction_workflows.py](../module/extraction_workflows.py). Entrypoint imports and the shared lock retain object identity. CLI, remote and batch still call the same workflow.
- Baseline matched 20 unit tests, 12 CLI runs and 21 report hashes. Source and isolated ZIP also matched direct return data, quiet mode, raw directory/ZIP, explicit file output, missing-step behavior and a remote mock that runs real local extraction. Packaged Python and BAT passed local batch and reporting checks.
- [Workflow evidence and candidate ZIP](../verify_20261118_local_split/REPORT.md). Remote evidence is from mocks. The next phase moves remote coordination, followed by batch.

## Stage 3 — remote extraction workflow — 2026-11-18

- Moved remote coordination and SN detection into [module/extraction_workflows.py](../module/extraction_workflows.py). The entrypoint wrapper keeps the original signature and passes the CLI input and summary functions. SSH/WinRM transport and batch code were preserved.
- Baseline matched 20 unit tests, 12 CLI runs and 21 report hashes. Source and packaged mocks also matched run ordering, multiple output paths, prompts, list-only history behavior, session ownership, cleanup and summary/retry CSV. Python and BAT from the isolated ZIP passed local CLI checks.
- [Remote workflow evidence and candidate ZIP](../verify_20261118_remote_split/REPORT.md). Remote evidence is from mocks. Next phase moves batch coordination.

## Stage 3 — batch extraction workflow — 2026-11-18

- Moved batch execution and IP target detection to [module/extraction_workflows.py](../module/extraction_workflows.py). The entrypoint keeps the original batch signature and passes the existing CLI remote adapter and summary renderer. Local/remote parsing and transport bodies were preserved.
- Baseline matched 20 unit tests, 12 CLI runs and 21 report hashes. Before/after and packaged batch mocks matched result order, host serialization and parallelism, SSH reuse, fail-fast and summary/retry CSV. Python and BAT from the isolated ZIP passed local CLI checks.
- [Batch evidence and candidate ZIP](../verify_20261118_batch_split/REPORT.md). Remote evidence is from mocks. Stage 3 is complete. Next phase extracts `module/cli_ui.py`.

## Stage 4 — terminal UI — 2026-11-18

- Moved 14 functions for the banner, menus, input, station map, Windows dialogs and post-actions to [module/cli_ui.py](../module/cli_ui.py). Argparse and dispatch stay in the entrypoint. Entry adapters preserve signatures, imports and the existing workflow calls.
- Baseline matched 20 unit tests, 12 CLI runs and 21 report hashes. All 20 UI checks matched source and embedded Python. Packaged Python and BAT passed piped mode 7 and a Windows PTY run using the individual 7, R and Q keys.
- [Verification and candidate ZIP](../verify_20261118_cli_split/REPORT.md). Native dialogs, Explorer/Clipboard operations and remote sessions were tested through mocks. The planned module split is complete, with live desktop dialog verification tracked separately.

## PN P61070-001 (HPE MSA 2070 FC Controller) — 2026-11-19

- Added [module/extract_p61070.py](../module/extract_p61070.py) and wired PN `P61070-001` detection/dispatch across [module/log_io.py](../module/log_io.py), [module/extraction_workflows.py](../module/extraction_workflows.py), [module/reporting.py](../module/reporting.py), [module/cli_ui.py](../module/cli_ui.py), and [extract_mfg_logs.py](../extract_mfg_logs.py).
- Parses all 5 Section-4 commands from `test_mfg_restore_default_setting/debug.log` (4 commands + XML fallback) and the final post-reset XML `<RESPONSE REQUEST="show certificates">` in `test_restore_defaults_factory_remove_certs/debug.log`, cross-checking SN against `controllers`, `enclosure-fru`, and `redundancy`.
- Outputs both `FW.txt` (MSA CLI format with non-colliding 2-column `Versions` and real status timestamps) and `FW_RAW.md` (Markdown 2-column `Versions` table + complete filtered `key: value` dumps), keeping target controller/IOM isolated (`compare_with_golden_sample()` now checks `.txt` and `.md`).
- 27 unit tests pass (20 existing + 7 in [tests/test_p61070_reports.py](../tests/test_p61070_reports.py)). Baseline capture matches all 12 prior cases / 21 SHA-256 report hashes (`io_api` signatures and `I/O probes` intact; old `verify_20261118_io_baseline/run_nfkgeuo0/baseline.json` gave local `PermissionError`, so comparison verified against readable `verify_20261117_rpc73/results.json`).
- Verified real `rbod_fin2_test_uut0_P61070-001_1VAD4YB000_1VAD4YB007_20260928-155654` folder, `.zip` archive, `--batch-dir`, and `--cycle-time` in `verify_20261119_p61070/`: folder, `.zip`, and `--batch-dir` outputs match 100% SHA-256 (`1VAD4YB007`: `FW.txt` 214 lines / 9,783 B `ddb93518...`, `FW_RAW.md` 893 lines / 26,018 B `363a7dcb...`; `1VAD4YB000`: `FW.txt` 214 lines / 9,780 B `bd408193...`, `FW_RAW.md` 893 lines / 26,013 B `97282205...`). Existing `config.json`, `reports/`, `downloads/`, `dist/`, and unrelated worktree files preserved; live bridge and standalone ZIP package rebuild not exercised in this change.

## PN S1H41-62001 (HPE MSA 2070 FC LFF Chassis) — 2026-11-19

- Added [module/extract_s1h41.py](../module/extract_s1h41.py) and wired PN `S1H41-62001` (`Chas S1H41`) detection/dispatch across [module/extraction_workflows.py](../module/extraction_workflows.py), [module/reporting.py](../module/reporting.py), [module/cli_ui.py](../module/cli_ui.py), and [extract_mfg_logs.py](../extract_mfg_logs.py), leaving `module/extract_p61070.py`, `module/log_io.py`, and CLI help/flags unchanged.
- Parses all 6 Section-5 commands: `show firmware-bundles all` (last valid XML from `test_rbod_rfwd` Step 57 with fallback to `test_restore_default_factory_firmware` Step 55, yielding `Active/Default`), `show system`, `show license`, `show frus detail`, and `show configuration` from `test_mfg_restore_default_setting` (Step 62 dict + XML fallback), plus post-reset `show certificates` (last valid XML in `test_restore_defaults_factory_remove_certs` Step 58 keeping both Controller A & B). Validates target SN against midplane, SKU, and FRU serials before writing.
- Outputs `FW.txt` (546 lines on real sample, MSA CLI format with `Midplane Serial Number`, all 17 `show license` lines, 5 FRUs with `Configuration SN` and PSU `Original SN/PN/Rev`, both controllers, non-colliding 2-column `Versions` and `PSU Versions`, `Root Expander-A/B`, Port A/B tables with `Speed(C)`, Disks/Slots/Disk Groups/Pools/Enclosures, and A/B certificates) and `FW_RAW.md` (2,688 lines with 2-column Markdown tables for `Versions` and `PSU Versions` + complete YAML dumps).
- 34 unit tests pass (27 existing + 7 in [tests/test_s1h41_reports.py](../tests/test_s1h41_reports.py)). Regression baseline `verify_20261118_io_baseline/capture.py --compare verify_20261118_io_baseline/run_m4s02ais/baseline.json` passed (`Behavior matches supplied baseline`, exit 0, all 12 prior cases + `cli_help_sha256` + `io_api` + `probes`). Real `P61070-001` (`1VAD4YB007`) matched `verify_20261119_p61070/raw_dir/1VAD4YB007` 100% SHA-256 (`ddb93518...` / `363a7dcb...`).
- Verified real `rbod_fin2_test_uut0_S1H41-62001_1VAD4ZB004_20261106-170516` directory (explicit SN & auto-detected SN), `.zip` archive, `--batch-dir`, and `--cycle-time` in `verify_20261119_s1h41/`: all extraction paths match 100% SHA-256 (`FW.txt`: 546 lines / 19,750 B `de58192108da56d4c9604047851036d4427991dac887f08b84c74ea259c8a7fe`; `FW_RAW.md`: 2,688 lines / 77,590 B `9c12bf632fdd1d08520099eb4fb6a25526c814c16ddeb3f64a12166e9a34c121`) with CRLF, zero trailing spaces, and `Warnings=OK`. Existing `config.json`, `reports/`, `downloads/`, `dist/`, and unrelated worktree files preserved; live bridge and standalone ZIP package rebuild not exercised in this change.

## PN 9D57G — Customer VPD theo mẫu mới — 2026-11-19

- Parser giữ bảng `3898` của canister khớp SN đến hết dấu phân cách sau `fru_description`. Mẫu `SAFVN26468368FF_Sample` hiện hành bổ sung Customer PN/SN/Rev, CRC và FRU Description. [Parser](../module/extract_rpc73.py)
- `SAFVN26468368FF` (`ctrlb`) khớp mẫu từng byte trên source và ZIP thử nghiệm, 140 dòng / 8.320 byte. `SAFVN26468368ED` (`ctrla`) cũng có 140 dòng và khớp hash giữa source và ZIP. Ca thiếu dấu phân cách cuối trả mã 1 trước khi ghi báo cáo.
- Toàn bộ 35 unit test đạt. 26 báo cáo hồi quy của 11 ca cũ và ba ca HPE khớp SHA-256. ZIP chạy qua Python nhúng và BAT, gồm hai ca HPE để xác nhận runtime XML. Phạm vi kiểm chứng là CLI local.
- Runtime 3.13.13 trong ZIP gốc thiếu thư viện chuẩn `xml` cần cho parser HPE hiện tại. ZIP thử nghiệm bổ sung 22 file Python của `xml` từ bản CPython cùng phiên bản. [Báo cáo, manifest và ZIP thử nghiệm](../verify_20261119_9d57g_update/REPORT.md)

## PN 9D57G — nhãn Dòng SP theo tên gói log

- Điều phối IOM lấy PN từ token sau `uut` trong tên thư mục hoặc archive. Banner, bảng kết quả và `Product_Family` trong CSV hiển thị `IOM 9D57G` cho gói 9D57G. Cột `Part_Number` lấy cùng PN. VPD 49 vẫn dùng để nhận diện cấu trúc log và ghép đúng canister. [Điều phối IOM](../module/extraction_workflows.py)
- Kiểm chứng cả hai canister 9D57G, 9D57G kiểu cũ và RPC73 trên source và ZIP thử nghiệm. Các hash `FW_VPD.txt` khớp kết quả trước chỉnh nhãn và `SAFVN26468368FF` khớp mẫu. Toàn bộ 36 unit test đạt, gồm ca cố tình để PN trong metadata khác tên gói.
- Kiểm chứng package còn chạy hai ca HPE với runtime Python 3.13.13 đã bổ sung XML trong staging. [Manifest ZIP](../verify_20261119_9d57g_product/zip_0ru7e4cz/results.json)

## PN S3T80-62001 (HPE MSA 2070 32Gb FC SFF Chassis) — 2026-11-20

- Added [module/extract_s3t80.py](../module/extract_s3t80.py) and wired PN `S3T80-62001` (`Chas S3T80`) detection/dispatch across [module/extraction_workflows.py](../module/extraction_workflows.py), [module/reporting.py](../module/reporting.py), [module/cli_ui.py](../module/cli_ui.py), and [extract_mfg_logs.py](../extract_mfg_logs.py), leaving `module/extract_p61070.py`, `module/extract_s1h41.py`, `module/log_io.py`, and CLI help/flags unchanged.
- Parses all 7 FAIR Section-4 commands: `show firmware-bundles`, `show system`, `show license`, `show frus detail` (rendered `# show fru detail`), `show frus secrets` (dict or XML `show frus secrets`/`show fru secrets`, rendered `# show fru secrets detail` with 10 `Midplane Information` fields), and `show configuration` (24 SFF drive slots, `MSA2070-ENCL-SFF`/`2U24-12Gv3`, connected 32Gb ports and empty `Speed(A)` for `N/A` ports) from `test_mfg_restore_default_setting`, plus post-reset `show certificates` (both A & B) from `test_restore_defaults_factory_remove_certs`. Validates target SN across `midplane-serial-number`, `enclosure-sku`, `CHASSIS_MIDPLANE`, `fru-tlasn`, and `fru-oemsn` before writing.
- 43 unit tests pass (36 existing + 7 in [tests/test_s3t80_reports.py](../tests/test_s3t80_reports.py)). Per-case regression checks confirmed `cli_help_sha256`, `io_api`, all 7 legacy cases inside `capture.py`, plus `w47dg_zip`, `rpc73_new`, `rpc73_ctrlb`, and moved `7pntn` (in `downloads/172.19.116.172/New folder/`, moved externally before this session) all match `run_m4s02ais/baseline.json`; `9d57g` (`SAFVN26468368FF`) matches `reports/SAFVN26468368FF_Sample/FW_VPD.txt` (140 lines / 8,320 B `e82cb5790...` from the prior 2026-11-19 `extract_rpc73.py` update); real `P61070-001` (`1VAD4YB007`) and real `S1H41-62001` (`1VAD4ZB004`) both match prior SHA-256 100%.
- Verified real `rbod_fin2_test_uut0_S3T80-62001_1VAD4ZB02Z_20261106-170339` directory (explicit SN & auto-detected SN), `.zip` archive, `--batch-dir`, and `--cycle-time` in `verify_20261120_s3t80/`: all 4 extraction paths match 100% SHA-256 (`FW.txt`: 576 lines / 21,076 B `39645f3473fd7b1cd8a40716639d836df81c53e2bba6eba1ea0bdebf73f48777`; `FW_RAW.md`: 2,848 lines / 80,724 B `dd24f8525954d4462bc8bbed3030d7328354bc173400bf36a07fe5af50045072`) with CRLF, zero trailing spaces, `Cycle_Time_Short=2h 15m 19s`, and `Warnings=OK`. Existing `config.json`, `reports/`, `downloads/`, `dist/`, and unrelated worktree files preserved; live bridge and standalone ZIP package rebuild not exercised in this change.

## Release v1.8.0 — 2026-11-20

- **Kiến trúc Module hóa hoàn chỉnh (`module/`)**: Tách biệt rõ ràng 10 module chuyên trách (`log_io`, `extract_basic`, `extract_chassis_5u`, `extract_rpc73`, `extract_psu`, `extract_juno`, `extract_p61070`, `extract_s1h41`, `extract_s3t80`, `extraction_workflows`, `reporting`, `cli_ui`, `console_style`). Giữ nguyên 100% tương thích ngược CLI arguments và launcher `Chay_Tool_Log.bat`.
- **Hỗ trợ 3 dòng thiết bị HPE MSA 2070 (Chuẩn FAIR)**:
  - `P61070-001` (IO Controller FC): Trích xuất Section 4 FAIR (`FW.txt` định dạng CLI + `FW_RAW.md` bảng Markdown 2 cột & dump YAML) với 5 lệnh chuẩn từ `test_mfg_restore_default_setting` và post-reset certificates từ `test_restore_defaults_factory_remove_certs`.
  - `S1H41-62001` (Chassis FC LFF): Trích xuất Section 5 FAIR (`FW.txt` + `FW_RAW.md`) với 6 lệnh chuẩn gồm cả `show license`, đầy đủ 2 Controller A & B, Ports A & B có `Speed(C)`.
  - `S3T80-62001` (Chassis 32Gb FC SFF): Trích xuất Section 4 FAIR (`FW.txt` + `FW_RAW.md`) với 7 lệnh chuẩn bao gồm `show fru secrets detail` (`Midplane Information`), 24 Drive Slots SFF, Ports 32Gb.
- **Dell 5U 7PNTN & IOM 9D57G**:
  - `7PNTN`: Trích xuất Fan Controller FW (Step 07), Fan VPD 122–126 (Step 06), chuẩn hóa bố cục VPD 260 dòng.
  - `9D57G`: Canister selection qua VPD 49, bảng validation 140 dòng tới sau `fru_description`, chuẩn hóa nhãn `IOM 9D57G` theo tên gói log.
- **Bộ Kiểm Thử Toàn Diện**: 43 unit tests đạt 100% pass (từ 11 tests mở rộng lên 43 tests), bytecode compileall sạch, CLI help smoke test pass.
- **Đóng gói Phát hành**: Đóng gói `dist/JA_MFG_Log_Extractor_v1.8.0_Windows_x64.zip` (27.8 MB, SHA256: `9af6026355cfb49393d289bae1df640b191abb4804207ecc0ad2032a2c92397a`). Runtime nhúng tích hợp sẵn `xml` từ CPython 3.13. Post-package smoke test trong staging độc lập vượt qua hoàn toàn.
- **Tài liệu & Đồng bộ**: Đồng bộ `v1.8.0` trên `extract_mfg_logs.py`, `module/config.py`, `Chay_Tool_Log.bat`, `build.bat`, `ABOUT.txt`, `README.md`, `USERGUIDE.md`, `CHANGELOG.md`, `RELEASE_NOTES.md`, `dist/version.json` và `dist/SHA256SUMS.txt`. Root `config.json`, `reports/`, `downloads/` và các file runtime/data được bảo toàn.

## PN S1H42-62001 (HPE MSA 2070 16Gb FC SFF Chassis) — 2026-11-25

- Added [module/extract_s1h42.py](../module/extract_s1h42.py) and wired PN `S1H42-62001` (`Chas S1H42`) detection/dispatch across [module/extraction_workflows.py](../module/extraction_workflows.py), [module/reporting.py](../module/reporting.py), [module/cli_ui.py](../module/cli_ui.py), and [extract_mfg_logs.py](../extract_mfg_logs.py), leaving `module/extract_p61070.py`, `module/extract_s1h41.py`, `module/extract_s3t80.py`, `module/log_io.py`, and CLI help/flags unchanged.
- Parses all 8 FAIR Section-4 commands (pages 6–24): `show firmware-bundles`, `show system`, `show license`, `show frus detail`, `show frus secrets` (rendered `# show frus secrets detail` with 10 `Midplane Information` fields), `show configuration` (24 SFF drive slots, `MSA2070-ENCL-SFF`/`2U24-12Gv3`, 16Gb FC ports & empty `Speed(A)` for `N/A`), and `show advanced-settings` (26 fields; dict `Advanced Settings:` or XML fallback) from `test_mfg_restore_default_setting`, plus post-reset `show certificates` (both A & B) from `test_restore_defaults_factory_remove_certs`. Validates target SN across `midplane-serial-number`, `enclosure-sku`, `CHASSIS_MIDPLANE`, `fru-tlasn`, and `fru-oemsn` before writing.
- Added 8 unit tests in [tests/test_s1h42_reports.py](../tests/test_s1h42_reports.py); full `python -B -m unittest discover -s tests` (51 tests) passes. `cli_help_sha256` (`db1c42dd9943`) and real regressions for `P61070-001` (`1VAD4YB007`), `S1H41-62001` (`1VAD4ZB004`), and `S3T80-62001` (`1VAD4ZB02Z`) match prior SHA-256 100%.
- Verified real `rbod_fin2_test_uut0_S1H42-62001_1VAD4ZB031_20261106-161050` directory (explicit SN & auto-detected SN), `.zip` archive, `--batch-dir`, and `--cycle-time` in `verify_20261125_s1h42/`: all 4 extraction paths match 100% SHA-256 (`FW.txt`: 607 lines / 21,921 B `7f113422ad784383f5482f25bc3dfa64c3fe448cd5a3a0f6dbc897528c25c2dd`; `FW_RAW.md`: 2,943 lines / 83,643 B `61a57bdccc70b87f912c974b71571897d1f8f1f44b1c954560a8a3747a3e5eb3`) with CRLF, zero trailing spaces, `Cycle_Time_Short=2h 15m 36s`, and `Warnings=OK`. Existing `config.json`, `reports/`, `downloads/`, `dist/`, and unrelated worktree files preserved; live bridge and standalone ZIP package rebuild (`dist/`) were not exercised in this change.

## PN S1H48-62001 (HPE MSA 2070 12Gb SAS SFF Chassis) — 2026-11-25

- Added [module/extract_s1h48.py](../module/extract_s1h48.py) and wired PN `S1H48-62001` (`Chas S1H48`) detection/dispatch across [module/extraction_workflows.py](../module/extraction_workflows.py), [module/reporting.py](../module/reporting.py), [module/cli_ui.py](../module/cli_ui.py), and [extract_mfg_logs.py](../extract_mfg_logs.py), leaving all existing parsers, `module/log_io.py`, and CLI help/flags unchanged.
- Parses all 8 FAIR Section-4 commands (pages 6–23): `show firmware-bundles`, `show system`, `show license`, `show frus detail`, `show frus secrets` (rendered `# show frus secrets detail` with 10 `Midplane Information` fields), `show configuration` (with dedicated SAS port renderer `_render_ports_sas_s1h48()` displaying `Topo(C)`, `Lanes Expected`, `Active Lanes`, `Disabled Lanes` without `Speed(C)`/SFP, plus 24 SFF drive slots and `MSA2070-ENCL-SFF`/`2U24-12Gv3`), and `show advanced-settings` (26 fields; dict `Advanced Settings:` or XML fallback) from `test_mfg_restore_default_setting`, plus post-reset `show certificates` (both A & B) from `test_restore_defaults_factory_remove_certs`. Validates target SN across `midplane-serial-number`, `enclosure-sku`, `CHASSIS_MIDPLANE`, `fru-tlasn`, and `fru-oemsn` before writing.
- Added 8 unit tests in [tests/test_s1h48_reports.py](../tests/test_s1h48_reports.py); full `python -B -m unittest discover -s tests` (59 tests) passes. `cli_help_sha256` (`db1c42dd9943`) and real regressions for `P61070-001` (`1VAD4YB007`), `S1H41-62001` (`1VAD4ZB004`), `S3T80-62001` (`1VAD4ZB02Z`), and `S1H42-62001` (`1VAD4ZB031`) match prior SHA-256 100%.
- Verified real `rbod_fin2_test_uut0_S1H48-62001_1VAD4ZB02C_20261106-054514` directory (explicit SN & auto-detected SN), `.zip` archive, `--batch-dir`, and `--cycle-time` in `verify_20261125_s1h48/`: all 4 extraction paths match 100% SHA-256 (`FW.txt`: 607 lines / 21,403 B `f29aa4731be7d9ecd671f8358b23e38a8e6f05c93406b2bf18ce59fd9137f41a`; `FW_RAW.md`: 2,799 lines / 77,903 B `a7e69641b68111678467d1f555392e152f1c006aeb833585728aa3999c232dd0`) with CRLF, zero trailing spaces, `Cycle_Time_Short=2h 15m 57s`, and `Warnings=OK`. Existing `config.json`, `reports/`, `downloads/`, `dist/`, and unrelated worktree files preserved; live bridge and standalone ZIP package rebuild (`dist/`) were not exercised in this change.

## Release v1.8.2 — 2026-11-25

- **Phát hành v1.8.2 bổ sung dòng HPE MSA 2070 12Gb SAS SFF Chassis (`S1H48-62001`)**: Tích hợp [module/extract_s1h48.py](../module/extract_s1h48.py) bóc tách toàn diện 8 lệnh FAIR Section-4 với bộ dựng cổng SAS 12Gb chuyên biệt, xuất bộ đôi `FW.txt` và `FW_RAW.md`.
- **Bộ Kiểm Thử Toàn Diện**: 59 unit tests đạt 100% pass (bổ sung [tests/test_s1h48_reports.py](../tests/test_s1h48_reports.py) với 8 bài test), bytecode compileall sạch, CLI help smoke test pass.
- **Đóng gói Phát hành**: Đóng gói `dist/JA_MFG_Log_Extractor_v1.8.2_Windows_x64.zip`, cập nhật `dist/version.json` và `dist/SHA256SUMS.txt`. Post-package smoke test trong staging độc lập vượt qua hoàn toàn.
- **Tài liệu & Đồng bộ**: Đồng bộ `v1.8.2` trên `extract_mfg_logs.py`, `module/config.py`, `Chay_Tool_Log.bat`, `build.bat`, `ABOUT.txt`, `README.md`, `USERGUIDE.md`, `CHANGELOG.md`, `RELEASE_NOTES.md`. Dữ liệu cấu hình và runtime/data được bảo toàn.


## Release v1.8.1 — 2026-11-25

- **Phát hành v1.8.1 bổ sung dòng HPE MSA 2070 16Gb FC SFF Chassis (`S1H42-62001`)**: Tích hợp [module/extract_s1h42.py](../module/extract_s1h42.py) bóc tách toàn diện 8 lệnh FAIR Section-4, xuất bộ đôi `FW.txt` và `FW_RAW.md`.
- **Bộ Kiểm Thử Toàn Diện**: 51 unit tests đạt 100% pass (bổ sung [tests/test_s1h42_reports.py](../tests/test_s1h42_reports.py) với 8 bài test), bytecode compileall sạch, CLI help smoke test pass.
- **Đóng gói Phát hành**: Đóng gói `dist/JA_MFG_Log_Extractor_v1.8.1_Windows_x64.zip`, cập nhật `dist/version.json` và `dist/SHA256SUMS.txt`. Post-package smoke test trong staging độc lập vượt qua hoàn toàn.
- **Tài liệu & Đồng bộ**: Đồng bộ `v1.8.1` trên `extract_mfg_logs.py`, `module/config.py`, `Chay_Tool_Log.bat`, `build.bat`, `ABOUT.txt`, `README.md`, `USERGUIDE.md`, `CHANGELOG.md`, `RELEASE_NOTES.md`. Dữ liệu cấu hình và runtime/data được bảo toàn.


