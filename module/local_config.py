"""Load local JSON settings, creating a credential-free template if absent."""
import ipaddress
import json
import logging
from copy import deepcopy
from pathlib import Path
from typing import Dict

logger = logging.getLogger("log_downloader.config")

DEFAULT_SETTINGS = {
    "network": {
        "ip_prefix": "172.19",
        "target_network": "172.19.0.0/16",
        "client_network": "172.21.0.0/16",
    },
    "bridge": {
        "host": "172.21.168.241",
        "username": "V1801179",
        "password": "",
        "connection": "auto",
        "transport": "auto",
        "ssh_port": 22,
        "winrm_https": False,
    },
    "ssh": {"username": "root", "password": "", "port": 22},
    "windows_ssh": {"username": "V1801179", "password": ""},
}


def load_local_config(path: Path) -> Dict:
    """Never overwrite existing settings or include their values in errors."""
    if not path.exists():
        try:
            with path.open("x", encoding="utf-8") as stream:
                json.dump(DEFAULT_SETTINGS, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
        except FileExistsError:
            # Another process created it between the existence check and open.
            logger.debug("File cấu hình đã được tiến trình khác tạo: %s", path)
        except OSError as exc:
            raise ValueError(f"Không tạo được file cấu hình: {path}") from exc
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Không đọc được JSON hợp lệ tại {path}; kiểm tra file cấu hình.") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"Cấu hình phải là JSON object: {path}")
    settings = deepcopy(DEFAULT_SETTINGS)
    for section, defaults in settings.items():
        supplied = raw.get(section, {})
        if not isinstance(supplied, dict):
            raise ValueError(f"Mục {section} trong {path} phải là JSON object.")
        for key, default in defaults.items():
            value = supplied.get(key, default)
            if type(value) is not type(default):
                raise ValueError(f"Sai kiểu dữ liệu cho {section}.{key} trong {path}.")
            defaults[key] = value
    _validate_settings(settings, path)
    return settings


def _validate_settings(settings: Dict, path: Path) -> None:
    try:
        for key in ("target_network", "client_network"):
            network = ipaddress.ip_network(settings["network"][key])
            if network.version != 4:
                raise ValueError()
        prefix = settings["network"]["ip_prefix"].split(".")
        if len(prefix) != 2 or any(not part.isdigit() or not 0 <= int(part) <= 255 for part in prefix):
            raise ValueError()
        if ipaddress.ip_address(settings["bridge"]["host"]).version != 4:
            raise ValueError()
        if any(not 1 <= settings[section][key] <= 65535
               for section, key in (("bridge", "ssh_port"), ("ssh", "port"))):
            raise ValueError()
        if settings["bridge"]["connection"] not in ("auto", "direct", "bridge"):
            raise ValueError()
        if settings["bridge"]["transport"] not in ("auto", "ssh", "winrm"):
            raise ValueError()
    except ValueError as exc:
        raise ValueError(f"IP, dải mạng, cổng hoặc chế độ kết nối không hợp lệ trong {path}.") from exc
