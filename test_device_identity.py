"""Unit tests for devices.json and identity helpers (no hardware, no display)."""

import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent
DEVICES_JSON = ROOT / "devices.json"


class SerialException(Exception):
    """Stand-in for pyserial.SerialException so tests never need hardware."""


def _install_import_stubs():
    """serial_port_app and device_editor import tkinter/pyserial at load time."""
    serial_mod = MagicMock(name="serial")
    serial_mod.SerialException = SerialException
    serial_mod.STOPBITS_ONE = 1
    serial_mod.STOPBITS_ONE_POINT_FIVE = 1.5
    serial_mod.STOPBITS_TWO = 2
    sys.modules.setdefault("tkinter", MagicMock())
    sys.modules.setdefault("tkinter.ttk", MagicMock())
    sys.modules.setdefault("tkinter.font", MagicMock())
    sys.modules.setdefault("tkinter.messagebox", MagicMock())
    sys.modules.setdefault("serial", serial_mod)
    sys.modules.setdefault("serial.tools", MagicMock())
    sys.modules.setdefault("serial.tools.list_ports", MagicMock())


_install_import_stubs()

from device_data import (  # noqa: E402
    device_matches_ids,
    format_device_column,
    load_device_file,
    load_devices_info_file,
    load_serial_ports_file,
    parse_controllers_text,
    scan_controller_ids,
)
from device_editor import DeviceEditorApp, PORT_VID_PID_LABEL  # noqa: E402
from device_data import STANDARD_BAUD_RATES  # noqa: E402
from picker_logic import (  # noqa: E402
    DATA_BITS_CHOICES,
    DEVICE_SCAN_DONE,
    DEVICE_SCANNING,
    DEVICE_STATUS_UNIDENTIFIED,
    SCAN_SKIPPED_OPEN,
    FLOW_CHOICES,
    MODE_AUTOMATIC,
    MODE_MANUAL,
    PARITY_CHOICES,
    STOP_BITS_CHOICES,
    bottom_port_status_text,
    device_status_size_samples,
    exit_handoff_payload,
    format_port_scan_header,
    format_scan_usb_id,
    grid_ceil_px,
    identify_attempt_message,
    port_status_size_samples,
)
from serial_port_app import SerialPortApp, UI_CONTROL_H, UI_PAD  # noqa: E402


def _load_definitions():
    payload, error = load_device_file(str(DEVICES_JSON))
    assert error is None, error
    return payload


def _device_by_model(model, baudrate=None):
    for device in _load_definitions()["devices"]:
        if device["model"] != model:
            continue
        rates = device["serial_parameters"]["baud_rates"]
        if baudrate is None or baudrate in rates:
            return device
    raise AssertionError(f"No devices.json entry for {model!r}")


def _devices_for_vid(vendor_id):
    return [
        device
        for device in _load_definitions()["devices"]
        if device_matches_ids(device, vendor_id)
    ]


def _bare_app():
    return SerialPortApp.__new__(SerialPortApp)


MB607_FLASH_REPLY = "Running Flash        REV= 0010, RevP1.01 003/09/24"
MB607_WAIT_FOR = "Press CR key for comand Debug Mode"
MB607_EXPECT = "Enter command"
MB607_PROBE_REPLY = f"{MB607_WAIT_FOR}\r\n{MB607_EXPECT}\r\n{MB607_FLASH_REPLY}"
MB607_RESET_TIMEOUT = (
    "DTR reset timeout waiting for 'Press CR key for comand Debug Mode'"
)


class _Flag:
    """Minimal stand-in for tk.BooleanVar."""

    def __init__(self, value=False):
        self.value = bool(value)

    def get(self):
        return self.value

    def set(self, value):
        self.value = bool(value)


def _controller_id_text(device, vendor_id, product_id=None):
    ids = scan_controller_ids(device, vendor_id, product_id)
    if ids is None:
        return "any"
    return format_scan_usb_id(ids[0], ids[1], empty="any")


def _device_line(
    device,
    baud,
    frame,
    vendor_id,
    product_id=None,
    **result,
):
    return identify_attempt_message(
        device,
        baud,
        frame,
        _controller_id_text(device, vendor_id, product_id),
        **result,
    )


def _logged(mock_log):
    return [call.args[0] for call in mock_log.call_args_list if call.args]


class FakeSerial:
    """Context-manager stand-in for pyserial.Serial.

    Matches the idle-DTR open helper: construct closed, set dtr, then open().
    fail_open / fail_baudrates raise from open(), as a real port-busy error would.
    """

    fail_open = False
    fail_baudrates = ()
    response = b""
    responses_by_baud = {}
    instances = []

    def __init__(self, port=None, **kwargs):
        self.port = port
        self.kwargs = kwargs
        self.written = []
        self._dtr = True
        self._rts = True
        self.is_open = False
        self.events = []
        self.close_calls = 0
        baud = kwargs.get("baudrate")
        by_baud = FakeSerial.responses_by_baud or {}
        if baud in by_baud:
            data = by_baud[baud]
        else:
            data = FakeSerial.response
        self.response_data = data
        self.in_waiting = len(data)
        FakeSerial.instances.append(self)

    @property
    def dtr(self):
        return self._dtr

    @dtr.setter
    def dtr(self, value):
        self._dtr = bool(value)
        self.events.append(("dtr", self._dtr, self.is_open))

    @property
    def rts(self):
        return self._rts

    @rts.setter
    def rts(self, value):
        self._rts = bool(value)
        self.events.append(("rts", self._rts, self.is_open))

    def open(self):
        self.events.append(("open", self._dtr, self.is_open))
        baud = self.kwargs.get("baudrate")
        if FakeSerial.fail_open or baud in FakeSerial.fail_baudrates:
            raise SerialException("port busy")
        self.is_open = True

    def close(self):
        self.close_calls += 1
        self.is_open = False
        self.events.append(("close",))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def write(self, data):
        self.written.append(data)

    def read(self, size=1):
        return self.response_data


class FakeSerialTests(unittest.TestCase):
    def setUp(self):
        FakeSerial.fail_open = False
        FakeSerial.fail_baudrates = ()
        FakeSerial.response = b""
        FakeSerial.responses_by_baud = {}
        FakeSerial.instances = []


class DevicesJsonLoadTests(unittest.TestCase):
    def test_file_loads_a_devices_list(self):
        data = _load_definitions()
        self.assertIsInstance(data, dict)
        self.assertIn("devices", data)
        self.assertIsInstance(data["devices"], list)
        self.assertGreaterEqual(len(data["devices"]), 1)

    def test_each_device_has_the_fields_the_apps_read(self):
        required = (
            "controllers",
            "manufacturer",
            "model",
            "type",
            "serial_parameters",
            "commands",
            "response",
        )
        for device in _load_definitions()["devices"]:
            for field in required:
                self.assertIn(field, device, msg=f"missing {field} on {device}")
            self.assertIsInstance(device["controllers"], list)
            self.assertIsInstance(device["type"], str)
            self.assertIn("baud_rates", device["serial_parameters"])
            self.assertGreaterEqual(len(device["serial_parameters"]["baud_rates"]), 1)
            self.assertIn("initialize", device["commands"])
            self.assertIn("identify", device["commands"])
            self.assertIn("pause_ms", device["commands"]["initialize"])
            self.assertIn("pause_ms", device["commands"]["identify"])
            self.assertIn("regex", device["response"])
            self.assertIn("device_column", device["response"])
            self.assertIn("append_response", device["response"])
            self.assertIsInstance(device["response"]["append_response"], bool)

    def test_response_regexes_compile(self):
        for device in _load_definitions()["devices"]:
            pattern = (device.get("response") or {}).get("regex") or ""
            re.compile(pattern)


class VendorIdMatchTests(unittest.TestCase):
    def test_known_vendor_ids_select_the_expected_models(self):
        self.assertEqual(
            [d["model"] for d in _devices_for_vid("1027")],
            ["SIM7080"],
        )
        self.assertEqual(
            [
                (d["model"], d["serial_parameters"]["baud_rates"])
                for d in _devices_for_vid("4292")
            ],
            [("MB607", [460800, 115200])],
        )
        self.assertEqual(
            [d["model"] for d in _devices_for_vid("0x10C4")],
            ["MB607"],
        )
        self.assertEqual(
            [d["model"] for d in _devices_for_vid("0x067B")],
            ["MB607"],
        )
        self.assertEqual(
            [d["model"] for d in _devices_for_vid("1234")],
            ["HMP4040"],
        )
        self.assertEqual(
            [d["model"] for d in _devices_for_vid("4592")],
            ["S-Woom32"],
        )

    def test_unknown_vendor_id_matches_nothing(self):
        self.assertEqual(_devices_for_vid("9999"), [])
        self.assertEqual(_devices_for_vid("Unknown"), [])

    def test_vendor_id_int_and_str_are_the_same_match(self):
        self.assertTrue(SerialPortApp._vendor_id_in_list(4292, ["4292"]))
        self.assertTrue(SerialPortApp._vendor_id_in_list("4292", [4292]))
        self.assertTrue(SerialPortApp._vendor_id_in_list("0x10C4", ["4292"]))
        self.assertTrue(SerialPortApp._vendor_id_in_list(4292, ["0x10C4"]))
        self.assertFalse(SerialPortApp._vendor_id_in_list("1027", ["4292"]))


