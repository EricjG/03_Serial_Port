"""Pure picker helpers (no Tkinter, no serial). Used by serial_port_app and tests."""

import re
from itertools import product

DEFAULT_PARITY = "None"
STATUS_AVAILABLE = "Available"
STATUS_IN_USE = "In Use"
STATUS_OPEN = "Open"
STATUS_IDENTIFIED = "Identified"
STATUS_NONE = "None Available"

DATA_BITS_CHOICES = ("8", "7", "6", "5")
STOP_BITS_CHOICES = ("1", "2")
PARITY_CHOICES = ("None", "Odd", "Even", "Mark", "Space")
FLOW_XOFF_XON = "xOff/xOn"
FLOW_CHOICES = ("None", "RTS/CTS", FLOW_XOFF_XON)
FLOW_ALIASES = {
    "XON/XOFF": FLOW_XOFF_XON,
    "XOFF/XON": FLOW_XOFF_XON,
    "XOff/xOn": FLOW_XOFF_XON,
    "xon/xoff": FLOW_XOFF_XON,
    "xoff/xon": FLOW_XOFF_XON,
}

PORT_STATUS_CLOSED = "Closed"
PORT_STATUS_OPENED = "Opened"
PORT_STATUS_FAILED = "Failed"
PORT_STATUS_UNKNOWN = "Unknown"

DEVICE_STATUS_UNIDENTIFIED = "Unidentified"
DEVICE_STATUS_IDENTIFIED = "Identified"

BAUD_SHORT = [
    (300, "300"),
    (1200, "1.2K"),
    (2400, "2.4K"),
    (4800, "4.8K"),
    (9600, "9.6K"),
    (14400, "14.4K"),
    (19200, "19.2K"),
    (28800, "28.8K"),
    (38400, "38.4K"),
    (57600, "57.6K"),
    (115200, "115.2K"),
    (230400, "230.4K"),
    (460800, "460.8K"),
    (921600, "921.6K"),
]
BAUD_SHORT_BY_VALUE = {value: label for value, label in BAUD_SHORT}

STATUS_RANK = {
    STATUS_OPEN: 0,
    STATUS_IDENTIFIED: 1,
    STATUS_AVAILABLE: 2,
    STATUS_IN_USE: 3,
}


def format_vid_pid(vid, pid=None):
    """USB IDs as hex, e.g. 0x10C4:0xEA60. Missing IDs become Unknown."""
    vid_int = _as_int(vid)
    if vid_int is None:
        return "Unknown"
    pid_int = _as_int(pid)
    if pid_int is None:
        return f"0x{vid_int:04X}"
    return f"0x{vid_int:04X}:0x{pid_int:04X}"


def _as_int(value):
    if value is None or value == "":
        return None
    if isinstance(value, str) and value.strip().lower() == "unknown":
        return None
    try:
        if isinstance(value, str):
            return int(value, 0)
        return int(value)
    except (TypeError, ValueError):
        return None


def unique_device_labels(labels):
    """Keep the first name as-is; later copies get ' (2)', ' (3)', ..."""
    seen = {}
    unique = []
    for label in labels:
        text = label if label else "device"
        seen[text] = seen.get(text, 0) + 1
        count = seen[text]
        unique.append(text if count == 1 else f"{text} ({count})")
    return unique


def unique_labeled_items(items, label_of):
    labels = unique_device_labels([label_of(item) for item in items])
    return list(zip(labels, items))


def format_settings_text(data, stop, parity, flow):
    """Data - Stop - Parity - Flow, e.g. 8 - 1 - None - None."""
    return f"{data} - {stop} - {parity} - {flow}"


def normalize_flow_choice(flow):
    """Map old/alias spellings onto the slide-3 Flow list."""
    text = "" if flow is None else str(flow).strip()
    if not text:
        return "None"
    if text in FLOW_CHOICES:
        return text
    mapped = FLOW_ALIASES.get(text) or FLOW_ALIASES.get(text.upper())
    if mapped:
        return mapped
    return "None"


def longest_settings_text(
    data_choices=DATA_BITS_CHOICES,
    stop_choices=STOP_BITS_CHOICES,
    parity_choices=PARITY_CHOICES,
    flow_choices=FLOW_CHOICES,
):
    """Longest Data - Stop - Parity - Flow string from the legal lists."""
    longest = ""
    for data, stop, parity, flow in product(
        data_choices, stop_choices, parity_choices, flow_choices
    ):
        text = format_settings_text(data, stop, parity, flow)
        if len(text) > len(longest):
            longest = text
    return longest


