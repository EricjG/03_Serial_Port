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

from device_editor import DeviceEditorApp  # noqa: E402
from serial_port_app import SerialPortApp  # noqa: E402


def _load_definitions():
    with open(DEVICES_JSON, encoding="utf-8") as handle:
        return json.load(handle)


def _device_by_model(model, baudrate=None):
    for device in _load_definitions()["devices"]:
        if device["model"] != model:
            continue
        if baudrate is None or device["serial_parameters"]["baudrate"] == baudrate:
            return device
    raise AssertionError(f"No devices.json entry for {model!r}")


def _devices_for_vid(vendor_id):
    return [
        device
        for device in _load_definitions()["devices"]
        if SerialPortApp._vendor_id_in_list(vendor_id, device["vendor_ids"])
    ]


def _bare_app():
    return SerialPortApp.__new__(SerialPortApp)


class FakeSerial:
    """Context-manager stand-in for pyserial.Serial."""

    fail_open = False
    fail_baudrates = ()
    response = b""
    instances = []

    def __init__(self, port, **kwargs):
        self.port = port
        self.kwargs = kwargs
        self.written = []
        if FakeSerial.fail_open or kwargs.get("baudrate") in FakeSerial.fail_baudrates:
            raise SerialException("port busy")
        self.in_waiting = len(FakeSerial.response)
        FakeSerial.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def write(self, data):
        self.written.append(data)

    def read(self, size=1):
        return FakeSerial.response


class FakeSerialTests(unittest.TestCase):
    def setUp(self):
        FakeSerial.fail_open = False
        FakeSerial.fail_baudrates = ()
        FakeSerial.response = b""
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
            "vendor_ids",
            "manufacturer",
            "model",
            "serial_parameters",
            "commands",
            "response",
        )
        for device in _load_definitions()["devices"]:
            for field in required:
                self.assertIn(field, device, msg=f"missing {field} on {device}")
            self.assertIsInstance(device["vendor_ids"], list)
            self.assertIn("baudrate", device["serial_parameters"])
            self.assertIn("initialize", device["commands"])
            self.assertIn("identify", device["commands"])
            self.assertIn("regex", device["response"])
            self.assertIn("device_column", device["response"])

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
            [(d["model"], d["serial_parameters"]["baudrate"]) for d in _devices_for_vid("4292")],
            [("MB607", 460800), ("MB607", 115200)],
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
        self.assertFalse(SerialPortApp._vendor_id_in_list("1027", ["4292"]))


class RegexAndDeviceColumnTests(unittest.TestCase):
    def test_mb607_regex_and_identified_label(self):
        device = _device_by_model("MB607", baudrate=460800)
        match = re.search(device["response"]["regex"], "junk RevPK1.23 01/15/24 more")
        self.assertIsNotNone(match)
        self.assertEqual(match.group("revision"), "1.23 01/15/24")
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
        usb = "CP210x USB to UART Bridge Controller"
        self.assertEqual(
            app._driver_or_device_column(
                "Identified",
                "MUX Wiring MB607 - BCM with 7-Inputs 6-Outputs & CAN bus",
                usb,
            ),
            "MUX Wiring MB607 - BCM with 7-Inputs 6-Outputs & CAN bus",
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


class IdBaudColumnTests(unittest.TestCase):
    def test_identified_shows_short_baud_not_vendor_id(self):
        app = _bare_app()
        self.assertEqual(app._id_baud_column("Identified", "4292", 460800), "460.8K")
        self.assertEqual(app._id_baud_column("Identified", "1027", 115200), "115.2K")
        self.assertEqual(app._id_baud_column("Identified", "1234", 9600), "9.6K")

    def test_unidentified_shows_vendor_id(self):
        app = _bare_app()
        self.assertEqual(app._id_baud_column("Available", "4292", None), "4292")
        self.assertEqual(app._id_baud_column("In Use", "1027", None), "1027")
        self.assertEqual(app._id_baud_column("Identified", "4292", None), "4292")
        self.assertEqual(app._id_baud_column("Available", "", None), "Unknown")

    def test_format_baud_known_and_unknown_values(self):
        self.assertIsNone(SerialPortApp.format_baud(None))
        self.assertEqual(SerialPortApp.format_baud(115200), "115.2K")
        self.assertEqual(SerialPortApp.format_baud(42), "42")


class IdentifyWithMockSerialTests(FakeSerialTests):
    def _identify(self, port, vendor_id, definitions=None):
        app = _bare_app()
        with patch("serial_port_app.serial.Serial", FakeSerial), patch(
            "serial_port_app.time.sleep"
        ):
            return app._identify_device_with_defs(
                port, vendor_id, definitions or _load_definitions()
            )

    def test_matching_reply_returns_label_and_baud(self):
        FakeSerial.response = b"junk RevPK1.23 01/15/24 more"
        label, baud = self._identify("COM5", "4292")
        self.assertEqual(
            label,
            "MUX Wiring MB607 - BCM with 7-Inputs 6-Outputs & CAN bus",
        )
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

    def test_empty_regex_device_is_not_identified(self):
        FakeSerial.response = b"anything"
        label, baud = self._identify("COM5", "4592")
        self.assertIsNone(label)
        self.assertIsNone(baud)

    def test_open_failure_on_first_baud_tries_next_definition(self):
        FakeSerial.fail_baudrates = (460800,)
        FakeSerial.response = b"RevPK1.23 01/15/24"
        label, baud = self._identify("COM5", "4292")
        self.assertEqual(
            label,
            "MUX Wiring MB607 - BCM with 7-Inputs 6-Outputs & CAN bus",
        )
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


class DeviceEditorLoadTests(unittest.TestCase):
    def _editor(self, path):
        editor = DeviceEditorApp.__new__(DeviceEditorApp)
        editor.json_file = path
        return editor

    def test_load_devices_reads_repo_devices_json(self):
        devices = self._editor(str(DEVICES_JSON)).load_devices()
        self.assertEqual(devices[0]["model"], "SIM7080")
        self.assertEqual(len(devices), len(_load_definitions()["devices"]))

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


if __name__ == "__main__":
    unittest.main()
