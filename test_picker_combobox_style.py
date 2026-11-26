"""Live ttk check: Picker.TCombobox must not use native vista/theme chrome."""

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
    import tkinter.ttk as ttk
    from serial_port_app import (
        PICKER_COMBOBOX_ARROWSIZE,
        configure_picker_combobox_style,
        picker_combobox_layout_element_names,
    )

    root = tk.Tk()
    root.withdraw()
    style = ttk.Style()
    configure_picker_combobox_style(style)
    names = picker_combobox_layout_element_names(style.layout("Picker.TCombobox"))
    failures = []
    for native in ("Combobox.downarrow", "Combobox.field", "Combobox.rightdownarrow"):
        if native in names:
            failures.append(f"layout still references native {native!r}: {names}")
    for cloned in (
        "Picker.Combobox.downarrow",
        "Picker.Combobox.field",
        "Picker.Combobox.textarea",
    ):
        if cloned not in names:
            failures.append(f"layout missing cloned {cloned!r}: {names}")
    cfg = style.configure("Picker.TCombobox") or {}
    arrowsize = cfg.get("arrowsize")
    if arrowsize not in (PICKER_COMBOBOX_ARROWSIZE, str(PICKER_COMBOBOX_ARROWSIZE)):
        failures.append(f"arrowsize={arrowsize!r} want {PICKER_COMBOBOX_ARROWSIZE}")
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


class PickerComboboxStyleTests(unittest.TestCase):
    @unittest.skipUnless(_tk_available(), "Tk display required (use xvfb-run on Linux)")
    def test_live_layout_does_not_use_native_combobox_chrome(self):
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
            msg=result.stderr or result.stdout or "picker combobox style probe failed",
        )
