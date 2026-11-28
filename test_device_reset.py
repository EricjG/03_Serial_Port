"""Per-device reset sequence: schema, TTL mapping, mock-serial identify."""

import unittest
from unittest.mock import MagicMock, patch

from device_data import (
    command_steps,
    format_init_steps_text,
    format_sent_message,
    initialize_expect,
    initialize_steps,
    load_device_file,
    matched_text,
    migrate_device,
    parse_init_steps_text,
    prompt_found,
    reset_command,
    run_initialize_sequence,
    run_reset_sequence,
    set_control_line,
    ttl_level_to_pyserial,
    wait_for_prompt,
    wait_for_text,
)
from test_device_identity import (
    DEVICES_JSON,
    FakeSerial,
    FakeSerialTests,
    MB607_EXPECT,
    MB607_INIT_WRITES,
    MB607_NOISY_PROBE_REPLY,
    MB607_PROBE_REPLY,
    MB607_RESET_TIMEOUT,
    MB607_STEPS_TEXT,
    MB607_WAIT_FOR,
    _bare_app,
    _device_by_model,
)
from serial_port_app import SerialPortApp


def _log_lines(mock_log):
    return [call.args[0] for call in mock_log.call_args_list if call.args]


def _mb607():
    return _device_by_model("MB607")


class QueueSerial:
    """Serial stand-in that yields one RX chunk per read (for split-match tests)."""

    def __init__(self, chunks):
        self.chunks = [bytes(chunk) if not isinstance(chunk, bytes) else chunk for chunk in chunks]
        self.written = []
        self.in_waiting = 1 if self.chunks else 0

    def write(self, data):
        self.written.append(data)

    def read(self, size=1):
        del size
        if not self.chunks:
            self.in_waiting = 0
            return b""
        chunk = self.chunks.pop(0)
        self.in_waiting = 1 if self.chunks else 0
        return chunk


class TtlMappingTests(unittest.TestCase):
    def test_high_is_pyserial_false_low_is_true(self):
        self.assertFalse(ttl_level_to_pyserial("High"))
        self.assertFalse(ttl_level_to_pyserial("high"))
        self.assertTrue(ttl_level_to_pyserial("Low"))
        self.assertTrue(ttl_level_to_pyserial("low"))

    def test_dtr_and_rts_use_the_same_mapping(self):
        ser = FakeSerial("COM8")
        ser.events.clear()
        set_control_line(ser, "DTR", "Low")
        set_control_line(ser, "DTR", "High")
        set_control_line(ser, "RTS", "Low")
        set_control_line(ser, "RTS", "High")
        self.assertEqual(
            ser.events,
            [
                ("dtr", True, False),
                ("dtr", False, False),
                ("rts", True, False),
                ("rts", False, False),
            ],
        )
        self.assertFalse(ser.dtr)
        self.assertFalse(ser.rts)