class RegexAndDeviceColumnTests(unittest.TestCase):
    def test_mb607_regex_matches_revp_flash_line(self):
        device = _device_by_model("MB607", baudrate=460800)
        self.assertEqual(
            device["response"]["regex"],
            r"RevP(?P<revision>\d+\.\d+)\s+(?P<date>\d+/\d+/\d+)",
        )
        self.assertEqual(device["response"]["device_column"], "Revision {revision}")
        match = re.search(device["response"]["regex"], MB607_FLASH_REPLY)
        self.assertIsNotNone(match)
        self.assertEqual(match.group("revision"), "1.01")
        self.assertEqual(
            format_device_column(device, match.groupdict()),
            "Revision 1.01",
        )
        self.assertEqual(
            SerialPortApp._connected_device_label(device),
            "MUX Wiring MB607 - BCM with 7-Inputs 6-Outputs & CAN bus",
        )

    def test_sim7080_regex_fills_model_and_label_is_manufacturer_model(self):
        device = _device_by_model("SIM7080")
        match = re.search(device["response"]["regex"], "SIMCOM_SIM7080")
        self.assertIsNotNone(match)
        self.assertEqual(match.group("model"), "SIM7080")
        self.assertEqual(
            format_device_column(device, match.groupdict()),
            "SIMCom SIM7080",
        )
        self.assertEqual(
            SerialPortApp._connected_device_label(device),
            "SIMCom SIM7080",
        )

    def test_hmp4040_regex_named_groups(self):
        device = _device_by_model("HMP4040")
        match = re.search(
            device["response"]["regex"],
            "Rohde & Schwarz, HMP4040, 12345, 2.0",
        )
        self.assertIsNotNone(match)
        self.assertEqual(match.group("serial"), "12345")
        self.assertEqual(match.group("firmware"), "2.0")
        self.assertEqual(
            format_device_column(device, match.groupdict()),
            "Rohde & Schwarz HMP4040 (S/N: 12345, FW: 2.0)",
        )
        self.assertEqual(
            SerialPortApp._connected_device_label(device),
            "Rohde & Schwarz HMP4040",
        )

    def test_empty_regex_is_skipped_the_same_way_identify_does(self):
        device = _device_by_model("S-Woom32")
        pattern = (device.get("response") or {}).get("regex") or ""
        self.assertEqual(pattern, "")
        # An empty pattern would match anything; the app therefore skips it.
        self.assertFalse(bool(pattern))

    def test_identified_column_shows_device_not_usb_driver(self):
        app = _bare_app()
        app.serial_ports = {"serial_ports": []}
        app.devices_info = {"devices": []}
        usb = "CP210x USB to UART Bridge Controller"
        mb607 = {
            "manufacturer": "MUX Wiring",
            "model": "MB607",
            "short_description": "Body Control Module",
            "response": {"append_response": False},
        }
        self.assertEqual(
            app._driver_or_device_column(
                "Identified",
                "Revision 1.01",
                usb,
                identified_device=mb607,
            ),
            "MUX Wiring MB607 Body Control Module",
        )
        self.assertEqual(app._driver_or_device_column("Available", None, usb), usb)
        self.assertEqual(app._driver_or_device_column("In Use", None, usb), usb)
        self.assertEqual(
            app._driver_or_device_column("Identified", None, usb),
            usb,
        )
        self.assertEqual(
            app._driver_or_device_column("Available", None, None),
            "Unknown",
        )

    def test_available_row_uses_uart_ic_when_vid_pid_matches(self):
        app = _bare_app()
        app.serial_ports, error = load_serial_ports_file(str(ROOT / "serial_ports.json"))
        self.assertIsNone(error)
        app.devices_info = {"devices": []}
        self.assertEqual(
            app._driver_or_device_column(
                "Available",
                None,
                "USB Serial Port",
                "0x0403:0x6001",
            ),
            "FTDI FT232R/RL/RQ",
        )
        self.assertEqual(
            app._driver_or_device_column(
                "In Use",
                None,
                "USB-to-Serial Comm Port",
                "0x067B:0x2303",
            ),
            "Prolific PL2303HX/TA/SA/RA",
        )
        self.assertEqual(
            app._driver_or_device_column(
                "Available",
                None,
                "Some other adapter",
                "0x0000:0x0001",
            ),
            "Some other adapter",
        )

    def test_identified_row_prefers_devices_info_short_description(self):
        app = _bare_app()
        app.serial_ports = {"serial_ports": []}
        app.devices_info, error = load_devices_info_file(str(ROOT / "devices_info.json"))
        self.assertIsNone(error)
        mb607 = _device_by_model("MB607")
        self.assertEqual(
            app._driver_or_device_column(
                "Identified",
                "Revision 1.23 01/15/24",
                "CP210x USB to UART Bridge Controller",
                "0x10C4:0xEA60",
                mb607,
            ),
            "MUX Wiring MB607 Body Control Module - Revision 1.23 01/15/24",
        )

    def test_identified_device_status_matches_connected_device_column(self):
        app = _bare_app()
        app.serial_ports = {"serial_ports": []}
        app.devices_info, error = load_devices_info_file(str(ROOT / "devices_info.json"))
        self.assertIsNone(error)
        mb607 = _device_by_model("MB607")
        sim = _device_by_model("SIM7080")
        cases = (
            (mb607, "Revision 1.23 01/15/24", "CP210x USB to UART Bridge Controller"),
            (sim, "SIMCom SIM7080", "FTDI"),
        )
        for device, column, usb in cases:
            connected = app._driver_or_device_column(
                "Identified",
                column,
                usb,
                "0x10C4:0xEA60",
                device,
            )
            status = app._identified_connected_text(device, column)
            if status:
                self.assertEqual(connected, status)
            self.assertEqual(
                connected,
                app._driver_or_device_column(
                    "Identified", column, usb, "0x10C4:0xEA60", device
                ),
            )
        self.assertEqual(
            app._identified_connected_text(mb607, "Revision 1.23 01/15/24"),
            "MUX Wiring MB607 Body Control Module - Revision 1.23 01/15/24",
        )
        self.assertEqual(
            app._identified_connected_text(sim, "SIMCom SIM7080"),
            "SIMCom SIM7080",
        )
        self.assertIsNone(
            app._identified_connected_text(None, "Revision 1.0 01/01/26"),
        )

    def test_device_status_size_samples_include_catalog_labels(self):
        app = _bare_app()
        app.device_definitions, error = load_device_file(str(DEVICES_JSON))
        app.devices_info, info_error = load_devices_info_file(
            str(ROOT / "devices_info.json")
        )
        self.assertIsNone(error)
        self.assertIsNone(info_error)
        samples = app._device_status_size_samples()
        self.assertIn(
            "MUX Wiring MB607 Body Control Module - Revision 1.01", samples
        )
        self.assertIn("Nothing Identified", samples)
        self.assertIn("Identified", samples)
        self.assertIn("Unknown Device", samples)
        baseline = device_status_size_samples()
        for word in baseline:
            self.assertIn(word, samples)


class IdBaudColumnTests(unittest.TestCase):
    def test_identified_shows_short_baud_not_vendor_id(self):
        app = _bare_app()
        self.assertEqual(app._id_baud_column("Identified", "4292", 460800), "460,800")
        self.assertEqual(app._id_baud_column("Open", "4292", 460800), "460,800")
        self.assertEqual(app._id_baud_column("Identified", "1027", 115200), "115,200")
        self.assertEqual(app._id_baud_column("Identified", "1234", 9600), "9,600")

    def test_unidentified_shows_vendor_id(self):
        app = _bare_app()
        self.assertEqual(app._id_baud_column("Available", "4292", None), "4292")
        self.assertEqual(app._id_baud_column("In Use", "1027", None), "1027")
        self.assertEqual(app._id_baud_column("Identified", "4292", None), "4292")
        self.assertEqual(app._id_baud_column("Available", "", None), "Unknown")

    def test_format_baud_known_and_unknown_values(self):
        self.assertIsNone(SerialPortApp.format_baud(None))
        self.assertEqual(SerialPortApp.format_baud(115200), "115,200")
        self.assertEqual(SerialPortApp.format_baud(42), "42")
        self.assertEqual(SerialPortApp.format_baud("9,600"), "9,600")
        self.assertEqual(SerialPortApp.format_baud(1000000), "1,000,000")

    def test_parse_baud_strips_commas(self):
        app = _bare_app()
        self.assertEqual(app._parse_baud("115,200"), 115200)
        self.assertEqual(app._parse_baud("1,000,000"), 1000000)
        self.assertEqual(app._parse_baud("115.2K"), 115200)
        self.assertEqual(app._parse_baud("300"), 300)


