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
    from picker_logic import port_status_size_samples
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

    def probe_reqwidth(widget, text, font=None):
        probe = tk.Label(
            root,
            text=text,
            font=font or resolved_font(widget),
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
    device_samples = app._device_status_size_samples()
    catalog = app._catalog_identified_labels()
    for label in catalog:
        if label not in device_samples:
            failures.append(f"catalog label missing from size samples: {label!r}")
    checks = (
        (app.device_status_entry, device_samples),
        (app.port_status_entry, port_status_size_samples()),
    )
    wrap_widths = {}
    for widget, samples in checks:
        wrap = widget.master
        wrap.update_idletasks()
        wrap_w = int(wrap.winfo_width())
        if wrap_w <= 1:
            wrap_w = int(wrap.cget("width") or 0)
        wrap_widths[widget] = wrap_w
        for text in samples:
            need = probe_reqwidth(widget, text)
            if wrap_w < need:
                failures.append(
                    f"{widget} {text!r}: wrap={wrap_w} < label reqwidth={need}"
                )

    device_wrap = app.device_status_entry.master
    min_w = int(device_wrap.cget("width") or 0)
    actual_w = wrap_widths[app.device_status_entry]
    if actual_w < min_w:
        failures.append(
            f"Device Status wrap actual={actual_w} < min width={min_w}"
        )

    min_win_w, _min_win_h = root.minsize()
    req_w = int(root.winfo_reqwidth())
    if int(min_win_w or 0) < req_w:
        failures.append(
            f"window minsize {min_win_w} < reqwidth {req_w} (would clip Device Status)"
        )

    before_w = int(root.winfo_width())
    wide = max(before_w + 200, req_w + 200, min_w + 400)
    root.deiconify()
    root.geometry(f"{wide}x{max(int(root.winfo_height()), 1)}")
    root.update()
    stretched = int(device_wrap.winfo_width())
    after_w = int(root.winfo_width())
    if stretched < min_w:
        failures.append(
            f"Device Status shrank below min when window grew: {stretched} < {min_w}"
        )
    if after_w > before_w + 40 and stretched <= min_w:
        failures.append(
            f"Device Status did not stretch at {wide}px: wrap={stretched} min={min_w}"
        )

    segoe = tkfont.Font(family="Segoe UI", size=9)
    segoe_highlight = 1
    try:
        segoe_highlight = int(float(str(device_wrap.cget("highlightthickness")).split()[0]))
    except (tk.TclError, TypeError, ValueError):
        pass
    from picker_logic import grid_ceil_px
    from serial_port_app import UI_PAD
    segoe_need = 0
    for text in device_samples:
        need = probe_reqwidth(app.device_status_entry, text, font=segoe)
        segoe_need = max(segoe_need, need)
        would = grid_ceil_px(need + 2 * segoe_highlight, UI_PAD)
        if would < need:
            failures.append(
                f"Segoe UI 9 helper too narrow for {text!r}: {would} < {need}"
            )
    if sys.platform == "win32" and actual_w < segoe_need:
        failures.append(
            f"vista/Segoe UI 9 wrap={actual_w} < longest sample reqwidth={segoe_need}"
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
