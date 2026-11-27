"""Live Tk: In Use header button count label and fixed width."""

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
    from serial_port_app import SerialPortApp

    SerialPortApp.start_initial_scan = lambda self: None

    root = tk.Tk()
    root.withdraw()
    app = SerialPortApp(root)
    root.update_idletasks()
    root.deiconify()
    root.update()
    failures = []

    btn = app._in_use_header_btn
    wrap = app._in_use_header_wrap

    def wrap_width():
        wrap.update_idletasks()
        width = int(wrap.winfo_width())
        if width <= 1:
            width = int(wrap.cget("width") or 0)
        if width <= 1:
            width = int(wrap.winfo_reqwidth())
        return width

    width0 = wrap_width()
    if str(btn.cget("text")) != "In Use x0":
        failures.append(f"startup label {btn.cget('text')!r} != 'In Use x0'")
    if width0 < 2:
        failures.append(f"In Use wrap width {width0} too small")
    sized = app._label_font.measure("In Use x99")
    if width0 < sized:
        failures.append(f"wrap {width0} narrower than two-digit label {sized}")

    def row(status, port):
        return (status, port, None, None, "desc", None)

    def set_ports(*statuses):
        app.port_data = [
            row(status, f"COM{i + 1}") for i, status in enumerate(statuses)
        ]
        app.update_ports_from_data()
        root.update_idletasks()

    app.show_in_use_var.set(False)
    set_ports("Available", "In Use", "In Use", "In Use", "Open")
    if str(btn.cget("text")) != "In Use x3":
        failures.append(f"after 3 in-use {btn.cget('text')!r} != 'In Use x3'")
    shown = [app.tree.item(iid, "values")[0] for iid in app.tree.get_children()]
    if "In Use" in shown:
        failures.append(f"filter off still shows In Use rows: {shown}")

    width3 = wrap_width()
    set_ports(*(["In Use"] * 12))
    if str(btn.cget("text")) != "In Use x12":
        failures.append(f"after 12 in-use {btn.cget('text')!r} != 'In Use x12'")
    width12 = wrap_width()
    if width3 != width0:
        failures.append(f"width jumped x0->{width3}")
    if width12 != width0:
        failures.append(f"width jumped x0->{width12} at two digits")

    app.show_in_use_var.set(True)
    app.update_ports_from_data()
    root.update_idletasks()
    if str(btn.cget("text")) != "In Use x12":
        failures.append(f"filter on changed count to {btn.cget('text')!r}")
    shown = [app.tree.item(iid, "values")[0] for iid in app.tree.get_children()]
    if shown.count("In Use") != 12:
        failures.append(f"filter on should show 12 In Use rows, got {shown}")

    app.scan_ports = lambda full=False: None
    app.show_in_use_var.set(False)
    app.auto_port_scan_var.set(True)
    app.device_scan_var.set(True)
    app.on_in_use_button()
    if not app.show_in_use_var.get():
        failures.append("In Use button did not check In Use")
    if app.auto_port_scan_var.get() or app.device_scan_var.get():
        failures.append("In Use button did not clear Scan Ports / Scan Devices")

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


class InUseHeaderButtonTests(unittest.TestCase):
    @unittest.skipUnless(_tk_available(), "Tk display required (use xvfb-run on Linux)")
    def test_count_label_width_and_filter_semantics(self):
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
            msg=result.stderr or result.stdout or "in-use button probe failed",
        )


if __name__ == "__main__":
    unittest.main()