class IdentifyWithMockSerialTests(FakeSerialTests):
    def _identify(self, port, vendor_id, definitions=None):
        app = _bare_app()
        with patch("serial_port_app.serial.Serial", FakeSerial), patch(
            "serial_port_app.time.sleep"
        ):
            result = app._identify_device_with_defs(
                port, vendor_id, definitions or _load_definitions()
            )
            return result[0], result[1]

    def test_matching_reply_returns_label_and_baud(self):
        FakeSerial.response = MB607_PROBE_REPLY.encode()
        label, baud = self._identify("COM5", "4292")
        self.assertEqual(label, "Revision 1.01")
        self.assertEqual(baud, 460800)
        self.assertEqual(FakeSerial.instances[0].written, [b"\r\r", b"I\r"])

    def test_sim7080_identify_commands_and_label(self):
        FakeSerial.response = b"SIMCOM_SIM7080"
        label, baud = self._identify("/dev/ttyUSB0", "1027")
        self.assertEqual(label, "SIMCom SIM7080")
        self.assertEqual(baud, 115200)
        self.assertEqual(FakeSerial.instances[0].written, [b"AT\r", b"AT+GMM\r"])

    def test_wrong_vendor_id_does_not_open_serial(self):
        FakeSerial.response = b"SIMCOM_SIM7080"
        label, baud = self._identify("COM5", "9999")
        self.assertIsNone(label)
        self.assertIsNone(baud)
        self.assertEqual(FakeSerial.instances, [])

    def test_empty_controllers_are_tried_on_any_port(self):
        empty = {
            "devices": [
                {
                    "controllers": [],
                    "manufacturer": "Any",
                    "model": "Box",
                    "serial_parameters": {
                        "baud_rates": [9600],
                        "parity": "N",
                        "stopbits": 1,
                        "bytesize": 8,
                    },
                    "commands": {
                        "initialize": {"message": "", "pause_ms": 0},
                        "identify": {"message": "I\r", "pause_ms": 0},
                    },
                    "response": {"regex": "HELLO", "device_column": "{model}"},
                }
            ]
        }
        FakeSerial.response = b"HELLO"
        label, baud = self._identify("COM5", "9999", definitions=empty)
        self.assertEqual(label, "Box")
        self.assertEqual(baud, 9600)
        self.assertEqual(FakeSerial.instances[0].written, [b"I\r"])

    def test_identify_open_port_skips_serial_when_ids_do_not_match(self):
        app = _bare_app()
        app.port_data = [("Open", "COM3", "0x0403:0x6001", None, "FTDI", None)]
        app._log = MagicMock()
        app._log_cont = MagicMock()
        app.root = MagicMock()
        mb607 = _device_by_model("MB607")
        FakeSerial.instances = []
        with patch("serial_port_app.serial.Serial", FakeSerial):
            app._connection_scan_worker(
                "COM3", {"baudrate": 9600}, mb607, True
            )
        self.assertEqual(FakeSerial.instances, [])
        app.root.after.assert_called()
        skip_logs = _logged(app._log_cont)
        self.assertIn(format_port_scan_header("COM3", "0x0403:0x6001"), skip_logs)
        self.assertIn(
            _device_line(mb607, 9600, "8N1", "0x0403:0x6001", skipped_vid_pid=True),
            skip_logs,
        )
        self.assertFalse(any("Trying " in text for text in skip_logs))
        self.assertFalse(any("does not match device" in text for text in skip_logs))

    def test_identify_logs_reply_when_regex_does_not_match(self):
        app = _bare_app()
        app.port_data = [("Open", "COM5", "0x10C4:0xEA60", None, "CP210x", None)]
        app._log = MagicMock()
        app._log_cont = MagicMock()
        app.root = MagicMock()
        mb607 = _device_by_model("MB607")
        garbage = f"{MB607_WAIT_FOR}\r\n{MB607_EXPECT}\r\nRevPK garbage\r\n"
        FakeSerial.response = garbage.encode()
        with patch("serial_port_app.serial.Serial", FakeSerial), patch(
            "serial_port_app.time.sleep"
        ):
            app._connection_scan_worker(
                "COM5",
                {
                    "baudrate": 115200,
                    "parity": "N",
                    "bytesize": 8,
                    "stopbits": 1,
                },
                mb607,
                True,
            )
        logs = _logged(app._log_cont)
        self.assertEqual(logs[0], format_port_scan_header("COM5", "0x10C4:0xEA60"))
        self.assertIn(
            _device_line(
                mb607, 115200, "8N1", "0x10C4:0xEA60", reply=garbage
            ),
            logs,
        )
        self.assertIn(DEVICE_SCAN_DONE, logs)
        self.assertFalse(any("NOT FOUND" in text for text in logs))
        self.assertFalse(any("Trying " in text for text in logs))
        app._log.assert_any_call(DEVICE_SCANNING)

    def test_scan_logs_each_baud_try_and_skip(self):
        app = _bare_app()
        app._log_cont = MagicMock()
        mb607 = _device_by_model("MB607")
        FakeSerial.response = b""
        with patch("serial_port_app.serial.Serial", FakeSerial), patch(
            "serial_port_app.time.sleep"
        ):
            label, baud, device = app._identify_device_with_defs(
                "COM5",
                "4292",
                {"devices": [mb607]},
            )
        self.assertIsNone(label)
        self.assertIsNone(baud)
        self.assertIsNone(device)
        logs = _logged(app._log_cont)
        self.assertEqual(
            logs,
            [
                _device_line(mb607, 460800, "8N1", "4292", error=MB607_RESET_TIMEOUT),
                _device_line(mb607, 115200, "8N1", "4292", error=MB607_RESET_TIMEOUT),
            ],
        )

    def test_scan_logs_vid_pid_skip_without_opening_serial(self):
        app = _bare_app()
        app._log_cont = MagicMock()
        mb607 = _device_by_model("MB607")
        FakeSerial.instances = []
        with patch("serial_port_app.serial.Serial", FakeSerial):
            label, baud, _device = app._identify_device_with_defs(
                "COM5", "9999", {"devices": [mb607]}
            )
        self.assertIsNone(label)
        self.assertIsNone(baud)
        self.assertEqual(FakeSerial.instances, [])
        logs = _logged(app._log_cont)
        self.assertEqual(
            logs,
            [_device_line(mb607, 460800, "8N1", "9999", skipped_vid_pid=True)],
        )

    def test_device_allowed_on_port_follows_controller_rule(self):
        app = _bare_app()
        app.port_data = [("Open", "COM3", "0x0403:0x6001", None, "FTDI", None)]
        self.assertTrue(app._device_allowed_on_port(_device_by_model("SIM7080"), "COM3"))
        self.assertFalse(app._device_allowed_on_port(_device_by_model("MB607"), "COM3"))
        self.assertTrue(app._device_allowed_on_port({"controllers": []}, "COM3"))
        self.assertTrue(app._device_allowed_on_port({}, "COM3"))

    def test_empty_regex_device_is_not_identified(self):
        FakeSerial.response = b"anything"
        label, baud = self._identify("COM5", "4592")
        self.assertIsNone(label)
        self.assertIsNone(baud)

    def test_open_failure_on_first_baud_tries_next_baud_in_the_list(self):
        FakeSerial.fail_baudrates = (460800,)
        FakeSerial.response = MB607_PROBE_REPLY.encode()
        label, baud = self._identify("COM5", "4292")
        self.assertEqual(label, "Revision 1.01")
        self.assertEqual(baud, 115200)

    def test_probe_open_port_uses_the_same_regex(self):
        app = _bare_app()
        device = _device_by_model("SIM7080")
        FakeSerial.response = b"SIMCOM_SIM7080"
        ser = FakeSerial("COM5")
        with patch("serial_port_app.time.sleep"):
            self.assertTrue(app._probe_open_port(ser, device))
        FakeSerial.response = b"nope"
        ser = FakeSerial("COM5")
        with patch("serial_port_app.time.sleep"):
            self.assertFalse(app._probe_open_port(ser, device))
        empty = _device_by_model("S-Woom32")
        self.assertFalse(app._probe_open_port(ser, empty))

    def test_old_schema_definitions_still_identify(self):
        old = {
            "devices": [
                {
                    "vendor_ids": ["4292"],
                    "manufacturer": "MUX Wiring",
                    "model": "MB607",
                    "serial_parameters": {
                        "baudrate": 115200,
                        "parity": "N",
                        "stopbits": 1,
                        "bytesize": 8,
                    },
                    "commands": {
                        "initialize": {"message": "\r\r", "pause": 1},
                        "identify": {"message": "I\r", "pause": 1},
                    },
                    "response": {
                        "regex": "RevPK(?P<revision>\\d+\\.\\d+ \\d{2}/\\d{2}/\\d{2})",
                        "device_column": "Revision {revision}",
                    },
                }
            ]
        }
        FakeSerial.response = b"RevPK1.23 01/15/24"
        label, baud = self._identify("COM5", "4292", definitions=old)
        self.assertEqual(label, "Revision 1.23 01/15/24")
        self.assertEqual(baud, 115200)

    def test_identify_sleeps_pause_ms(self):
        FakeSerial.response = b"SIMCOM_SIM7080"
        app = _bare_app()
        with patch("serial_port_app.serial.Serial", FakeSerial), patch(
            "serial_port_app.time.sleep"
        ) as slept:
            app._identify_device_with_defs("COM5", "1027", _load_definitions())
        slept.assert_any_call(1.0)
        slept.assert_any_call(2.0)

    def test_open_failure_logs_error_then_tries_next_baud(self):
        FakeSerial.fail_baudrates = (460800,)
        FakeSerial.response = MB607_PROBE_REPLY.encode()
        app = _bare_app()
        app._log_cont = MagicMock()
        mb607 = _device_by_model("MB607")
        with patch("serial_port_app.serial.Serial", FakeSerial), patch(
            "serial_port_app.time.sleep"
        ):
            label, baud, device = app._identify_device_with_defs(
                "COM5", "4292", {"devices": [mb607]}
            )
        self.assertEqual(label, "Revision 1.01")
        self.assertEqual(baud, 115200)
        logs = _logged(app._log_cont)
        self.assertEqual(
            logs,
            [
                _device_line(mb607, 460800, "8N1", "4292", error="port busy"),
                _device_line(mb607, 115200, "8N1", "4292", matched=True),
            ],
        )


