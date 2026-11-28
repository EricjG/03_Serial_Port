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
PARITY_LABELS = {
    "N": "None",
    "NONE": "None",
    "O": "Odd",
    "ODD": "Odd",
    "E": "Even",
    "EVEN": "Even",
    "M": "Mark",
    "MARK": "Mark",
    "S": "Space",
    "SPACE": "Space",
}
STANDARD_SETTINGS_CHOICES = {
    "data_bits": DATA_BITS_CHOICES,
    "stop_bits": STOP_BITS_CHOICES,
    "parity": PARITY_CHOICES,
    "flow_control": FLOW_CHOICES,
}
# Settings dialog 2×2 reading order: Data, Parity, Stop, Flow.
SETTINGS_DIALOG_FIELDS = (
    ("Data Bits", "data_bits"),
    ("Parity", "parity"),
    ("Stop Bits", "stop_bits"),
    ("Flow", "flow_control"),
)
FLOW_SUMMARY_NONE = "No Flow"
FLOW_SUMMARY_XON_XOFF = "XON/XOFF"
_FLOW_SUMMARY_LABELS = {
    "None": FLOW_SUMMARY_NONE,
    "NO FLOW": FLOW_SUMMARY_NONE,
    FLOW_SUMMARY_NONE: FLOW_SUMMARY_NONE,
    "RTS/CTS": "RTS/CTS",
    FLOW_XOFF_XON: FLOW_SUMMARY_XON_XOFF,
    "XON/XOFF": FLOW_SUMMARY_XON_XOFF,
    "XOFF/XON": FLOW_SUMMARY_XON_XOFF,
}
# Single-letter flow for Settings / Port Status: N none, R RTS/CTS, X XON/XOFF.
FLOW_LETTER_NONE = "N"
FLOW_LETTER_RTS_CTS = "R"
FLOW_LETTER_XON_XOFF = "X"
_FLOW_LETTER = {
    "None": FLOW_LETTER_NONE,
    "NONE": FLOW_LETTER_NONE,
    "N": FLOW_LETTER_NONE,
    "NO FLOW": FLOW_LETTER_NONE,
    FLOW_SUMMARY_NONE: FLOW_LETTER_NONE,
    "RTS/CTS": FLOW_LETTER_RTS_CTS,
    "R": FLOW_LETTER_RTS_CTS,
    FLOW_XOFF_XON: FLOW_LETTER_XON_XOFF,
    "XON/XOFF": FLOW_LETTER_XON_XOFF,
    "XOFF/XON": FLOW_LETTER_XON_XOFF,
    "X": FLOW_LETTER_XON_XOFF,
}

PORT_STATUS_CLOSED = "Closed"
PORT_STATUS_OPENED = "Opened"
PORT_STATUS_FAILED = "Failed"
PORT_STATUS_UNKNOWN = "Unknown"

DEVICE_STATUS_UNIDENTIFIED = "Nothing Identified"
DEVICE_STATUS_IDENTIFIED = "Identified"

