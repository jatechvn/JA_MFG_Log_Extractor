# Module navigation

[Project map](../docs/AI_CONTEXT.md) · [Test guide](../tests/README.md)

| Responsibility | Start here |
| --- | --- |
| Local log/step discovery, archive input, report paths and writing | [log_io.py](log_io.py): `find_step_dir()`, `prepare_log_input_source()` and `write_extracted_file()`; existing entrypoint imports remain available |
| HPE MSA 2070 FC (PN P61070-001) | [extract_p61070.py](extract_p61070.py): `extract_p61070_logs()`; Step `test_mfg_restore_default_setting` + post-reset `show certificates`, SN-to-controller validation and `FW.txt`/`FW_RAW.md` |
| HPE MSA 2070 FC LFF Chassis (PN S1H41-62001) | [extract_s1h41.py](extract_s1h41.py): `extract_s1h41_logs()`; Step `test_rbod_rfwd`/`test_restore_default_factory_firmware` (`show firmware-bundles all`) + Step `test_mfg_restore_default_setting` + post-reset `show certificates` (A & B), midplane/SKU SN validation and `FW.txt`/`FW_RAW.md` |
| HPE MSA 2070 16Gb FC SFF Chassis (PN S1H42-62001) | [extract_s1h42.py](extract_s1h42.py): `extract_s1h42_logs()`; Step `test_mfg_restore_default_setting` (`show firmware-bundles`, `show frus secrets`, 24 SFF slots, `show advanced-settings`) + post-reset `show certificates` (A & B), midplane/SKU/fru-secrets SN validation and `FW.txt`/`FW_RAW.md` |
| HPE MSA 2070 12Gb SAS SFF Chassis (PN S1H48-62001) | [extract_s1h48.py](extract_s1h48.py): `extract_s1h48_logs()`; Step `test_mfg_restore_default_setting` (8 commands, 12Gb SAS ports with Lanes, 24 SFF slots, `show advanced-settings`) + post-reset `show certificates` (A & B), midplane/SKU/fru-secrets SN validation and `FW.txt`/`FW_RAW.md` |
| HPE MSA 2070 32Gb FC SFF Chassis (PN S3T80-62001) | [extract_s3t80.py](extract_s3t80.py): `extract_s3t80_logs()`; Step `test_mfg_restore_default_setting` (`show firmware-bundles`, `show frus secrets`, 24 SFF slots) + post-reset `show certificates` (A & B), midplane/SKU/fru-secrets SN validation and `FW.txt`/`FW_RAW.md` |
| Dell 5U FW/VPD for W47DG and 7PNTN | [extract_chassis_5u.py](extract_chassis_5u.py): `extract_chassis_5u_dell_logs()`; Step 07 Midplane, 7PNTN Fan/WWN/VPD and legacy W47DG output |
| IOM FW/VPD for RPC73 and 9D57G | [extract_rpc73.py](extract_rpc73.py): `extract_iom_rpc73()`; VPD 49 serial matching, controller pairing and variant-specific validation end markers |
| PSU 2U DYJW5 and 5U 0R4C4 | [extract_psu.py](extract_psu.py): `extract_psu_logs()`; model detection, PCM selection and Step 06/07 report sections |
| Juno 4U chassis (FVB) | [extract_juno.py](extract_juno.py): `extract_chassis_4u_logs()`; six reports and GETVPD/VER pairing from raw or archived enclosure logs |
| Standard IO and Chassis 2U | [extract_basic.py](extract_basic.py): `extract_fw()` and `extract_vpd()` for the requested IO controller, `extract_chassis_vpd()` for 2U. All three use cleaned log lines. |
| Cycle-time metadata, result CSV, diagnostics and golden comparison | [reporting.py](reporting.py): `extract_cycle_time_metadata()`, `export_cycle_time_summary_csv()`, `analyze_test_failures()` and `compare_with_golden_sample()`. [console_style.py](console_style.py) supplies ANSI styles for both CLI and reporting. |
| Local single-unit extraction and controller selection | [extraction_workflows.py](extraction_workflows.py): `process_single_extraction()` chooses the parser, validates the result and returns the result dictionary used by the CLI, batch and remote workflows. |
| Remote extraction workflow | [extraction_workflows.py](extraction_workflows.py): `process_remote_extraction()` owns log selection, service lifecycle at the workflow level, handoff to local extraction, history and CSV. |
| Batch extraction workflow | [extraction_workflows.py](extraction_workflows.py): `run_batch_extraction()` dispatches local and remote items, preserves result order and manages per-host locks, sessions and retry CSV. |
| Interactive terminal UI | [cli_ui.py](cli_ui.py): menus, input and key handling, station diagram, native dialog invocation and post-extraction actions. |
| SSH session, remote search and selective download | [remote_fetcher.py](remote_fetcher.py): `SshLogService.connect()`, `find_matching_entries()` and `fetch_selective_log_to_temp()` |
| Bridge policy and socket fallback | [bridge.py](bridge.py), [winrm_socket.py](winrm_socket.py), [winrm_bridge.ps1](winrm_bridge.ps1) |
| Runtime paths, configuration loading and validation | [config.py](config.py), [local_config.py](local_config.py) |
| IP normalization and station map | [ip_utils.py](ip_utils.py) |
| Search results, P/F/L/A selection and table formatting | [log_finder.py](log_finder.py) |
| Clipboard, Explorer, retry CSV and recent history | [smart_actions.py](smart_actions.py) |
| Remote/path helpers and shared errors | [path_utils.py](path_utils.py), [exceptions.py](exceptions.py). The CLI's existing extended-path semantics are in `log_io.py`. |

Argument parsing, CLI dispatch and batch input discovery live in [extract_mfg_logs.py](../extract_mfg_logs.py). The entrypoint wires menu actions to the existing workflows. Do not move report formatting into SSH transport. Preserve connection ownership, retries, per-host locking and the absence of history writes in `--list-only`. Use the established mock tests before any authorized live check.