class ScanLogLayoutTests(FakeSerialTests):
    def _scan_app(self, port_data, definitions, comports):
        app = _bare_app()
        app._log = MagicMock()
        app._log_cont = MagicMock()
        app.root = MagicMock()
        app.port_data = port_data
        app.device_definitions = definitions
        by_device = {port.device: port for port in comports}
        app._comports_by_device = MagicMock(return_value=(comports, by_device))
        return app

    def test_eric_sample_layout_on_one_port(self):
        sim = _device_by_model("SIM7080")
        mb607 = _device_by_model("MB607")
        port = MagicMock(device="COM8", vid=0x10C4, pid=0xEA60)
        app = self._scan_app(
            [("Available", "COM8", "0x10C4:0xEA60", None, "CP210x", None)],
            {"devices": [sim, mb607]},
            [port],
        )
        FakeSerial.responses_by_baud = {
            460800: b"",
            115200: MB607_PROBE_REPLY.encode(),
        }
        FakeSerial.response = b""
        with patch("serial_port_app.serial.Serial", FakeSerial), patch(
            "serial_port_app.time.sleep"
        ):
            app._scan_devices_worker()
        self.assertEqual(
            _logged(app._log_cont),
            [
                "Port: COM8 (0x10C4/0xEA60)",
                "Device: SIMCom SIM7080 115200 8N1 (0x0403): "
                "Skipped, port ID doesn't match",
                _device_line(mb607, 460800, "8N1", "0x10C4:0xEA60", error=MB607_RESET_TIMEOUT),
                "Device: MUX Wiring MB607 115200 8N1 (0x10C4/0xEA60): Matched",
                DEVICE_SCAN_DONE,
            ],
        )
        app._log.assert_any_call(DEVICE_SCANNING)

    def test_ports_are_outer_loop_then_devices_json_then_baud_list(self):
        sim = _device_by_model("SIM7080")
        mb607 = _device_by_model("MB607")
        p8 = MagicMock(device="COM8", vid=0x10C4, pid=0xEA60)
        p3 = MagicMock(device="COM3", vid=0x0403, pid=0x6001)
        app = self._scan_app(
            [
                ("Available", "COM8", "0x10C4:0xEA60", None, "CP210x", None),
                ("Available", "COM3", "0x0403:0x6001", None, "FTDI", None),
            ],
            {"devices": [sim, mb607]},
            [p8, p3],
        )
        FakeSerial.response = b""
        with patch("serial_port_app.serial.Serial", FakeSerial), patch(
            "serial_port_app.time.sleep"
        ):
            app._scan_devices_worker()
        logs = _logged(app._log_cont)
        port_at = [i for i, line in enumerate(logs) if line.startswith("Port:")]
        self.assertEqual(
            [logs[i] for i in port_at],
            [
                "Port: COM8 (0x10C4/0xEA60)",
                "Port: COM3 (0x0403/0x6001)",
            ],
        )
        com8 = [line for line in logs[port_at[0] : port_at[1]] if line.startswith("Device:")]
        com3 = [line for line in logs[port_at[1] :] if line.startswith("Device:")]
        self.assertEqual(
            com8,
            [
                "Device: SIMCom SIM7080 115200 8N1 (0x0403): "
                "Skipped, port ID doesn't match",
                _device_line(mb607, 460800, "8N1", "0x10C4:0xEA60", error=MB607_RESET_TIMEOUT),
                _device_line(mb607, 115200, "8N1", "0x10C4:0xEA60", error=MB607_RESET_TIMEOUT),
            ],
        )
        self.assertEqual(
            com3,
            [
                "Device: SIMCom SIM7080 115200 8N1 (0x0403): No response",
                "Device: MUX Wiring MB607 460800 8N1 (0x10C4/0xEA60): "
                "Skipped, port ID doesn't match",
            ],
        )
        self.assertEqual(sum(1 for line in com3 if "MB607" in line), 1)
        self.assertFalse(any("FOUND" in line or "Trying " in line for line in logs))

    def test_match_stops_further_bauds_but_still_logs_later_devices(self):
        first = {
            "manufacturer": "First",
            "model": "A",
            "controllers": [{"vid": "0x10C4", "pid": "0xEA60"}],
            "serial_parameters": {
                "baud_rates": [460800, 115200],
                "parity": "N",
                "stopbits": 1,
                "bytesize": 8,
            },
            "commands": {
                "initialize": {"message": "", "pause_ms": 0},
                "identify": {"message": "A\r", "pause_ms": 0},
            },
            "response": {"regex": "HELLO", "device_column": "{model}"},
        }
        second = {
            "manufacturer": "Second",
            "model": "B",
            "controllers": [{"vid": "0x10C4", "pid": "0xEA60"}],
            "serial_parameters": {
                "baud_rates": [9600],
                "parity": "N",
                "stopbits": 1,
                "bytesize": 8,
            },
            "commands": {
                "initialize": {"message": "", "pause_ms": 0},
                "identify": {"message": "B\r", "pause_ms": 0},
            },
            "response": {"regex": "WORLD", "device_column": "{model}"},
        }
        app = _bare_app()
        app._log_cont = MagicMock()
        FakeSerial.response = b"HELLO"
        with patch("serial_port_app.serial.Serial", FakeSerial), patch(
            "serial_port_app.time.sleep"
        ):
            label, baud, device = app._identify_device_with_defs(
                "COM8",
                0x10C4,
                {"devices": [first, second]},
                0xEA60,
            )
        self.assertEqual(label, "A")
        self.assertEqual(baud, 460800)
        self.assertEqual(device["model"], "A")
        self.assertEqual(
            [inst.kwargs.get("baudrate") for inst in FakeSerial.instances],
            [460800, 9600],
        )
        logs = _logged(app._log_cont)
        self.assertEqual(
            logs,
            [
                "Device: First A 460800 8N1 (0x10C4/0xEA60): Matched",
                "Device: Second B 9600 8N1 (0x10C4/0xEA60): No match: 'HELLO'",
            ],
        )

    def test_in_use_port_gets_header_and_summary(self):
        sim = _device_by_model("SIM7080")
        p3 = MagicMock(device="COM3", vid=0x0403, pid=0x6001)
        p8 = MagicMock(device="COM8", vid=0x10C4, pid=0xEA60)
        app = self._scan_app(
            [
                ("In Use", "COM3", "0x0403:0x6001", None, "FTDI", None),
                ("Available", "COM8", "0x10C4:0xEA60", None, "CP210x", None),
            ],
            {"devices": [sim]},
            [p3, p8],
        )
        FakeSerial.response = b""
        with patch("serial_port_app.serial.Serial", FakeSerial), patch(
            "serial_port_app.time.sleep"
        ):
            app._scan_devices_worker()
        logs = _logged(app._log_cont)
        self.assertEqual(logs[0], "Port: COM3 (0x0403/0x6001)")
        self.assertEqual(logs[1], "  skipped (In Use)")
        self.assertEqual(logs[2], "Port: COM8 (0x10C4/0xEA60)")
        self.assertTrue(logs[3].startswith("Device: SIMCom SIM7080"))
        self.assertEqual(logs[-1], DEVICE_SCAN_DONE)

    def test_no_usb_id_port_header_and_any_controller(self):
        empty = {
            "manufacturer": "Any",
            "model": "Box",
            "controllers": [],
            "serial_parameters": {
                "baud_rates": [9600],
                "parity": "N",
                "stopbits": 1,
                "bytesize": 8,
            },
            "commands": {
                "initialize": {"message": "", "pause_ms": 0},
                "identify": {"message": "I\r", "pause_ms": 0},
            },
            "response": {"regex": "HELLO", "device_column": "{model}"},
        }
        port = MagicMock(device="COM9", vid=None, pid=None)
        app = self._scan_app(
            [("Available", "COM9", "Unknown", None, "mystery", None)],
            {"devices": [empty]},
            [port],
        )
        FakeSerial.response = b"HELLO"
        with patch("serial_port_app.serial.Serial", FakeSerial), patch(
            "serial_port_app.time.sleep"
        ):
            app._scan_devices_worker()
        logs = _logged(app._log_cont)
        self.assertEqual(logs[0], "Port: COM9 (no USB ID)")
        self.assertEqual(logs[1], "Device: Any Box 9600 8N1 (any): Matched")

    def test_open_port_gets_header_and_is_not_identified(self):
        sim = _device_by_model("SIM7080")
        mb607 = _device_by_model("MB607")
        open_row = (
            "Open",
            "COM8",
            "0x10C4:0xEA60",
            "Revision 1.01",
            "CP210x",
            115200,
        )
        p8 = MagicMock(device="COM8", vid=0x10C4, pid=0xEA60)
        app = self._scan_app(
            [open_row],
            {"devices": [sim, mb607]},
            [p8],
        )
        app._held_port = "COM8"
        app._identified_device_by_port = {"COM8": mb607}
        app._identify_device_with_defs = MagicMock(
            side_effect=AssertionError("Open port must not be identified")
        )
        FakeSerial.response = b"HELLO"
        with patch("serial_port_app.serial.Serial", FakeSerial), patch(
            "serial_port_app.time.sleep"
        ):
            app._scan_devices_worker()
        logs = _logged(app._log_cont)
        self.assertEqual(logs[0], "Port: COM8 (0x10C4/0xEA60)")
        self.assertEqual(logs[1], f"  {SCAN_SKIPPED_OPEN}")
        self.assertEqual(logs[-1], DEVICE_SCAN_DONE)
        app._identify_device_with_defs.assert_not_called()
        self.assertEqual(app.port_data[0], open_row)


