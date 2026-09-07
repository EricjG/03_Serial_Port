"""Unit tests for identified-device table display (no serial hardware)."""

import json
import re
import sys
import unittest
from unittest.mock import MagicMock

# serial_port_app imports tkinter/pyserial at module load; this VM may lack them.
sys.modules.setdefault("tkinter", MagicMock())
sys.modules.setdefault("tkinter.ttk", MagicMock())
sys.modules.setdefault("serial", MagicMock())
sys.modules.setdefault("serial.tools", MagicMock())
sys.modules.setdefault("serial.tools.list_ports", MagicMock())

from serial_port_app import IdentifiedDevice, SerialPortApp  # noqa: E402


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
        self.assertEqual(identity.device_column, "Revision 1.23 01/15/24")
        self.assertEqual(identity.description, "MUX Wiring MB607")

    def test_sim7080_fills_model_from_regex(self):
        device = _device_by_model("SIM7080")
        match = re.search(device["response"]["regex"], "SIMCOM_SIM7080")
        identity = SerialPortApp._format_device_identity(device, match)
        self.assertEqual(identity.device_column, "SIMCom SIM7080")
        self.assertEqual(identity.description, "SIMCom SIM7080")

    def test_hmp4040_fills_serial_and_firmware(self):
        device = _device_by_model("HMP4040")
        match = re.search(
            device["response"]["regex"],
            "Rohde & Schwarz, HMP4040, 12345, 2.0",
        )
        identity = SerialPortApp._format_device_identity(device, match)
        self.assertEqual(
            identity.device_column,
            "Rohde & Schwarz HMP4040 (S/N: 12345, FW: 2.0)",
        )
        self.assertEqual(identity.description, "Rohde & Schwarz HMP4040")

    def test_empty_device_column_falls_back_to_manufacturer_model(self):
        device = {
            "manufacturer": "ESO",
            "model": "S-Woom32",
            "response": {"regex": "", "device_column": ""},
        }
        match = re.search("", "anything")
        identity = SerialPortApp._format_device_identity(device, match)
        self.assertEqual(identity.device_column, "ESO S-Woom32")
        self.assertEqual(identity.description, "ESO S-Woom32")

    def test_missing_template_key_does_not_raise(self):
        device = {
            "manufacturer": "Acme",
            "model": "X1",
            "response": {"device_column": "Rev {revision}"},
        }
        match = re.search("ok", "ok")
        identity = SerialPortApp._format_device_identity(device, match)
        self.assertEqual(identity.device_column, "Rev")
        self.assertEqual(identity.description, "Acme X1")


class RowDisplayColumnTests(unittest.TestCase):
    USB_DESC = "CP210x USB to UART Bridge Controller"

    def test_identified_with_device_scan_replaces_usb_description(self):
        identified = IdentifiedDevice(
            device_column="Revision 1.23 01/15/24",
            description="MUX Wiring MB607",
        )
        device_col, desc_col = SerialPortApp._row_display_columns(
            True, "4292", identified, self.USB_DESC
        )
        self.assertEqual(device_col, "Revision 1.23 01/15/24")
        self.assertEqual(desc_col, "MUX Wiring MB607")
        self.assertNotIn("CP210x", desc_col)
        self.assertNotIn("USB", desc_col)

    def test_unidentified_keeps_vendor_and_usb_description(self):
        device_col, desc_col = SerialPortApp._row_display_columns(
            True, "1027", None, self.USB_DESC
        )
        self.assertEqual(device_col, "1027")
        self.assertEqual(desc_col, self.USB_DESC)

    def test_device_scan_off_keeps_port_driver_text(self):
        identified = IdentifiedDevice(
            device_column="Revision 1.23 01/15/24",
            description="MUX Wiring MB607",
        )
        device_col, desc_col = SerialPortApp._row_display_columns(
            False, "4292", identified, self.USB_DESC
        )
        self.assertEqual(device_col, "4292")
        self.assertEqual(desc_col, self.USB_DESC)

    def test_legacy_model_string_still_displays(self):
        device_col, desc_col = SerialPortApp._row_display_columns(
            True, "4292", "MB607", self.USB_DESC
        )
        self.assertEqual(device_col, "MB607")
        self.assertEqual(desc_col, "MB607")


if __name__ == "__main__":
    unittest.main()
