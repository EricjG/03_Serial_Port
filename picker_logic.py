"""Pure picker helpers (no Tkinter, no serial). Used by serial_port_app and tests."""

import re

DEFAULT_PARITY = "None"
STATUS_AVAILABLE = "Available"
STATUS_IN_USE = "In Use"
STATUS_OPEN = "Open"
STATUS_IDENTIFIED = "Identified"
STATUS_NONE = "None Available"

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
    """kind is empty | available | held | in_use."""
    if kind == "held" and port:
        return f"Close: {port}"
    if kind == "in_use" and port:
        return f"In-Use: {port}"
    if kind == "available" and port:
        return f"Open: {port}"
    return "Open:"


def port_status_text(has_ports, row_status=None):
    if not has_ports:
        return STATUS_NONE
    return row_status or "Unknown"


def port_event_message(port, event):
    if not port:
        return f"Port: {STATUS_NONE}"
    return f"Port: {port} is {event}"


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


def apply_header_button_click(in_use, scan_ports, scan_devices):
    """Any header button click clears all three auto-repeat flags."""
    return False, False, False


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
