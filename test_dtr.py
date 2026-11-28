"""DTR idle-high open helper (no hardware). TEMP Reset (DTR) button is gone."""

import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path
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
    SerialPortApp,
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
        app._probe_match = MagicMock(return_value=(None, "", None))
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

    def test_temp_reset_button_symbols_are_gone(self):
        self.assertFalse(hasattr(SerialPortApp, "_on_temp_dtr_reset"))
        self.assertFalse(hasattr(SerialPortApp, "_finish_temp_dtr_reset"))
        import serial_port_app as app_mod

        self.assertFalse(hasattr(app_mod, "TEMP_DTR_RESET_BUTTON"))
        self.assertFalse(hasattr(app_mod, "DTR_RESET_PULSE_MS"))


ROOT = Path(__file__).resolve().parent

_LAYOUT_PROBE = textwrap.dedent(
    r"""
    import sys
    import tkinter as tk
    from serial_port_app import SerialPortApp

    SerialPortApp.start_initial_scan = lambda self: None
    root = tk.Tk()
    root.withdraw()
    app = SerialPortApp(root)
    root.update_idletasks()
    root.deiconify()
    root.update()
    failures = []

    reset = getattr(app, "_temp_dtr_reset_button", None)
    if reset is not None:
        failures.append("TEMP Reset (DTR) button is still present")
    labels = []

    def walk(widget):
        try:
            text = str(widget.cget("text"))
        except tk.TclError:
            text = ""
        if text:
            labels.append(text)
        for child in widget.winfo_children():
            walk(child)

    walk(root)
    if any("Reset (DTR)" in text for text in labels):
        failures.append(f"Reset (DTR) still in UI: {labels}")
    open_btn = getattr(app, "open_port_button", None)
    open_wrap = getattr(app, "_open_wrap", None)
    in_use = getattr(app, "_in_use_header_btn", None)
    in_use_wrap = getattr(app, "_in_use_header_wrap", None)
    identify = getattr(app, "identify_button", None)
    if open_btn is None or open_wrap is None:
        failures.append("Open button missing")
    if in_use is None or in_use_wrap is None:
        failures.append("In Use header button missing")
    if in_use is not None and str(in_use.cget("text")) != "In Use x0":
        failures.append(f"In Use label {in_use.cget('text')!r} != 'In Use x0'")
    if open_wrap is not None and identify is not None:
        identify_wrap = identify.master
        ox2 = int(open_wrap.winfo_rootx()) + int(open_wrap.winfo_width())
        ix2 = int(identify_wrap.winfo_rootx()) + int(identify_wrap.winfo_width())
        if abs(ox2 - ix2) > 2:
            failures.append(f"Open/Identify right edges {ox2} vs {ix2}")

    root.destroy()
    if failures:
        sys.stderr.write("\n".join(failures) + "\n")
        raise SystemExit(1)
    """
)


def _tk_available():
    probe = "import tkinter as tk; r = tk.Tk(); r.destroy()"
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    return result.returncode == 0


class ManuallyRowLayoutTests(unittest.TestCase):
    @unittest.skipUnless(_tk_available(), "Tk display required (use xvfb-run on Linux)")
    def test_reset_button_removed_open_aligns_with_identify(self):
        result = subprocess.run(
            [sys.executable, "-c", _LAYOUT_PROBE],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=result.stderr or result.stdout or "Manually-row layout probe failed",
        )


if __name__ == "__main__":
    unittest.main()
