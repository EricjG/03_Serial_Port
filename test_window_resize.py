"""Live Tk: extra window height goes to the Automated table; min is one row."""

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
    from serial_port_app import (
        SerialPortApp,
        UI_CONTROL_H,
        UI_TREE_MIN_ROWS,
        UI_TREE_ROWS,
    )

    SerialPortApp.start_initial_scan = lambda self: None
    root = tk.Tk()
    app = SerialPortApp(root)
    root.deiconify()
    root.update()
    failures = []

    def h(widget):
        widget.update_idletasks()
        return int(widget.winfo_height())

    row_h = app._tree_row_height()
    tree0 = h(app._tree_host)
    title0 = h(app._title_strip)
    man0 = h(app._settings_box)
    bot0 = h(app._bottom_bar)
    win0 = int(root.winfo_height())
    min_w, min_h = root.minsize()
    if min_h >= win0:
        failures.append(f"min height {min_h} should be below default {win0}")
    if tree0 < row_h * (UI_TREE_ROWS - 1):
        failures.append(f"default table height {tree0} too short for {UI_TREE_ROWS} rows of {row_h}")

    extra = row_h * 4
    root.geometry(f"{root.winfo_width()}x{win0 + extra}")
    root.update()
    tree1 = h(app._tree_host)
    title1 = h(app._title_strip)
    man1 = h(app._settings_box)
    bot1 = h(app._bottom_bar)
    grown = tree1 - tree0
    if grown < extra - row_h:
        failures.append(
            f"table did not take extra height: tree {tree0}->{tree1} extra={extra}"
        )
    if abs(title1 - title0) > 2:
        failures.append(f"title strip height changed {title0}->{title1}")
    if abs(man1 - man0) > 2:
        failures.append(f"Manually box height changed {man0}->{man1}")
    if abs(bot1 - bot0) > 2:
        failures.append(f"bottom bar height changed {bot0}->{bot1}")

    root.geometry(f"{min_w}x{min_h}")
    root.update()
    tree_min = h(app._tree_host)
    max_one = row_h * UI_TREE_MIN_ROWS + 8
    if tree_min > max_one:
        failures.append(
            f"min window still shows more than one row: table={tree_min} row={row_h}"
        )
    if tree_min < row_h - 2:
        failures.append(f"min table shorter than one row: {tree_min} < {row_h}")
    if abs(h(app._title_strip) - title0) > 2:
        failures.append("title strip height changed at min size")
    if abs(h(app._settings_box) - man0) > 2:
        failures.append("Manually box height changed at min size")
    if abs(h(app._bottom_bar) - bot0) > 2:
        failures.append("bottom bar height changed at min size")

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


class WindowResizeTests(unittest.TestCase):
    @unittest.skipUnless(_tk_available(), "Tk display required (use xvfb-run on Linux)")
    def test_extra_height_goes_to_automated_table(self):
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
            msg=result.stderr or result.stdout or "window resize probe failed",
        )
