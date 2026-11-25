"""Headless tests for devices.json load / migrate / validate."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from device_data import (
    STANDARD_BAUD_RATES,
    baud_rates_for_device,
    command_steps,
    connected_device_label,
    default_baud,
    device_matches_ids,
    format_device_column,
    format_usb_id,
    load_device_file,
    migrate_device,
    migrate_payload,
    parse_usb_id,
    parse_vid_pid,
)

ROOT = Path(__file__).resolve().parent
DEVICES_JSON = ROOT / "devices.json"


def _raw_file():
    with open(DEVICES_JSON, encoding="utf-8") as handle:
        return json.load(handle)


def _loaded():
    payload, error = load_device_file(str(DEVICES_JSON))
    return payload, error


class UsbIdTests(unittest.TestCase):
    def test_hex_decimal_and_combined_forms(self):
        self.assertEqual(parse_usb_id("0x10C4"), 0x10C4)
        self.assertEqual(parse_usb_id(4292), 0x10C4)
        self.assertEqual(parse_usb_id("4292"), 0x10C4)
        self.assertEqual(parse_usb_id("0x10C4:0xEA60"), 0x10C4)
        self.assertEqual(parse_vid_pid("0x10C4:0xEA60"), (0x10C4, 0xEA60))
        self.assertEqual(format_usb_id(4292), "0x10C4")
        self.assertEqual(format_usb_id("1027"), "0x0403")
        self.assertIsNone(parse_usb_id(None))
        self.assertIsNone(parse_usb_id("Unknown"))


class MigrateOldSchemaTests(unittest.TestCase):
    def test_pause_seconds_become_pause_ms(self):
        migrated, error = migrate_device(
            {
                "manufacturer": "Old",
                "model": "Box",
                "vendor_ids": ["4292"],
                "serial_parameters": {"baudrate": 115200, "parity": "N", "stopbits": 1, "bytesize": 8},
                "commands": {
                    "initialize": {"message": "A", "pause": 1},
                    "identify": {"message": "B", "pause": 2},
                },
                "response": {"regex": "X", "device_column": "{model}"},
            }
        )
        self.assertIsNone(error)
        self.assertEqual(migrated["commands"]["initialize"]["pause_ms"], 1000)
        self.assertEqual(migrated["commands"]["identify"]["pause_ms"], 2000)
        self.assertNotIn("pause", migrated["commands"]["initialize"])

    def test_pause_ms_is_kept_and_old_pause_is_ignored(self):
        migrated, error = migrate_device(
            {
                "commands": {
                    "initialize": {"message": "A", "pause": 1, "pause_ms": 250},
                    "identify": {"message": "B", "pause_ms": 10},
                }
            }
        )
        self.assertIsNone(error)
        self.assertEqual(migrated["commands"]["initialize"]["pause_ms"], 250)
        self.assertEqual(migrated["commands"]["identify"]["pause_ms"], 10)

    def test_single_baudrate_becomes_a_list(self):
        migrated, error = migrate_device(
            {"serial_parameters": {"baudrate": 9600, "parity": "Even", "bytesize": 7, "stopbits": 2}}
        )
        self.assertIsNone(error)
        self.assertEqual(migrated["serial_parameters"]["baud_rates"], [9600])
        self.assertEqual(migrated["serial_parameters"]["parity"], "E")
        self.assertEqual(migrated["serial_parameters"]["bytesize"], 7)
        self.assertEqual(migrated["serial_parameters"]["stopbits"], 2)

    def test_decimal_vendor_ids_become_hex_controllers(self):
        migrated, error = migrate_device({"vendor_ids": ["4292", 1027]})
        self.assertIsNone(error)
        self.assertEqual(
            migrated["controllers"],
            [{"vid": "0x10C4"}, {"vid": "0x0403"}],
        )

    def test_type_is_free_text_not_an_enum(self):
        for value in ("RS232", "USB-Serial", "GPIB", "Ethernet", "something Eric typed"):
            migrated, error = migrate_device({"type": value, "model": "X"})
            self.assertIsNone(error, msg=value)
            self.assertEqual(migrated["type"], value)

    def test_missing_type_becomes_empty_string(self):
        migrated, error = migrate_device({"model": "X"})
        self.assertIsNone(error)
        self.assertEqual(migrated["type"], "")

    def test_invalid_regex_is_skipped(self):
        migrated, error = migrate_device({"response": {"regex": "("}})
        self.assertIsNone(migrated)
        self.assertIn("regex", error)

    def test_migrate_is_idempotent(self):
        first, error = migrate_device(_raw_file()["devices"][1])
        self.assertIsNone(error)
        again, error = migrate_device(first)
        self.assertIsNone(error)
        self.assertEqual(first, again)


class LoadFileTests(unittest.TestCase):
    def test_repo_file_loads(self):
        payload, error = _loaded()
        self.assertIsNone(error)
        self.assertEqual(len(payload["devices"]), 4)
        models = [d["model"] for d in payload["devices"]]
        self.assertEqual(models, ["SIM7080", "MB607", "HMP4040", "S-Woom32"])
        self.assertEqual(models.count("MB607"), 1)

    def test_missing_file_is_empty_with_message(self):
        payload, error = load_device_file(str(ROOT / "no_such_devices.json"))
        self.assertEqual(payload, {"devices": []})
        self.assertIn("missing", error)
        self.assertIn("no known devices", error)

    def test_invalid_json_is_empty_with_message(self):
        handle, path = tempfile.mkstemp(suffix=".json")
        os.close(handle)
        try:
            with open(path, "w", encoding="utf-8") as out:
                out.write("{not json")
            payload, error = load_device_file(path)
            self.assertEqual(payload, {"devices": []})
            self.assertIn("not valid JSON", error)
        finally:
            os.unlink(path)

    def test_missing_devices_key_is_empty_with_message(self):
        payload, error = migrate_payload({})
        self.assertEqual(payload, {"devices": []})
        self.assertIn("no device list", error)
        payload, error = migrate_payload([])
        self.assertEqual(payload["devices"], [])
        self.assertIsNotNone(error)

    def test_bad_row_is_skipped_others_load(self):
        payload, error = migrate_payload(
            {
                "devices": [
                    {"model": "Good", "response": {"regex": "A"}},
                    {"model": "Bad", "response": {"regex": "("}},
                    {"model": "Also", "response": {"regex": "B"}},
                ]
            }
        )
        self.assertIsNone(error)
        self.assertEqual([d["model"] for d in payload["devices"]], ["Good", "Also"])


class OnDiskSchemaTests(unittest.TestCase):
    def test_file_uses_new_field_names(self):
        data = _raw_file()
        self.assertEqual(len(data["devices"]), 4)
        for device in data["devices"]:
            self.assertIn("controllers", device)
            self.assertNotIn("vendor_ids", device)
            self.assertIn("baud_rates", device["serial_parameters"])
            self.assertNotIn("baudrate", device["serial_parameters"])
            for key in ("initialize", "identify"):
                command = device["commands"][key]
                self.assertIn("pause_ms", command)
                self.assertNotIn("pause", command)
            self.assertIsInstance(device.get("type"), str)
            for controller in device["controllers"]:
                self.assertTrue(str(controller["vid"]).startswith("0x"))
                if "pid" in controller:
                    self.assertTrue(str(controller["pid"]).startswith("0x"))

    def test_mb607_is_one_row_with_both_bauds_and_hex_ids(self):
        mb607 = next(d for d in _raw_file()["devices"] if d["model"] == "MB607")
        self.assertEqual(mb607["serial_parameters"]["baud_rates"], [460800, 115200])
        self.assertEqual(
            mb607["controllers"],
            [{"vid": "0x10C4", "pid": "0xEA60"}],
        )
        self.assertEqual(mb607["type"], "Body Control Module")


class BaudAndMatchTests(unittest.TestCase):
    def test_device_baud_list_else_standard(self):
        payload, _error = _loaded()
        mb607 = next(d for d in payload["devices"] if d["model"] == "MB607")
        self.assertEqual(baud_rates_for_device(mb607), [460800, 115200])
        self.assertEqual(default_baud(mb607), 460800)
        self.assertEqual(baud_rates_for_device(None), list(STANDARD_BAUD_RATES))
        self.assertEqual(
            baud_rates_for_device({"serial_parameters": {}}),
            list(STANDARD_BAUD_RATES),
        )

    def test_vid_pid_match_hex_and_old_decimal(self):
        payload, _error = _loaded()
        mb607 = next(d for d in payload["devices"] if d["model"] == "MB607")
        self.assertTrue(device_matches_ids(mb607, 4292))
        self.assertTrue(device_matches_ids(mb607, "0x10C4"))
        self.assertTrue(device_matches_ids(mb607, "0x10C4:0xEA60"))
        self.assertTrue(device_matches_ids(mb607, 0x10C4, 0xEA60))
        self.assertFalse(device_matches_ids(mb607, 0x10C4, 0x0001))
        self.assertFalse(device_matches_ids(mb607, 1027))
        sim = next(d for d in payload["devices"] if d["model"] == "SIM7080")
        self.assertTrue(device_matches_ids(sim, "0x0403", 0x6001))
        self.assertTrue(device_matches_ids(sim, 1027))


class DeviceColumnTests(unittest.TestCase):
    def test_template_uses_regex_groups_and_device_fields(self):
        payload, _error = _loaded()
        mb607 = next(d for d in payload["devices"] if d["model"] == "MB607")
        self.assertEqual(
            format_device_column(mb607, {"revision": "1.23 01/15/24"}),
            "Revision 1.23 01/15/24",
        )
        self.assertEqual(
            connected_device_label(mb607),
            "MUX Wiring MB607 - BCM with 7-Inputs 6-Outputs & CAN bus",
        )
        sim = next(d for d in payload["devices"] if d["model"] == "SIM7080")
        self.assertEqual(
            format_device_column(sim, {"model": "SIM7080"}),
            "SIMCom SIM7080",
        )
        hmp = next(d for d in payload["devices"] if d["model"] == "HMP4040")
        self.assertEqual(
            format_device_column(
                hmp, {"serial": "12345", "firmware": "2.0", "manufacturer": "Rohde & Schwarz", "model": "HMP4040"}
            ),
            "Rohde & Schwarz HMP4040 (S/N: 12345, FW: 2.0)",
        )

    def test_empty_template_falls_back_to_name(self):
        device = {"manufacturer": "ESO", "model": "S-Woom32", "response": {"device_column": ""}}
        self.assertEqual(format_device_column(device), "ESO S-Woom32")

    def test_command_steps_skip_empty_and_use_ms(self):
        payload, _error = _loaded()
        sim = next(d for d in payload["devices"] if d["model"] == "SIM7080")
        self.assertEqual(
            command_steps(sim),
            [("AT\r", 1.0), ("AT+GMM\r", 2.0)],
        )
        hmp = next(d for d in payload["devices"] if d["model"] == "HMP4040")
        self.assertEqual(command_steps(hmp), [("*idn?\r", 1.0)])


if __name__ == "__main__":
    unittest.main()
