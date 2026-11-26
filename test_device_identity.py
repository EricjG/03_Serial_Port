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
    load_uart_ics_file,
)
from device_editor import DeviceEditorApp  # noqa: E402
from device_data import STANDARD_BAUD_RATES  # noqa: E402
from picker_logic import (  # noqa: E402
    DATA_BITS_CHOICES,
    FLOW_CHOICES,
    PARITY_CHOICES,
    STOP_BITS_CHOICES,
    exit_handoff_payload,
    longest_device_status_text,
    longest_port_status_text,
    status_value_width_px,
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
    def test_mb607_regex_and_identified_label(self):
        device = _device_by_model("MB607", baudrate=460800)
        match = re.search(device["response"]["regex"], "junk RevPK1.23 01/15/24 more")
        self.assertIsNotNone(match)
        self.assertEqual(match.group("revision"), "1.23 01/15/24")
        self.assertEqual(
            format_device_column(device, match.groupdict()),
            "Revision 1.23 01/15/24",
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

    def test_available_row_uses_uart_ic_when_vid_pid_matches(self):
        app = _bare_app()
        app.uart_ics, error = load_uart_ics_file(str(ROOT / "uart_ics.json"))
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
        app.uart_ics = {"uart_ics": []}
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
            "MUX Wiring MB607 Body Control Module",
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
            result = app._identify_device_with_defs(
                port, vendor_id, definitions or _load_definitions()
            )
            return result[0], result[1]

    def test_matching_reply_returns_label_and_baud(self):
        FakeSerial.response = b"junk RevPK1.23 01/15/24 more"
        label, baud = self._identify("COM5", "4292")
        self.assertEqual(label, "Revision 1.23 01/15/24")
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

    def test_open_failure_on_first_baud_tries_next_baud_in_the_list(self):
        FakeSerial.fail_baudrates = (460800,)
        FakeSerial.response = b"RevPK1.23 01/15/24"
        label, baud = self._identify("COM5", "4292")
        self.assertEqual(label, "Revision 1.23 01/15/24")
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


class BaudDropdownTests(unittest.TestCase):
    def test_device_baud_list_is_short_labels(self):
        app = _bare_app()
        device = _device_by_model("MB607")
        self.assertEqual(app._baud_labels_for_device(device), ["460.8K", "115.2K"])
        self.assertEqual(app._baud_labels_for_device(_device_by_model("SIM7080")), ["115.2K"])
        standard = app._baud_labels_for_device(None)
        self.assertEqual(standard[0], "300")
        self.assertNotIn("600", standard)
        self.assertIn("115.2K", standard)
        self.assertIn("921.6K", standard)

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
        app._device_entries = [("MUX Wiring  MB607  460.8K Baud", mb607)]
        app.device_definitions = {"devices": [mb607]}
        app.uart_ics = {"uart_ics": []}
        app.devices_info = {"devices": []}
        app.port_data = [("Open", "COM3", "0x0403:0x6001", None, "FTDI", None)]
        app._port_bottom_status_by_port = {"COM3": "Opened"}
        app.settings_device_var = MagicMock()
        app.settings_device_var.get.return_value = "MUX Wiring  MB607  460.8K Baud"
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
        app._refresh_baud_dropdown.assert_called()
        self.assertEqual(app._identify_fail_count, 0)
        app.device_status_var.set.assert_called_with("Unidentified")

    def test_select_payload_with_and_without_catalog_matches(self):
        app = _bare_app()
        mb607 = _device_by_model("MB607")
        app.uart_ics, uart_error = load_uart_ics_file(str(ROOT / "uart_ics.json"))
        app.devices_info, info_error = load_devices_info_file(str(ROOT / "devices_info.json"))
        self.assertIsNone(uart_error)
        self.assertIsNone(info_error)
        app.device_definitions = {"devices": [mb607]}
        app._device_entries = [("MUX Wiring  MB607  460.8K Baud", mb607)]
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
        app.settings_device_var.get.return_value = "MUX Wiring  MB607  460.8K Baud"
        app.settings_baud_var = MagicMock()
        app.settings_baud_var.get.return_value = "115.2K"
        app.settings_summary_var = MagicMock()
        app.settings_summary_var.get.return_value = "8 - 1 - None - None"
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
        self.assertEqual(payload["result"], "select")
        self.assertEqual(payload["port"], "COM3")
        self.assertEqual(payload["baud"], 115200)
        self.assertEqual(payload["settings"], "8 - 1 - None - None")
        self.assertEqual(payload["data_bits"], 8)
        self.assertEqual(payload["stop_bits"], 1)
        self.assertEqual(payload["device"]["model"], "MB607")
        self.assertEqual(payload["device"]["device_column"], "Revision 1.0 01/01/26")
        self.assertEqual(payload["port_hardware"]["manufacturer"], "FTDI")
        self.assertEqual(payload["device_attributes"]["model"], "MB607")

        app.settings_port_var.get.return_value = ""
        app.port_data = []
        empty = app._select_handoff_payload()
        self.assertEqual(empty["result"], "select")
        self.assertIsNone(empty["port"])

    def test_exit_payload_is_null_result(self):
        self.assertEqual(exit_handoff_payload(), {"result": None})
        self.assertEqual(json.dumps(exit_handoff_payload()), '{"result": null}')

    def test_status_fields_fit_longest_value_on_8px_grid(self):
        app = _bare_app()
        font = MagicMock()
        font.measure.side_effect = lambda s: len(str(s)) * 8
        app._widget_font = lambda _widget: font
        app._control_font = font

        def make_value():
            wrap = MagicMock()
            wrap.cget.side_effect = lambda key: 1 if key == "highlightthickness" else 0
            label = MagicMock()
            label.master = wrap
            label.cget.side_effect = lambda key: 4 if key == "padx" else 0
            return wrap, label

        device_wrap, device_label = make_value()
        port_wrap, port_label = make_value()
        app.device_status_entry = device_label
        app.port_status_entry = port_label

        app._size_status_fields()

        font.measure.assert_any_call(longest_device_status_text())
        font.measure.assert_any_call(longest_port_status_text())
        device_w = status_value_width_px(
            len(longest_device_status_text()) * 8,
            padx=4,
            border=0,
            highlight=1,
            grid=UI_PAD,
            slack=UI_PAD,
        )
        port_w = status_value_width_px(
            len(longest_port_status_text()) * 8,
            padx=4,
            border=0,
            highlight=1,
            grid=UI_PAD,
            slack=UI_PAD,
        )
        device_wrap.configure.assert_called_with(width=device_w, height=UI_CONTROL_H)
        port_wrap.configure.assert_called_with(width=port_w, height=UI_CONTROL_H)
        self.assertEqual(device_w % UI_PAD, 0)
        self.assertGreater(device_w, port_w)
        device_label.configure.assert_not_called()

    def test_unknown_port_without_device_uses_standard_baud_dropdown(self):
        app = _bare_app()
        labels = app._baud_labels_for_device(None, uart_ic=None)
        expected = [
            SerialPortApp.format_baud(baud) or str(baud)
            for baud in STANDARD_BAUD_RATES
        ]
        self.assertEqual(labels, expected)
        self.assertNotIn("600", labels)
        chip = {"serial_parameters": {"baud_rates": [9600]}}
        self.assertEqual(app._baud_labels_for_device(None, uart_ic=chip), expected)

    def test_selected_device_baud_list_wins_on_unknown_port(self):
        app = _bare_app()
        device = _device_by_model("MB607")
        self.assertEqual(
            app._baud_labels_for_device(device, uart_ic=None),
            ["460.8K", "115.2K"],
        )

    def test_unknown_port_without_identified_device_uses_slide_settings(self):
        app = _bare_app()
        app.port_data = [
            ("Available", "COM99", "0x1234:0x5678", None, "unknown chip", None)
        ]
        app.settings_port_var = MagicMock()
        app.settings_port_var.get.return_value = "COM99"
        app._identified_device_by_port = {}
        app.uart_ics, _error = load_uart_ics_file(str(ROOT / "uart_ics.json"))
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
        app.uart_ics, _error = load_uart_ics_file(str(ROOT / "uart_ics.json"))
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
