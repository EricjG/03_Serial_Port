"""App icon files exist and Tk can apply them."""

from __future__ import annotations

import os
import struct
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class AppIconFileTests(unittest.TestCase):
    def test_png_set_and_ico_are_present(self):
        from serial_port_app import (
            ICON_PNG_SIZES,
            app_icon_ico_path,
            app_icon_png_paths,
        )

        paths = {path.name: path for path in app_icon_png_paths()}
        for size in ICON_PNG_SIZES:
            name = f"serial_icon_{size}.png"
            self.assertIn(name, paths, msg=name)
            self.assertGreater(paths[name].stat().st_size, 32)
        self.assertTrue((ROOT / "assets" / "serial_icon.png").is_file())
        ico = app_icon_ico_path()
        self.assertIsNotNone(ico)
        data = ico.read_bytes()
        reserved, kind, count = struct.unpack_from("<HHH", data)
        self.assertEqual(reserved, 0)
        self.assertEqual(kind, 1)
        self.assertGreaterEqual(count, 4)


class AppIconTkTests(unittest.TestCase):
    def test_live_iconphoto_loads_pngs(self):
        probe = r"""
import sys
import tkinter as tk
from serial_port_app import SerialPortApp, ICON_PNG_SIZES, app_icon_png_paths

SerialPortApp.start_initial_scan = lambda self: None
failures = []
root = tk.Tk()
root.withdraw()
for path in app_icon_png_paths():
    img = tk.PhotoImage(file=str(path))
    w, h = int(img.width()), int(img.height())
    stem = path.stem
    if stem.startswith("serial_icon_") and stem.split("_")[-1].isdigit():
        size = int(stem.split("_")[-1])
        if (w, h) != (size, size):
            failures.append(f"{path.name} is {w}x{h}, want {size}x{size}")
app = SerialPortApp(root)
if not getattr(app, "_icon_photos", None):
    failures.append("SerialPortApp stored no icon photos")
app._open_port_settings_dialog()
win = app._settings_dialog
win.update_idletasks()
root.destroy()
if failures:
    sys.stderr.write("\n".join(failures) + "\n")
    raise SystemExit(1)
"""
        check = subprocess.run(
            [sys.executable, "-c", "import tkinter as tk; r = tk.Tk(); r.destroy()"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        )
        if check.returncode != 0:
            self.skipTest("Tk display required (use xvfb-run on Linux)")
        result = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=result.stderr or result.stdout or "icon Tk probe failed",
        )
