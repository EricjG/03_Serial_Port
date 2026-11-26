"""Load, migrate, and validate device data files (no Tkinter, no serial)."""

from __future__ import annotations

import json
import os
import re

STANDARD_BAUD_RATES = (
    300,
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
    if pid is None and isinstance(vid, str):
        text = vid.strip()
        for sep in (":", "/"):
            if sep in text:
                left, right = text.split(sep, 1)
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


def _standard_baud_rates_in_range(min_baud, max_baud):
    """STANDARD_BAUD_RATES inside min_baud..max_baud (inclusive). None bound = open."""
    rates = []
    for baud in STANDARD_BAUD_RATES:
        if min_baud is not None and baud < min_baud:
            continue
        if max_baud is not None and baud > max_baud:
            continue
        rates.append(baud)
    return rates


def _chip_baud_rates(uart_ic):
    """serial_ports.json chip Baud list, or STANDARD_BAUD_RATES in min_baud..max_baud."""
    params = (uart_ic or {}).get("serial_parameters") or {}
    rates = []
    seen = set()
    for item in params.get("baud_rates") or []:
        baud = _as_int(item)
        if baud is None or baud <= 0 or baud in seen:
            continue
        seen.add(baud)
        rates.append(baud)
    if rates:
        return rates
    return _standard_baud_rates_in_range(
        _as_int(params.get("min_baud")),
        _as_int(params.get("max_baud")),
    )


def baud_rates_for_picker(device=None, uart_ic=None):
    """Baud dropdown: serial_ports.json chip rates; else STANDARD_BAUD_RATES.

    If the selected port matches a serial_ports.json chip (VID/PID), use that
    chip's serial_parameters.baud_rates. If baud_rates is missing/empty, use
    STANDARD_BAUD_RATES filtered to the chip's min_baud..max_baud (inclusive).
    An unknown port (no VID/PID match) stays on the UI-slide standard list
    (no 600). A selected device does not shrink this list; it only preselects
    its first baud when that rate is already in the list.
    """
    _ = device
    if uart_ic:
        rates = _chip_baud_rates(uart_ic)
        if rates:
            return rates
    return list(STANDARD_BAUD_RATES)


def default_baud(device):
    rates = baud_rates_for_device(device)
    return rates[0] if rates else None


def _usable_controllers(device):
    """(vid_int, pid_int_or_None) for each controllers entry that has a vid."""
    usable = []
    for controller in (device or {}).get("controllers") or []:
        if not isinstance(controller, dict):
            continue
        cvid = parse_usb_id(controller.get("vid"))
        if cvid is None:
            continue
        cpid = parse_usb_id(controller.get("pid"))
        usable.append((cvid, cpid))
    return usable


def device_matches_ids(device, vid, pid=None):
    """True if this device should be tried on a port with this VID/PID.

    A device with no usable controllers (missing, empty, null, or every
    entry lacks vid) matches every port. Otherwise any listed controller
    may match: VID required, PID optional on the controller.
    """
    controllers = _usable_controllers(device)
    if not controllers:
        return True
    port_vid, port_pid = parse_vid_pid(vid, pid)
    if port_vid is None:
        return False
    for cvid, cpid in controllers:
        if cvid != port_vid:
            continue
        if cpid is None or port_pid is None or cpid == port_pid:
            return True
    return False


def scan_controller_ids(device, vid=None, pid=None):
    """Controller (vid, pid) printed on a scan Device line, or None for (any).

    Prefers the controller that matches this port; otherwise the first listed.
    """
    controllers = _usable_controllers(device)
    if not controllers:
        return None
    port_vid, port_pid = parse_vid_pid(vid, pid)
    if port_vid is not None:
        for cvid, cpid in controllers:
            if cvid != port_vid:
                continue
            if cpid is None or port_pid is None or cpid == port_pid:
                return (cvid, cpid)
    return controllers[0]


def _parse_hex_id_token(text):
    """USB ID as int from hex with or without 0x (editor field tokens)."""
    if text is None:
        return None
    token = str(text).strip()
    if not token or token.lower() == "unknown":
        return None
    try:
        return int(token, 16)
    except ValueError:
        return None


def parse_controllers_text(text):
    """Parse '0403:6001, 10C4' into controllers [{'vid': '0x0403', 'pid': '0x6001'}, ...].

    Comma-separated entries. PID is optional. Hex with or without 0x.
    Blank or whitespace is []. Invalid tokens are skipped.
    """
    if text is None:
        return []
    entries = []
    for part in str(text).split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            left, right = part.split(":", 1)
            vid = _parse_hex_id_token(left)
            pid = _parse_hex_id_token(right)
        else:
            vid = _parse_hex_id_token(part)
            pid = None
        if vid is None:
            continue
        entry = {"vid": format_usb_id(vid)}
        if pid is not None:
            formatted_pid = format_usb_id(pid)
            if formatted_pid is not None:
                entry["pid"] = formatted_pid
        entries.append(entry)
    return entries


def format_controllers_text(controllers):
    """controllers list -> '0x0403:0x6001, 0x10C4'. Blank if none."""
    parts = []
    for item in controllers or []:
        if not isinstance(item, dict):
            continue
        vid = format_usb_id(item.get("vid"))
        if vid is None:
            continue
        pid = format_usb_id(item.get("pid"))
        parts.append(f"{vid}:{pid}" if pid else vid)
    return ", ".join(parts)


def controllers_field_text(device):
    """Editor Port VID:PID value from controllers (or old vendor_ids)."""
    return format_controllers_text(_migrate_controllers(device or {}))


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


def _as_bool(value, default=False):
    """JSON true/false, plus a few string/number spellings. Missing → default."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in ("true", "1", "yes"):
        return True
    if text in ("false", "0", "no", ""):
        return False
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
    """Keep an explicit controllers list, including []. Old files use vendor_ids."""
    controllers = device.get("controllers")
    if isinstance(controllers, list):
        migrated = []
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
        return migrated
    migrated = []
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
            "append_response": _as_bool(response.get("append_response"), False),
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


def migrate_uart_ic(entry):
    """Normalize one serial_ports.json chip entry. Returns (entry, error) — error means skip it."""
    if not isinstance(entry, dict):
        return None, "uart ic entry is not an object"
    vid = format_usb_id(entry.get("vid"))
    if vid is None:
        return None, "uart ic is missing vid"
    manufacturer = entry.get("manufacturer") or ""
    model = entry.get("model") or ""
    if not manufacturer or not model:
        return None, "uart ic is missing manufacturer or model"
    migrated = dict(entry)
    migrated["manufacturer"] = manufacturer
    migrated["model"] = model
    migrated["vid"] = vid
    pid = format_usb_id(entry.get("pid")) if entry.get("pid") not in (None, "") else None
    if pid is not None:
        migrated["pid"] = pid
    elif "pid" in migrated:
        del migrated["pid"]
    return migrated, None


def _serial_ports_rows(data):
    """Chip list from serial_ports.json. Accepts the old uart_ics root key."""
    if not isinstance(data, dict):
        return None
    if isinstance(data.get("serial_ports"), list):
        return data["serial_ports"]
    if isinstance(data.get("uart_ics"), list):
        return data["uart_ics"]
    return None


def migrate_serial_ports_payload(data):
    """Return (payload, error). payload always has a serial_ports list."""
    rows = _serial_ports_rows(data)
    if rows is None:
        return {"serial_ports": []}, "serial_ports.json has no serial_ports list"
    ics = []
    for item in rows:
        migrated, error = migrate_uart_ic(item)
        if migrated is not None:
            ics.append(migrated)
    return {"serial_ports": ics}, None


def load_serial_ports_file(path):
    """Read serial_ports.json. Never raises. Returns (payload, error_or_None)."""
    empty = {"serial_ports": []}
    name = os.path.basename(path) if path else "serial_ports.json"
    if not path or not os.path.exists(path):
        return empty, f"{name} is missing — no known UART ICs."
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError:
        return empty, f"{name} is not valid JSON — no known UART ICs."
    except OSError:
        return empty, f"{name} could not be read — no known UART ICs."
    payload, error = migrate_serial_ports_payload(data)
    if error:
        return payload, f"{name} is invalid — no known UART ICs."
    return payload, None


def migrate_device_info(entry):
    """Normalize one devices_info.json entry. Returns (entry, error)."""
    if not isinstance(entry, dict):
        return None, "device attributes entry is not an object"
    migrated = dict(entry)
    migrated["manufacturer"] = entry.get("manufacturer") or ""
    migrated["model"] = entry.get("model") or ""
    migrated["type"] = entry.get("type") or ""
    migrated["short_description"] = entry.get("short_description") or ""
    migrated["long_description"] = entry.get("long_description") or ""
    return migrated, None


def migrate_devices_info_payload(data):
    """Return (payload, error). payload always has a devices list."""
    if not isinstance(data, dict) or not isinstance(data.get("devices"), list):
        return {"devices": []}, "devices_info.json has no device list"
    devices = []
    for item in data["devices"]:
        migrated, error = migrate_device_info(item)
        if migrated is not None:
            devices.append(migrated)
    return {"devices": devices}, None


def load_devices_info_file(path):
    """Read devices_info.json. Never raises. Returns (payload, error_or_None)."""
    empty = {"devices": []}
    name = os.path.basename(path) if path else "devices_info.json"
    if not path or not os.path.exists(path):
        return empty, f"{name} is missing — no known device attributes."
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError:
        return empty, f"{name} is not valid JSON — no known device attributes."
    except OSError:
        return empty, f"{name} could not be read — no known device attributes."
    payload, error = migrate_devices_info_payload(data)
    if error:
        return payload, f"{name} is invalid — no known device attributes."
    return payload, None


def uart_ic_list(payload):
    if isinstance(payload, dict):
        return payload.get("serial_ports") or payload.get("uart_ics") or []
    if isinstance(payload, list):
        return payload
    return []


def devices_info_list(payload):
    if isinstance(payload, dict):
        return payload.get("devices") or []
    if isinstance(payload, list):
        return payload
    return []


def match_uart_ic(ics, vid, pid=None):
    """Matched serial_ports.json chip entry for a port VID/PID, or None.

    An entry with no pid matches any product ID from that vendor. Prefer an
    exact VID+PID hit over a vid-only entry.
    """
    port_vid, port_pid = parse_vid_pid(vid, pid)
    if port_vid is None:
        return None
    exact = None
    vid_only = None
    for ic in ics or []:
        if not isinstance(ic, dict):
            continue
        cvid = parse_usb_id(ic.get("vid"))
        if cvid is None or cvid != port_vid:
            continue
        cpid = parse_usb_id(ic.get("pid")) if ic.get("pid") not in (None, "") else None
        if cpid is not None:
            if port_pid is not None and cpid == port_pid:
                exact = ic
                break
            continue
        if vid_only is None:
            vid_only = ic
    return exact or vid_only


def match_device_info(devices, manufacturer, model):
    """devices_info.json entry linked by manufacturer + model, or None."""
    manufacturer = (manufacturer or "").strip()
    model = (model or "").strip()
    if not manufacturer and not model:
        return None
    for item in devices or []:
        if not isinstance(item, dict):
            continue
        if (item.get("manufacturer") or "").strip() != manufacturer:
            continue
        if (item.get("model") or "").strip() != model:
            continue
        return item
    return None


def prefer_info_field(info, device, key, default=""):
    """Prefer devices_info.json, then the identify template, then default."""
    for source in (info, device):
        if not source:
            continue
        value = source.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return default


def uart_ic_label(ic):
    """Port-list chip name: Manufacturer model."""
    if not ic:
        return None
    name = " ".join(
        part
        for part in (ic.get("manufacturer"), ic.get("model"))
        if part
    ).strip()
    return name or None


def response_append_enabled(device):
    """True when response.append_response is set. Missing / invalid → False."""
    if not isinstance(device, dict):
        return False
    response = device.get("response")
    if not isinstance(response, dict):
        return False
    return _as_bool(response.get("append_response"), False)


_SAMPLE_RESPONSE_GROUPS = {
    "revision": "1.01",
    "firmware": "1.01",
    "date": "01/01/26",
    "serial": "12345",
}


def sample_response_groups(device):
    """Named regex groups filled with sample values for Device Status sizing."""
    pattern = ((device or {}).get("response") or {}).get("regex") or ""
    if not pattern:
        return None
    try:
        compiled = re.compile(pattern)
    except re.error:
        return None
    if not compiled.groupindex:
        return None
    return {
        name: _SAMPLE_RESPONSE_GROUPS.get(name, "1.01")
        for name in compiled.groupindex
    }


def sample_device_column(device):
    """device_column filled from sample regex groups (field-width probe)."""
    return format_device_column(device, sample_response_groups(device))


def identified_connected_label(info, device, device_column=None):
    """Identified-row Connected Device / Device Status text.

    One helper so the table column and the bottom Device Status field cannot
    drift. Always manufacturer + model + short_description from
    devices_info.json (falling back field-by-field to devices.json). When
    response.append_response is true, append the formatted device_column
    after that name, separated by ' - '. When false, never show the
    response text.
    """
    manufacturer = (prefer_info_field(info, device, "manufacturer") or "").strip()
    model = (prefer_info_field(info, device, "model") or "").strip()
    short = (prefer_info_field(info, device, "short_description") or "").strip()
    label = " ".join(part for part in (manufacturer, model, short) if part)
    column = (device_column or "").strip()
    if response_append_enabled(device) and column:
        if label:
            return f"{label} - {column}"
        return column
    return label or None


def catalog_device_list(payload):
    if isinstance(payload, dict):
        return payload.get("devices") or []
    if isinstance(payload, list):
        return payload
    return []


def catalog_identified_labels(devices_payload, info_payload):
    """Identified labels the current devices.json + devices_info.json can show."""
    devices = catalog_device_list(devices_payload)
    infos = devices_info_list(info_payload)
    labels = []
    seen = set()
    for device in devices:
        if not isinstance(device, dict):
            continue
        info = match_device_info(
            infos, device.get("manufacturer"), device.get("model")
        )
        column = (
            sample_device_column(device) if response_append_enabled(device) else ""
        )
        label = identified_connected_label(info, device, column)
        if not label or label in seen:
            continue
        seen.add(label)
        labels.append(label)
    return tuple(labels)


def device_identity_fields(info, device, device_column=""):
    """Select-payload device block: manufacturer, model, short_description.

    Prefer devices_info.json, then devices.json. Returns None when no device
    was identified. device_column is ignored (kept so older callers still run).
    """
    if not device:
        return None
    return {
        "manufacturer": prefer_info_field(info, device, "manufacturer", "") or "",
        "model": prefer_info_field(info, device, "model", "") or "",
        "short_description": prefer_info_field(info, device, "short_description", "") or "",
    }
