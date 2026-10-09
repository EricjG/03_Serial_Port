"""Headless tests for picker rules (no window, no serial port)."""

import unittest

from picker_logic import (
    DEFAULT_PARITY,
    apply_header_button_click,
    device_message_text,
    dropdown_ports,
    format_settings_text,
    format_vid_pid,
    natural_port_sort_key,
    open_button_text,
    picker_control_state,
    port_event_message,
    port_status_text,
    unique_device_labels,
    unique_labeled_items,
    visible_tree_rows,
)


class UniqueDeviceLabelTests(unittest.TestCase):
    def test_first_copy_stays_plain_later_copies_get_hash_suffix(self):
        self.assertEqual(
            unique_device_labels(
                [
                    "MB607 Module",
                    "MB607 Module",
                    "SIMCom SIM7080",
                    "MB607 Module",
                ]
            ),
            [
                "MB607 Module",
                "MB607 Module (2)",
                "SIMCom SIM7080",
                "MB607 Module (3)",
            ],
        )

    def test_unique_names_are_unchanged(self):
        self.assertEqual(
            unique_device_labels(["A", "B"]),
            ["A", "B"],
        )

    def test_labeled_items_keep_the_matching_payload(self):
        items = [
            {"name": "MB607 Module", "baud": 460800},
            {"name": "MB607 Module", "baud": 115200},
        ]
        labeled = unique_labeled_items(items, lambda item: item["name"])
        self.assertEqual(labeled[0][0], "MB607 Module")
        self.assertEqual(labeled[0][1]["baud"], 460800)
        self.assertEqual(labeled[1][0], "MB607 Module (2)")
        self.assertEqual(labeled[1][1]["baud"], 115200)


class HexVidPidTests(unittest.TestCase):
    def test_vid_pid_are_uppercase_hex_with_0x(self):
        self.assertEqual(format_vid_pid(0x10C4, 0xEA60), "0x10C4:0xEA60")
        self.assertEqual(format_vid_pid(4292, 60000), "0x10C4:0xEA60")
        self.assertEqual(format_vid_pid("4292", "60000"), "0x10C4:0xEA60")
        self.assertEqual(format_vid_pid("0x10C4", "0xEA60"), "0x10C4:0xEA60")

    def test_missing_ids_are_unknown_or_vid_only(self):
        self.assertEqual(format_vid_pid(None, None), "Unknown")
        self.assertEqual(format_vid_pid("Unknown", None), "Unknown")
        self.assertEqual(format_vid_pid(4292, None), "0x10C4")


class SettingsTextTests(unittest.TestCase):
    def test_order_is_data_stop_parity_flow(self):
        self.assertEqual(
            format_settings_text("8", "1", "None", "None"),
            "8 - 1 - None - None",
        )
        self.assertEqual(
            format_settings_text("7", "2", "Even", "XON/XOFF"),
            "7 - 2 - Even - XON/XOFF",
        )

    def test_default_parity_is_none(self):
        self.assertEqual(DEFAULT_PARITY, "None")
        self.assertEqual(
            format_settings_text("8", "1", DEFAULT_PARITY, "None"),
            "8 - 1 - None - None",
        )


class NaturalPortSortTests(unittest.TestCase):
    def test_com2_before_com10(self):
        ports = ["COM10", "COM2", "COM1", "COM20"]
        self.assertEqual(
            sorted(ports, key=natural_port_sort_key),
            ["COM1", "COM2", "COM10", "COM20"],
        )

    def test_linux_tty_names_sort_naturally(self):
        ports = ["/dev/ttyUSB10", "/dev/ttyUSB2"]
        self.assertEqual(
            sorted(ports, key=natural_port_sort_key),
            ["/dev/ttyUSB2", "/dev/ttyUSB10"],
        )


class StatusAndMessageTests(unittest.TestCase):
    def test_none_available_when_list_is_empty(self):
        self.assertEqual(port_status_text(False), "None Available")
        self.assertEqual(port_status_text(True, "Available"), "Available")
        self.assertEqual(port_status_text(True, "In Use"), "In Use")
        self.assertEqual(port_status_text(True, "Open"), "Open")
        self.assertEqual(port_status_text(True, "Identified"), "Identified")

    def test_port_and_device_message_lines(self):
        self.assertEqual(port_event_message("COM4", "Closed"), "Port: COM4 is Closed")
        self.assertEqual(port_event_message("COM4", "Open"), "Port: COM4 is Open")
        self.assertEqual(port_event_message(None, "Closed"), "Port: None Available")
        self.assertEqual(
            device_message_text(
                {
                    "manufacturer": "MUX Wiring",
                    "model": "MB607",
                    "short_description": "Body Control Module",
                }
            ),
            "Device: MUX Wiring MB607 Body Control Module",
        )
        self.assertEqual(
            device_message_text({"manufacturer": "SIMCom", "model": "SIM7080"}),
            "Device: SIMCom SIM7080",
        )
        self.assertEqual(device_message_text(None), "Device:")


