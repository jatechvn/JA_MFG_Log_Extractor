# Verification guide

From the project root, run the existing unittest suite with `python -B -m unittest discover -s tests`. A targeted run is `python -B -m unittest tests.test_smart_features`. Keep the established interpreter and dependencies.

| Test module | Scope |
| --- | --- |
| [test_smart_features.py](test_smart_features.py) | Station/IP helpers, selection, table, history, list-only and mock SSH behavior |
| [test_w47dg_fw.py](test_w47dg_fw.py) | W47DG Midplane status from Step 07 |
| `tests/test_7pntn_reports.py` | PN and selected Fan/WWN/Customer VPD rules in the current worktree |
| `tests/test_rpc73_reports.py` | Canister SN matching and validation end markers for 9D57G/RPC73 in the current worktree |
| `tests/test_p61070_reports.py` | P61070-001 PN/SN detection, controller cross-check, post-reset certificates, 2-column Versions and `FW.txt`/`FW_RAW.md` output |
| `tests/test_s1h41_reports.py` | S1H41-62001 PN/SN detection, `show firmware-bundles all` selection, midplane/SKU SN cross-check, 2-column `Versions`/`PSU Versions`, A/B ports & certificates and `FW.txt`/`FW_RAW.md` output |
| `tests/test_s1h42_reports.py` | S1H42-62001 PN/SN detection, `show frus detail`/`show frus secrets detail`/`show advanced-settings` (dict `Advanced Settings` & XML fallback), midplane/SKU/fru-secrets SN cross-check, 24 SFF slots, 2-column `Versions`/`PSU Versions`, A/B ports & certificates and `FW.txt`/`FW_RAW.md` output |
| `tests/test_s1h44_reports.py` | S1H44-62001 PN/SN detection, 10/25GbE iSCSI ports (`iqn.` + `Port Details` 11 fields, blank `Speed(A)` for disconnected ports), `show advanced-settings` dict/XML fallback, midplane/SKU/fru-secrets SN cross-check, 24 SFF slots, post-reset A/B certificates past split `Bytes read:` lines and `FW.txt`/`FW_RAW.md` output |
| `tests/test_s1h47_reports.py` | S1H47-62001 PN/SN detection, 12Gb SAS ports (`Direct` + Lanes, no `Speed(C)`/SFP) & disconnected empty `Speed(A)`, `show advanced-settings` dict/XML fallback, midplane/SKU/fru-secrets SN cross-check, 12 LFF slots, A/B certificates and `FW.txt`/`FW_RAW.md` output |
| `tests/test_s1h48_reports.py` | S1H48-62001 PN/SN detection, 12Gb SAS ports (`Direct` + Lanes, no `Speed(C)`/SFP) & disconnected empty `Speed(A)`, `show advanced-settings` dict/XML fallback, midplane/SKU/fru-secrets SN cross-check, 24 SFF slots, A/B certificates and `FW.txt`/`FW_RAW.md` output |
| `tests/test_s3t80_reports.py` | S3T80-62001 PN/SN detection, `show frus secrets` (`show fru secrets` XML alias) & midplane/SKU SN cross-check, connected 32Gb & empty `Speed(A)` ports, 24 SFF slots, 2-column `Versions`/`PSU Versions`, A/B certificates and `FW.txt`/`FW_RAW.md` output |

For FW/VPD changes, run the CLI with the supplied raw path, `--target-sn`, independent output directory and `--verify-sample`. Use the latest relevant entry in [AI_HANDOFF.md](../docs/AI_HANDOFF.md) to locate local evidence; ignored verification folders and golden samples are not present on every machine. Compare filenames and bytes, including line endings and trailing spaces. If a fixture is unavailable, mark that check unverified rather than substituting a stale sample. The synthetic unit tests do not exercise the packaged Python runtime or a live bridge.
