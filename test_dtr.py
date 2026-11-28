"""DTR idle-high open helper and TEMP Reset (DTR) pulse (no hardware)."""

import unittest
from unittest.mock import MagicMock, patch

from test_device_identity import (
    FakeSerial,
    FakeSerialTests,
    SerialException,
    _bare_app,
    _device_by_model,
)
from serial_port_app import (
    DTR_IDLE,
    DTR_RESET_PULSE_MS,
    NO_PORTS_LABEL,
    SerialPortApp,
    TEMP_DTR_RESET_BUTTON,
    open_serial_idle_dtr,
)


def _assert_idle_dtr_before_open(testcase, ser):
    """ser.dtr = False while closed, then open(), then ser.dtr = False again."""
    testcase.assertEqual(DTR_IDLE, False)
    testcase.assertFalse(any(event[0] == "rts" for event in ser.events))
    dtr_before = [
        event for event in ser.events if event[0] == "dtr" and event[2] is False
    ]
    opens = [event for event in ser.events if event[0] == "open"]
    dtr_after = [
        event for event in ser.events if event[0] == "dtr" and event[2] is True
    ]
    testcase.assertTrue(dtr_before, "dtr was not set before open()")
    testcase.assertEqual(dtr_before[0][1], False)
    testcase.assertTrue(opens, "open() was not called")
    testcase.assertEqual(opens[0][1], False, "dtr was not False at open()")
    testcase.assertTrue(dtr_after, "dtr was not re-asserted after open()")
    testcase.assertEqual(dtr_after[0][1], False)


class _PortVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def _pulse_app(port="COM8", held=False, serial_obj=None):
    app = _bare_app()
    app.settings_port_var = _PortVar(port)
    app.root = MagicMock()
    pending = []

    def _after(ms, fn):
        pending.append((ms, fn))
        return "after-id"

    app.root.after = _after
    app.root.after_cancel = MagicMock()
    app._log = MagicMock()
    app._temp_dtr_reset_button = None
    app._open_serial = serial_obj
    app._held_port = port if held else None
    app._dtr_pulse_busy = False
    app._dtr_pulse_state = None
    app._dtr_pulse_after_id = None
    return app, pending


def _ui_settings():
    return {
        "baudrate": 115200,
        "parity": "N",
        "bytesize": 8,
        "stopbits": 1,
        "xonxoff": False,
        "rtscts": False,
        "dsrdtr": False,
    }


class OpenSerialIdleDtrTests(FakeSerialTests):
    def test_sets_dtr_false_before_and_after_open(self):
        with patch("serial_port_app.serial.Serial", FakeSerial):
            ser = open_serial_idle_dtr(
                "COM8", timeout=1, baudrate=115200, rtscts=False
            )
        self.assertEqual(ser.port, "COM8")
        self.assertTrue(ser.is_open)
        self.assertFalse(ser.dtr)
        _assert_idle_dtr_before_open(self, ser)
        self.assertEqual(ser.kwargs.get("baudrate"), 115200)
        self.assertEqual(ser.kwargs.get("rtscts"), False)

    def test_open_failure_still_sets_dtr_false_first(self):
        FakeSerial.fail_open = True
        with patch("serial_port_app.serial.Serial", FakeSerial):
            with self.assertRaises(SerialException):
                open_serial_idle_dtr("COM8", timeout=1)
        ser = FakeSerial.instances[0]
        self.assertEqual(ser.events[0], ("dtr", False, False))
        self.assertEqual(ser.events[1][0], "open")
        self.assertEqual(ser.events[1][1], False)
        self.assertFalse(ser.is_open)

    def test_reopen_held_uses_idle_dtr_helper(self):
        app = _bare_app()
        app._log = MagicMock()
        app._serial_settings_from_ui = _ui_settings
        with patch("serial_port_app.serial.Serial", FakeSerial):
            self.assertTrue(SerialPortApp._reopen_held(app, "COM8"))
        ser = FakeSerial.instances[0]
        self.assertIs(app._open_serial, ser)
        self.assertEqual(app._held_port, "COM8")
        _assert_idle_dtr_before_open(self, ser)

    def test_is_port_available_uses_idle_dtr_helper_and_closes(self):
        app = _bare_app()
        with patch("serial_port_app.serial.Serial", FakeSerial):
            self.assertTrue(SerialPortApp.is_port_available(app, "COM4"))
        ser = FakeSerial.instances[0]
        _assert_idle_dtr_before_open(self, ser)
        self.assertGreaterEqual(ser.close_calls, 1)
        self.assertFalse(ser.is_open)

    def test_is_port_available_false_when_open_fails(self):
        FakeSerial.fail_open = True
        app = _bare_app()
        with patch("serial_port_app.serial.Serial", FakeSerial):
            self.assertFalse(SerialPortApp.is_port_available(app, "COM4"))
        ser = FakeSerial.instances[0]
        self.assertEqual(ser.events[0], ("dtr", False, False))
        self.assertEqual(ser.events[1][0], "open")

    def test_identify_open_sets_dtr_false_before_open(self):
        FakeSerial.response = b"SIMCOM_SIM7080"
        app = _bare_app()
        sim = _device_by_model("SIM7080")
        with patch("serial_port_app.serial.Serial", FakeSerial), patch(
            "serial_port_app.time.sleep"
        ):
            label, baud, device = SerialPortApp._identify_device_with_defs(
                app, "COM3", "1027", {"devices": [sim]}
            )
        self.assertEqual(device["model"], "SIM7080")
        self.assertIsNotNone(label)
        _assert_idle_dtr_before_open(self, FakeSerial.instances[0])

    def test_connection_scan_worker_sets_dtr_false_before_open(self):
        app = _bare_app()
        app._log = MagicMock()
        app._log_cont = MagicMock()
        app._port_ids_for_match = MagicMock(return_value=None)
        app._device_allowed_on_port = MagicMock(return_value=True)
        app._probe_match = MagicMock(return_value=(None, ""))
        app.root = MagicMock()
        device = {"manufacturer": "X", "model": "Y"}
        with patch("serial_port_app.serial.Serial", FakeSerial), patch(
            "serial_port_app.time.sleep"
        ):
            SerialPortApp._connection_scan_worker(
                app, "COM8", {"baudrate": 115200}, device, False
            )
        _assert_idle_dtr_before_open(self, FakeSerial.instances[0])
        self.assertGreaterEqual(FakeSerial.instances[0].close_calls, 1)


