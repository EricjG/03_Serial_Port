"""Load, migrate, and validate devices.json (no Tkinter, no serial)."""

from __future__ import annotations

import json
import os
import re

STANDARD_BAUD_RATES = (
    300,
    600,
    1200,
    2400,
    4800,
    9600,
    14400,
    19200,
    28800,
    38400,
    57600,
    115200,
    230400,
    460800,
    921600,
)

PARITY_TO_CODE = {
    "N": "N",
    "NONE": "N",
    "E": "E",
    "EVEN": "E",
    "O": "O",
    "ODD": "O",
    "M": "M",
    "MARK": "M",
    "S": "S",
    "SPACE": "S",
}

_DEVICE_FORMAT_KEYS = (
    "manufacturer",
    "model",
    "type",
    "short_description",
    "long_description",
)


class _BlankMissing(dict):
    def __missing__(self, key):
        return ""


def parse_usb_id(value):
    """USB vendor/product ID as int, or None. Accepts hex, decimal, and '0x10C4:0xEA60'."""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() == "unknown":
            return None
        if ":" in text:
            text = text.split(":", 1)[0].strip()
        try:
            return int(text, 0)
        except ValueError:
            if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
                return int(text, 10)
            return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_vid_pid(vid, pid=None):
    """Return (vid_int_or_None, pid_int_or_None). Splits '0x10C4:0xEA60' when pid is omitted."""
    if pid is None and isinstance(vid, str) and ":" in vid:
        left, right = vid.split(":", 1)
        return parse_usb_id(left), parse_usb_id(right)
    return parse_usb_id(vid), parse_usb_id(pid)


def format_usb_id(value):
    """Canonical file form, e.g. '0x10C4'. None if the value is not an ID."""
    number = parse_usb_id(value)
    if number is None:
        return None
    return f"0x{number:04X}"


def connected_device_label(device):
    """Dropdown / fallback name: Manufacturer model [- long_description]."""
    if not device:
        return None
    name = " ".join(
        part
        for part in (device.get("manufacturer"), device.get("model"))
        if part
    ).strip()
    long_desc = (device.get("long_description") or "").strip()
    if name and long_desc:
        return f"{name} - {long_desc}"
    return name or long_desc or None


def format_device_column(device, match_groups=None):
    """Fill response.device_column from device fields and regex named groups."""
    response = device.get("response") or {}
    template = (response.get("device_column") or "").strip()
    values = {key: device.get(key) or "" for key in _DEVICE_FORMAT_KEYS}
    if match_groups:
        for key, value in match_groups.items():
            if value is not None:
                values[key] = value
    if template:
        try:
            text = re.sub(r"\s+", " ", template.format_map(_BlankMissing(values))).strip()
            if text:
                return text
        except (ValueError, IndexError):
            pass
    return connected_device_label(device)


def baud_rates_for_device(device):
    """Device baud list, or the standard list when it is missing/empty."""
    if not device:
        return list(STANDARD_BAUD_RATES)
    params = device.get("serial_parameters") or {}
    rates = params.get("baud_rates") or []
    return list(rates) if rates else list(STANDARD_BAUD_RATES)


def default_baud(device):
    rates = baud_rates_for_device(device)
    return rates[0] if rates else None


def device_matches_ids(device, vid, pid=None):
    """True if any controller's VID matches, and PID matches when the controller lists one."""
    port_vid, port_pid = parse_vid_pid(vid, pid)
    if port_vid is None:
        return False
    for controller in device.get("controllers") or []:
        cvid = parse_usb_id((controller or {}).get("vid"))
        if cvid is None or cvid != port_vid:
            continue
        cpid = parse_usb_id((controller or {}).get("pid"))
        if cpid is None or port_pid is None or cpid == port_pid:
            return True
    return False


def command_steps(device):
    """(message, pause_seconds) for initialize then identify. Empty messages are skipped."""
    commands = device.get("commands") or {}
    steps = []
    for key in ("initialize", "identify"):
        command = commands.get(key) or {}
        message = command.get("message")
        if message is None or message == "":
            continue
        pause_ms = command.get("pause_ms", 0)
        try:
            pause_s = max(0.0, float(pause_ms) / 1000.0)
        except (TypeError, ValueError):
            pause_s = 0.0
        steps.append((str(message), pause_s))
    return steps


def _parity_code(value):
    if value is None or value == "":
        return "N"
    return PARITY_TO_CODE.get(str(value).strip().upper(), "N")


def _as_int(value, default=None):
    if value is None or value == "":
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _as_float(value, default=None):
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _pause_ms_from_command(command):
    if not isinstance(command, dict):
        return 0
    if "pause_ms" in command and command["pause_ms"] is not None:
        ms = _as_int(command["pause_ms"], 0)
        return max(0, ms or 0)
    if "pause" in command and command["pause"] is not None:
        # Old files stored pause in seconds (time.sleep(pause)).
        seconds = _as_float(command["pause"], 0.0) or 0.0
        return max(0, int(round(seconds * 1000)))
    return 0