def format_baud_label(baud):
    """Typical-speeds short label, e.g. 115200 -> 115.2K."""
    if baud is None:
        return None
    try:
        baud = int(baud)
    except (TypeError, ValueError):
        return str(baud)
    return BAUD_SHORT_BY_VALUE.get(baud, str(baud))


def picker_device_label(device, baud_text):
    """Dropdown text: Manufacturer  model  115.2K Baud."""
    if not device:
        return None
    manufacturer = (device.get("manufacturer") or "").strip()
    model = (device.get("model") or "").strip()
    baud = "" if baud_text is None else str(baud_text).strip()
    head = "  ".join(part for part in (manufacturer, model) if part)
    if baud:
        baud_part = f"{baud} Baud"
        return f"{head}  {baud_part}" if head else baud_part
    return head or None


def natural_port_sort_key(name):
    """COM2 before COM10; also works for ttyUSB2 vs ttyUSB10."""
    text = "" if name is None else str(name)
    parts = re.split(r"(\d+)", text)
    key = []
    for part in parts:
        if not part:
            continue
        if part.isdigit():
            key.append((1, int(part)))
        else:
            key.append((0, part.lower()))
    return tuple(key)


def open_button_text(port, kind):
    """kind is empty | available | held | in_use. Label does not include the port."""
    if kind == "held" and port:
        return "Close"
    if kind == "in_use" and port:
        return "In Use"
    return "Open"


def port_status_text(has_ports, row_status=None):
    if not has_ports:
        return STATUS_NONE
    return row_status or "Unknown"


def port_event_message(port, event):
    if not port:
        return f"Port: {STATUS_NONE}"
    return f"Port: {port} is {event}"


UNKNOWN_DEVICE_MESSAGE = DEVICE_STATUS_UNIDENTIFIED


def device_identity_key(device):
    """Manufacturer + model; None if both are empty."""
    if not device:
        return None
    manufacturer = (device.get("manufacturer") or "").strip()
    model = (device.get("model") or "").strip()
    if not manufacturer and not model:
        return None
    return (manufacturer, model)


def device_message_text(device):
    if not device:
        return "Device:"
    parts = [
        (device.get("manufacturer") or "").strip(),
        (device.get("model") or "").strip(),
        (device.get("short_description") or "").strip(),
    ]
    name = " ".join(part for part in parts if part)
    return f"Device: {name}" if name else "Device:"


