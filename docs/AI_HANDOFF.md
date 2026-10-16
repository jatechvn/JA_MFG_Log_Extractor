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
