# -*- coding: utf-8 -*-
"""Cấu hình mặc định cho JA_MFG_Log_Extractor (Remote SSH/Bridge & Local Reports).

IP, thông tin đăng nhập SSH và cấu hình Bridge (172.21.168.241 -> 172.19.*.*)
được đọc từ config.json đặt cùng thư mục với ứng dụng.
Báo cáo phân tích mặc định được lưu tập trung tại <App_Dir>/reports/.
"""
import os
import sys
from pathlib import Path
from typing import Any, Dict

from .local_config import load_local_config


APP_NAME = "JA_MFG_Log_Extractor"
APP_VERSION = "1.6.0"


def get_script_dir() -> Path:
    """Lấy đường dẫn thư mục tuyệt đối chứa script/exe hiện tại."""
    if getattr(sys, "frozen", False):
        return Path(os.path.dirname(os.path.abspath(sys.executable)))
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_script_dir()
CONFIG_PATH = BASE_DIR / "config.json"
SAMPLE_CONFIG_PATH = BASE_DIR / "config_sample.json"
REPORTS_DIR = BASE_DIR / "reports"
DOWNLOADS_DIR = BASE_DIR / "downloads"
LOGS_DIR = BASE_DIR / "logs"


def load_active_settings() -> Dict[str, Any]:
    """Đọc config.json. Nếu chưa tồn tại, trả về cấu hình mặc định (hoặc báo lỗi khi kết nối từ xa)."""
    if CONFIG_PATH.is_file():
        return load_local_config(CONFIG_PATH)
    return {
        "network": {
            "client_cidr": "172.21.0.0/16",
            "target_cidr": "172.19.0.0/16",
            "ip_prefix": "172.19",
        },
        "ssh": {
            "username": "root",
            "password": "",
            "port": 22,
            "fallback_credentials": [("seagate", "")],
        },
        "windows_ssh": {
            "username": "V1801179",
            "password": "",
        },
        "bridge": {
            "mode": "auto",
            "transport": "auto",
            "host": "172.21.168.241",
            "ssh_port": 22,
            "winrm_port": 5985,
            "username": "V1801179",
            "password": "",
            "connect_timeout": 15,
            "target_networks": ["172.19.0.0/16"],
        },
    }


try:
    LOCAL_SETTINGS = load_active_settings()
    CONFIG_ERROR_MSG = ""
except ValueError as exc:
    CONFIG_ERROR_MSG = str(exc)
    LOCAL_SETTINGS = {
        "network": {
            "client_cidr": "172.21.0.0/16",
            "target_cidr": "172.19.0.0/16",
            "ip_prefix": "172.19",
        },
        "ssh": {
            "username": "root",
            "password": "",
            "port": 22,
            "fallback_credentials": [],
        },
        "windows_ssh": {
            "username": "V1801179",
            "password": "",
        },
        "bridge": {
            "mode": "auto",
            "transport": "auto",
            "host": "172.21.168.241",
            "ssh_port": 22,
            "winrm_port": 5985,
            "username": "V1801179",
            "password": "",
            "connect_timeout": 15,
            "target_networks": ["172.19.0.0/16"],
        },
    }

# Thông tin đăng nhập rig test từ JSON, có thể override qua môi trường hoặc CLI.
DEFAULT_SSH_USER = os.environ.get("LOG_DL_SSH_USER", LOCAL_SETTINGS["ssh"]["username"])
DEFAULT_SSH_PASSWORD = os.environ.get("LOG_DL_SSH_PASSWORD", LOCAL_SETTINGS["ssh"]["password"])
DEFAULT_SSH_PORT = int(os.environ.get("LOG_DL_SSH_PORT", LOCAL_SETTINGS["ssh"]["port"]))

# Đường dẫn log mặc định trên máy đích Linux
DEFAULT_REMOTE_BASE_PATH = os.environ.get("LOG_DL_REMOTE_PATH", "/CTP/logs/test/")

# Thông tin đăng nhập SSH mặc định cho máy test Windows trong xưởng
DEFAULT_WIN_SSH_USER = os.environ.get("LOG_DL_WIN_USER", LOCAL_SETTINGS["windows_ssh"]["username"])
DEFAULT_WIN_SSH_PASSWORD = os.environ.get("LOG_DL_WIN_PASSWORD", LOCAL_SETTINGS["windows_ssh"]["password"])
DEFAULT_WIN_REMOTE_BASE_PATH = os.environ.get("LOG_DL_WIN_REMOTE_PATH", "D:/JA_sendfile-seagate/SgCsvLogs")

# Danh sách thư mục ứng viên quét log thông minh nếu không thấy ở đường dẫn mặc định
LINUX_CANDIDATE_PATHS = [
    "/CTP/logs/test/",
    "/CTP/logs/",
    "/home/seagate/logs/",
]
WINDOWS_CANDIDATE_PATHS = [
    "D:/JA_sendfile-seagate/SgCsvLogs",
    "D:/sendfile-seagate/SgCsvLogs",
    "D:/JA_TESTER/LOGS_ANL",
    "D:/",
    "C:/SgCsvOutput",
]

# Dải mạng IP các máy test trong xưởng luôn cố định 2 octet đầu -> cho phép
# người dùng chỉ gõ 2 octet cuối (vd "116.174" hoặc "116174") thay vì gõ đầy đủ IP.
DEFAULT_IP_PREFIX = os.environ.get("LOG_DL_IP_PREFIX", LOCAL_SETTINGS["network"]["ip_prefix"])

SSH_CONNECT_TIMEOUT_SEC = int(os.environ.get("LOG_DL_CONNECT_TIMEOUT", "15"))
SSH_KEEPALIVE_INTERVAL_SEC = int(os.environ.get("LOG_DL_KEEPALIVE", "15"))
SFTP_MAX_RETRIES = int(os.environ.get("LOG_DL_MAX_RETRIES", "3"))
ENABLE_REMOTE_PRECOMPRESS = os.environ.get("LOG_DL_PRECOMPRESS", "1").lower() in ("1", "true", "yes")