class ResetSchemaTests(unittest.TestCase):
    def test_repo_file_loads_mb607_reset_and_others_have_none(self):
        payload, error = load_device_file(str(DEVICES_JSON))
        self.assertIsNone(error)
        by_model = {d["model"]: d for d in payload["devices"]}
        reset = reset_command(by_model["MB607"])
        self.assertEqual(reset["line"], "DTR")
        self.assertEqual(reset["run_state"], "High")
        self.assertEqual(reset["reset_state"], "Low")
        self.assertEqual(reset["pulse_ms"], 100)
        self.assertEqual(reset["wait_for"], MB607_WAIT_FOR)
        self.assertEqual(reset["timeout_ms"], 1000)
        self.assertNotIn("wait_for_regex", reset)
        expect, timeout_ms = initialize_expect(by_model["MB607"])
        self.assertEqual(expect, MB607_EXPECT)
        self.assertEqual(timeout_ms, 1000)
        self.assertEqual(
            initialize_steps(by_model["MB607"]),
            [
                {"pause_ms": 10},
                {"send": "\r"},
                {"pause_ms": 10},
                {"send": "debug\r"},
                {"pause_ms": 10},
                {"send": "\r"},
                {"pause_ms": 100},
            ],
        )
        self.assertEqual(
            format_init_steps_text(initialize_steps(by_model["MB607"])),
            MB607_STEPS_TEXT,
        )
        self.assertEqual(
            parse_init_steps_text(MB607_STEPS_TEXT),
            initialize_steps(by_model["MB607"]),
        )
        for model in ("SIM7080", "HMP4040", "S-Woom32"):
            self.assertIsNone(reset_command(by_model[model]))
            self.assertEqual(initialize_expect(by_model[model]), (None, 0))
            self.assertNotIn("reset", by_model[model]["commands"])
            self.assertNotIn("expect", by_model[model]["commands"]["initialize"])

    def test_missing_reset_stays_omitted(self):
        migrated, error = migrate_device(
            {
                "model": "X",
                "commands": {
                    "initialize": {"message": "A", "pause_ms": 10},
                    "identify": {"message": "B", "pause_ms": 10},
                },
            }
        )
        self.assertIsNone(error)
        self.assertNotIn("reset", migrated["commands"])
        self.assertNotIn("expect", migrated["commands"]["initialize"])
        self.assertEqual(command_steps(migrated), [("A", 0.01), ("B", 0.01)])

    def test_invalid_reset_is_dropped_not_the_device(self):
        migrated, error = migrate_device(
            {
                "model": "X",
                "commands": {"reset": {"line": "TX", "run_state": "High"}},
            }
        )
        self.assertIsNone(error)
        self.assertNotIn("reset", migrated["commands"])

    def test_initialize_expect_defaults_timeout_to_pause_ms(self):
        migrated, error = migrate_device(
            {
                "commands": {
                    "initialize": {
                        "message": "\r",
                        "pause_ms": 250,
                        "expect": "Ready",
                    }
                }
            }
        )
        self.assertIsNone(error)
        self.assertEqual(
            initialize_expect(migrated),
            ("Ready", 250),
        )

    def test_sent_message_logs_cr_tokens(self):
        self.assertEqual(format_sent_message("\r\r"), "CR CR")
        self.assertEqual(format_sent_message("AT\r"), "AT CR")
        self.assertEqual(format_sent_message("debug\r"), "debug CR")
        self.assertEqual(
            matched_text("xx Press CR key for command Debug Mode yy", MB607_WAIT_FOR),
            MB607_WAIT_FOR,
        )

    def test_invalid_wait_for_regex_is_dropped(self):
        migrated, error = migrate_device(
            {
                "commands": {
                    "reset": {
                        "line": "DTR",
                        "run_state": "High",
                        "reset_state": "Low",
                        "pulse_ms": 1,
                        "wait_for": "Hi",
                        "wait_for_regex": "(",
                        "timeout_ms": 10,
                    }
                }
            }
        )
        self.assertIsNone(error)
        self.assertEqual(migrated["commands"]["reset"]["wait_for"], "Hi")
        self.assertNotIn("wait_for_regex", migrated["commands"]["reset"])