class OpenButtonAndControlStateTests(unittest.TestCase):
    def test_open_button_labels(self):
        self.assertEqual(open_button_text("COM4", "available"), "Open: COM4")
        self.assertEqual(open_button_text("COM4", "held"), "Close: COM4")
        self.assertEqual(open_button_text("COM5", "in_use"), "In-Use: COM5")
        self.assertEqual(open_button_text(None, "empty"), "Open:")

    def test_empty_list_disables_connection_controls(self):
        state = picker_control_state(has_ports=False)
        self.assertFalse(state["port"])
        self.assertFalse(state["baud"])
        self.assertFalse(state["settings"])
        self.assertFalse(state["open"])
        self.assertFalse(state["device"])
        self.assertFalse(state["identify"])
        self.assertFalse(state["select"])
        self.assertEqual(state["open_label"], "Open:")
        self.assertEqual(state["status"], "None Available")

    def test_open_port_locks_settings_and_enables_identify(self):
        state = picker_control_state(
            has_ports=True,
            selected_port="COM4",
            port_status="Open",
            held=True,
        )
        self.assertFalse(state["port"])
        self.assertFalse(state["baud"])
        self.assertFalse(state["settings"])
        self.assertTrue(state["open"])
        self.assertEqual(state["open_label"], "Close: COM4")
        self.assertTrue(state["device"])
        self.assertTrue(state["identify"])
        self.assertTrue(state["select"])

    def test_in_use_port_grays_open_and_blocks_identify(self):
        state = picker_control_state(
            has_ports=True,
            selected_port="COM5",
            port_status="In Use",
            held=False,
        )
        self.assertTrue(state["port"])
        self.assertFalse(state["open"])
        self.assertEqual(state["open_label"], "In-Use: COM5")
        self.assertFalse(state["identify"])
        self.assertTrue(state["select"])

    def test_available_port_can_open_but_not_identify(self):
        state = picker_control_state(
            has_ports=True,
            selected_port="COM4",
            port_status="Available",
            held=False,
        )
        self.assertTrue(state["port"])
        self.assertTrue(state["baud"])
        self.assertTrue(state["settings"])
        self.assertTrue(state["open"])
        self.assertEqual(state["open_label"], "Open: COM4")
        self.assertTrue(state["device"])
        self.assertFalse(state["identify"])
        self.assertTrue(state["select"])


class AutoRepeatAndPortListTests(unittest.TestCase):
    def test_header_button_click_clears_all_auto_repeat(self):
        self.assertEqual(apply_header_button_click(True, True, True), (False, False, False))
        self.assertEqual(apply_header_button_click(False, True, False), (False, False, False))
        self.assertEqual(apply_header_button_click(True, False, True), (False, False, False))

    def test_dropdown_hides_in_use_unless_requested(self):
        rows = [
            ("Available", "COM10"),
            ("In Use", "COM5"),
            ("Identified", "COM2"),
            ("Open", "COM4"),
        ]
        self.assertEqual(
            dropdown_ports(rows, include_in_use=False),
            ["COM2", "COM4", "COM10"],
        )
        self.assertEqual(
            dropdown_ports(rows, include_in_use=True),
            ["COM2", "COM4", "COM5", "COM10"],
        )
        self.assertEqual(
            dropdown_ports(rows, include_in_use=False, extra=("COM5",)),
            ["COM2", "COM4", "COM5", "COM10"],
        )

    def test_tree_rows_sort_by_status_then_natural_port(self):
        rows = [
            ("Available", "COM10", "id"),
            ("Available", "COM2", "id"),
            ("In Use", "COM5", "id"),
            ("Identified", "COM4", "id"),
        ]
        visible = visible_tree_rows(rows, include_in_use=False)
        self.assertEqual([row[1] for row in visible], ["COM4", "COM2", "COM10"])
        visible_all = visible_tree_rows(rows, include_in_use=True)
        self.assertEqual([row[1] for row in visible_all], ["COM4", "COM2", "COM10", "COM5"])


if __name__ == "__main__":
    unittest.main()