def _migrate_controllers(device):
    controllers = device.get("controllers")
    migrated = []
    if isinstance(controllers, list):
        for item in controllers:
            if not isinstance(item, dict):
                continue
            vid = format_usb_id(item.get("vid"))
            if vid is None:
                continue
            entry = {"vid": vid}
            pid = format_usb_id(item.get("pid"))
            if pid is not None:
                entry["pid"] = pid
            migrated.append(entry)
        if migrated:
            return migrated
    vendor_ids = device.get("vendor_ids") or []
    product_ids = device.get("product_ids") or []
    pids = [format_usb_id(pid) for pid in product_ids]
    pids = [pid for pid in pids if pid]
    for vendor in vendor_ids:
        vid = format_usb_id(vendor)
        if vid is None:
            continue
        if pids:
            migrated.extend({"vid": vid, "pid": pid} for pid in pids)
        else:
            migrated.append({"vid": vid})
    return migrated


def _migrate_baud_rates(params):
    if not isinstance(params, dict):
        return []
    raw = params.get("baud_rates")
    if raw is None:
        raw = params.get("baudrates")
    if raw is None and params.get("baudrate") is not None:
        raw = [params.get("baudrate")]
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple)):
        raw = [raw]
    rates = []
    seen = set()
    for item in raw:
        baud = _as_int(item)
        if baud is None or baud <= 0 or baud in seen:
            continue
        seen.add(baud)
        rates.append(baud)
    return rates


def _migrate_serial_parameters(params):
    params = params if isinstance(params, dict) else {}
    stop = params.get("stop_bits", params.get("stopbits", 1))
    stop_f = _as_float(stop, 1.0)
    if stop_f is None:
        stop_f = 1.0
    if float(stop_f) == int(stop_f):
        stop_out = int(stop_f)
    else:
        stop_out = stop_f
    flow = params.get("flow_control", params.get("flow", "None")) or "None"
    return {
        "baud_rates": _migrate_baud_rates(params),
        "parity": _parity_code(params.get("parity", "N")),
        "stopbits": stop_out,
        "bytesize": _as_int(params.get("data_bits", params.get("bytesize", 8)), 8),
        "flow_control": str(flow),
    }


def _migrate_command(command):
    command = command if isinstance(command, dict) else {}
    message = command.get("message", "")
    if message is None:
        message = ""
    return {"message": message, "pause_ms": _pause_ms_from_command(command)}


def migrate_device(device):
    """Normalize one device dict. Returns (device, error) — error means skip it."""
    if not isinstance(device, dict):
        return None, "device entry is not an object"
    commands = device.get("commands") if isinstance(device.get("commands"), dict) else {}
    response = device.get("response") if isinstance(device.get("response"), dict) else {}
    device_type = device.get("type", "")
    if device_type is None:
        device_type = ""
    else:
        device_type = str(device_type)
    regex = response.get("regex") or ""
    if regex:
        try:
            re.compile(regex)
        except re.error as exc:
            return None, f"invalid response.regex: {exc}"
    migrated = {
        "manufacturer": device.get("manufacturer") or "",
        "model": device.get("model") or "",
        "type": device_type,
        "short_description": device.get("short_description") or "",
        "long_description": device.get("long_description") or "",
        "controllers": _migrate_controllers(device),
        "serial_parameters": _migrate_serial_parameters(device.get("serial_parameters")),
        "commands": {
            "initialize": _migrate_command(commands.get("initialize")),
            "identify": _migrate_command(commands.get("identify")),
        },
        "response": {
            "regex": regex,
            "device_column": response.get("device_column") or "",
        },
    }
    return migrated, None


def migrate_payload(data):
    """Return (payload, error). payload always has a devices list."""
    if not isinstance(data, dict) or not isinstance(data.get("devices"), list):
        return {"devices": []}, "devices.json has no device list"
    devices = []
    for item in data["devices"]:
        migrated, error = migrate_device(item)
        if migrated is not None:
            devices.append(migrated)
    return {"devices": devices}, None


def load_device_file(path):
    """Read path, migrate, validate. Never raises. Returns (payload, error_or_None)."""
    empty = {"devices": []}
    name = os.path.basename(path) if path else "devices.json"
    if not path or not os.path.exists(path):
        return empty, f"{name} is missing — no known devices."
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError:
        return empty, f"{name} is not valid JSON — no known devices."
    except OSError:
        return empty, f"{name} could not be read — no known devices."
    payload, error = migrate_payload(data)
    if error:
        return payload, f"{name} is invalid — no known devices."
    return payload, None
