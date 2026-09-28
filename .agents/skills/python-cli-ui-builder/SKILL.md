---
name: python-cli-ui-builder
description: >-
  Framework and design pattern for building professional, color-coded, user-friendly Python CLI tools.
  Includes Windows ANSI color support, instant 1-keypress selection via msvcrt, smart path defaults, batch folder/CSV processing, and summary table formatting.
  Use this skill whenever asked to build or refactor a Python CLI tool or script with interactive UI and batch processing features.
---

# Python CLI UI & Feature Builder Skill

This skill provides a complete, reusable architecture and copy-pasteable template for creating professional, robust Python command-line tools. It incorporates UI/UX best practices, Windows ANSI color support, instant single-key input, batch processing, and error-isolated execution.

---

## 1. Core Architectural Pillars

### A. Windows ANSI Virtual Terminal Processing
Enables native 24-bit/16-color ANSI escape codes (`\033[...]`) on Windows CMD and PowerShell consoles:
```python
if sys.platform == 'win32':
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
            sys.stdin.reconfigure(encoding='utf-8')
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # ENABLE_PROCESSED_OUTPUT (1) | ENABLE_WRAP_AT_EOL_OUTPUT (2) | ENABLE_VIRTUAL_TERMINAL_PROCESSING (4)
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass
```

### B. Instant Single-Key Menu Selection (`msvcrt`)
Captures a single keypress instantly on Windows without waiting for the user to press `Enter`:
```python
def get_single_key_choice(prompt_text, valid_keys, default_key="1"):
    print(prompt_text, end="", flush=True)
    if sys.platform == 'win32':
        try:
            import msvcrt
            while True:
                ch = msvcrt.getwch()
                if ch in ('\r', '\n'):
                    print(f"{default_key}")
                    return default_key
                elif ch in valid_keys:
                    print(f"{ch}")
                    return ch
                elif ch == '\x03':  # Ctrl+C
                    print()
                    raise KeyboardInterrupt
        except Exception:
            pass
    inp = input().strip(' "\' \t\r\n')
    return inp if inp in valid_keys else default_key
```

### C. Reliable Script Directory Resolution
Resolves paths relative to where the script/executable actually resides (instead of `os.getcwd()`), preventing files from dropping into `C:\Users\<User>` when launched via shortcuts:
```python
def get_script_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    else:
        return os.path.dirname(os.path.abspath(__file__))
```

### D. Multi-Mode Architecture
- **Mode 1**: Single Item Interactive Mode.
- **Mode 2**: Batch Subfolder Scan Mode.
- **Mode 3**: Batch CSV / TXT Import Mode.
- **Mode 4**: Generate Template CSV File Mode.

### E. Error Isolation & Summary Table Reporting
Batch items are wrapped in individual `try...except` blocks. Failing items are marked `FAIL` without crashing the rest of the batch, followed by a formatted ANSI summary table.

### F. Windows Multi-Stage Shell Launcher (`run.bat`)
Auto-detects available terminal environments on Windows and launches in order of priority:
1. **Windows Terminal (`wt.exe`)**: Modern tabs, full ANSI color support, custom fonts.
2. **PowerShell (`powershell.exe`)**: Fallback if `wt.exe` is absent.
3. **CMD (`cmd.exe`)**: Final fallback running directly in the existing console.

Includes auto-detection of internal `python_runtime\python.exe` (Portable mode) or system `python`.

---

## 2. Reusable Template Reference

- Python Core Script Template: [`templates/cli_app_template.py`](file:///d:/JA_TESTER/LOGS_ANL/.agents/skills/python-cli-ui-builder/templates/cli_app_template.py)
- Batch Launcher Template: [`templates/run.bat`](file:///d:/JA_TESTER/LOGS_ANL/.agents/skills/python-cli-ui-builder/templates/run.bat)

### Key Sections to Customize in New Scripts:
1. **`process_single_item(input_path, extra_arg, output_dir)`**: Implement your core business logic here.
2. **`detect_item_attributes(folder_path)`**: Implement smart auto-detection from folder names.
3. **`print_header()`**: Customize tool title and subtitle banners.
