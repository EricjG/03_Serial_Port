"""Live Tk: Baud 1.5x vs Port trade, Settings 8 - N - 1 - N, dialog order."""

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
    from picker_logic import (
        SETTINGS_DIALOG_FIELDS,
        format_settings_text,
        longest_settings_text,
    )
    from serial_port_app import (
        BAUD_COMBO_WIDTH_SCALE,
        SerialPortApp,
    )

    SerialPortApp.start_initial_scan = lambda self: None

    root = tk.Tk()
    root.withdraw()
    app = SerialPortApp(root)
    root.update_idletasks()
    failures = []

    def wrap_req(widget):
        widget.update_idletasks()
        return int(widget.winfo_reqwidth())

    port_wrap = app._port_combo_wrap
    baud_wrap = app._baud_combo_wrap
    base_baud = int(getattr(app, "_baud_wrap_base_w", 0) or 0)
    base_port = int(getattr(app, "_port_wrap_base_w", 0) or 0)
    baud_w = wrap_req(baud_wrap)
    port_w = wrap_req(port_wrap)
    want_baud = SerialPortApp.scaled_baud_width_px(base_baud, BAUD_COMBO_WIDTH_SCALE)
    if abs(baud_w - want_baud) > 1:
        failures.append(f"Baud wrap {baud_w} != 1.5x base {base_baud} -> {want_baud}")
    if abs((port_w + baud_w) - (base_port + base_baud)) > 1:
        failures.append(
            f"Port+Baud {port_w}+{baud_w}={port_w + baud_w} "
            f"!= base {base_port}+{base_baud}={base_port + base_baud}"
        )
    if baud_w <= base_baud:
        failures.append(f"Baud did not grow: {baud_w} <= base {base_baud}")
    if port_w >= base_port:
        failures.append(f"Port did not shrink: {port_w} >= base {base_port}")

    summary = app.settings_summary_var.get()
    if summary != "8 - N - 1 - N":
        failures.append(f"Settings default {summary!r} != '8 - N - 1 - N'")
    longest = longest_settings_text()
    field = app.settings_summary
    probe = tk.Entry(
        root,
        font=field.cget("font"),
        width=field.cget("width"),
        relief=tk.FLAT,
        bd=0,
    )
    probe.insert(0, longest)
    probe.update_idletasks()
    # Character-width entries: width in chars must cover longest string.
    if int(field.cget("width") or 0) < len(longest):
        failures.append(
            f"Settings width={field.cget('width')} < longest {longest!r} ({len(longest)})"
        )
    probe.destroy()

    app._open_port_settings_dialog()
    win = app._settings_dialog
    win.deiconify()
    win.update()
    stored_fields = list(getattr(app, "_settings_dialog_fields", ()))
    stored = [label for label, _cell in stored_fields]
    want = [label for label, _key in SETTINGS_DIALOG_FIELDS]
    if stored != want:
        failures.append(f"dialog field order {stored} != {want}")
    for index, (label, cell) in enumerate(stored_fields):
        info = cell.grid_info()
        row, col = divmod(index, 2)
        got_row = int(str(info.get("row", -1)))
        got_col = int(str(info.get("column", -1)))
        if got_row != row or got_col != col:
            failures.append(
                f"{label} at grid ({got_row},{got_col}), want ({row},{col})"
            )
    preview = getattr(app, "_settings_preview_var", None)
    if preview is None or preview.get() != "8 - N - 1 - N":
        failures.append(
            f"dialog preview {None if preview is None else preview.get()!r} "
            "!= '8 - N - 1 - N'"
        )
    if preview is not None:
        import tkinter.ttk as ttk
        combos = []

        def walk_combos(widget):
            if isinstance(widget, ttk.Combobox):
                combos.append(widget)
            for child in widget.winfo_children():
                walk_combos(child)

        walk_combos(win)
        parity_combo = None
        for combo in combos:
            values = [str(v) for v in combo.cget("values")]
            if "Even" in values and "None" in values:
                parity_combo = combo
                break
        if parity_combo is None:
            failures.append("no Parity combobox in settings dialog")
        else:
            parity_combo.set("Even")
            win.update_idletasks()
            want_preview = format_settings_text("8", "1", "Even", "None")
            if preview.get() != want_preview:
                failures.append(
                    f"live preview after Even {preview.get()!r} != {want_preview!r}"
                )
            if want_preview != "8 - E - 1 - N":
                failures.append(f"helper produced {want_preview!r}")
    win.destroy()
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


class ManuallyLayoutTests(unittest.TestCase):
    @unittest.skipUnless(_tk_available(), "Tk display required (use xvfb-run on Linux)")
    def test_baud_port_trade_settings_text_and_dialog_order(self):
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
            msg=result.stderr or result.stdout or "manually layout probe failed",
        )
