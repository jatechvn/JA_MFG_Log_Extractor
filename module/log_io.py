"""Shared log and report I/O for the extractor.

Product detection, report content and CLI orchestration belong to the callers.
"""

import contextlib
import os
import re
import shutil
import sys
import tarfile
import tempfile
import zipfile


def to_long_path(path):
    """
    Convert a path to Windows extended-length path (\\\\?\\...) if running on Windows.
    Bypasses the 260-character MAX_PATH limit.
    """
    if sys.platform == 'win32' and path:
        abs_p = os.path.abspath(path)
        if not abs_p.startswith('\\\\?\\') and not abs_p.startswith('\\\\.\\'):
            if abs_p.startswith('\\\\'):
                return '\\\\?\\UNC\\' + abs_p[2:]
            return '\\\\?\\' + abs_p
        return abs_p
    return os.path.abspath(path) if path else path


def from_long_path(path):
    """Strip \\\\?\\ or \\\\?\\UNC\\ prefix if present for clean display to user."""
    if path and isinstance(path, str):
        if path.startswith('\\\\?\\UNC\\'):
            return '\\\\' + path[8:]
        if path.startswith('\\\\?\\'):
            return path[4:]
    return path


def get_script_dir():
    """
    Get absolute directory path where extract_mfg_logs.py (or frozen executable) is located.
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    else:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_default_reports_dir():
    """
    Return the centralized reports directory inside the app folder (<App_Dir>/reports).
    """
    rep_dir = os.path.join(get_script_dir(), "reports")
    os.makedirs(to_long_path(rep_dir), exist_ok=True)
    return rep_dir


def get_default_downloads_dir():
    """
    Return the centralized downloads directory inside the app folder (<App_Dir>/downloads).
    """
    dl_dir = os.path.join(get_script_dir(), "downloads")
    os.makedirs(to_long_path(dl_dir), exist_ok=True)
    return dl_dir


def find_step_dir(test_results_dir, pattern):
    """
    Find the directory inside test-results matching pattern.
    If multiple match, pick the one with the highest step number prefix.
    """
    long_tr = to_long_path(test_results_dir)
    if not os.path.exists(long_tr):
        raise FileNotFoundError(f"Directory not found: {from_long_path(test_results_dir)}")

    matching_dirs = []
    for item in os.listdir(long_tr):
        full_path = os.path.join(test_results_dir, item)
        if os.path.isdir(to_long_path(full_path)) and pattern in item:
            match = re.match(r'^(\d+)-', item)
            step_num = int(match.group(1)) if match else 0
            matching_dirs.append((step_num, full_path))

    if not matching_dirs:
        raise FileNotFoundError(f"No test step directory matching '{pattern}' in {from_long_path(test_results_dir)}")

    matching_dirs.sort(key=lambda x: x[0], reverse=True)
    return matching_dirs[0][1]


def clean_log_lines(filepath):
    """
    Read debug.log and replace 'YYYY-MM-DD...(|XXXX|)' prefix with '$1'.
    """
    long_p = to_long_path(filepath)
    if not os.path.exists(long_p):
        raise FileNotFoundError(f"Log file not found: {from_long_path(filepath)}")

    with open(long_p, 'r', encoding='utf-8', errors='ignore') as f:
        raw_lines = f.readlines()

    clean_lines = [re.sub(r'^\d{4}-\d{2}-\d{2}.*?(\|\d+\|)', r'\1', l) for l in raw_lines]
    return clean_lines


def write_extracted_file(filepath, lines, trim_last_newline=True):

    """
    Write extracted lines to file preserving Windows CRLF line endings.
    """
    if not lines:
        return

    long_p = to_long_path(filepath)
    os.makedirs(os.path.dirname(long_p), exist_ok=True)
    with open(long_p, 'w', encoding='utf-8', newline='\r\n') as f:
        for i, line in enumerate(lines):
            if i == len(lines) - 1 and trim_last_newline:
                f.write(line.rstrip('\r\n'))
            else:
                f.write(line)


def resolve_output_paths(base_output_dir, target_sn, is_chassis, unit_root=None):
    """
    Resolve target output directory and output file paths.
    """
    if not base_output_dir:
        base_output_dir = get_default_reports_dir()
    clean_base = base_output_dir.strip(' "\' \t\r\n')

    if clean_base.lower().endswith('.txt'):
        out_dir = os.path.dirname(os.path.abspath(clean_base))
        if is_chassis:
            return out_dir, os.path.abspath(clean_base)
        else:
            return out_dir, None

    abs_base = os.path.abspath(clean_base)
    if os.path.basename(abs_base.rstrip('\\/')) == target_sn:
        target_dir = abs_base
    else:
        target_dir = os.path.join(abs_base, target_sn)

    os.makedirs(to_long_path(target_dir), exist_ok=True)

    if is_chassis:
        chassis_file = os.path.join(target_dir, f"{target_sn}.txt")
        return target_dir, chassis_file
    else:
        return target_dir, None


def is_archive_path(path):
    """Return True if path points to a supported archive (.zip, .tar.gz, .tgz, .tar.xz)."""
    if not path:
        return False
    low = path.strip(' "\' \t\r\n').lower()
    return low.endswith(('.zip', '.tar.gz', '.tgz', '.tar.xz'))


def strip_archive_ext(filename):
    """Strip archive extension (.zip, .tar.gz, .tgz, .tar.xz) from filename."""
    for ext in ('.tar.gz', '.tar.xz', '.tgz', '.zip'):
        if filename.lower().endswith(ext):
            return filename[:-len(ext)]
    return filename


def find_test_results_dir(input_dir):
    """
    Locate the 'test-results' directory inside input_dir regardless of nesting level.
    """
    abs_input = os.path.abspath(input_dir.strip(' "\' \t\r\n'))
    long_input = to_long_path(abs_input)

    if os.path.basename(abs_input.rstrip('\\/')) == 'test-results' and os.path.isdir(long_input):
        return abs_input

    direct_tr = os.path.join(abs_input, 'test-results')
    if os.path.isdir(to_long_path(direct_tr)):
        return direct_tr

    latest_tr = os.path.join(abs_input, 'latest', 'test-results')
    if os.path.isdir(to_long_path(latest_tr)):
        return latest_tr

    if os.path.isdir(long_input):
        try:
            for item in os.listdir(long_input):
                full_item = os.path.join(abs_input, item)
                if item.startswith('job-'):
                    tr = os.path.join(full_item, 'test-results')
                    if os.path.isdir(to_long_path(tr)):
                        return tr
        except Exception:
            pass

    for root, dirs, files in os.walk(long_input):
        if 'test-results' in dirs:
            return from_long_path(os.path.join(root, 'test-results'))

    raise FileNotFoundError(f"Không tìm thấy thư mục 'test-results' trong {from_long_path(input_dir)}")


def get_log_unit_root(input_dir):
    """
    Given an input directory (which may be unit root, latest, job-*, test-results, or archive file),
    resolve and return the top-level raw log folder (unit root).
    """
    abs_input = os.path.abspath(input_dir.strip(' "\' \t\r\n'))
    if os.path.isfile(to_long_path(abs_input)) and is_archive_path(abs_input):
        return os.path.join(os.path.dirname(abs_input), strip_archive_ext(os.path.basename(abs_input)))
    try:
        tr = find_test_results_dir(abs_input)
        unit_root = os.path.dirname(tr)
        if os.path.basename(unit_root) == 'latest' or os.path.basename(unit_root).startswith('job-'):
            unit_root = os.path.dirname(unit_root)
        return unit_root
    except Exception:
        return abs_input


def _should_extract_archive_member(member_name):
    """
    Selective filter for archive members: skip heavy serial_logs, sysinfo, sqlite, html
    while keeping all test-results debug.log, enc_logs, results.json/xml, job.log, and top-level logs.
    """
    norm = member_name.replace('\\', '/')
    low = norm.lower()
    if '/serial_logs/' in low or low.startswith('serial_logs/'):
        return False
    if '/sysinfo/' in low or low.startswith('sysinfo/'):
        return False
    if '/connection_configs/' in low or low.startswith('connection_configs/'):
        return False
    if low.endswith(('.journal.sqlite', 'results.html', 'results.tap', '.pyc')):
        return False
    return True


@contextlib.contextmanager
def prepare_log_input_source(input_path_raw):
    """
    Context manager that accepts either a folder path or an archive (.zip, .tar.gz, .tgz, .tar.xz).
    If an archive is provided, selectively extracts needed files to a fast temporary directory
    and cleans up automatically upon exit.
    Yields: (working_input_dir, logical_unit_root, logical_folder_name)
    """
    abs_input = os.path.abspath(input_path_raw.strip(' "\' \t\r\n'))
    long_input = to_long_path(abs_input)

    if os.path.isfile(long_input) and is_archive_path(abs_input):
        tmp_dir = tempfile.mkdtemp(prefix="ja_mfg_zip_")
        logical_name = strip_archive_ext(os.path.basename(abs_input))
        logical_unit_root = os.path.join(os.path.dirname(abs_input), logical_name)
        try:
            low_path = abs_input.lower()
            if low_path.endswith('.zip'):
                with zipfile.ZipFile(long_input, 'r') as zf:
                    for info in zf.infolist():
                        if info.is_dir():
                            continue
                        if _should_extract_archive_member(info.filename):
                            target_p = os.path.join(tmp_dir, *info.filename.replace('\\', '/').split('/'))
                            os.makedirs(to_long_path(os.path.dirname(target_p)), exist_ok=True)
                            with zf.open(info, 'r') as src, open(to_long_path(target_p), 'wb') as dst:
                                shutil.copyfileobj(src, dst)
            else:
                with tarfile.open(long_input, 'r:*') as tf:
                    for member in tf.getmembers():
                        if not member.isfile():
                            continue
                        if _should_extract_archive_member(member.name):
                            target_p = os.path.join(tmp_dir, *member.name.replace('\\', '/').split('/'))
                            os.makedirs(to_long_path(os.path.dirname(target_p)), exist_ok=True)
                            src = tf.extractfile(member)
                            if src:
                                with src, open(to_long_path(target_p), 'wb') as dst:
                                    shutil.copyfileobj(src, dst)

            entries = [d for d in os.listdir(to_long_path(tmp_dir)) if os.path.isdir(to_long_path(os.path.join(tmp_dir, d)))]
            if len(entries) == 1 and entries[0] not in ('test-results', 'latest', 'enc_logs') and not entries[0].startswith('job-'):
                working_dir = os.path.join(tmp_dir, entries[0])
            else:
                working_dir = tmp_dir
            yield working_dir, logical_unit_root, logical_name
        finally:
            shutil.rmtree(to_long_path(tmp_dir), ignore_errors=True)
    else:
        unit_root = get_log_unit_root(abs_input)
        folder_name = os.path.basename(unit_root.rstrip('\\/'))
        yield abs_input, unit_root, folder_name


def get_log_package_pn(folder_name):
    """Read the PN token between the UUT and serial number in a log name."""
    match = re.search(r'_uut\d+_([A-Z0-9-]+)_(?:S[AG]F|FVB|PM)', folder_name, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    match = re.search(
        r'_uut\d+_([A-Z0-9-]+)_(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*\d)[A-Z0-9]{10,}(?:_|$)',
        folder_name,
        re.IGNORECASE,
    )
    return match.group(1).upper() if match else ""