def english_ordinal(n):
    """1 -> 1st, 2 -> 2nd, 3 -> 3rd, 11 -> 11th, 21 -> 21st, ..."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = 0
    abs_n = abs(n)
    if 10 <= (abs_n % 100) <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(abs_n % 10, "th")
    return f"{n}{suffix}"


def identify_failure_label(fail_count):
    """Identify-button Device Status: Failed, then 2nd Failure, 3rd Failure, ..."""
    try:
        count = int(fail_count)
    except (TypeError, ValueError):
        count = 0
    if count <= 0:
        return DEVICE_STATUS_UNIDENTIFIED
    if count == 1:
        return "Failed"
    return f"{english_ordinal(count)} Failure"


def device_status_text(
    identified_device, selected_device, fail_count=0, fail_key=None
):
    """Bottom Device Status. Unidentified until Identify or Scan Devices confirms."""
    identified_key = device_identity_key(identified_device)
    selected_key = device_identity_key(selected_device)
    if identified_key and identified_key == selected_key:
        return DEVICE_STATUS_IDENTIFIED
    if fail_count and fail_key and fail_key == selected_key:
        return identify_failure_label(fail_count)
    return DEVICE_STATUS_UNIDENTIFIED


def identified_device_message(
    identified_device, selected_device, fail_count=0, fail_key=None
):
    """Bottom Device Status value. Unidentified until this port matches the dropdown device."""
    return device_status_text(
        identified_device, selected_device, fail_count, fail_key
    )


def apply_device_pick(
    previous_key,
    selected_device,
    *,
    baud,
    settings,
    port_status,
    identified_device=None,
    fail_count=0,
    fail_key=None,
):
    """State after picking a Device. Baud, settings, and Port Status stay put."""
    new_key = device_identity_key(selected_device)
    if new_key != previous_key:
        fail_count = 0
        fail_key = new_key
    return {
        "baud": baud,
        "settings": settings,
        "port_status": port_status,
        "device_status": device_status_text(
            identified_device, selected_device, fail_count, fail_key
        ),
        "fail_count": fail_count,
        "fail_key": fail_key,
        "refresh_baud_list": True,
        "apply_baud": False,
        "apply_settings": False,
        "mark_port_unknown": False,
    }


def record_identify_success(device):
    """Identify/Scan confirmation: Identified, failure count cleared."""
    return {
        "fail_count": 0,
        "fail_key": device_identity_key(device),
        "device_status": DEVICE_STATUS_IDENTIFIED,
    }


def record_identify_failure(device, fail_count=0, fail_key=None):
    """Identify miss for the dropdown device. Scan Devices misses do not use this."""
    key = device_identity_key(device)
    try:
        count = int(fail_count)
    except (TypeError, ValueError):
        count = 0
    if key != fail_key:
        count = 1
    else:
        count = count + 1
    return {
        "fail_count": count,
        "fail_key": key,
        "device_status": identify_failure_label(count),
        "port_status_unchanged": True,
    }


def blank_device_identity():
    return {
        "manufacturer": "",
        "model": "",
        "type": "",
        "short_description": "",
        "long_description": "",
        "device_column": "",
    }


def exit_handoff_payload():
    """Window X / Exit: empty result for the calling app."""
    return {"result": None}


def select_handoff_payload(
    *,
    port=None,
    baud=None,
    settings=None,
    data_bits=None,
    stop_bits=None,
    parity=None,
    flow_control=None,
    port_status=None,
    device_status=None,
    device=None,
    port_hardware=None,
    device_attributes=None,
):
    """Select preview payload. Prefer null over dropping a key."""
    identity = blank_device_identity()
    if isinstance(device, dict):
        identity.update(device)
    return {
        "result": "select",
        "port": port,
        "baud": baud,
        "settings": settings,
        "data_bits": data_bits,
        "stop_bits": stop_bits,
        "parity": parity,
        "flow_control": flow_control,
        "port_status": port_status,
        "device_status": device_status,
        "device": identity,
        "port_hardware": port_hardware,
        "device_attributes": device_attributes,
    }


def apply_header_button_click(in_use, scan_ports, scan_devices):
    """Any header button click clears all three auto-repeat flags."""
    return False, False, False


CHECK_BUTTON_PAD_PX = 4  # extra pixels past the measured checkbox


def check_button_char_width(
    text_px, checkbox_px, gap_px, avg_char, extra_pad_px=CHECK_BUTTON_PAD_PX
):
    """Tk Button width= chars so label sits fully right of checkbox + gap."""
    avg = max(int(avg_char) or 1, 1)
    need = (
        max(0, int(checkbox_px))
        + max(0, int(gap_px))
        + max(0, int(text_px))
        + max(0, int(extra_pad_px))
    )
    return max(4, (need + avg - 1) // avg)


def dropdown_ports(rows, include_in_use, extra=()):
    """Available / Open / Identified always; In Use only if include_in_use or extra."""
    extra = {port for port in extra if port}
    ports = []
    seen = set()
    for status, port in rows:
        if status == STATUS_IN_USE and not include_in_use and port not in extra:
            continue
        if port in seen:
            continue
        seen.add(port)
        ports.append(port)
    for port in extra:
        if port not in seen:
            seen.add(port)
            ports.append(port)
    ports.sort(key=natural_port_sort_key)
    return ports


def visible_tree_rows(rows, include_in_use, extra=()):
    extra = {port for port in extra if port}
    visible = []
    for row in rows:
        status, port = row[0], row[1]
        if status == STATUS_IN_USE and not include_in_use and port not in extra:
            continue
        visible.append(row)
    visible.sort(key=lambda row: (STATUS_RANK.get(row[0], 9), natural_port_sort_key(row[1])))
    return visible


def picker_control_state(has_ports, selected_port=None, port_status=None, held=False):
    """Enabled flags and Open-button label for the connection controls."""
    if not has_ports or not selected_port:
        return {
            "port": False,
            "baud": False,
            "settings": False,
            "open": False,
            "open_label": open_button_text(None, "empty"),
            "device": False,
            "identify": False,
            "select": False,
            "status": STATUS_NONE,
        }
    if held:
        return {
            "port": False,
            "baud": False,
            "settings": False,
            "open": True,
            "open_label": open_button_text(selected_port, "held"),
            "device": True,
            "identify": True,
            "select": True,
            "status": port_status or STATUS_OPEN,
        }
    if port_status == STATUS_IN_USE:
        return {
            "port": True,
            "baud": True,
            "settings": True,
            "open": False,
            "open_label": open_button_text(selected_port, "in_use"),
            "device": True,
            "identify": False,
            "select": True,
            "status": STATUS_IN_USE,
        }
    return {
        "port": True,
        "baud": True,
        "settings": True,
        "open": True,
        "open_label": open_button_text(selected_port, "available"),
        "device": True,
        "identify": False,
        "select": True,
        "status": port_status or STATUS_AVAILABLE,
    }
