"""Headless tests for picker rules (no window, no serial port)."""

import unittest

from device_data import STANDARD_BAUD_RATES
from picker_logic import (
    BAUD_SHORT,
    DATA_BITS_CHOICES,
    DEFAULT_PARITY,
    DEVICE_STATUS_IDENTIFIED,
    DEVICE_STATUS_UNIDENTIFIED,
    FLOW_CHOICES,
    FLOW_XOFF_XON,
    PARITY_CHOICES,
    STOP_BITS_CHOICES,
    UNKNOWN_DEVICE_MESSAGE,
    MODE_AUTOMATIC,
    MODE_MANUAL,
    apply_device_pick,
    apply_header_button_click,
    format_identify_reply_preview,
    format_serial_frame,
    identify_attempt_message,
    identify_attempt_result,
    check_button_char_width,
    device_identity_key,
    device_message_text,
    device_status_size_samples,
    device_status_text,
    dropdown_ports,
    english_ordinal,
    exit_handoff_payload,
    grid_ceil_px,
    longest_device_status_text,
    longest_port_status_text,
    status_value_width_px,
    format_baud_label,
    format_settings_text,
    format_vid_pid,
    identified_device_message,
    identify_failure_label,
    longest_settings_text,
    natural_port_sort_key,
    normalize_flow_choice,
    open_button_text,
    picker_control_state,
    picker_device_label,
    port_event_message,
    port_status_text,
    record_identify_failure,
    record_identify_success,
    select_handoff_payload,
    settings_choices_for_picker,
    STANDARD_SETTINGS_CHOICES,
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
            format_settings_text("7", "2", "Even", FLOW_XOFF_XON),
            "7 - 2 - Even - xOff/xOn",
        )
        self.assertEqual(
            format_settings_text("8", "1", "Space", "RTS/CTS"),
            "8 - 1 - Space - RTS/CTS",
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


class IdentifiedDeviceDisplayTests(unittest.TestCase):
    mb607 = {
        "manufacturer": "MUX Wiring",
        "model": "MB607",
        "short_description": "Body Control Module",
    }
    sim = {"manufacturer": "SIMCom", "model": "SIM7080"}

    def test_unknown_until_identify_confirms_the_dropdown_device(self):
        self.assertEqual(
            identified_device_message(None, self.mb607),
            UNKNOWN_DEVICE_MESSAGE,
        )
        self.assertEqual(
            identified_device_message(None, None),
            UNKNOWN_DEVICE_MESSAGE,
        )
        self.assertEqual(
            identified_device_message(self.mb607, self.mb607),
            DEVICE_STATUS_IDENTIFIED,
        )

    def test_other_dropdown_or_other_port_resets_until_that_result_matches(self):
        self.assertEqual(
            identified_device_message(self.mb607, self.sim),
            UNKNOWN_DEVICE_MESSAGE,
        )
        self.assertEqual(
            identified_device_message(self.sim, self.mb607),
            UNKNOWN_DEVICE_MESSAGE,
        )
        self.assertEqual(
            identified_device_message(self.sim, self.sim),
            DEVICE_STATUS_IDENTIFIED,
        )

    def test_device_status_is_unidentified_until_confirmed(self):
        self.assertEqual(UNKNOWN_DEVICE_MESSAGE, DEVICE_STATUS_UNIDENTIFIED)
        self.assertEqual(
            device_status_text(None, self.mb607),
            DEVICE_STATUS_UNIDENTIFIED,
        )
        self.assertEqual(
            device_status_text(self.mb607, self.mb607),
            DEVICE_STATUS_IDENTIFIED,
        )

    def test_identity_key_is_manufacturer_and_model(self):
        self.assertEqual(device_identity_key(self.mb607), ("MUX Wiring", "MB607"))
        self.assertEqual(
            device_identity_key({"manufacturer": "MUX Wiring", "model": "MB607"}),
            device_identity_key(self.mb607),
        )
        self.assertIsNone(device_identity_key({}))
        self.assertIsNone(device_identity_key(None))


class OpenButtonAndControlStateTests(unittest.TestCase):
    def test_open_button_labels(self):
        self.assertEqual(open_button_text("COM4", "available"), "Open")
        self.assertEqual(open_button_text("COM4", "held"), "Close")
        self.assertEqual(open_button_text("COM5", "in_use"), "In Use")
        self.assertEqual(open_button_text(None, "empty"), "Open")

    def test_open_button_text_never_includes_the_port(self):
        for kind in ("available", "held", "in_use", "empty"):
            text = open_button_text("/tmp/serialdemo/ttyUSB0", kind)
            self.assertNotIn("/", text)
            self.assertNotIn("ttyUSB0", text)
            self.assertIn(text, ("Open", "Close", "In Use"))

    def test_empty_list_disables_connection_controls(self):
        state = picker_control_state(has_ports=False)
        self.assertFalse(state["port"])
        self.assertFalse(state["baud"])
        self.assertFalse(state["settings"])
        self.assertFalse(state["open"])
        self.assertFalse(state["device"])
        self.assertFalse(state["identify"])
        self.assertFalse(state["select"])
        self.assertEqual(state["open_label"], "Open")
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
        self.assertEqual(state["open_label"], "Close")
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
        self.assertEqual(state["open_label"], "In Use")
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
        self.assertEqual(state["open_label"], "Open")
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


class CheckButtonWidthTests(unittest.TestCase):
    def test_linux_checkbox_needs_more_chars_than_windows(self):
        text_px, gap_px, avg = 70, 4, 7
        linux = check_button_char_width(text_px, 26, gap_px, avg, extra_pad_px=4)
        windows = check_button_char_width(text_px, 13, gap_px, avg, extra_pad_px=4)
        self.assertGreater(linux, windows)
        self.assertEqual(linux, 15)  # 26 + 4 + 70 + 4 = 104; ceil(104/7) = 15
        self.assertEqual(windows, 13)  # 13 + 4 + 70 + 4 = 91; ceil(91/7) = 13

    def test_width_covers_checkbox_gap_and_label(self):
        avg = 7
        chars = check_button_char_width(80, 26, 4, avg, extra_pad_px=4)
        self.assertGreaterEqual(chars * avg, 26 + 4 + 80)

    def test_zero_checkbox_still_fits_the_label(self):
        self.assertEqual(check_button_char_width(21, 0, 0, 7, extra_pad_px=0), 4)
        self.assertEqual(check_button_char_width(7, 0, 0, 7, extra_pad_px=0), 4)


class SlideOptionListTests(unittest.TestCase):
    def test_data_stop_parity_flow_match_slide_3(self):
        self.assertEqual(DATA_BITS_CHOICES, ("8", "7", "6", "5"))
        self.assertEqual(STOP_BITS_CHOICES, ("1", "2"))
        self.assertEqual(PARITY_CHOICES, ("None", "Odd", "Even", "Mark", "Space"))
        self.assertEqual(FLOW_CHOICES, ("None", "RTS/CTS", "xOff/xOn"))
        self.assertNotIn("1.5", STOP_BITS_CHOICES)
        self.assertNotIn("DSR/DTR", FLOW_CHOICES)
        self.assertNotIn("XON/XOFF", FLOW_CHOICES)

    def test_unknown_port_without_identified_device_uses_slide_settings_lists(self):
        expected = {
            "data_bits": DATA_BITS_CHOICES,
            "stop_bits": STOP_BITS_CHOICES,
            "parity": PARITY_CHOICES,
            "flow_control": FLOW_CHOICES,
        }
        self.assertEqual(STANDARD_SETTINGS_CHOICES, expected)
        self.assertEqual(
            settings_choices_for_picker(device=None, uart_ic=None),
            expected,
        )
        chip = {
            "serial_parameters": {
                "data_bits": [7, 8],
                "stop_bits": [1],
                "parity": ["None", "Even"],
                "flow_control": ["None", "XON/XOFF"],
            }
        }
        self.assertEqual(
            settings_choices_for_picker(device=None, uart_ic=chip),
            expected,
        )

    def test_identified_device_settings_lists_win_on_unknown_port(self):
        device = {
            "serial_parameters": {
                "data_bits": [8],
                "stop_bits": [1, 2],
                "parity": ["None", "Odd"],
                "flow_control": ["None", "XON/XOFF"],
            }
        }
        self.assertEqual(
            settings_choices_for_picker(device=device, uart_ic=None),
            {
                "data_bits": ("8",),
                "stop_bits": ("1", "2"),
                "parity": ("None", "Odd"),
                "flow_control": ("None", "xOff/xOn"),
            },
        )

    def test_typical_speeds_drop_600(self):
        values = [value for value, _label in BAUD_SHORT]
        self.assertNotIn(600, values)
        self.assertEqual(values[0], 300)
        self.assertEqual(values[1], 1200)
        self.assertEqual(format_baud_label(115200), "115.2K")
        self.assertEqual(format_baud_label(460800), "460.8K")
        self.assertEqual(format_baud_label(600), "600")
        self.assertEqual(tuple(value for value, _label in BAUD_SHORT), STANDARD_BAUD_RATES)

    def test_flow_aliases_map_to_xoff_xon(self):
        self.assertEqual(normalize_flow_choice("xOff/xOn"), "xOff/xOn")
        self.assertEqual(normalize_flow_choice("XON/XOFF"), "xOff/xOn")
        self.assertEqual(normalize_flow_choice("DSR/DTR"), "None")
        self.assertEqual(normalize_flow_choice(None), "None")

    def test_longest_settings_fits_space_and_xoff_xon(self):
        longest = longest_settings_text()
        self.assertEqual(longest, "8 - 1 - Space - xOff/xOn")
        self.assertGreaterEqual(len(longest), len("8 - 1 - Space - RTS/CTS"))

    def test_device_dropdown_uses_slide_format(self):
        mb607 = {
            "manufacturer": "MUX Wiring",
            "model": "MB607",
            "long_description": "BCM with 7-Inputs 6-Outputs & CAN bus",
        }
        self.assertEqual(
            picker_device_label(mb607, "115.2K"),
            "MUX Wiring  MB607  115.2K Baud",
        )
        self.assertEqual(
            picker_device_label(
                {"manufacturer": "SIMCom", "model": "SIM7080"},
                "115.2K",
            ),
            "SIMCom  SIM7080  115.2K Baud",
        )


class LayoutTokenTests(unittest.TestCase):
    def test_iris_grid_and_control_sizes(self):
        import sys
        from unittest.mock import MagicMock

        sys.modules.setdefault("tkinter", MagicMock())
        sys.modules.setdefault("tkinter.ttk", MagicMock())
        sys.modules.setdefault("tkinter.font", MagicMock())
        sys.modules.setdefault("serial", MagicMock())
        sys.modules.setdefault("serial.tools", MagicMock())
        sys.modules.setdefault("serial.tools.list_ports", MagicMock())
        from serial_port_app import (
            LONGEST_PORT_SAMPLE,
            PICKER_COMBOBOX_ARROWSIZE,
            PICKER_COMBOBOX_STYLE,
            UI_BTN_W,
            UI_CONTROL_H,
            UI_GAP,
            UI_GROUP_GAP,
            UI_ORANGE_BORDER,
            UI_OUTLINE,
            UI_PAD,
            UI_TITLE_H,
            UI_TREE_CELL_PAD,
            UI_TREE_COL_WIDTHS,
            UI_TREE_PORT_SAMPLE,
            UI_TREE_ROWS,
            picker_combobox_layout_element_names,
        )

        self.assertEqual(UI_PAD, 8)
        self.assertEqual(UI_GAP, 8)
        self.assertEqual(UI_GROUP_GAP, 16)
        self.assertEqual(UI_CONTROL_H, 24)
        self.assertEqual(UI_BTN_W, 96)
        self.assertEqual(UI_TITLE_H, 28)
        self.assertEqual(UI_ORANGE_BORDER, 3)
        self.assertEqual(UI_OUTLINE, "#A0A0A0")
        self.assertEqual(UI_TREE_ROWS, 6)
        self.assertEqual(UI_TREE_CELL_PAD, 2)
        self.assertEqual(
            UI_TREE_COL_WIDTHS,
            {"Status": 80, "Port #": 64, "ID/Baud": 110},
        )
        self.assertLess(UI_TREE_COL_WIDTHS["Port #"], 170)
        self.assertEqual(LONGEST_PORT_SAMPLE, "/tmp/serialdemo/ttyUSB0")
        self.assertEqual(UI_TREE_PORT_SAMPLE, "COM99")
        self.assertEqual(PICKER_COMBOBOX_STYLE["borderwidth"], 0)
        self.assertEqual(PICKER_COMBOBOX_STYLE["relief"], "flat")
        self.assertEqual(PICKER_COMBOBOX_STYLE["background"], "#FFFFFF")
        self.assertEqual(PICKER_COMBOBOX_STYLE["bordercolor"], "#FFFFFF")
        self.assertEqual(PICKER_COMBOBOX_STYLE["lightcolor"], "#FFFFFF")
        self.assertEqual(PICKER_COMBOBOX_STYLE["darkcolor"], "#FFFFFF")
        self.assertEqual(PICKER_COMBOBOX_ARROWSIZE, UI_CONTROL_H // 2)
        self.assertEqual(PICKER_COMBOBOX_STYLE["arrowsize"], PICKER_COMBOBOX_ARROWSIZE)
        names = picker_combobox_layout_element_names()
        self.assertNotIn("Combobox.downarrow", names)
        self.assertNotIn("Combobox.field", names)
        self.assertNotIn("Combobox.rightdownarrow", names)
        self.assertIn("Picker.Combobox.downarrow", names)
        self.assertIn("Picker.Combobox.field", names)
        self.assertIn("Picker.Combobox.textarea", names)
        self.assertEqual(grid_ceil_px(1, 8), 8)
        self.assertEqual(grid_ceil_px(64, 8), 64)
        self.assertEqual(grid_ceil_px(65, 8), 72)
        # Unidentified at 80px + padx 4*2 + outline 1*2 + 8px slack = 98 → 104
        self.assertEqual(
            status_value_width_px(80, padx=4, border=0, highlight=1, grid=8, slack=8),
            104,
        )
        self.assertGreater(
            status_value_width_px(80, padx=4, highlight=1, slack=8),
            80,
        )
        self.assertEqual(
            status_value_width_px(80, padx=4, highlight=1, slack=8) % 8,
            0,
        )


class IdentifyFailureOrdinalTests(unittest.TestCase):
    def test_failed_then_english_ordinals(self):
        self.assertEqual(identify_failure_label(1), "Failed")
        self.assertEqual(identify_failure_label(2), "2nd Failure")
        self.assertEqual(identify_failure_label(3), "3rd Failure")
        self.assertEqual(identify_failure_label(4), "4th Failure")
        self.assertEqual(identify_failure_label(11), "11th Failure")
        self.assertEqual(identify_failure_label(21), "21st Failure")
        self.assertEqual(identify_failure_label(22), "22nd Failure")
        self.assertEqual(identify_failure_label(23), "23rd Failure")

    def test_status_fields_size_to_longest_visible_value(self):
        self.assertEqual(longest_device_status_text(), "Unidentified")
        self.assertGreaterEqual(len(longest_device_status_text()), len("Identified"))
        self.assertGreaterEqual(len(longest_device_status_text()), len("10th Failure"))
        self.assertGreaterEqual(len(longest_device_status_text()), len("11th Failure"))
        self.assertEqual(longest_port_status_text(), "Unknown")
        for word in ("Closed", "Opened", "Failed", "Unknown"):
            self.assertLessEqual(len(word), len(longest_port_status_text()))
        samples = device_status_size_samples()
        for word in (
            "Unidentified",
            "Identified",
            "3rd Failure",
            "Unknown Device",
        ):
            self.assertIn(word, samples)

    def test_ordinal_helper_teen_and_twenty_cases(self):
        self.assertEqual(english_ordinal(1), "1st")
        self.assertEqual(english_ordinal(2), "2nd")
        self.assertEqual(english_ordinal(3), "3rd")
        self.assertEqual(english_ordinal(4), "4th")
        self.assertEqual(english_ordinal(11), "11th")
        self.assertEqual(english_ordinal(12), "12th")
        self.assertEqual(english_ordinal(13), "13th")
        self.assertEqual(english_ordinal(21), "21st")
        self.assertEqual(english_ordinal(22), "22nd")
        self.assertEqual(english_ordinal(23), "23rd")
        self.assertEqual(english_ordinal(24), "24th")

    def test_identify_success_clears_the_count(self):
        mb607 = {"manufacturer": "MUX Wiring", "model": "MB607"}
        result = record_identify_success(mb607)
        self.assertEqual(result["device_status"], DEVICE_STATUS_IDENTIFIED)
        self.assertEqual(result["fail_count"], 0)
        self.assertEqual(result["fail_key"], ("MUX Wiring", "MB607"))

    def test_identify_failures_accumulate_for_the_same_device(self):
        mb607 = {"manufacturer": "MUX Wiring", "model": "MB607"}
        first = record_identify_failure(mb607, 0, None)
        self.assertEqual(first["device_status"], "Failed")
        self.assertEqual(first["fail_count"], 1)
        second = record_identify_failure(mb607, first["fail_count"], first["fail_key"])
        self.assertEqual(second["device_status"], "2nd Failure")
        third = record_identify_failure(mb607, second["fail_count"], second["fail_key"])
        self.assertEqual(third["device_status"], "3rd Failure")
        self.assertTrue(third["port_status_unchanged"])

    def test_device_status_shows_failure_until_identified(self):
        mb607 = {"manufacturer": "MUX Wiring", "model": "MB607"}
        self.assertEqual(
            device_status_text(None, mb607, fail_count=2, fail_key=("MUX Wiring", "MB607")),
            "2nd Failure",
        )
        self.assertEqual(
            device_status_text(mb607, mb607, fail_count=2, fail_key=("MUX Wiring", "MB607")),
            DEVICE_STATUS_IDENTIFIED,
        )


class DevicePickSideEffectTests(unittest.TestCase):
    mb607 = {
        "manufacturer": "MUX Wiring",
        "model": "MB607",
        "serial_parameters": {"baud_rates": [460800, 115200]},
    }
    sim = {"manufacturer": "SIMCom", "model": "SIM7080"}

    def test_pick_does_not_change_baud_settings_or_port_status(self):
        result = apply_device_pick(
            ("SIMCom", "SIM7080"),
            self.mb607,
            baud="115.2K",
            settings="8 - 1 - None - None",
            port_status="Opened",
            identified_device=None,
            fail_count=3,
            fail_key=("SIMCom", "SIM7080"),
        )
        self.assertEqual(result["baud"], "115.2K")
        self.assertEqual(result["settings"], "8 - 1 - None - None")
        self.assertEqual(result["port_status"], "Opened")
        self.assertEqual(result["device_status"], DEVICE_STATUS_UNIDENTIFIED)
        self.assertEqual(result["fail_count"], 0)
        self.assertEqual(result["fail_key"], ("MUX Wiring", "MB607"))
        self.assertTrue(result["refresh_baud_list"])
        self.assertFalse(result["apply_baud"])
        self.assertFalse(result["apply_settings"])
        self.assertFalse(result["mark_port_unknown"])

    def test_manual_mode_does_not_apply_port_settings(self):
        result = apply_device_pick(
            ("SIMCom", "SIM7080"),
            self.mb607,
            baud="115.2K",
            settings="8 - 1 - None - None",
            port_status="Opened",
            mode=MODE_MANUAL,
        )
        self.assertFalse(result["apply_baud"])
        self.assertFalse(result["apply_settings"])
        self.assertEqual(result["baud"], "115.2K")
        self.assertEqual(result["settings"], "8 - 1 - None - None")

    def test_automatic_mode_may_apply_device_settings(self):
        result = apply_device_pick(
            ("SIMCom", "SIM7080"),
            self.mb607,
            baud="115.2K",
            settings="8 - 1 - None - None",
            port_status="Opened",
            mode=MODE_AUTOMATIC,
        )
        self.assertTrue(result["apply_baud"])
        self.assertTrue(result["apply_settings"])
        self.assertEqual(result["baud"], "115.2K")
        self.assertEqual(result["port_status"], "Opened")
        self.assertFalse(result["mark_port_unknown"])

    def test_same_device_pick_keeps_failure_count(self):
        result = apply_device_pick(
            ("MUX Wiring", "MB607"),
            self.mb607,
            baud="9600",
            settings="8 - 1 - None - None",
            port_status="Opened",
            fail_count=2,
            fail_key=("MUX Wiring", "MB607"),
        )
        self.assertEqual(result["fail_count"], 2)
        self.assertEqual(result["device_status"], "2nd Failure")
        self.assertEqual(result["port_status"], "Opened")


class IdentifyAttemptMessageTests(unittest.TestCase):
    mb607 = {"manufacturer": "MUX Wiring", "model": "MB607"}

    def test_frame_is_classic_8n1(self):
        self.assertEqual(format_serial_frame(8, "N", 1), "8N1")
        self.assertEqual(format_serial_frame(8, "None", 1), "8N1")
        self.assertEqual(format_serial_frame(7, "Even", 2), "7E2")

    def test_trying_line_names_device_port_and_settings(self):
        self.assertEqual(
            identify_attempt_message(
                self.mb607, "COM5", 115200, "8N1", matched=True
            ),
            "Trying MUX Wiring MB607 on COM5 @ 115200 8N1... matched",
        )

    def test_results_cover_skip_empty_and_mismatch(self):
        self.assertEqual(
            identify_attempt_result(skipped_vid_pid=True),
            "skipped: VID/PID doesn't match",
        )
        self.assertEqual(identify_attempt_result(matched=True), "matched")
        self.assertEqual(identify_attempt_result(reply=""), "no response")
        self.assertEqual(identify_attempt_result(reply=None), "no response")
        self.assertEqual(
            identify_attempt_result(reply="RevPK nope"),
            "reply did not match: 'RevPK nope'",
        )

    def test_mismatch_preview_is_repr_escaped_and_truncated(self):
        self.assertEqual(
            format_identify_reply_preview("ok\r\n"),
            "'ok\\r\\n'",
        )
        long_reply = "RevPK" + ("x" * 80)
        preview = format_identify_reply_preview(long_reply)
        self.assertEqual(preview, repr(long_reply[:40]))
        self.assertEqual(len(long_reply[:40]), 40)
        self.assertEqual(
            identify_attempt_message(
                self.mb607, "COM5", 460800, "8N1", reply=long_reply
            ),
            "Trying MUX Wiring MB607 on COM5 @ 460800 8N1... "
            f"reply did not match: {repr(long_reply[:40])}",
        )


class HandoffPayloadTests(unittest.TestCase):
    def test_exit_is_null_result(self):
        self.assertEqual(exit_handoff_payload(), {"result": None})
        self.assertEqual(
            __import__("json").dumps(exit_handoff_payload(), indent=2),
            '{\n  "result": null\n}',
        )

    def test_select_shape_is_open_specs_plus_device_or_null(self):
        payload = select_handoff_payload()
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
        for dropped in (
            "result",
            "settings",
            "port_status",
            "device_status",
            "port_hardware",
            "device_attributes",
        ):
            self.assertNotIn(dropped, payload)
        self.assertIsNone(payload["port"])
        self.assertIsNone(payload["device"])

    def test_select_identified_device_keeps_only_name_fields(self):
        payload = select_handoff_payload(
            port="COM3",
            baud=115200,
            data_bits=8,
            stop_bits=1,
            parity="None",
            flow_control="None",
            device={
                "manufacturer": "SIMCom",
                "model": "SIM7080",
                "type": "Cellular Module",
                "short_description": "",
                "long_description": "ignored",
                "device_column": "ignored",
            },
        )
        self.assertEqual(
            payload,
            {
                "port": "COM3",
                "baud": 115200,
                "data_bits": 8,
                "stop_bits": 1,
                "parity": "None",
                "flow_control": "None",
                "device": {
                    "manufacturer": "SIMCom",
                    "model": "SIM7080",
                    "short_description": "",
                },
            },
        )
        self.assertEqual(
            set(payload["device"]),
            {"manufacturer", "model", "short_description"},
        )


if __name__ == "__main__":
    unittest.main()