# Typical baud values (same set as device_data.STANDARD_BAUD_RATES).
# Display labels are comma-grouped integers from format_baud_label, not "115.2K".
BAUD_SHORT_VALUES = (
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
SETTINGS_JOIN = " - "
PORT_STATUS_GROUP_SEP = "   "  # three spaces between port, baud, settings
BAUD_DISPLAY_SAMPLE = "1,000,000"

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


def format_flow_summary(flow):
    """Long flow names: No Flow, RTS/CTS, XON/XOFF."""
    text = "" if flow is None else str(flow).strip()
    if not text:
        return FLOW_SUMMARY_NONE
    mapped = _FLOW_SUMMARY_LABELS.get(text) or _FLOW_SUMMARY_LABELS.get(text.upper())
    if mapped:
        return mapped
    alias = FLOW_ALIASES.get(text) or FLOW_ALIASES.get(text.upper())
    if alias:
        return _FLOW_SUMMARY_LABELS.get(alias, FLOW_SUMMARY_XON_XOFF)
    return FLOW_SUMMARY_NONE


def format_flow_letter(flow):
    """Single-letter flow: N none, R RTS/CTS, X XON/XOFF."""
    text = "" if flow is None else str(flow).strip()
    if not text:
        return FLOW_LETTER_NONE
    mapped = _FLOW_LETTER.get(text) or _FLOW_LETTER.get(text.upper())
    if mapped:
        return mapped
    alias = FLOW_ALIASES.get(text) or FLOW_ALIASES.get(text.upper())
    if alias:
        return _FLOW_LETTER.get(alias, FLOW_LETTER_XON_XOFF)
    return FLOW_LETTER_NONE


def join_setting_parts(*parts):
    """Join port-setting tokens with ' - ', skipping blanks."""
    texts = []
    for part in parts:
        if part is None:
            continue
        text = str(part).strip()
        if text:
            texts.append(text)
    return SETTINGS_JOIN.join(texts)


def serial_frame_parts(data_bits=8, parity="N", stop_bits=1):
    """Data bits, parity letter, stop bits as separate tokens."""
    try:
        size_text = str(int(float(data_bits)))
    except (TypeError, ValueError):
        size_text = "8"
    parity_text = "" if parity is None else str(parity).strip()
    letter = _PARITY_FRAME_LETTER.get(parity_text) or _PARITY_FRAME_LETTER.get(
        parity_text.upper()
    )
    if letter is None:
        label = _parity_choice_label(parity_text)
        letter = _PARITY_FRAME_LETTER.get(label or "", "N")
    stop_text = _stop_bits_choice_label(stop_bits) or "1"
    return size_text, letter, stop_text


def format_settings_text(data, stop, parity, flow):
    """Settings line: `8 - N - 1 - N` (data - parity - stop - flow)."""
    size_text, letter, stop_text = serial_frame_parts(data, parity, stop)
    return join_setting_parts(size_text, letter, stop_text, format_flow_letter(flow))


MODE_MANUAL = "manual"
MODE_AUTOMATIC = "automatic"
IDENTIFY_REPLY_PREVIEW = 30
IDENTIFY_ERROR_PREVIEW = 40
IDENTIFY_MATCHED = "Matched"
IDENTIFY_NO_RESPONSE = "No response"
IDENTIFY_SKIPPED_VID_PID = "Skipped, port ID doesn't match"
SCAN_SKIPPED_OPEN = "Skipped, port is Open"
SCAN_NO_USB_ID = "no USB ID"
SCAN_ANY_ID = "any"
DEVICE_SCANNING = "Device Scanning..."
DEVICE_SCAN_DONE = "Device scan Done"

_PARITY_FRAME_LETTER = {
    "None": "N",
    "Odd": "O",
    "Even": "E",
    "Mark": "M",
    "Space": "S",
    "N": "N",
    "O": "O",
    "E": "E",
    "M": "M",
    "S": "S",
}


def format_serial_frame(data_bits=8, parity="N", stop_bits=1):
    """Classic 8N1 shorthand (scan logs). Settings UI uses format_settings_text."""
    size_text, letter, stop_text = serial_frame_parts(data_bits, parity, stop_bits)
    return f"{size_text}{letter}{stop_text}"


def identify_device_name(device):
    """Manufacturer model, e.g. MUX Wiring MB607."""
    if not device:
        return "device"
    name = " ".join(
        part
        for part in (
            (device.get("manufacturer") or "").strip(),
            (device.get("model") or "").strip(),
        )
        if part
    )
    return name or "device"


def format_scan_usb_id(vid, pid=None, *, empty=SCAN_NO_USB_ID):
    """Scan-log USB IDs as 0x10C4/0xEA60. empty is 'no USB ID' or 'any'."""
    if pid is None and isinstance(vid, str):
        text = vid.strip()
        for sep in ("/", ":"):
            if sep in text:
                left, right = text.split(sep, 1)
                vid, pid = left, right
                break
    vid_int = _as_int(vid)
    if vid_int is None:
        return empty
    pid_int = _as_int(pid)
    if pid_int is None:
        return f"0x{vid_int:04X}"
    return f"0x{vid_int:04X}/0x{pid_int:04X}"


def format_port_scan_header(port, vid=None, pid=None):
    """One Port: header, e.g. Port: COM8 (0x10C4/0xEA60)."""
    port_text = port or "?"
    return f"Port: {port_text} ({format_scan_usb_id(vid, pid)})"


def format_identify_reply_preview(reply, limit=IDENTIFY_REPLY_PREVIEW):
    """First ~30 chars of a probe reply, Python-repr escaped."""
    text = "" if reply is None else str(reply)
    try:
        width = int(limit)
    except (TypeError, ValueError):
        width = IDENTIFY_REPLY_PREVIEW
    if width < 0:
        width = IDENTIFY_REPLY_PREVIEW
    return repr(text[:width])


def format_identify_error(exc, limit=IDENTIFY_ERROR_PREVIEW):
    """Short one-line Error: text from an exception or string."""
    if exc is None:
        text = "error"
    else:
        raw = str(exc).strip()
        text = raw.splitlines()[0].strip() if raw else "error"
    try:
        width = int(limit)
    except (TypeError, ValueError):
        width = IDENTIFY_ERROR_PREVIEW
    if width < 1:
        width = IDENTIFY_ERROR_PREVIEW
    if len(text) > width:
        text = text[:width].rstrip()
    return text


def identify_attempt_result(
    *, matched=False, skipped_vid_pid=False, reply=None, error=None
):
    """Result after one Identify/Scan try: Matched, skip, empty, mismatch, or Error."""
    if skipped_vid_pid:
        return IDENTIFY_SKIPPED_VID_PID
    if matched:
        return IDENTIFY_MATCHED
    if error is not None:
        return f"Error: {format_identify_error(error)}"
    if reply is None or reply == "":
        return IDENTIFY_NO_RESPONSE
    return f"No match: {format_identify_reply_preview(reply)}"


def identify_attempt_message(
    device,
    baud,
    frame,
    controller_id=None,
    *,
    matched=False,
    skipped_vid_pid=False,
    reply=None,
    error=None,
):
    """One Device: line, e.g. Device: MUX Wiring MB607 115200 8N1 (0x10C4/0xEA60): Matched."""
    baud_text = "?" if baud is None or baud == "" else str(baud)
    frame_text = frame or "8N1"
    id_text = controller_id or SCAN_ANY_ID
    result = identify_attempt_result(
        matched=matched,
        skipped_vid_pid=skipped_vid_pid,
        reply=reply,
        error=error,
    )
    return (
        f"Device: {identify_device_name(device)} {baud_text} {frame_text} "
        f"({id_text}): {result}"
    )


def ui_settings_from_device(device):
    """Port Settings values from a device's serial_parameters."""
    params = (device or {}).get("serial_parameters") or {}
    data = (
        _data_bits_choice_label(params.get("data_bits", params.get("bytesize"))) or "8"
    )
    stop = (
        _stop_bits_choice_label(params.get("stop_bits", params.get("stopbits"))) or "1"
    )
    parity = _parity_choice_label(params.get("parity")) or DEFAULT_PARITY
    flow = normalize_flow_choice(params.get("flow_control", params.get("flow")))
    return {
        "data_bits": data,
        "stop_bits": stop,
        "parity": parity,
        "flow_control": flow,
    }


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


def _data_bits_choice_label(value):
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return str(number)


def _stop_bits_choice_label(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number == int(number):
        return str(int(number))
    return str(number)


def _parity_choice_label(value):
    text = "" if value is None else str(value).strip()
    if not text:
        return None
    if text in PARITY_CHOICES:
        return text
    return PARITY_LABELS.get(text.upper())


def _flow_choice_label(value):
    text = "" if value is None else str(value).strip()
    if not text:
        return None
    if text in FLOW_CHOICES:
        return text
    return FLOW_ALIASES.get(text) or FLOW_ALIASES.get(text.upper())


def _choice_labels(value, label_of):
    if value is None or value == "":
        return None
    raw = list(value) if isinstance(value, (list, tuple)) else [value]
    labels = []
    seen = set()
    for item in raw:
        label = label_of(item)
        if not label or label in seen:
            continue
        seen.add(label)
        labels.append(label)
    return labels or None


def settings_choices_for_picker(device=None, uart_ic=None):
    """Settings dialog Data/Stop/Parity/Flow lists.

    Unknown port (no serial_ports.json VID:PID match) and no identified device
    use the UI-slide lists. A device's own serial_parameters win when a
    device is identified. Chip catalog lists do not replace the slide lists
    when no device is identified.
    """
    _ = uart_ic
    if device:
        params = device.get("serial_parameters") or {}
        data = _choice_labels(
            params.get("data_bits", params.get("bytesize")),
            _data_bits_choice_label,
        )
        stop = _choice_labels(
            params.get("stop_bits", params.get("stopbits")),
            _stop_bits_choice_label,
        )
        parity = _choice_labels(params.get("parity"), _parity_choice_label)
        flow = _choice_labels(
            params.get("flow_control", params.get("flow")),
            _flow_choice_label,
        )
        if data or stop or parity or flow:
            return {
                "data_bits": tuple(data) if data else DATA_BITS_CHOICES,
                "stop_bits": tuple(stop) if stop else STOP_BITS_CHOICES,
                "parity": tuple(parity) if parity else PARITY_CHOICES,
                "flow_control": tuple(flow) if flow else FLOW_CHOICES,
            }
    return dict(STANDARD_SETTINGS_CHOICES)


def longest_settings_text(
    data_choices=DATA_BITS_CHOICES,
    stop_choices=STOP_BITS_CHOICES,
    parity_choices=PARITY_CHOICES,
    flow_choices=FLOW_CHOICES,
):
    """Longest `8 - N - 1 - N` string from the legal lists."""
    longest = ""
    for data, stop, parity, flow in product(
        data_choices, stop_choices, parity_choices, flow_choices
    ):
        text = format_settings_text(data, stop, parity, flow)
        if len(text) > len(longest):
            longest = text
    return longest


def parse_baud(text):
    """Displayed or typed baud → int. Strips commas; still accepts 115.2K."""
    if text is None:
        raise ValueError("empty baud")
    if isinstance(text, bool):
        raise ValueError("invalid baud")
    if isinstance(text, int):
        return int(text)
    if isinstance(text, float):
        return int(text)
    raw = str(text).strip().upper().replace(" ", "").replace(",", "")
    if not raw:
        raise ValueError("empty baud")
    if raw.endswith("K"):
        return int(round(float(raw[:-1]) * 1000))
    return int(float(raw))


def format_baud_label(baud):
    """Full integer with comma thousands separators, e.g. 115200 -> 115,200."""
    if baud is None or baud == "":
        return None
    try:
        value = parse_baud(baud)
    except (TypeError, ValueError):
        return str(baud)
    return f"{value:,}"


BAUD_SHORT = [(value, format_baud_label(value)) for value in BAUD_SHORT_VALUES]
BAUD_SHORT_BY_VALUE = {value: label for value, label in BAUD_SHORT}


def picker_device_label(device, baud_text):
    """Dropdown text: Manufacturer  model  115,200 Baud."""
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


PORT_STATUS_VALUES = (
    PORT_STATUS_CLOSED,
    PORT_STATUS_OPENED,
    PORT_STATUS_FAILED,
    PORT_STATUS_UNKNOWN,
)

PORT_STATUS_KIND_SELECTED = "selected"
PORT_STATUS_KIND_OPENED = "opened"
PORT_STATUS_KIND_IDENTIFIED = "identified"
PORT_STATUS_KIND_FAILED = "failed"
PORT_STATUS_SAMPLE_PORT = "COM256"

_BOTTOM_PORT_STATUS_KIND_ALIASES = {
    "selected": PORT_STATUS_KIND_SELECTED,
    "closed": PORT_STATUS_KIND_SELECTED,
    "unknown": PORT_STATUS_KIND_SELECTED,
    "opened": PORT_STATUS_KIND_OPENED,
    "open": PORT_STATUS_KIND_OPENED,
    "identified": PORT_STATUS_KIND_IDENTIFIED,
    "failed": PORT_STATUS_KIND_FAILED,
    "fail": PORT_STATUS_KIND_FAILED,
}


def normalize_bottom_port_status_kind(kind):
    """Map UI/event names onto selected / opened / identified / failed."""
    if kind is None:
        return PORT_STATUS_KIND_SELECTED
    text = str(kind).strip()
    if not text:
        return PORT_STATUS_KIND_SELECTED
    return _BOTTOM_PORT_STATUS_KIND_ALIASES.get(text.lower(), PORT_STATUS_KIND_SELECTED)


def flow_choice_from_serial_flags(settings=None):
    """pyserial rtscts/xonxoff flags → UI flow choice."""
    settings = settings or {}
    if settings.get("rtscts"):
        return "RTS/CTS"
    if settings.get("xonxoff"):
        return FLOW_XOFF_XON
    return "None"


def bottom_port_status_fields_from_serial_settings(settings=None):
    """Open/Identify serial.Serial kwargs → Port Status fields."""
    settings = settings or {}
    return {
        "baud": settings.get("baudrate"),
        "data_bits": settings.get("bytesize", 8),
        "parity": settings.get("parity", "N"),
        "stop_bits": settings.get("stopbits", 1),
        "flow_control": flow_choice_from_serial_flags(settings),
    }


def bottom_port_status_fields_from_device(device, baud=None):
    """Scan/Identify device serial_parameters → Port Status fields."""
    params = (device or {}).get("serial_parameters") or {}
    return {
        "baud": baud,
        "data_bits": params.get("data_bits", params.get("bytesize", 8)),
        "parity": params.get("parity", "N"),
        "stop_bits": params.get("stop_bits", params.get("stopbits", 1)),
        "flow_control": params.get("flow_control", "None"),
    }


def bottom_port_status_text(
    port,
    kind=PORT_STATUS_KIND_SELECTED,
    baud=None,
    data_bits=8,
    parity="N",
    stop_bits=1,
    flow_control=None,
    **_ignored,
):
    """Bottom Port Status. One helper for click / identify / open / fail.

    Click or select: `COM8`. Identified or opened: `COM8   115,200   8 - N - 1 - N`.
    Open failed: `COM8 - Failed to open`.
    """
    name = "" if port is None else str(port).strip()
    if not name or name == "No Ports Available":
        return ""
    kind = normalize_bottom_port_status_kind(kind)
    if kind == PORT_STATUS_KIND_FAILED:
        return join_setting_parts(name, "Failed to open")
    if kind in (PORT_STATUS_KIND_OPENED, PORT_STATUS_KIND_IDENTIFIED) and baud is not None:
        baud_text = format_baud_label(baud)
        if not baud_text:
            baud_text = str(baud)
        settings_text = format_settings_text(data_bits, stop_bits, parity, flow_control)
        return (
            f"{name}{PORT_STATUS_GROUP_SEP}{baud_text}"
            f"{PORT_STATUS_GROUP_SEP}{settings_text}"
        )
    return name

# Values the Device Status box must fully show. Nothing Identified is the
# longest of these status words; catalog Identified labels (with optional
# appended response text) are passed in as extra samples and are longer.
DEVICE_STATUS_VALUE_SAMPLES = (
    DEVICE_STATUS_UNIDENTIFIED,
    DEVICE_STATUS_IDENTIFIED,
    "Failed",
    "2nd Failure",
    "3rd Failure",
    "10th Failure",
    "11th Failure",
    "12th Failure",
    "13th Failure",
    "21st Failure",
    "22nd Failure",
    "23rd Failure",
)


def _unique_texts(*groups):
    seen = []
    for group in groups:
        for text in group:
            if text not in seen:
                seen.append(text)
    return tuple(seen)


def port_status_size_samples(*extra):
    """Every Port Status string the field must fully show."""
    port = PORT_STATUS_SAMPLE_PORT
    built = (
        bottom_port_status_text(port, PORT_STATUS_KIND_SELECTED),
        bottom_port_status_text(port, PORT_STATUS_KIND_FAILED),
        bottom_port_status_text(
            port,
            PORT_STATUS_KIND_OPENED,
            baud=921600,
            data_bits=8,
            parity="N",
            stop_bits=1,
        ),
        bottom_port_status_text(
            port,
            PORT_STATUS_KIND_IDENTIFIED,
            baud=115200,
            data_bits=8,
            parity="N",
            stop_bits=1,
        ),
        bottom_port_status_text(
            port,
            PORT_STATUS_KIND_OPENED,
            baud=1000000,
            data_bits=8,
            parity="Space",
            stop_bits=2,
            flow_control="XON/XOFF",
        ),
        "COM8",
        "COM8 - Failed to open",
        "COM8   115,200   8 - N - 1 - N",
        "COM8   460,800   8 - N - 1 - N",
        "COM8   9,600   8 - N - 1 - N",
        "COM8   300   8 - N - 1 - N",
        "COM8   1,200   8 - N - 1 - N",
        "COM8   19,200   8 - N - 1 - N",
        "COM8   921,600   8 - N - 1 - N",
        "COM256   1,000,000   8 - S - 2 - X",
    )
    catalog = []
    for item in extra:
        if item is None:
            continue
        if isinstance(item, (list, tuple)):
            catalog.extend(str(text) for text in item if text)
        else:
            catalog.append(str(item))
    return _unique_texts(built, catalog)


def device_status_size_samples(*extra):
    """Every Device Status string the field must fully show.

    extra is catalog Identified labels (devices.json + devices_info.json).
    """
    failures = [
        identify_failure_label(count)
        for count in (1, 2, 3, 4, 10, 11, 12, 13, 21, 22, 23, 24)
    ]
    catalog = []
    for item in extra:
        if item is None:
            continue
        if isinstance(item, (list, tuple)):
            catalog.extend(str(text) for text in item if text)
        else:
            catalog.append(str(item))
    return _unique_texts(
        DEVICE_STATUS_VALUE_SAMPLES, failures, ("Unknown Device",), catalog
    )


def longest_port_status_text(*extra):
    return max(port_status_size_samples(*extra), key=len)


def longest_device_status_text(*extra):
    return max(device_status_size_samples(*extra), key=len)


def grid_ceil_px(px, grid=8):
    """Round pixel widths up onto the 8px grid."""
    try:
        px = int(px)
    except (TypeError, ValueError):
        px = 0
    step = max(int(grid) or 8, 1)
    if px <= 0:
        return step
    return ((px + step - 1) // step) * step


def status_value_width_px(
    text_px, padx=0, border=0, highlight=0, grid=8, slack=8
):
    """Pixel wrap width for a status value. Never uses character counts.

    text_px comes from Font.measure() on the widget's actual font. slack
    keeps the last glyph from clipping (Linux fallback fonts ran 1–2px over).
    """
    try:
        text_px = max(0, int(text_px))
    except (TypeError, ValueError):
        text_px = 0
    chrome = (
        2 * max(0, int(padx or 0))
        + 2 * max(0, int(border or 0))
        + 2 * max(0, int(highlight or 0))
        + max(0, int(slack or 0))
    )
    return grid_ceil_px(text_px + chrome, grid)


def device_status_text(
    identified_device,
    selected_device,
    fail_count=0,
    fail_key=None,
    identified_label=None,
):
    """Bottom Device Status. Nothing Identified until Identify or Scan confirms.

    When confirmed, identified_label is the same Connected Device column text
    (identified_connected_label). Other states stay Nothing Identified /
    failure ordinals.
    """
    identified_key = device_identity_key(identified_device)
    selected_key = device_identity_key(selected_device)
    if identified_key and identified_key == selected_key:
        label = (identified_label or "").strip()
        return label or DEVICE_STATUS_IDENTIFIED
    if fail_count and fail_key and fail_key == selected_key:
        return identify_failure_label(fail_count)
    return DEVICE_STATUS_UNIDENTIFIED


def identified_device_message(
    identified_device,
    selected_device,
    fail_count=0,
    fail_key=None,
    identified_label=None,
):
    """Bottom Device Status value. Nothing Identified until this port matches the dropdown device."""
    return device_status_text(
        identified_device,
        selected_device,
        fail_count,
        fail_key,
        identified_label=identified_label,
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
    mode=MODE_MANUAL,
):
    """State after picking a Device.

    Manual mode (Device dropdown) leaves baud, Settings, and Port Status
    unchanged. Automatic mode may apply the device's Port Settings.
    """
    new_key = device_identity_key(selected_device)
    if new_key != previous_key:
        fail_count = 0
        fail_key = new_key
    automatic = str(mode or MODE_MANUAL).strip().lower() == MODE_AUTOMATIC
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
        "apply_baud": automatic,
        "apply_settings": automatic,
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


def exit_handoff_payload():
    """Window X / Exit: empty result for the calling app."""
    return {"result": None}


_SELECT_DEVICE_KEYS = ("manufacturer", "model", "short_description")


def select_handoff_payload(
    *,
    port=None,
    baud=None,
    data_bits=None,
    stop_bits=None,
    parity=None,
    flow_control=None,
    device=None,
):
    """Select payload: open-port specs plus identified device, or null device."""
    if device:
        payload_device = {
            key: (device.get(key) or "") if isinstance(device, dict) else ""
            for key in _SELECT_DEVICE_KEYS
        }
    else:
        payload_device = None
    return {
        "port": port,
        "baud": baud,
        "data_bits": data_bits,
        "stop_bits": stop_bits,
        "parity": parity,
        "flow_control": flow_control,
        "device": payload_device,
    }


def apply_header_button_click(in_use, scan_ports, scan_devices, button):
    """Header click: stop Scan Ports / Scan Devices auto-repeat.

    In Use is a view filter, not auto-repeat. The In Use button checks it;
    Scan Ports / Scan Devices leave it as-is.
    """
    if button == "in_use":
        return True, False, False
    return bool(in_use), False, False


IN_USE_BUTTON_BASE = "In Use"
IN_USE_BUTTON_WIDTH_COUNT = 99  # size the header button for two-digit counts


def count_in_use_ports(rows):
    """In Use rows in the full port list, ignoring the view filter."""
    count = 0
    for row in rows or ():
        if not row:
            continue
        if row[0] == STATUS_IN_USE:
            count += 1
    return count


def in_use_button_text(count):
    """Header In Use button: `In Use x0`, `In Use x3` (no space after x)."""
    try:
        n = int(count)
    except (TypeError, ValueError):
        n = 0
    if n < 0:
        n = 0
    return f"{IN_USE_BUTTON_BASE} x{n}"


def in_use_button_size_text():
    """Longest header In Use label used to keep the button width fixed."""
    return in_use_button_text(IN_USE_BUTTON_WIDTH_COUNT)


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
