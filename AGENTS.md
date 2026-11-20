# JA_MFG_Log_Extractor

Windows-first Python 3.10+ CLI for manufacturing logs. It reads local folders/archives or fetches selected remote logs over SSH/WinRM and writes FW/VPD, diagnostics and cycle-time reports. Reply in Vietnamese by default.

## Start here

- Run `git status --short` and preserve local changes, including untracked tests. Keep edits scoped to the requested product or workflow.
- Read [AI_CONTEXT.md](docs/AI_CONTEXT.md) to find the responsible code and tests. For a continuation, read the latest relevant section of [AI_HANDOFF.md](docs/AI_HANDOFF.md) and append verified results when done.
- Use [USERGUIDE.md](USERGUIDE.md) for user-visible behavior. For product-specific extraction, read the [project extractor skill](.agents/skills/io-log-extractor/SKILL.md), then check the current raw and the sample supplied for this task. Historical examples are not current golden evidence.
- [MODULE_SPLIT_PLAN.md](docs/MODULE_SPLIT_PLAN.md) is a proposed migration, not the current code layout or authorization to refactor during unrelated work.

## Change and verification boundaries

- Preserve CLI flags and defaults, launcher and direct Python entrypoints, report filenames, exact bytes/newlines, PN/SN/controller matching and config locations unless the task explicitly changes them. Fix logic for the affected variant before touching other variants.
- Keep `config.json`, `reports/`, `downloads/`, history, raw logs, independent samples, backups and populated `dist/` intact. Do not log credentials or include them in tests, evidence or packages. Route fresh outputs to a separate ignored `verify_*` directory.
- Do not run `build.bat` on the live checkout for routine checks: it moves the embedded runtime and removes `dist/` and `dist_pack/`. Verify a candidate in isolated staging using the existing runtime when package behavior matters. A local check is not a release, push or Drive sync.
- Use the existing interpreter and `python -B -m unittest discover -s tests`. For parser changes, also run the CLI on the exact raw/SN with `--output-dir` and `--verify-sample`, and check the affected legacy output hashes. Follow [the test guide](tests/README.md).
- Separate evidence from unit tests, local extraction, unpacked ZIP, Windows UI, and live SSH/WinRM. Network checks are only for an authorized station/run; keep production history untouched. Do not claim all variants passed from one sample.