class OpenPortScanSkipTests(unittest.TestCase):
    """Open ports are never probed; each scan path logs Skipped, port is Open."""

    def _open_row(self):
        return (
            "Open",
            "COM8",
            "0x10C4:0xEA60",
            "Revision 1.01",
            "CP210x",
            115200,
        )

    def _open_app(self, *, comports=None):
        mb607 = _device_by_model("MB607")
        port = MagicMock(device="COM8", vid=0x10C4, pid=0xEA60)
        comports = comports if comports is not None else [port]
        by_device = {p.device: p for p in comports}
        app = _bare_app()
        app._log = MagicMock()
        app._log_cont = MagicMock()
        app.root = MagicMock()
        app.root.after.side_effect = lambda _delay, fn: fn()
        app.port_data = [self._open_row()]
        app.known_ports = {p.device for p in comports}
        app.device_definitions = {"devices": [mb607]}
        app._held_port = "COM8"
        app._identified_device_by_port = {"COM8": mb607}
        app._port_bottom_status_by_port = {}
        app._comports_by_device = MagicMock(return_value=(comports, by_device))
        app._identify_device_with_defs = MagicMock(
            side_effect=AssertionError("Open port must not be identified")
        )
        app.is_port_available = MagicMock(
            side_effect=AssertionError("Open port must not be probed")
        )
        app.update_ports_from_data = MagicMock()
        app._refresh_settings_port_list = MagicMock()
        app._refresh_identified_device_message = MagicMock()
        app._refresh_device_ui = MagicMock()
        app._finish_port_scan = MagicMock()
        app._finish_device_scan = MagicMock()
        app._finish_retest_scan = MagicMock()
        app._port_scan_lock = MagicMock()
        app._port_scan_lock.locked.return_value = False
        app._device_scan_lock = MagicMock()
        app._device_scan_lock.locked.return_value = False
        app._device_scan_after_port = False
        app._device_scan_running = False
        app.device_scan_var = _Flag(False)
        app.auto_port_scan_var = _Flag(False)
        app._devices_load_error = None
        app._serial_ports_error = None
        app._devices_info_error = None
        return app

    def test_scan_devices_worker_skips_open_and_does_not_identify(self):
        app = self._open_app()
        before = list(app.port_data)
        app._scan_devices_worker()
        app._identify_device_with_defs.assert_not_called()
        app.is_port_available.assert_not_called()
        self.assertEqual(app.port_data, before)
        logs = _logged(app._log_cont)
        self.assertEqual(logs[0], "Port: COM8 (0x10C4/0xEA60)")
        self.assertEqual(logs[1], f"  {SCAN_SKIPPED_OPEN}")

    def test_scan_ports_worker_skips_open_and_does_not_probe(self):
        app = self._open_app()
        app._port_scan_full = True
        before = list(app.port_data)
        identified = dict(app._identified_device_by_port)
        app._scan_ports_worker()
        app.is_port_available.assert_not_called()
        app._identify_device_with_defs.assert_not_called()
        self.assertEqual(app.port_data, before)
        self.assertEqual(app.port_data[0][0], "Open")
        self.assertEqual(app.port_data[0][3], "Revision 1.01")
        self.assertEqual(app._identified_device_by_port, identified)
        logs = _logged(app._log_cont)
        self.assertEqual(logs[0], "Port: COM8 (0x10C4/0xEA60)")
        self.assertEqual(logs[1], f"  {SCAN_SKIPPED_OPEN}")

    def test_retest_ports_worker_skips_open_and_does_not_identify(self):
        app = self._open_app()
        before = list(app.port_data)
        identified = dict(app._identified_device_by_port)
        app._retest_ports_worker()
        app._identify_device_with_defs.assert_not_called()
        app.is_port_available.assert_not_called()
        self.assertEqual(app.port_data, before)
        self.assertEqual(app.port_data[0][0], "Open")
        self.assertEqual(app.port_data[0][3], "Revision 1.01")
        self.assertEqual(app._identified_device_by_port, identified)
        logs = _logged(app._log_cont)
        self.assertEqual(logs[0], "Port: COM8 (0x10C4/0xEA60)")
        self.assertEqual(logs[1], f"  {SCAN_SKIPPED_OPEN}")
        self.assertFalse(any("held open" in line for line in logs))

    def test_scan_devices_identifies_available_but_not_open(self):
        app = self._open_app(
            comports=[
                MagicMock(device="COM8", vid=0x10C4, pid=0xEA60),
                MagicMock(device="COM3", vid=0x0403, pid=0x6001),
            ]
        )
        app.port_data = [
            self._open_row(),
            ("Available", "COM3", "0x0403:0x6001", None, "FTDI", None),
        ]
        app.known_ports = {"COM8", "COM3"}
        calls = []

        def identify(port, *args, **kwargs):
            calls.append(port)
            return None, None, None

        app._identify_device_with_defs = identify
        app._scan_devices_worker()
        self.assertEqual(calls, ["COM3"])
        logs = _logged(app._log_cont)
        self.assertIn(f"  {SCAN_SKIPPED_OPEN}", logs)
        self.assertEqual(app.port_data[0][0], "Open")
        self.assertEqual(app.port_data[0][3], "Revision 1.01")


def _standard_baud_labels():
    return [
        SerialPortApp.format_baud(baud) or str(baud)
        for baud in STANDARD_BAUD_RATES
    ]


class BaudDropdownTests(unittest.TestCase):
    def test_unknown_port_uses_standard_baud_labels(self):
        app = _bare_app()
        standard = _standard_baud_labels()
        self.assertEqual(app._baud_labels_for_device(None), standard)
        self.assertEqual(
            app._baud_labels_for_device(_device_by_model("SIM7080")),
            standard,
        )
        self.assertEqual(app._baud_labels_for_device(_device_by_model("MB607")), standard)
        self.assertEqual(standard[0], "300")
        self.assertNotIn("600", standard)
        self.assertIn("115,200", standard)
        self.assertIn("921,600", standard)

    def test_missing_devices_file_keeps_error_on_device_line(self):
        app = _bare_app()
        app._devices_load_error = "devices.json is missing — no known devices."
        app._device_entries = []
        app.port_message_var = MagicMock()
        app.device_message_var = MagicMock()
        app._set_message_lines(port_text="Port: None Available", device_text="Device:")
        app.device_message_var.set.assert_called_with(
            "devices.json is missing — no known devices."
        )


