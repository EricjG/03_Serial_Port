"""Headless tests for devices.json load / migrate / validate."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from device_data import (
    STANDARD_BAUD_RATES,
    baud_rates_for_device,
    baud_rates_for_picker,
    command_steps,
    connected_device_label,
    controllers_field_text,
    default_baud,
    device_identity_fields,
    device_matches_ids,
    format_controllers_text,
    format_device_column,
    format_usb_id,
    identified_connected_label,
    load_device_file,
    load_devices_info_file,
    load_serial_ports_file,
    match_device_info,
    match_uart_ic,
    migrate_device,
    migrate_payload,
    parse_controllers_text,
    parse_usb_id,
    parse_vid_pid,
    scan_controller_ids,
    uart_ic_label,
)

ROOT = Path(__file__).resolve().parent
DEVICES_JSON = ROOT / "devices.json"
SERIAL_PORTS_JSON = ROOT / "serial_ports.json"
DEVICES_INFO_JSON = ROOT / "devices_info.json"


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
            [
                {"vid": "0x10C4", "pid": "0xEA60"},
                {"vid": "0x067B", "pid": "0x2303"},
            ],
        )
        self.assertEqual(len(mb607["controllers"]), 2)
        self.assertEqual(mb607["type"], "Body Control Module")


class BaudAndMatchTests(unittest.TestCase):
    def test_device_baud_list_else_standard(self):
        payload, _error = _loaded()
        mb607 = next(d for d in payload["devices"] if d["model"] == "MB607")
        self.assertEqual(baud_rates_for_device(mb607), [460800, 115200])
        self.assertEqual(default_baud(mb607), 460800)
        self.assertEqual(baud_rates_for_device(None), list(STANDARD_BAUD_RATES))
        self.assertNotIn(600, STANDARD_BAUD_RATES)
        self.assertEqual(
            baud_rates_for_device({"serial_parameters": {}}),
            list(STANDARD_BAUD_RATES),
        )

    def test_unknown_port_uses_the_standard_baud_list(self):
        self.assertEqual(
            baud_rates_for_picker(device=None, uart_ic=None),
            list(STANDARD_BAUD_RATES),
        )
        self.assertNotIn(600, baud_rates_for_picker(None))
        device = {"serial_parameters": {"baud_rates": [460800, 115200]}}
        self.assertEqual(
            baud_rates_for_picker(device=device, uart_ic=None),
            list(STANDARD_BAUD_RATES),
        )

    def test_known_chip_uses_serial_ports_baud_rates(self):
        chip = {"serial_parameters": {"baud_rates": [9600, 19200]}}
        self.assertEqual(
            baud_rates_for_picker(device=None, uart_ic=chip),
            [9600, 19200],
        )
        device = {"serial_parameters": {"baud_rates": [460800, 115200]}}
        self.assertEqual(
            baud_rates_for_picker(device=device, uart_ic=chip),
            [9600, 19200],
        )

    def test_missing_chip_baud_rates_filters_standard_to_min_max(self):
        chip = {"serial_parameters": {"min_baud": 9600, "max_baud": 115200}}
        self.assertEqual(
            baud_rates_for_picker(device=None, uart_ic=chip),
            [rate for rate in STANDARD_BAUD_RATES if 9600 <= rate <= 115200],
        )

    def test_vid_pid_match_hex_and_old_decimal(self):
        payload, _error = _loaded()
        mb607 = next(d for d in payload["devices"] if d["model"] == "MB607")
        self.assertTrue(device_matches_ids(mb607, 4292))
        self.assertTrue(device_matches_ids(mb607, "0x10C4"))
        self.assertTrue(device_matches_ids(mb607, "0x10C4:0xEA60"))
        self.assertTrue(device_matches_ids(mb607, 0x10C4, 0xEA60))
        self.assertTrue(device_matches_ids(mb607, "0x067B", "0x2303"))
        self.assertTrue(device_matches_ids(mb607, 0x067B, 0x2303))
        self.assertFalse(device_matches_ids(mb607, 0x10C4, 0x0001))
        self.assertFalse(device_matches_ids(mb607, 0x067B, 0x0001))
        self.assertFalse(device_matches_ids(mb607, 1027))
        sim = next(d for d in payload["devices"] if d["model"] == "SIM7080")
        self.assertTrue(device_matches_ids(sim, "0x0403", 0x6001))
        self.assertTrue(device_matches_ids(sim, 1027))

    def test_multiple_controllers_any_listed_pair_may_match(self):
        device = {
            "controllers": [
                {"vid": "0x0403", "pid": "0x6001"},
                {"vid": "0x10C4"},
            ]
        }
        self.assertTrue(device_matches_ids(device, "0x0403", "0x6001"))
        self.assertFalse(device_matches_ids(device, "0x0403", "0x0001"))
        self.assertTrue(device_matches_ids(device, "0x10C4", "0xEA60"))
        self.assertTrue(device_matches_ids(device, 0x10C4))
        self.assertFalse(device_matches_ids(device, "0x067B", "0x2303"))

    def test_pid_is_optional_on_a_controller(self):
        vid_only = {"controllers": [{"vid": "0x0403"}]}
        self.assertTrue(device_matches_ids(vid_only, "0x0403", "0x6001"))
        self.assertTrue(device_matches_ids(vid_only, "0x0403", "0x0001"))
        self.assertTrue(device_matches_ids(vid_only, "0x0403"))
        self.assertFalse(device_matches_ids(vid_only, "0x10C4", "0xEA60"))
        with_pid = {"controllers": [{"vid": "0x0403", "pid": "0x6001"}]}
        self.assertTrue(device_matches_ids(with_pid, "0x0403", "0x6001"))
        self.assertFalse(device_matches_ids(with_pid, "0x0403", "0x0001"))
        self.assertTrue(device_matches_ids(with_pid, "0x0403"))

    def test_empty_controllers_match_every_port(self):
        for device in (
            {"controllers": []},
            {"controllers": None},
            {},
            {"controllers": [{}, {"pid": "0x0001"}, "skip"]},
        ):
            self.assertTrue(device_matches_ids(device, "0x0403", "0x6001"), msg=device)
            self.assertTrue(device_matches_ids(device, "9999"), msg=device)
            self.assertTrue(device_matches_ids(device, None), msg=device)
            self.assertTrue(device_matches_ids(device, "Unknown"), msg=device)

    def test_scan_controller_ids_prefers_the_port_match(self):
        payload, _error = _loaded()
        mb607 = next(d for d in payload["devices"] if d["model"] == "MB607")
        sim = next(d for d in payload["devices"] if d["model"] == "SIM7080")
        self.assertEqual(scan_controller_ids(mb607, 0x10C4, 0xEA60), (0x10C4, 0xEA60))
        self.assertEqual(scan_controller_ids(mb607, 0x067B, 0x2303), (0x067B, 0x2303))
        self.assertEqual(scan_controller_ids(mb607, 0x0403, 0x6001), (0x10C4, 0xEA60))
        self.assertEqual(scan_controller_ids(sim, 0x10C4, 0xEA60), (0x0403, None))
        self.assertIsNone(scan_controller_ids({"controllers": []}, 0x10C4, 0xEA60))
        self.assertEqual(
            parse_vid_pid("0x10C4/0xEA60"),
            (0x10C4, 0xEA60),
        )

    def test_explicit_empty_controllers_are_kept_and_not_dropped(self):
        migrated, error = migrate_device(
            {"controllers": [], "vendor_ids": ["4292"], "model": "NoIds"}
        )
        self.assertIsNone(error)
        self.assertEqual(migrated["model"], "NoIds")
        self.assertEqual(migrated["controllers"], [])
        migrated, error = migrate_device({"controllers": None, "model": "NullIds"})
        self.assertIsNone(error)
        self.assertEqual(migrated["controllers"], [])
        payload, error = migrate_payload(
            {"devices": [{"controllers": [], "model": "Kept"}]}
        )
        self.assertIsNone(error)
        self.assertEqual(len(payload["devices"]), 1)
        self.assertEqual(payload["devices"][0]["controllers"], [])


class ControllerEditorFieldTests(unittest.TestCase):
    def test_parse_comma_separated_hex_pid_optional(self):
        self.assertEqual(
            parse_controllers_text("0403:6001, 10C4"),
            [{"vid": "0x0403", "pid": "0x6001"}, {"vid": "0x10C4"}],
        )
        self.assertEqual(
            parse_controllers_text("0x0403:0x6001, 0x10C4"),
            [{"vid": "0x0403", "pid": "0x6001"}, {"vid": "0x10C4"}],
        )
        self.assertEqual(parse_controllers_text(""), [])
        self.assertEqual(parse_controllers_text("   "), [])
        self.assertEqual(parse_controllers_text(None), [])
        self.assertEqual(parse_controllers_text("10C4"), [{"vid": "0x10C4"}])

    def test_format_and_parse_round_trip(self):
        controllers = [{"vid": "0x0403", "pid": "0x6001"}, {"vid": "0x10C4"}]
        text = format_controllers_text(controllers)
        self.assertEqual(text, "0x0403:0x6001, 0x10C4")
        self.assertEqual(parse_controllers_text(text), controllers)
        self.assertEqual(
            parse_controllers_text(format_controllers_text(parse_controllers_text("0403:6001, 10C4"))),
            controllers,
        )
        self.assertEqual(format_controllers_text([]), "")
        self.assertEqual(format_controllers_text(None), "")
        self.assertEqual(
            controllers_field_text({"controllers": controllers}),
            "0x0403:0x6001, 0x10C4",
        )
        self.assertEqual(controllers_field_text({"controllers": []}), "")
        self.assertEqual(
            controllers_field_text({"vendor_ids": ["0x10C4"]}),
            "0x10C4",
        )


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


class SerialPortsFileTests(unittest.TestCase):
    def test_shipped_file_parses_and_has_erics_chips(self):
        with open(SERIAL_PORTS_JSON, encoding="utf-8") as handle:
            raw = json.load(handle)
        payload, error = load_serial_ports_file(str(SERIAL_PORTS_JSON))
        self.assertIsNone(error)
        self.assertEqual(len(raw["serial_ports"]), len(payload["serial_ports"]))
        models = [ic["model"] for ic in payload["serial_ports"]]
        self.assertIn("FT232R/RL/RQ", models)
        self.assertIn("PL2303HX/TA/SA/RA", models)
        self.assertIn("CP210x (CP2102/2104/2105/2108)", models)
        for ic in payload["serial_ports"]:
            self.assertTrue(str(ic["vid"]).startswith("0x"))
            self.assertIn("vid", ic)
            self.assertIn("manufacturer", ic)
            self.assertIn("model", ic)
            params = ic["serial_parameters"]
            self.assertIn("min_baud", params)
            self.assertIn("max_baud", params)
            expected = [
                rate
                for rate in STANDARD_BAUD_RATES
                if params["min_baud"] <= rate <= params["max_baud"]
            ]
            self.assertEqual(params["baud_rates"], expected)
            self.assertEqual(params["baud_rates"], sorted(params["baud_rates"]))
            self.assertEqual(
                baud_rates_for_picker(device=None, uart_ic=ic),
                expected,
            )

    def test_missing_and_invalid_files(self):
        payload, error = load_serial_ports_file(str(ROOT / "no_such_serial_ports.json"))
        self.assertEqual(payload, {"serial_ports": []})
        self.assertIn("missing", error)
        self.assertIn("no known UART ICs", error)
        handle, path = tempfile.mkstemp(suffix=".json")
        os.close(handle)
        try:
            with open(path, "w", encoding="utf-8") as out:
                out.write("{not json")
            payload, error = load_serial_ports_file(path)
            self.assertEqual(payload, {"serial_ports": []})
            self.assertIn("not valid JSON", error)
        finally:
            os.unlink(path)

    def test_old_uart_ics_root_key_still_loads(self):
        handle, path = tempfile.mkstemp(suffix=".json")
        os.close(handle)
        try:
            with open(path, "w", encoding="utf-8") as out:
                json.dump(
                    {
                        "uart_ics": [
                            {
                                "manufacturer": "FTDI",
                                "model": "Legacy",
                                "vid": "0x0403",
                                "pid": "0x6001",
                            }
                        ]
                    },
                    out,
                )
            payload, error = load_serial_ports_file(path)
            self.assertIsNone(error)
            self.assertEqual(payload["serial_ports"][0]["model"], "Legacy")
            self.assertNotIn("uart_ics", payload)
        finally:
            os.unlink(path)

    def test_vid_pid_lookup_prefers_exact_and_allows_vid_only(self):
        payload, _error = load_serial_ports_file(str(SERIAL_PORTS_JSON))
        ics = payload["serial_ports"]
        ftdi = match_uart_ic(ics, "0x0403", "0x6001")
        self.assertEqual(ftdi["manufacturer"], "FTDI")
        self.assertEqual(uart_ic_label(ftdi), "FTDI FT232R/RL/RQ")
        self.assertIsNone(match_uart_ic(ics, "0x0403", "0x9999"))
        prolific = match_uart_ic(ics, "0x067B:0x2303")
        self.assertEqual(prolific["model"], "PL2303HX/TA/SA/RA")
        cp210x = match_uart_ic(ics, 0x10C4, 0xEA60)
        self.assertIn("CP210x", cp210x["model"])
        vid_only = [
            {"manufacturer": "Any", "model": "Chip", "vid": "0x1234"},
            {"manufacturer": "Exact", "model": "Hit", "vid": "0x1234", "pid": "0x0001"},
        ]
        self.assertEqual(match_uart_ic(vid_only, "0x1234", "0x0001")["model"], "Hit")
        self.assertEqual(match_uart_ic(vid_only, "0x1234", "0x9999")["model"], "Chip")
        self.assertEqual(match_uart_ic(vid_only, "0x1234")["model"], "Chip")


class DevicesInfoFileTests(unittest.TestCase):
    def test_shipped_file_covers_every_devices_json_model(self):
        devices, error = load_device_file(str(DEVICES_JSON))
        info, info_error = load_devices_info_file(str(DEVICES_INFO_JSON))
        self.assertIsNone(error)
        self.assertIsNone(info_error)
        identify_models = [(d["manufacturer"], d["model"]) for d in devices["devices"]]
        info_models = [(d["manufacturer"], d["model"]) for d in info["devices"]]
        self.assertEqual(identify_models, info_models)
        mb607 = match_device_info(info["devices"], "MUX Wiring", "MB607")
        self.assertEqual(mb607["type"], "Body Control Module")
        self.assertEqual(mb607["hardware"]["interfaces"], ["SIP-Male"])
        self.assertIsNone(match_device_info(info["devices"], "MUX Wiring", "nope"))

    def test_missing_and_invalid_files(self):
        payload, error = load_devices_info_file(str(ROOT / "no_such_devices_info.json"))
        self.assertEqual(payload, {"devices": []})
        self.assertIn("missing", error)
        self.assertIn("no known device attributes", error)
        handle, path = tempfile.mkstemp(suffix=".json")
        os.close(handle)
        try:
            with open(path, "w", encoding="utf-8") as out:
                out.write("{not json")
            payload, error = load_devices_info_file(path)
            self.assertEqual(payload, {"devices": []})
            self.assertIn("not valid JSON", error)
        finally:
            os.unlink(path)

    def test_identity_fields_prefer_info_then_devices_json(self):
        info = {
            "manufacturer": "MUX Wiring",
            "model": "MB607",
            "type": "Body Control Module",
            "short_description": "Body Control Module",
            "long_description": "BCM with 7-Inputs 6-Outputs & CAN bus",
        }
        device = {
            "manufacturer": "MUX Wiring",
            "model": "MB607",
            "type": "Body Control Module",
            "short_description": "Body Control Module",
            "long_description": "from devices.json",
        }
        fields = device_identity_fields(info, device, "Revision 1.0 01/01/26")
        self.assertEqual(
            fields,
            {
                "manufacturer": "MUX Wiring",
                "model": "MB607",
                "short_description": "Body Control Module",
            },
        )
        self.assertIsNone(device_identity_fields(None, None))
        self.assertEqual(
            identified_connected_label(info, device, "Revision 1.0 01/01/26"),
            "MUX Wiring MB607 Body Control Module",
        )
        self.assertEqual(
            identified_connected_label(None, None, "Revision 1.0 01/01/26"),
            "Revision 1.0 01/01/26",
        )


if __name__ == "__main__":
    unittest.main()
