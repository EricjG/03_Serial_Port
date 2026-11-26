"""Real-Tk status-field geometry. Runs in a subprocess so mocked tkinter is unused."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent

_PROBE = textwrap.dedent(
    r"""
    import sys
    import tkinter as tk
    import tkinter.font as tkfont
    from picker_logic import device_status_size_samples, port_status_size_samples
    from serial_port_app import SerialPortApp

    SerialPortApp.start_initial_scan = lambda self: None

    root = tk.Tk()
    root.withdraw()
    app = SerialPortApp(root)
    root.update_idletasks()
    app._size_status_fields()
    root.update_idletasks()

    def resolved_font(widget):
        spec = widget.cget("font")
        try:
            return tkfont.nametofont(spec)
        except tk.TclError:
            return tkfont.Font(font=spec)

    def probe_reqwidth(widget, text):
        probe = tk.Label(
            root,
            text=text,
            font=resolved_font(widget),
            padx=widget.cget("padx"),
            pady=widget.cget("pady"),
            bd=widget.cget("bd"),
            highlightthickness=widget.cget("highlightthickness"),
            anchor="w",
            justify="left",
        )
        probe.update_idletasks()
        width = int(probe.winfo_reqwidth())
        probe.destroy()
        return width

    failures = []
    checks = (
        (app.device_status_entry, device_status_size_samples()),
        (app.port_status_entry, port_status_size_samples()),
    )
    for widget, samples in checks:
        wrap = widget.master
        wrap.update_idletasks()
        wrap_w = int(wrap.winfo_width())
        if wrap_w <= 1:
            wrap_w = int(wrap.cget("width") or 0)
        for text in samples:
            need = probe_reqwidth(widget, text)
            if wrap_w < need:
                failures.append(
                    f"{widget} {text!r}: wrap={wrap_w} < label reqwidth={need}"
                )
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


class StatusFieldWidthTests(unittest.TestCase):
    @unittest.skipUnless(_tk_available(), "Tk display required (use xvfb-run on Linux)")
    def test_wrapper_width_covers_each_status_value_reqwidth(self):
        result = subprocess.run(
            [sys.executable, "-c", _PROBE],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=result.stderr or result.stdout or "status field width probe failed",
        )