class DevicePickAndHandoffTests(unittest.TestCase):
    def test_picking_a_device_does_not_write_baud_settings_or_port_status(self):
        app = _bare_app()
        mb607 = _device_by_model("MB607")
        app._suppress_device_apply = False
        app._identify_fail_count = 2
        app._identify_fail_key = ("SIMCom", "SIM7080")
        app._selected_device_key = ("SIMCom", "SIM7080")
        app._identified_device_by_port = {}
        app._devices_load_error = None
        app._device_entries = [("MUX Wiring  MB607  460,800 Baud", mb607)]
        app.device_definitions = {"devices": [mb607]}
        app.serial_ports = {"serial_ports": []}
        app.devices_info = {"devices": []}
        app.port_data = [("Open", "COM3", "0x0403:0x6001", None, "FTDI", None)]
        app._port_bottom_status_by_port = {"COM3": "Opened"}
        app.settings_device_var = MagicMock()
        app.settings_device_var.get.return_value = "MUX Wiring  MB607  460,800 Baud"
        app.settings_port_var = MagicMock()
        app.settings_port_var.get.return_value = "COM3"
        app.settings_baud_var = MagicMock()
        app.settings_parity_var = MagicMock()
        app.settings_data_var = MagicMock()
        app.settings_stop_var = MagicMock()
        app.settings_flow_var = MagicMock()
        app.port_status_var = MagicMock()
        app.device_status_var = MagicMock()
        app.port_message_var = app.port_status_var
        app.device_message_var = app.device_status_var
        app._refresh_baud_dropdown = MagicMock()
        app._mark_port_status_unknown = MagicMock()
        app._refresh_settings_summary = MagicMock()

        app._apply_selected_device_preferences()

        app.settings_baud_var.set.assert_not_called()
        app.settings_parity_var.set.assert_not_called()
        app.settings_data_var.set.assert_not_called()
        app.settings_stop_var.set.assert_not_called()
        app.settings_flow_var.set.assert_not_called()
        app._mark_port_status_unknown.assert_not_called()
        app._refresh_settings_summary.assert_not_called()
        app._refresh_baud_dropdown.assert_called_with(mb607, apply_default=False)
        self.assertEqual(app._identify_fail_count, 0)
        app.device_status_var.set.assert_called_with("Nothing Identified")

    def test_identified_refresh_sets_connected_device_label(self):
        app = _bare_app()
        mb607 = _device_by_model("MB607")
        app._devices_load_error = None
        app._device_entries = [("MUX Wiring  MB607  460,800 Baud", mb607)]
        app.device_definitions = {"devices": [mb607]}
        app.serial_ports = {"serial_ports": []}
        app.devices_info, error = load_devices_info_file(str(ROOT / "devices_info.json"))
        self.assertIsNone(error)
        app.port_data = [
            (
                "Identified",
                "COM3",
                "0x10C4:0xEA60",
                "Revision 1.23 01/15/24",
                "CP210x",
                460800,
            )
        ]
        app._identified_device_by_port = {"COM3": mb607}
        app._identify_fail_count = 0
        app._identify_fail_key = ("MUX Wiring", "MB607")
        app.settings_device_var = MagicMock()
        app.settings_device_var.get.return_value = "MUX Wiring  MB607  460,800 Baud"
        app.settings_port_var = MagicMock()
        app.settings_port_var.get.return_value = "COM3"
        app.port_status_var = MagicMock()
        app.device_status_var = MagicMock()
        app.port_message_var = app.port_status_var
        app.device_message_var = app.device_status_var

        column = app._driver_or_device_column(
            "Identified",
            "Revision 1.23 01/15/24",
            "CP210x",
            "0x10C4:0xEA60",
            mb607,
        )
        app._refresh_identified_device_message()
        app.device_status_var.set.assert_called_with(column)
        self.assertEqual(
            column, "MUX Wiring MB607 Body Control Module - Revision 1.23 01/15/24"
        )
        self.assertNotEqual(column, DEVICE_STATUS_UNIDENTIFIED)
        self.assertNotEqual(column, "Revision 1.23 01/15/24")

        app.settings_device_var.get.return_value = "SIMCom  SIM7080  115,200 Baud"
        app._device_entries = [
            ("MUX Wiring  MB607  460,800 Baud", mb607),
            ("SIMCom  SIM7080  115,200 Baud", _device_by_model("SIM7080")),
        ]
        app._refresh_identified_device_message()
        app.device_status_var.set.assert_called_with(DEVICE_STATUS_UNIDENTIFIED)

    def test_manual_open_keeps_identified_device_label(self):
        app = _bare_app()
        mb607 = _device_by_model("MB607")
        app.serial_ports = {"serial_ports": []}
        app.devices_info, error = load_devices_info_file(str(ROOT / "devices_info.json"))
        self.assertIsNone(error)
        app.port_data = [
            (
                "Identified",
                "COM8",
                "0x10C4:0xEA60",
                "Revision 1.01",
                "CP210x",
                115200,
            )
        ]
        app._identified_device_by_port = {"COM8": mb607}
        app._held_port = None
        app.settings_port_var = MagicMock()
        app.settings_port_var.get.return_value = "COM8"
        app._release_serial = MagicMock()
        app._reopen_held = MagicMock(return_value=True)
        app._serial_settings_from_ui = MagicMock(
            return_value={
                "baudrate": 115200,
                "bytesize": 8,
                "parity": "N",
                "stopbits": 1,
            }
        )
        app._format_settings_summary = MagicMock(return_value="8 - N - 1 - N")
        app._log = MagicMock()
        app.update_ports_from_data = MagicMock()
        app._sync_port_selection_ui = MagicMock()
        app._store_bottom_port_status = MagicMock()
        app._devices_load_error = None
        app._device_entries = [("MUX Wiring  MB607  460,800 Baud", mb607)]
        app.settings_device_var = MagicMock()
        app.settings_device_var.get.return_value = "MUX Wiring  MB607  460,800 Baud"
        app.device_status_var = MagicMock()
        app.port_status_var = MagicMock()
        app.device_message_var = app.device_status_var
        app.port_message_var = app.port_status_var

        SerialPortApp._on_open_port(app)

        row = app._port_row("COM8")
        self.assertEqual(row[0], "Open")
        self.assertEqual(row[3], "Revision 1.01")
        self.assertEqual(row[5], 115200)
        self.assertIs(app._identified_device_by_port["COM8"], mb607)
        connected = app._driver_or_device_column(
            "Open",
            row[3],
            "CP210x",
            "0x10C4:0xEA60",
            mb607,
        )
        self.assertEqual(
            connected,
            "MUX Wiring MB607 Body Control Module - Revision 1.01",
        )
        self.assertNotEqual(connected, "Revision 1.01")
        app._refresh_identified_device_message()
        app.device_status_var.set.assert_called_with(connected)

    def test_port_status_click_identify_open_and_fail_text(self):
        app = _bare_app()
        app._devices_load_error = None
        app._device_entries = [("MUX Wiring  MB607  460,800 Baud", _device_by_model("MB607"))]
        app._port_bottom_status_by_port = {}
        app.port_status_var = MagicMock()
        app.device_status_var = MagicMock()
        app.port_message_var = app.port_status_var
        app.device_message_var = app.device_status_var

        app._store_bottom_port_status("COM8")
        app.port_status_var.set.assert_called_with("COM8")
        self.assertEqual(bottom_port_status_text("COM8", "selected"), "COM8")

        app._store_bottom_port_status(
            "COM8",
            "identified",
            baud=115200,
            data_bits=8,
            parity="N",
            stop_bits=1,
        )
        app.port_status_var.set.assert_called_with("COM8   115,200   8 - N - 1 - N")
        app._show_bottom_port_status("COM8")
        app.port_status_var.set.assert_called_with("COM8   115,200   8 - N - 1 - N")

        app._store_bottom_port_status(
            "COM8",
            "opened",
            baud=460800,
            data_bits=8,
            parity="N",
            stop_bits=1,
        )
        app.port_status_var.set.assert_called_with("COM8   460,800   8 - N - 1 - N")

        app._store_bottom_port_status("COM8", "failed")
        app.port_status_var.set.assert_called_with("COM8 - Failed to open")

        app._store_bottom_port_status("COM256", "failed")
        app.port_status_var.set.assert_called_with("COM256 - Failed to open")
        self.assertIn("COM256 - Failed to open", port_status_size_samples())

    def test_manual_device_pick_does_not_apply_port_settings(self):
        app = _bare_app()
        mb607 = _device_by_model("MB607")
        app._suppress_device_apply = False
        app._identify_fail_count = 0
        app._identify_fail_key = None
        app._selected_device_key = None
        app._identified_device_by_port = {}
        app._devices_load_error = None
        app._device_entries = [("MUX Wiring  MB607  460,800 Baud", mb607)]
        app.settings_device_var = MagicMock()
        app.settings_device_var.get.return_value = "MUX Wiring  MB607  460,800 Baud"
        app.settings_port_var = MagicMock()
        app.settings_port_var.get.return_value = "COM3"
        app.settings_baud_var = MagicMock()
        app.settings_parity_var = MagicMock()
        app.settings_data_var = MagicMock()
        app.settings_stop_var = MagicMock()
        app.settings_flow_var = MagicMock()
        app.port_status_var = MagicMock()
        app.device_status_var = MagicMock()
        app.port_message_var = app.port_status_var
        app.device_message_var = app.device_status_var
        app._refresh_baud_dropdown = MagicMock()
        app._apply_device_serial_settings = MagicMock()
        app._refresh_identified_device_message = MagicMock()

        app._apply_selected_device_preferences(mode=MODE_MANUAL)

        app._refresh_baud_dropdown.assert_called_with(mb607, apply_default=False)
        app._apply_device_serial_settings.assert_not_called()
        app.settings_baud_var.set.assert_not_called()
        app.settings_parity_var.set.assert_not_called()
        app.settings_data_var.set.assert_not_called()
        app.settings_stop_var.set.assert_not_called()
        app.settings_flow_var.set.assert_not_called()

    def test_automatic_device_pick_applies_baud_and_settings(self):
        app = _bare_app()
        mb607 = _device_by_model("MB607")
        app._suppress_device_apply = False
        app._identify_fail_count = 0
        app._identify_fail_key = None
        app._selected_device_key = None
        app._identified_device_by_port = {}
        app._devices_load_error = None
        app._device_entries = [("MUX Wiring  MB607  460,800 Baud", mb607)]
        app.settings_device_var = MagicMock()
        app.settings_device_var.get.return_value = "MUX Wiring  MB607  460,800 Baud"
        app.settings_port_var = MagicMock()
        app.settings_port_var.get.return_value = "COM3"
        app.settings_baud_var = MagicMock()
        app.settings_parity_var = MagicMock()
        app.settings_data_var = MagicMock()
        app.settings_stop_var = MagicMock()
        app.settings_flow_var = MagicMock()
        app.settings_summary_var = MagicMock()
        app.port_status_var = MagicMock()
        app.device_status_var = MagicMock()
        app.port_message_var = app.port_status_var
        app.device_message_var = app.device_status_var
        app._refresh_baud_dropdown = MagicMock()
        app._refresh_identified_device_message = MagicMock()
        app.settings_summary = None

        app._apply_selected_device_preferences(mode=MODE_AUTOMATIC)

        app._refresh_baud_dropdown.assert_called_with(mb607, apply_default=True)
        app.settings_data_var.set.assert_called_with("8")
        app.settings_stop_var.set.assert_called_with("1")
        app.settings_parity_var.set.assert_called_with("None")
        app.settings_flow_var.set.assert_called_with("None")
        app.settings_summary_var.set.assert_called()

    def test_select_payload_with_and_without_catalog_matches(self):
        app = _bare_app()
        mb607 = _device_by_model("MB607")
        app.serial_ports, uart_error = load_serial_ports_file(str(ROOT / "serial_ports.json"))
        app.devices_info, info_error = load_devices_info_file(str(ROOT / "devices_info.json"))
        self.assertIsNone(uart_error)
        self.assertIsNone(info_error)
        app.device_definitions = {"devices": [mb607]}
        app._device_entries = [("MUX Wiring  MB607  460,800 Baud", mb607)]
        app._identified_device_by_port = {"COM3": mb607}
        app._identify_fail_count = 0
        app._identify_fail_key = ("MUX Wiring", "MB607")
        app._matched_port_hardware = None
        app._matched_device_attributes = None
        app._matched_device_column = "Revision 1.0 01/01/26"
        app.port_data = [
            ("Identified", "COM3", "0x0403:0x6001", "Revision 1.0 01/01/26", "FTDI", 115200)
        ]
        app._port_bottom_status_by_port = {"COM3": "Opened"}
        app.settings_port_var = MagicMock()
        app.settings_port_var.get.return_value = "COM3"
        app.settings_device_var = MagicMock()
        app.settings_device_var.get.return_value = "MUX Wiring  MB607  460,800 Baud"
        app.settings_baud_var = MagicMock()
        app.settings_baud_var.get.return_value = "115,200"
        app.settings_summary_var = MagicMock()
        app.settings_summary_var.get.return_value = "8 - N - 1 - N"
        app.settings_data_var = MagicMock()
        app.settings_data_var.get.return_value = "8"
        app.settings_stop_var = MagicMock()
        app.settings_stop_var.get.return_value = "1"
        app.settings_parity_var = MagicMock()
        app.settings_parity_var.get.return_value = "None"
        app.settings_flow_var = MagicMock()
        app.settings_flow_var.get.return_value = "None"
        app.device_status_var = MagicMock()
        app.device_status_var.get.return_value = "Identified"

        payload = app._select_handoff_payload()
        self.assertEqual(
            set(payload),
            {
                "port",
                "baud",
                "data_bits",
                "stop_bits",
                "parity",
                "flow_control",
                "device",
            },
        )
        self.assertEqual(payload["port"], "COM3")
        self.assertEqual(payload["baud"], 115200)
        self.assertEqual(payload["data_bits"], 8)
        self.assertEqual(payload["stop_bits"], 1)
        self.assertEqual(payload["parity"], "None")
        self.assertEqual(payload["flow_control"], "None")
        self.assertEqual(
            payload["device"],
            {
                "manufacturer": "MUX Wiring",
                "model": "MB607",
                "short_description": "Body Control Module",
            },
        )
        for dropped in (
            "result",
            "settings",
            "port_status",
            "device_status",
            "port_hardware",
            "device_attributes",
        ):
            self.assertNotIn(dropped, payload)
        self.assertNotIn("type", payload["device"])
        self.assertNotIn("long_description", payload["device"])
        self.assertNotIn("device_column", payload["device"])

        app._identified_device_by_port = {}
        unidentified = app._select_handoff_payload()
        self.assertEqual(unidentified["port"], "COM3")
        self.assertIsNone(unidentified["device"])

        app.settings_port_var.get.return_value = ""
        app.port_data = []
        empty = app._select_handoff_payload()
        self.assertIsNone(empty["port"])
        self.assertIsNone(empty["device"])

    def test_exit_payload_is_null_result(self):
        self.assertEqual(exit_handoff_payload(), {"result": None})
        self.assertEqual(json.dumps(exit_handoff_payload()), '{"result": null}')

    def test_status_fields_size_from_label_reqwidth(self):
        app = _bare_app()

        def make_value():
            wrap = MagicMock()
            wrap.cget.side_effect = lambda key: 1 if key == "highlightthickness" else 0
            label = MagicMock()
            label.master = wrap
            return wrap, label

        device_wrap, device_label = make_value()
        port_wrap, port_label = make_value()
        app.device_status_entry = device_label
        app.port_status_entry = port_label
        app._bottom_bar = None
        app._status_label_reqwidth = lambda widget, samples: (
            100 if widget is device_label else 80
        )

        app._size_status_fields()

        device_w = grid_ceil_px(100 + 2, UI_PAD)
        port_w = grid_ceil_px(80 + 2, UI_PAD)
        device_wrap.configure.assert_called_with(width=device_w, height=UI_CONTROL_H)
        port_wrap.configure.assert_called_with(width=port_w, height=UI_CONTROL_H)
        self.assertGreaterEqual(device_w, 100)
        self.assertGreaterEqual(port_w, 80)
        self.assertEqual(device_w % UI_PAD, 0)

    def test_unknown_port_without_device_uses_standard_baud_dropdown(self):
        app = _bare_app()
        labels = app._baud_labels_for_device(None, uart_ic=None)
        expected = _standard_baud_labels()
        self.assertEqual(labels, expected)
        self.assertNotIn("600", labels)

    def test_known_chip_baud_list_is_used_even_when_a_device_is_selected(self):
        app = _bare_app()
        device = _device_by_model("MB607")
        chip = {"serial_parameters": {"baud_rates": [9600, 115200, 460800]}}
        self.assertEqual(
            app._baud_labels_for_device(device, uart_ic=chip),
            ["9,600", "115,200", "460,800"],
        )
        self.assertEqual(
            app._baud_labels_for_device(None, uart_ic=chip),
            ["9,600", "115,200", "460,800"],
        )
        self.assertEqual(
            app._baud_labels_for_device(device, uart_ic=None),
            _standard_baud_labels(),
        )

    def test_refresh_preselects_device_baud_when_it_is_in_the_chip_list(self):
        app = _bare_app()
        device = _device_by_model("MB607")
        combo = {}
        baud_var = MagicMock()
        app.settings_baud_combo = combo
        app.settings_baud_var = baud_var
        app.settings_port_var = MagicMock()
        app.settings_port_var.get.return_value = "COM3"
        app.port_data = [
            ("Available", "COM3", "0x0403:0x6001", None, "FTDI", None)
        ]
        app.serial_ports, error = load_serial_ports_file(str(ROOT / "serial_ports.json"))
        self.assertIsNone(error)
        app._log = MagicMock()

        app._refresh_baud_dropdown(device, apply_default=True)

        expected = _standard_baud_labels()
        self.assertEqual(combo["values"], expected)
        baud_var.set.assert_called_with("460,800")
        app._log.assert_not_called()

    def test_refresh_keeps_chip_list_and_logs_when_device_baud_is_missing(self):
        app = _bare_app()
        device = {
            "manufacturer": "Odd",
            "model": "Box",
            "serial_parameters": {"baud_rates": [50]},
        }
        combo = {}
        baud_var = MagicMock()
        app.settings_baud_combo = combo
        app.settings_baud_var = baud_var
        app.settings_port_var = MagicMock()
        app.settings_port_var.get.return_value = "COM99"
        app.port_data = [
            ("Available", "COM99", "0x1234:0x5678", None, "unknown chip", None)
        ]
        app.serial_ports, error = load_serial_ports_file(str(ROOT / "serial_ports.json"))
        self.assertIsNone(error)
        app._log = MagicMock()

        app._refresh_baud_dropdown(device, apply_default=True)

        self.assertEqual(combo["values"], _standard_baud_labels())
        baud_var.set.assert_not_called()
        app._log.assert_called()
        self.assertIn("50", app._log.call_args[0][0])
        self.assertIn("leaving Baud unchanged", app._log.call_args[0][0])

    def test_unknown_port_without_identified_device_uses_slide_settings(self):
        app = _bare_app()
        app.port_data = [
            ("Available", "COM99", "0x1234:0x5678", None, "unknown chip", None)
        ]
        app.settings_port_var = MagicMock()
        app.settings_port_var.get.return_value = "COM99"
        app._identified_device_by_port = {}
        app.serial_ports, _error = load_serial_ports_file(str(ROOT / "serial_ports.json"))
        app.devices_info = {"devices": []}
        expected = {
            "data_bits": DATA_BITS_CHOICES,
            "stop_bits": STOP_BITS_CHOICES,
            "parity": PARITY_CHOICES,
            "flow_control": FLOW_CHOICES,
        }
        self.assertEqual(app._settings_choices_for_current_port(), expected)
        # Known chip, still unidentified: catalog lists must not replace the slide.
        app.port_data = [
            ("Available", "COM3", "0x0403:0x6001", None, "FTDI", None)
        ]
        app.settings_port_var.get.return_value = "COM3"
        self.assertEqual(app._settings_choices_for_current_port(), expected)

    def test_identified_device_settings_lists_win_on_unknown_port(self):
        app = _bare_app()
        device = {
            "manufacturer": "MUX Wiring",
            "model": "MB607",
            "serial_parameters": {
                "data_bits": [8],
                "stop_bits": [1],
                "parity": ["None"],
                "flow_control": ["None", "XON/XOFF"],
            },
        }
        app.port_data = [
            ("Identified", "COM99", "0x1234:0x5678", "MB607", "unknown chip", None)
        ]
        app.settings_port_var = MagicMock()
        app.settings_port_var.get.return_value = "COM99"
        app._identified_device_by_port = {"COM99": device}
        app.serial_ports, _error = load_serial_ports_file(str(ROOT / "serial_ports.json"))
        app.devices_info = {"devices": []}
        self.assertEqual(
            app._settings_choices_for_current_port(),
            {
                "data_bits": ("8",),
                "stop_bits": ("1",),
                "parity": ("None",),
                "flow_control": ("None", "xOff/xOn"),
            },
        )


