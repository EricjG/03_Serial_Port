"""Unit tests for identified-device table display (no serial hardware)."""

import json
import re
import sys
import unittest
from unittest.mock import MagicMock

# serial_port_app imports tkinter/pyserial at module load; this VM may lack them.
sys.modules.setdefault("tkinter", MagicMock())
sys.modules.setdefault("tkinter.ttk", MagicMock())
sys.modules.setdefault("tkinter.font", MagicMock())
sys.modules.setdefault("serial", MagicMock())
sys.modules.setdefault("serial.tools", MagicMock())
sys.modules.setdefault("serial.tools.list_ports", MagicMock())

from serial_port_app import SerialPortApp  # noqa: E402


def _device_by_model(model, baudrate=None):
    with open("devices.json", "r") as f:
        definitions = json.load(f)
    for device in definitions["devices"]:
        if device["model"] != model:
            continue
        if baudrate is None or device["serial_parameters"]["baudrate"] == baudrate:
            return device
    raise AssertionError(f"No devices.json entry for {model!r}")


class FormatDeviceIdentityTests(unittest.TestCase):
    def test_mb607_uses_device_column_revision(self):
        device = _device_by_model("MB607", baudrate=460800)
        match = re.search(
            device["response"]["regex"], "junk RevPK1.23 01/15/24 more"
        )
        self.assertIsNotNone(match)
        identity = SerialPortApp._format_device_identity(device, match)
        self.assertEqual(identity, "Revision 1.23 01/15/24")
        self.assertNotIn("RevPK", identity)
        self.assertNotIn("MB607", identity)

    def test_sim7080_fills_model_from_regex(self):
        device = _device_by_model("SIM7080")
        match = re.search(device["response"]["regex"], "SIMCOM_SIM7080")
        identity = SerialPortApp._format_device_identity(device, match)
        self.assertEqual(identity, "SIMCom SIM7080")

    def test_hmp4040_fills_serial_and_firmware(self):
        device = _device_by_model("HMP4040")
        match = re.search(
            device["response"]["regex"],
            "Rohde & Schwarz, HMP4040, 12345, 2.0",
        )
        identity = SerialPortApp._format_device_identity(device, match)
        self.assertEqual(
            identity,
            "Rohde & Schwarz HMP4040 (S/N: 12345, FW: 2.0)",
        )

    def test_empty_device_column_falls_back_to_manufacturer_model(self):
        device = {
            "manufacturer": "ESO",
            "model": "S-Woom32",
            "response": {"regex": "", "device_column": ""},
        }
        match = re.search("", "anything")
        identity = SerialPortApp._format_device_identity(device, match)
        self.assertEqual(identity, "ESO S-Woom32")

    def test_missing_template_key_does_not_raise(self):
        device = {
            "manufacturer": "Acme",
            "model": "X1",
            "response": {"device_column": "Rev {revision}"},
        }
        match = re.search("ok", "ok")
        identity = SerialPortApp._format_device_identity(device, match)
        self.assertEqual(identity, "Rev")


class DriverOrDeviceColumnTests(unittest.TestCase):
    USB_DESC = "CP210x USB to UART Bridge Controller"

    def test_identified_shows_formatted_identity_not_usb(self):
        app = SerialPortApp.__new__(SerialPortApp)
        connected = app._driver_or_device_column(
            "Identified", "Revision 1.23 01/15/24", self.USB_DESC
        )
        self.assertEqual(connected, "Revision 1.23 01/15/24")
        self.assertNotIn("CP210x", connected)
        self.assertNotIn("USB", connected)

    def test_available_keeps_pyserial_description(self):
        app = SerialPortApp.__new__(SerialPortApp)
        connected = app._driver_or_device_column(
            "Available", None, self.USB_DESC
        )
        self.assertEqual(connected, self.USB_DESC)

    def test_in_use_keeps_pyserial_description(self):
        app = SerialPortApp.__new__(SerialPortApp)
        connected = app._driver_or_device_column("In Use", None, self.USB_DESC)
        self.assertEqual(connected, self.USB_DESC)

    def test_identified_id_baud_is_baud_not_vendor(self):
        app = SerialPortApp.__new__(SerialPortApp)
        self.assertEqual(
            app._id_baud_column("Identified", "4292", 460800), "460.8K"
        )
        self.assertEqual(app._id_baud_column("Available", "4292", None), "4292")


class SelectedPortHelperTests(unittest.TestCase):
    def test_port_from_tree_values(self):
        self.assertEqual(
            SerialPortApp._port_from_tree_values(
                ("Available", "COM5", "4292", "CP210x")
            ),
            "COM5",
        )
        self.assertIsNone(SerialPortApp._port_from_tree_values(()))
        self.assertIsNone(SerialPortApp._port_from_tree_values(None))
        self.assertIsNone(SerialPortApp._port_from_tree_values(("Available",)))

    def test_scan_device_no_selection_is_noop(self):
        app = SerialPortApp.__new__(SerialPortApp)
        app.tree = MagicMock()
        app.tree.selection.return_value = ()
        app.settings_status_var = MagicMock()
        app.port_data = [
            ("Available", "COM5", "4292", None, "CP210x", None),
            ("Available", "COM6", "1027", None, "FTDI", None),
        ]
        app.scan_selected_port = MagicMock()

        app.on_scan_device_button()

        app.scan_selected_port.assert_not_called()
        app.settings_status_var.set.assert_called_with("Select a port")

    def test_scan_device_probes_only_selected_port(self):
        app = SerialPortApp.__new__(SerialPortApp)
        app.tree = MagicMock()
        app.tree.selection.return_value = ("item1",)
        app.tree.item.return_value = ("Available", "COM5", "4292", "CP210x")
        app.settings_status_var = MagicMock()
        app.port_data = [
            ("Available", "COM5", "4292", None, "CP210x", None),
            ("Available", "COM6", "1027", None, "FTDI", None),
        ]
        app.scan_selected_port = MagicMock()

        app.on_scan_device_button()

        app.scan_selected_port.assert_called_once_with("COM5")

    def test_scan_device_skips_in_use_selected_port(self):
        app = SerialPortApp.__new__(SerialPortApp)
        app.tree = MagicMock()
        app.tree.selection.return_value = ("item1",)
        app.tree.item.return_value = ("In Use", "COM5", "4292", "CP210x")
        app.settings_status_var = MagicMock()
        app.port_data = [
            ("In Use", "COM5", "4292", None, "CP210x", None),
        ]
        app.scan_selected_port = MagicMock()

        app.on_scan_device_button()

        app.scan_selected_port.assert_not_called()
        app.settings_status_var.set.assert_called_with("In Use")


if __name__ == "__main__":
    unittest.main()
