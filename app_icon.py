"""DE-9 window icon: asset paths, Windows AppUserModelID, Tk apply."""

from __future__ import annotations

import sys
from pathlib import Path

ICON_PNG_SIZES = (16, 24, 32, 48, 256)
ICON_ICO_NAME = "serial_icon.ico"
ICON_PNG_NAME = "serial_icon.png"
APP_USER_MODEL_ID = "EricjG.SerialPortApplication"


def app_dir(root=None):
    """Folder that holds `assets/`. Script dir, or sys._MEIPASS when frozen."""
    if root is not None:
        return Path(root)
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
    return Path(__file__).resolve().parent


def app_icon_png_paths(root=None):
    assets = app_dir(root) / "assets"
    paths = []
    for size in ICON_PNG_SIZES:
        path = assets / f"serial_icon_{size}.png"
        if path.is_file():
            paths.append(path)
    hero = assets / ICON_PNG_NAME
    if hero.is_file() and hero not in paths:
        paths.append(hero)
    return tuple(paths)


def app_icon_ico_path(root=None):
    path = app_dir(root) / "assets" / ICON_ICO_NAME
    return path if path.is_file() else None


def log_icon(message, log=None):
    text = f"App icon: {message}"
    if callable(log):
        log(text)
        return
    print(text, flush=True)


def set_windows_app_user_model_id(app_id=APP_USER_MODEL_ID, log=None):
    """Taskbar grouping / overlay icon on Windows. Call before creating Tk()."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(str(app_id))
        return True
    except Exception as exc:
        log_icon(f"SetCurrentProcessExplicitAppUserModelID failed: {exc}", log=log)
        return False


def load_icon_photos(log=None):
    """Load PNG PhotoImages. Keep the list so Tk does not GC them."""
    import tkinter as tk

    photos = []
    missing = []
    for path in app_icon_png_paths():
        try:
            photos.append(tk.PhotoImage(file=str(path)))
        except tk.TclError as exc:
            log_icon(f"failed to load {path.name}: {exc}", log=log)
            missing.append(path.name)
    if not photos:
        names = ", ".join(p.name for p in app_icon_png_paths()) or "none found"
        log_icon(f"no PNG icon loaded ({names})", log=log)
    return photos


def apply_window_icon(win, *, photos=None, log=None, default=False):
    """Apply the DE-9 icon. Windows uses .ico via iconbitmap; Linux uses iconphoto.

    Failed loads are logged. PNG iconphoto is the fallback if the .ico fails.
    """
    if win is None:
        return photos or []
    import tkinter as tk
    if photos is None:
        photos = load_icon_photos(log=log)

    used_ico = False
    if sys.platform == "win32":
        ico = app_icon_ico_path()
        if ico is None:
            log_icon(
                f"{ICON_ICO_NAME} missing; falling back to PNG iconphoto",
                log=log,
            )
        else:
            try:
                if default:
                    win.iconbitmap(default=str(ico))
                else:
                    win.iconbitmap(str(ico))
                used_ico = True
            except tk.TclError as exc:
                log_icon(f"iconbitmap({ico.name}) failed: {exc}", log=log)
                if default:
                    try:
                        win.iconbitmap(str(ico))
                        used_ico = True
                    except tk.TclError as exc2:
                        log_icon(
                            f"iconbitmap fallback({ico.name}) failed: {exc2}",
                            log=log,
                        )

    if used_ico:
        return photos

    if not photos:
        log_icon("no icon applied (ico and png both unavailable)", log=log)
        return photos
    try:
        win.iconphoto(True if default else False, *photos)
    except tk.TclError as exc:
        log_icon(f"iconphoto failed: {exc}", log=log)
        try:
            win.iconphoto(False, photos[-1])
        except tk.TclError as exc2:
            log_icon(f"iconphoto fallback failed: {exc2}", log=log)
    return photos