class DeviceEditorLoadTests(unittest.TestCase):
    def _editor(self, path):
        editor = DeviceEditorApp.__new__(DeviceEditorApp)
        editor.json_file = path
        return editor

    def test_load_devices_reads_repo_devices_json(self):
        devices = self._editor(str(DEVICES_JSON)).load_devices()
        self.assertEqual(devices[0]["model"], "SIM7080")
        self.assertEqual(len(devices), len(_load_definitions()["devices"]))

    def test_load_device_details_fills_port_vid_pid_from_controllers(self):
        editor = self._editor(str(DEVICES_JSON))
        editor.devices = editor.load_devices()
        editor.device_dropdown = MagicMock()
        editor.device_dropdown.current.return_value = 1  # MB607
        vid_field = MagicMock()
        editor.fields = {
            "Manufacturer": MagicMock(),
            "Model": MagicMock(),
            PORT_VID_PID_LABEL: vid_field,
        }
        editor.load_device_details()
        vid_field.insert.assert_called_with(0, "0x10C4:0xEA60, 0x067B:0x2303")

    def test_load_device_details_sets_append_response_checkbox(self):
        editor = self._editor(str(DEVICES_JSON))
        editor.devices = editor.load_devices()
        editor.device_dropdown = MagicMock()
        editor.device_dropdown.current.return_value = 1  # MB607
        editor.append_response_var = MagicMock()
        editor.fields = {
            "Manufacturer": MagicMock(),
            "Model": MagicMock(),
            PORT_VID_PID_LABEL: MagicMock(),
            "Response Regex": MagicMock(),
        }
        editor.load_device_details()
        editor.append_response_var.set.assert_called_with(True)
        editor.device_dropdown.current.return_value = 0  # SIM7080
        editor.load_device_details()
        editor.append_response_var.set.assert_called_with(False)

    def test_load_device_details_fills_reset_and_initialize_expect(self):
        editor = self._editor(str(DEVICES_JSON))
        editor.devices = editor.load_devices()
        editor.device_dropdown = MagicMock()
        editor.device_dropdown.current.return_value = 1  # MB607
        fields = {
            "Manufacturer": MagicMock(),
            "Model": MagicMock(),
            PORT_VID_PID_LABEL: MagicMock(),
            "Reset Line": MagicMock(),
            "Run State": MagicMock(),
            "Reset State": MagicMock(),
            "Pulse (ms)": MagicMock(),
            "Wait For": MagicMock(),
            "Reset Timeout (ms)": MagicMock(),
            "Initialize Command": MagicMock(),
            "Initialize Pause": MagicMock(),
            "Initialize Expect": MagicMock(),
            "Initialize Timeout": MagicMock(),
            "Identify Command": MagicMock(),
            "Identify Pause": MagicMock(),
            "Response Regex": MagicMock(),
        }
        editor.fields = fields
        editor.append_response_var = MagicMock()
        editor.load_device_details()
        fields["Reset Line"].set.assert_called_with("DTR")
        fields["Run State"].set.assert_called_with("High")
        fields["Reset State"].set.assert_called_with("Low")
        fields["Pulse (ms)"].insert.assert_called_with(0, "100")
        fields["Wait For"].insert.assert_called_with(0, MB607_WAIT_FOR)
        fields["Reset Timeout (ms)"].insert.assert_called_with(0, "3000")
        fields["Initialize Expect"].insert.assert_called_with(0, MB607_EXPECT)
        fields["Initialize Timeout"].insert.assert_called_with(0, "3000")
        editor.device_dropdown.current.return_value = 0  # SIM7080
        editor.load_device_details()
        fields["Reset Line"].set.assert_called_with("")
        fields["Initialize Expect"].insert.assert_called_with(0, "")

    def test_missing_file_or_key_returns_empty_list(self):
        self.assertEqual(
            self._editor(str(ROOT / "no_such_devices.json")).load_devices(),
            [],
        )
        handle, path = tempfile.mkstemp(suffix=".json")
        os.close(handle)
        try:
            with open(path, "w", encoding="utf-8") as out:
                json.dump({}, out)
            self.assertEqual(self._editor(path).load_devices(), [])
        finally:
            os.unlink(path)

    def test_port_vid_pid_field_round_trip(self):
        editor = self._editor(str(DEVICES_JSON))
        editor.fields = {PORT_VID_PID_LABEL: MagicMock()}
        editor.fields[PORT_VID_PID_LABEL].get.return_value = "0403:6001, 10C4"
        devices = editor.load_devices()
        editor.devices = devices
        editor.device_dropdown = MagicMock()
        editor.device_dropdown.current.return_value = 0
        editor.save_devices = MagicMock()
        editor.fields["Manufacturer"] = MagicMock()
        editor.fields["Manufacturer"].get.return_value = devices[0]["manufacturer"]
        editor.fields["Model"] = MagicMock()
        editor.fields["Model"].get.return_value = devices[0]["model"]
        for key in (
            "Baudrate",
            "Parity",
            "Stopbits",
            "Bytesize",
            "Initialize Command",
            "Initialize Pause",
            "Identify Command",
            "Identify Pause",
            "Response Regex",
        ):
            editor.fields[key] = MagicMock()
        editor.fields["Baudrate"].get.return_value = "115200"
        editor.fields["Parity"].get.return_value = "N"
        editor.fields["Stopbits"].get.return_value = "1"
        editor.fields["Bytesize"].get.return_value = "8"
        editor.fields["Initialize Command"].get.return_value = "''"
        editor.fields["Initialize Pause"].get.return_value = "1"
        editor.fields["Initialize Expect"] = MagicMock()
        editor.fields["Initialize Expect"].get.return_value = ""
        editor.fields["Initialize Timeout"] = MagicMock()
        editor.fields["Initialize Timeout"].get.return_value = ""
        editor.fields["Identify Command"].get.return_value = "''"
        editor.fields["Identify Pause"].get.return_value = "1"
        editor.fields["Reset Line"] = MagicMock()
        editor.fields["Reset Line"].get.return_value = ""
        editor.fields["Run State"] = MagicMock()
        editor.fields["Run State"].get.return_value = "High"
        editor.fields["Reset State"] = MagicMock()
        editor.fields["Reset State"].get.return_value = "Low"
        editor.fields["Pulse (ms)"] = MagicMock()
        editor.fields["Pulse (ms)"].get.return_value = ""
        editor.fields["Wait For"] = MagicMock()
        editor.fields["Wait For"].get.return_value = ""
        editor.fields["Reset Timeout (ms)"] = MagicMock()
        editor.fields["Reset Timeout (ms)"].get.return_value = ""
        editor.fields["Response Regex"].get.return_value = ""
        editor.append_response_var = MagicMock()
        editor.append_response_var.get.return_value = True
        editor.save_changes()
        self.assertTrue(devices[0]["response"]["append_response"])
        self.assertEqual(
            devices[0]["controllers"],
            parse_controllers_text("0403:6001, 10C4"),
        )
        self.assertNotIn("vendor_ids", devices[0])
        loaded = devices[0]["controllers"]
        self.assertEqual(
            loaded,
            [{"vid": "0x0403", "pid": "0x6001"}, {"vid": "0x10C4"}],
        )