class WaitForTextTests(unittest.TestCase):
    def test_empty_needle_succeeds(self):
        ser = FakeSerial("COM8")
        found, buf = wait_for_text(ser, "", 1000, sleep=lambda _s: None)
        self.assertTrue(found)
        self.assertEqual(buf, "")

    def test_timeout_counts_sleep_not_wall_clock(self):
        slept = []
        ser = FakeSerial("COM8")
        FakeSerial.response = b""
        ser.response_data = b""
        ser.in_waiting = 0
        found, buf = wait_for_text(
            ser, "never", 100, sleep=lambda s: slept.append(s)
        )
        self.assertFalse(found)
        self.assertEqual(buf, "")
        self.assertAlmostEqual(sum(slept), 0.1, places=6)

    def test_prompt_found_amid_extra_text(self):
        noisy = "boot...\r\n" + MB607_WAIT_FOR + " !! extra"
        self.assertTrue(prompt_found(noisy, MB607_WAIT_FOR, ""))
        ser = QueueSerial([noisy.encode()])
        found, buf = wait_for_prompt(
            ser, 1000, sleep=lambda _s: None, wait_for=MB607_WAIT_FOR
        )
        self.assertTrue(found)
        self.assertIn(MB607_WAIT_FOR, buf)

    def test_prompt_split_across_reads(self):
        ser = QueueSerial(
            [b"xx Press CR key for com", b"mand Debug Mode yy"]
        )
        found, buf = wait_for_prompt(
            ser, 1000, sleep=lambda _s: None, wait_for=MB607_WAIT_FOR
        )
        self.assertTrue(found)
        self.assertEqual(buf, "xx Press CR key for command Debug Mode yy")
        self.assertEqual(ser.chunks, [])

    def test_wait_for_regex_is_optional_and_case_insensitive(self):
        ser = QueueSerial([b"aa Press CR key for command Debug Mode zz"])
        found, buf = wait_for_prompt(
            ser,
            1000,
            sleep=lambda _s: None,
            wait_for_regex=r"press CR key for command Debug Mode",
        )
        self.assertTrue(found)
        self.assertIn("Press CR key for command Debug Mode", buf)


