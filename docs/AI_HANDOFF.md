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