def _header_app(*, in_use=False, scan_ports=False, scan_devices=False):
    app = _bare_app()
    app._suppress_auto_toggle = False
    app.show_in_use_var = _Flag(in_use)
    app.auto_port_scan_var = _Flag(scan_ports)
    app.device_scan_var = _Flag(scan_devices)
    app._log = MagicMock()
    app.update_ports_from_data = MagicMock()
    app._refresh_settings_port_list = MagicMock()
    app.start_auto_port_scan = MagicMock()
    app._cancel_auto_port_scan = MagicMock()
    app._cancel_auto_device_scan = MagicMock()
    app.scan_ports = MagicMock()
    app.retest_available_ports = MagicMock()
    app.root = MagicMock()
    app._auto_port_after_id = None
    app._auto_device_after_id = None
    app._device_scan_after_port = False
    app._port_scan_running = False
    app._device_scan_running = False
    return app


class InUseFilterAndHeaderButtonTests(unittest.TestCase):
    def test_toggle_in_use_only_refreshes_view(self):
        app = _header_app(in_use=True, scan_ports=False)
        SerialPortApp.toggle_ports_in_use(app)
        app.update_ports_from_data.assert_called_once()
        app._refresh_settings_port_list.assert_called_once()
        app.start_auto_port_scan.assert_not_called()
        app._cancel_auto_port_scan.assert_not_called()
        app.scan_ports.assert_not_called()

    def test_unchecking_in_use_does_not_stop_scan_ports_loop(self):
        app = _header_app(in_use=False, scan_ports=True)
        SerialPortApp.toggle_ports_in_use(app)
        app.start_auto_port_scan.assert_not_called()
        app._cancel_auto_port_scan.assert_not_called()

    def test_toggle_auto_port_scan_off_stops_even_if_in_use_checked(self):
        app = _header_app(in_use=True, scan_ports=False)
        SerialPortApp.toggle_auto_port_scan(app)
        app.start_auto_port_scan.assert_not_called()
        app._cancel_auto_port_scan.assert_called_once()

    def test_toggle_auto_port_scan_on_starts_loop(self):
        app = _header_app(in_use=False, scan_ports=True)
        SerialPortApp.toggle_auto_port_scan(app)
        app.start_auto_port_scan.assert_called_once()
        app._cancel_auto_port_scan.assert_not_called()

    def test_start_auto_port_scan_ignores_in_use_checkbox(self):
        app = _header_app(in_use=True, scan_ports=False)
        app._auto_port_after_id = "old"
        SerialPortApp.start_auto_port_scan(app)
        self.assertIsNone(app._auto_port_after_id)
        app.scan_ports.assert_not_called()
        app.root.after.assert_not_called()

    def test_start_auto_port_scan_runs_when_scan_ports_checked(self):
        app = _header_app(in_use=False, scan_ports=True)
        app.root.after.return_value = "after-id"
        SerialPortApp.start_auto_port_scan(app)
        app.scan_ports.assert_called_once_with(full=False)
        app.root.after.assert_called_once()
        self.assertEqual(app._auto_port_after_id, "after-id")

    def test_in_use_button_checks_in_use_and_stops_scan_ports(self):
        app = _header_app(in_use=False, scan_ports=True, scan_devices=True)
        SerialPortApp.on_in_use_button(app)
        self.assertTrue(app.show_in_use_var.get())
        self.assertFalse(app.auto_port_scan_var.get())
        self.assertFalse(app.device_scan_var.get())
        app._cancel_auto_port_scan.assert_called_once()
        app.update_ports_from_data.assert_called_once()
        app._refresh_settings_port_list.assert_called_once()
        app.scan_ports.assert_called_once_with(full=True)

    def test_scan_ports_button_leaves_in_use_and_does_one_shot_scan(self):
        app = _header_app(in_use=True, scan_ports=True, scan_devices=True)
        SerialPortApp.on_scan_ports_button(app)
        self.assertTrue(app.show_in_use_var.get())
        self.assertFalse(app.auto_port_scan_var.get())
        self.assertFalse(app.device_scan_var.get())
        app.scan_ports.assert_called_once_with(full=True)

    def test_scan_devices_button_leaves_in_use(self):
        app = _header_app(in_use=True, scan_ports=True, scan_devices=True)
        SerialPortApp.on_scan_devices_button(app)
        self.assertTrue(app.show_in_use_var.get())
        self.assertFalse(app.auto_port_scan_var.get())
        self.assertFalse(app.device_scan_var.get())
        app.retest_available_ports.assert_called_once()
        app.scan_ports.assert_not_called()


if __name__ == "__main__":
    unittest.main()