class TempDtrResetPulseTests(FakeSerialTests):
    def test_flag_and_pulse_width(self):
        self.assertTrue(TEMP_DTR_RESET_BUTTON)
        self.assertEqual(DTR_RESET_PULSE_MS, 100)
        self.assertIs(DTR_IDLE, False)

    def test_no_port_selected_does_nothing(self):
        app, pending = _pulse_app(port=NO_PORTS_LABEL)
        with patch("serial_port_app.serial.Serial", FakeSerial), patch(
            "serial_port_app.time.sleep"
        ) as slept:
            SerialPortApp._on_temp_dtr_reset(app)
            slept.assert_not_called()
        self.assertEqual(pending, [])
        self.assertEqual(FakeSerial.instances, [])
        app._log.assert_not_called()

    def test_pulse_on_already_open_port_does_not_reopen_or_close(self):
        held = FakeSerial("COM8")
        held.is_open = True
        held.dtr = False
        held.events.clear()
        before = list(FakeSerial.instances)
        app, pending = _pulse_app(port="COM8", held=True, serial_obj=held)
        with patch("serial_port_app.serial.Serial", FakeSerial), patch(
            "serial_port_app.time.sleep"
        ) as slept:
            SerialPortApp._on_temp_dtr_reset(app)
            slept.assert_not_called()
        self.assertEqual(FakeSerial.instances, before)
        self.assertEqual(held.dtr, True)
        self.assertEqual(pending, [(100, app._finish_temp_dtr_reset)])
        self.assertTrue(app._dtr_pulse_busy)
        SerialPortApp._finish_temp_dtr_reset(app)
        self.assertEqual(held.dtr, False)
        self.assertEqual(held.close_calls, 0)
        self.assertTrue(held.is_open)
        self.assertIs(app._open_serial, held)
        app._log.assert_called_with("COM8 - DTR reset pulse 100 ms")
        self.assertFalse(app._dtr_pulse_busy)
        dtr_values = [event[1] for event in held.events if event[0] == "dtr"]
        self.assertEqual(dtr_values, [True, False])

    def test_pulse_opens_temporarily_when_port_is_not_held(self):
        app, pending = _pulse_app(port="COM8", held=False)
        with patch("serial_port_app.serial.Serial", FakeSerial), patch(
            "serial_port_app.time.sleep"
        ) as slept:
            SerialPortApp._on_temp_dtr_reset(app)
            slept.assert_not_called()
        self.assertEqual(len(FakeSerial.instances), 1)
        ser = FakeSerial.instances[0]
        _assert_idle_dtr_before_open(self, ser)
        self.assertEqual(ser.dtr, True)
        self.assertTrue(ser.is_open)
        self.assertIsNone(app._open_serial)
        self.assertEqual(pending[0][0], DTR_RESET_PULSE_MS)
        SerialPortApp._finish_temp_dtr_reset(app)
        self.assertEqual(ser.dtr, False)
        self.assertGreaterEqual(ser.close_calls, 1)
        self.assertFalse(ser.is_open)
        self.assertIsNone(app._open_serial)
        app._log.assert_called_with("COM8 - DTR reset pulse 100 ms")
        dtr_when_open = [
            event[1] for event in ser.events if event[0] == "dtr" and event[2] is True
        ]
        self.assertEqual(dtr_when_open, [False, True, False])

    def test_pulse_logs_failure_when_port_is_busy(self):
        FakeSerial.fail_open = True
        app, pending = _pulse_app(port="COM8")
        with patch("serial_port_app.serial.Serial", FakeSerial):
            SerialPortApp._on_temp_dtr_reset(app)
        self.assertEqual(pending, [])
        self.assertFalse(app._dtr_pulse_busy)
        self.assertIsNone(app._open_serial)
        logged = app._log.call_args[0][0]
        self.assertIn("COM8 - DTR reset failed:", logged)
        self.assertIn("port busy", logged)

    def test_reset_button_enabled_only_when_port_selected(self):
        app, _pending = _pulse_app(port=NO_PORTS_LABEL)
        app._temp_dtr_reset_button = object()
        app._set_button_enabled = MagicMock()
        SerialPortApp._sync_temp_dtr_reset_button(app)
        app._set_button_enabled.assert_called_with(app._temp_dtr_reset_button, False)
        app.settings_port_var.set("COM8")
        SerialPortApp._sync_temp_dtr_reset_button(app)
        app._set_button_enabled.assert_called_with(app._temp_dtr_reset_button, True)


if __name__ == "__main__":
    unittest.main()