class ResetSequenceSuccessTests(FakeSerialTests):
    def test_full_mb607_sequence_success(self):
        FakeSerial.response = MB607_PROBE_REPLY.encode()
        app = _bare_app()
        app._log = MagicMock()
        mb607 = _mb607()
        with patch("serial_port_app.serial.Serial", FakeSerial), patch(
            "serial_port_app.time.sleep"
        ):
            label, baud, device = SerialPortApp._identify_device_with_defs(
                app, "COM8", "4292", {"devices": [mb607]}
            )
        self.assertEqual(label, "Revision 1.01")
        self.assertEqual(baud, 460800)
        self.assertEqual(device["model"], "MB607")
        ser = FakeSerial.instances[0]
        self.assertEqual(ser.written, MB607_INIT_WRITES)
        dtr_open = [
            event[1] for event in ser.events if event[0] == "dtr" and event[2] is True
        ]
        self.assertEqual(dtr_open, [False, True, False])
        self.assertFalse(any(event[0] == "rts" for event in ser.events))
        logs = _log_lines(app._log)
        self.assertIn("COM8 - DTR reset pulse 100 ms", logs)
        self.assertIn(f"COM8 - Received: {MB607_WAIT_FOR}", logs)
        self.assertIn("COM8 - Wait 10 ms", logs)
        self.assertIn("COM8 - Sent: CR", logs)
        self.assertIn("COM8 - Sent: debug CR", logs)
        self.assertIn("COM8 - Wait 100 ms", logs)
        self.assertNotIn("COM8 - Sent: CR CR", logs)
        self.assertIn(f"COM8 - Received: {MB607_EXPECT}", logs)

    def test_wait_for_timeout_is_identify_failure(self):
        FakeSerial.response = b""
        app = _bare_app()
        app._log = MagicMock()
        app._log_cont = MagicMock()
        mb607 = _mb607()
        with patch("serial_port_app.serial.Serial", FakeSerial), patch(
            "serial_port_app.time.sleep"
        ):
            label, baud, device = SerialPortApp._identify_device_with_defs(
                app, "COM8", "4292", {"devices": [mb607]}
            )
        self.assertIsNone(label)
        self.assertIsNone(baud)
        self.assertIsNone(device)
        logs = _log_lines(app._log)
        self.assertTrue(any("DTR reset pulse 100 ms" in line for line in logs))
        self.assertTrue(
            any("DTR reset timeout waiting for" in line for line in logs)
        )
        attempt_logs = _log_lines(app._log_cont)
        self.assertTrue(any("Error:" in line for line in attempt_logs))
        self.assertTrue(any(MB607_RESET_TIMEOUT[:20] in line for line in attempt_logs))
        self.assertEqual(FakeSerial.instances[0].written, [])

    def test_expect_timeout_is_identify_failure(self):
        FakeSerial.response = MB607_WAIT_FOR.encode()
        app = _bare_app()
        app._log = MagicMock()
        app._log_cont = MagicMock()
        mb607 = _mb607()
        with patch("serial_port_app.serial.Serial", FakeSerial), patch(
            "serial_port_app.time.sleep"
        ):
            label, baud, device = SerialPortApp._identify_device_with_defs(
                app, "COM8", "4292", {"devices": [mb607]}
            )
        self.assertIsNone(label)
        self.assertIsNone(device)
        logs = _log_lines(app._log)
        self.assertIn("COM8 - Sent: CR", logs)
        self.assertIn("COM8 - Sent: debug CR", logs)
        self.assertTrue(
            any("Timeout waiting for 'Enter Command'" in line for line in logs)
        )
        self.assertEqual(
            FakeSerial.instances[0].written, [b"\r", b"debug\r", b"\r"]
        )

    def test_device_without_reset_unchanged(self):
        FakeSerial.response = b"SIMCOM_SIM7080"
        app = _bare_app()
        app._log = MagicMock()
        sim = _device_by_model("SIM7080")
        with patch("serial_port_app.serial.Serial", FakeSerial), patch(
            "serial_port_app.time.sleep"
        ) as slept:
            label, baud, device = SerialPortApp._identify_device_with_defs(
                app, "COM3", "1027", {"devices": [sim]}
            )
        self.assertEqual(device["model"], "SIM7080")
        self.assertIsNotNone(label)
        ser = FakeSerial.instances[0]
        self.assertEqual(ser.written, [b"AT\r", b"AT+GMM\r"])
        slept.assert_any_call(1.0)
        slept.assert_any_call(2.0)
        dtr_open = [
            event[1] for event in ser.events if event[0] == "dtr" and event[2] is True
        ]
        self.assertEqual(dtr_open, [False])
        self.assertFalse(any(event[0] == "rts" for event in ser.events))
        self.assertEqual(_log_lines(app._log), [])

    def test_mb607_prompt_amid_extra_text_still_identifies(self):
        FakeSerial.response = MB607_NOISY_PROBE_REPLY.encode()
        app = _bare_app()
        app._log = MagicMock()
        with patch("serial_port_app.serial.Serial", FakeSerial), patch(
            "serial_port_app.time.sleep"
        ) as slept:
            label, baud, device = SerialPortApp._identify_device_with_defs(
                app, "COM8", "4292", {"devices": [_mb607()]}
            )
        self.assertEqual(label, "Revision 1.01")
        self.assertEqual(device["model"], "MB607")
        self.assertEqual(FakeSerial.instances[0].written, MB607_INIT_WRITES)
        self.assertEqual(
            [call.args[0] for call in slept.call_args_list[:5]],
            [0.1, 0.01, 0.01, 0.01, 0.1],
        )

    def test_initialize_steps_run_in_order_then_expect(self):
        FakeSerial.response = MB607_EXPECT.encode()
        ser = FakeSerial("COM8")
        slept = []
        logs = []
        ok, received, error = run_initialize_sequence(
            ser,
            _mb607(),
            port="COM8",
            log=logs.append,
            sleep=lambda s: slept.append(s),
        )
        self.assertTrue(ok)
        self.assertIsNone(error)
        self.assertIn(MB607_EXPECT, received)
        self.assertEqual(ser.written, [b"\r", b"debug\r", b"\r"])
        self.assertEqual(slept, [0.01, 0.01, 0.01, 0.1])
        self.assertEqual(
            logs[:7],
            [
                "COM8 - Wait 10 ms",
                "COM8 - Sent: CR",
                "COM8 - Wait 10 ms",
                "COM8 - Sent: debug CR",
                "COM8 - Wait 10 ms",
                "COM8 - Sent: CR",
                "COM8 - Wait 100 ms",
            ],
        )
        self.assertIn(f"COM8 - Received: {MB607_EXPECT}", logs)

    def test_legacy_initialize_message_and_expect_unchanged(self):
        device = {
            "commands": {
                "initialize": {
                    "message": "\r\r",
                    "pause_ms": 10,
                    "expect": "Enter command",
                    "timeout_ms": 500,
                }
            }
        }
        FakeSerial.response = b"xx Enter command yy"
        ser = FakeSerial("COM8")
        logs = []
        ok, received, error = run_initialize_sequence(
            ser, device, port="COM8", log=logs.append, sleep=lambda _s: None
        )
        self.assertTrue(ok)
        self.assertIsNone(error)
        self.assertEqual(ser.written, [b"\r\r"])
        self.assertIn("COM8 - Sent: CR CR", logs)
        self.assertIn("COM8 - Received: Enter command", logs)
        self.assertIn("Enter command", received)

    def test_legacy_initialize_without_expect_is_noop_for_helper(self):
        device = {
            "commands": {
                "initialize": {"message": "AT\r", "pause_ms": 1000},
                "identify": {"message": "AT+GMM\r", "pause_ms": 2000},
            }
        }
        ser = FakeSerial("COM8")
        ok, received, error = run_initialize_sequence(ser, device, port="COM8")
        self.assertTrue(ok)
        self.assertEqual(received, "")
        self.assertIsNone(error)
        self.assertEqual(ser.written, [])
        self.assertEqual(command_steps(device), [("AT\r", 1.0), ("AT+GMM\r", 2.0)])

    def test_rts_reset_pulses_rts_not_dtr(self):
        FakeSerial.response = b"HELLO"
        device = {
            "manufacturer": "X",
            "model": "Y",
            "controllers": [],
            "serial_parameters": {
                "baud_rates": [9600],
                "parity": "N",
                "stopbits": 1,
                "bytesize": 8,
            },
            "commands": {
                "reset": {
                    "line": "RTS",
                    "run_state": "High",
                    "reset_state": "Low",
                    "pulse_ms": 50,
                    "wait_for": "",
                    "timeout_ms": 0,
                },
                "initialize": {"message": "", "pause_ms": 0},
                "identify": {"message": "I\r", "pause_ms": 0},
            },
            "response": {"regex": "HELLO", "device_column": "{model}"},
        }
        app = _bare_app()
        app._log = MagicMock()
        with patch("serial_port_app.serial.Serial", FakeSerial), patch(
            "serial_port_app.time.sleep"
        ) as slept:
            label, baud, found = SerialPortApp._identify_device_with_defs(
                app, "COM4", "9999", {"devices": [device]}
            )
        self.assertEqual(label, "Y")
        ser = FakeSerial.instances[0]
        rts_open = [
            event[1] for event in ser.events if event[0] == "rts" and event[2] is True
        ]
        self.assertEqual(rts_open, [True, False])
        dtr_open = [
            event[1] for event in ser.events if event[0] == "dtr" and event[2] is True
        ]
        self.assertEqual(dtr_open, [False])
        slept.assert_any_call(0.05)
        self.assertIn("COM4 - RTS reset pulse 50 ms", _log_lines(app._log))
        self.assertEqual(ser.written, [b"I\r"])

    def test_run_reset_sequence_helper_without_reset_is_noop(self):
        ser = FakeSerial("COM8")
        ser.events.clear()
        ok, received, error = run_reset_sequence(ser, {"commands": {}}, port="COM8")
        self.assertTrue(ok)
        self.assertEqual(received, "")
        self.assertIsNone(error)
        self.assertEqual(ser.events, [])


class IdleDtrStillUsedTests(FakeSerialTests):
    def test_identify_still_opens_idle_high(self):
        FakeSerial.response = MB607_PROBE_REPLY.encode()
        app = _bare_app()
        with patch("serial_port_app.serial.Serial", FakeSerial), patch(
            "serial_port_app.time.sleep"
        ):
            SerialPortApp._identify_device_with_defs(
                app, "COM8", "4292", {"devices": [_mb607()]}
            )
        ser = FakeSerial.instances[0]
        dtr_before = [
            event for event in ser.events if event[0] == "dtr" and event[2] is False
        ]
        opens = [event for event in ser.events if event[0] == "open"]
        self.assertEqual(dtr_before[0][1], False)
        self.assertEqual(opens[0][1], False)


if __name__ == "__main__":
    unittest.main()
