
#! Run from this folder: .\run.bat
#! PowerShell venv: .\.venv\Scripts\Activate.ps1   then   python .\serial_port_app.py

import tkinter as tk
import tkinter.ttk as ttk
import tkinter.font as tkfont
from serial.tools import list_ports  # requires pyserial package: pip install pyserial
import serial  # requires pyserial package: pip install pyserial
import json
import re
import threading
import time

from picker_logic import (
    DEFAULT_PARITY,
    apply_header_button_click,
    device_message_text,
    dropdown_ports,
    format_settings_text,
    format_vid_pid,
    picker_control_state,
    port_event_message,
    unique_device_labels,
    visible_tree_rows,
)

APP_VERSION = "3.0"
AUTO_PORT_SCAN_MS = 1000  # wait before each auto port-scan sequence
NO_PORTS_LABEL = "No Ports Available"
AUTO_DEVICE_SCAN_MS = 1000  # repeat once a second when the header box is checked
PORT_OPEN_TIMEOUT = 0.15  # seconds; faster availability probe

# Page-3 look (cleaned Serial Port Application UI)
UI_BG = "#FFFFFF"  # window / content white
UI_PANEL = "#FFFFFF"
UI_BOTTOM = "#FFFFFF"
UI_HEADER = "#D6E8F8"  # light blue section bars/boxes
UI_BTN_GRAY = "#C0C0C0"
UI_ORANGE = "#FF8C00"
UI_FG = "#1a1a1a"
UI_GREEN = "#90EE90"
UI_DISABLED = "#808080"
UI_ROW_SELECTED = "#FFFF00"
UI_CURRENT_SETTINGS = "#FFF2CC"

PARITY_CHOICES = ("None", "Even", "Odd", "Mark", "Space")
STOP_BITS_CHOICES = ("1", "1.5", "2")
DATA_BITS_CHOICES = ("5", "6", "7", "8")
FLOW_CHOICES = ("None", "XON/XOFF", "RTS/CTS", "DSR/DTR")
PARITY_TO_UI = {"N": "None", "E": "Even", "O": "Odd", "M": "Mark", "S": "Space"}
UI_TO_PARITY = {label: code for code, label in PARITY_TO_UI.items()}

BAUD_SHORT = [
    (300, "300"),
    (600, "600"),
    (1200, "1.2K"),
    (2400, "2.4K"),
    (4800, "4.8K"),
    (9600, "9.6K"),
    (14400, "14.4K"),
    (19200, "19.2K"),
    (28800, "28.8K"),
    (38400, "38.4K"),
    (57600, "57.6K"),
    (115200, "115.2K"),
    (230400, "230.4K"),
    (460800, "460.8K"),
    (921600, "921.6K"),
]
BAUD_SHORT_BY_VALUE = {v: s for v, s in BAUD_SHORT}


class SerialPortApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Serial Port Application v{APP_VERSION}")
        self.root.geometry("720x480")
        self.root.minsize(700, 440)
        self.root.configure(bg=UI_BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_exit)

        # --- state ---
        self.known_ports = set()
        self.port_data = []  # (status, port, vendor_id, device_name, description, baud)
        self._port_scan_lock = threading.Lock()
        self._port_scan_running = False
        self._device_scan_lock = threading.Lock()
        self._device_scan_running = False
        self._device_scan_after_port = False
        self._port_scan_full = False
        self._auto_port_after_id = None
        self._auto_device_after_id = None
        self._settings_dialog = None
        self._device_align_after = None
        self._syncing_device_combo = False
        self._log_lock = threading.Lock()
        self._open_serial = None
        self._held_port = None
        self._suppress_device_apply = False
        self._show_in_use_once = False
        self._suppress_auto_toggle = False
        self._device_entries = []

        with open("devices.json", "r") as f:
            self.device_definitions = json.load(f)
        self._rebuild_device_entries()

        style = ttk.Style()
        style.configure("Treeview", font=("Arial", 10), rowheight=22)
        style.configure(
            "Treeview.Heading", font=("Arial", 10, "bold"), foreground="#000000"
        )
        style.configure("TCombobox", font=("Arial", 10, "bold"))
        style.map(
            "Treeview",
            background=[("selected", UI_ROW_SELECTED)],
            foreground=[("selected", "#000000")],
        )
        style.map(
            "TCombobox",
            foreground=[("disabled", UI_DISABLED)],
            fieldbackground=[("disabled", "#F0F0F0")],
        )

        self.show_in_use_var = tk.BooleanVar(value=False)
        self.auto_port_scan_var = tk.BooleanVar(value=True)
        self.device_scan_var = tk.BooleanVar(value=False)

        self._build_ui()
        self.root.update_idletasks()
        req_w = max(700, self.root.winfo_reqwidth())
        req_h = max(440, self.root.winfo_reqheight())
        self.root.minsize(req_w, req_h)
        self.root.after(100, self.start_initial_scan)

    # ------------------------------------------------------------------ UI
    def _panel(self, parent, bg=None):
        """Untitled background box for a UI section (no per-widget orange)."""
        return tk.Frame(
            parent,
            bg=bg or UI_PANEL,
            bd=0,
            relief=tk.FLAT,
            padx=8,
            pady=6,
        )

    def _build_ui(self):
        # One orange border around the whole UI; sections inside have no orange.
        shell = tk.Frame(self.root, bg=UI_ORANGE, padx=3, pady=3)
        shell.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

        main = tk.Frame(shell, bg=UI_BG)
        main.pack(fill=tk.BOTH, expand=True)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=0)
        main.rowconfigure(1, weight=3)
        main.rowconfigure(2, weight=0)
        main.rowconfigure(3, weight=0)

        header = tk.Frame(
            main,
            bg=UI_HEADER,
            padx=8,
            pady=2,
            highlightbackground="#000000",
            highlightthickness=1,
            highlightcolor="#000000",
        )
        # White gap between orange outer border and this blue box
        header.grid(row=0, column=0, sticky="ew", pady=(12, 8), padx=14)
        self._build_status_header(header)

        status_box = tk.Frame(
            main,
            bg=UI_HEADER,
            padx=6,
            pady=6,
            highlightbackground="#000000",
            highlightthickness=1,
            highlightcolor="#000000",
        )
        status_box.grid(row=1, column=0, sticky="nsew", pady=(0, 8), padx=14)
        self._build_status_tree(status_box)

        settings_box = tk.Frame(
            main,
            bg=UI_HEADER,
            padx=6,
            pady=6,
            highlightbackground="#000000",
            highlightthickness=1,
            highlightcolor="#000000",
        )
        settings_box.grid(row=2, column=0, sticky="ew", pady=(0, 8), padx=14)
        self._build_port_settings_scaffold(settings_box)

        bottom = tk.Frame(main, bg=UI_BOTTOM, padx=8, pady=6)
        bottom.grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 8))
        self._build_bottom_bar(bottom)
        self._sync_port_selection_ui()

    def _build_status_tree(self, parent):
        """Port list in blue box; column titles live in the blue area, aligned to columns."""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        cols = (
            ("Status", "center", 90),
            ("Port #", "center", 80),
            ("ID/Baud", "center", 90),
            ("Serial Driver / Connected Device", "w", 280),
        )
        self._tree_cols = [c[0] for c in cols]

        # Titles in the blue fill, above the list (not inside Treeview headings)
        self._tree_header = tk.Frame(parent, bg=UI_HEADER)
        self._tree_header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 2))
        self._tree_header_labels = []
        for i, (name, anchor, _width) in enumerate(cols):
            lbl = tk.Label(
                self._tree_header,
                text=name,
                bg=UI_HEADER,
                fg="#000000",
                font=("Arial", 10, "bold"),
                anchor=anchor,
            )
            lbl.grid(row=0, column=i, sticky="nsew")
            self._tree_header_labels.append(lbl)
        self._tree_header_scroll_pad = tk.Frame(self._tree_header, bg=UI_HEADER, width=18)
        self._tree_header_scroll_pad.grid(row=0, column=len(cols), sticky="ns")

        self.tree = ttk.Treeview(
            parent,
            columns=self._tree_cols,
            show="",  # titles are in blue area above
            height=5,
        )
        for name, anchor, width in cols:
            stretch = name not in ("Status", "Port #", "ID/Baud")
            self.tree.column(
                name, width=width, minwidth=40, anchor=anchor, stretch=stretch
            )

        scroll = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=1, column=0, sticky="nsew")
        scroll.grid(row=1, column=1, sticky="ns")
        self._tree_scrollbar = scroll

        self._tree_body_font = tkfont.Font(family="Arial", size=10)
        self._tree_header_font = tkfont.Font(family="Arial", size=10, weight="bold")
        self._tree_identified_font = tkfont.Font(family="Arial", size=10, weight="bold")
        self.tree.tag_configure("identified", font=self._tree_identified_font)
        self._fixed_tree_cols = ("Status", "Port #", "ID/Baud")

        self.tree.bind("<Configure>", self._sync_tree_header_widths)
        parent.bind("<Configure>", self._sync_tree_header_widths)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Double-1>", self._on_tree_double_click)
        self.root.after(50, self._fit_fixed_tree_columns)
        self.root.after(60, self._sync_tree_header_widths)

    def _text_px(self, text, bold=False):
        font = self._tree_header_font if bold else self._tree_body_font
        return font.measure(str(text))

    def _fit_fixed_tree_columns(self):
        """Fixed width for Status / Port # / ID/Baud: max(header, content) + space each side."""
        if not getattr(self, "tree", None):
            return
        space = self._text_px(" ")  # one space each side
        try:
            for col in self._fixed_tree_cols:
                need = self._text_px(col, bold=True)
                for item in self.tree.get_children():
                    vals = self.tree.item(item, "values")
                    idx = self._tree_cols.index(col)
                    if idx < len(vals):
                        need = max(need, self._text_px(vals[idx]))
                width = need + 2 * space
                self.tree.column(col, width=width, minwidth=width, stretch=False)
            self._sync_tree_header_widths()
        except tk.TclError:
            pass

    def _sync_tree_header_widths(self, event=None):
        """Keep blue-area titles pixel-aligned with Treeview columns + scrollbar."""
        if not getattr(self, "_tree_header_labels", None):
            return
        try:
            for i, col in enumerate(self._tree_cols):
                w = int(self.tree.column(col, "width"))
                self._tree_header.columnconfigure(i, minsize=w, weight=0)
            sw = self._tree_scrollbar.winfo_width()
            if sw < 2:
                sw = 18
            self._tree_header_scroll_pad.configure(width=sw)
            self._tree_header.columnconfigure(len(self._tree_cols), minsize=sw, weight=0)
        except tk.TclError:
            pass

    def _build_check_button(self, parent, label, var, on_toggle, on_button, bg=None):
        """Checkbox on top-left; label right-aligned with room so text isn't covered."""
        cell_bg = bg if bg is not None else UI_PANEL
        cell = tk.Frame(parent, bg=cell_bg)
        cell.pack(side=tk.LEFT, padx=4)
        btn_font = tkfont.Font(family="Arial", size=8, weight="bold")
        avg_char = max(btn_font.measure("0"), 1)
        # Left gutter for checkbox + gap; text sits on the right
        cb_clear_px = 0
        extra_spaces = 1 if len(label) > 8 else 1
        gap_px = btn_font.measure(" " * extra_spaces)
        width_chars = max(
            4,
            (btn_font.measure(label) + cb_clear_px + gap_px + avg_char - 1) // avg_char
            + 1,
        )
        btn = tk.Button(
            cell,
            text=label,
            command=on_button,
            width=width_chars,
            font=btn_font,
            bg=UI_BTN_GRAY,
            activebackground="#A8A8A8",
            anchor="e",
            justify="right",
            relief=tk.RAISED,
            padx=2,
            pady=1,
        )
        btn.pack()
        cb = tk.Checkbutton(
            cell,
            variable=var,
            command=on_toggle,
            bg=UI_BTN_GRAY,
            activebackground=UI_BTN_GRAY,
            selectcolor=UI_BOTTOM,
            highlightthickness=0,
            bd=0,
        )
        cb.place(in_=btn, x=1, y=0, anchor="nw")

    def _build_status_header(self, parent):
        """Light-blue bar: title left (black); checkbox-on-button controls right-aligned."""
        tk.Label(
            parent,
            text="UART Connection Status",
            bg=UI_HEADER,
            fg="#000000",
            font=("Arial", 11, "bold"),
            anchor="w",
        ).pack(side=tk.LEFT)

        trio = tk.Frame(parent, bg=UI_HEADER)
        trio.pack(side=tk.RIGHT)
        self._build_check_button(
            trio,
            "In Use",
            self.show_in_use_var,
            self.toggle_ports_in_use,
            self.on_in_use_button,
            bg=UI_HEADER,
        )
        self._build_check_button(
            trio,
            "Scan Ports",
            self.auto_port_scan_var,
            self.toggle_auto_port_scan,
            self.on_scan_ports_button,
            bg=UI_HEADER,
        )
        self._build_check_button(
            trio,
            "Scan Devices",
            self.device_scan_var,
            self.toggle_device_scan,
            self.on_scan_devices_button,
            bg=UI_HEADER,
        )

    def _labeled_combo(
        self, parent, label, var, values, width, bg=None, editable=False
    ):
        cell_bg = bg if bg is not None else UI_PANEL
        col = tk.Frame(parent, bg=cell_bg)
        col.pack(side=tk.LEFT, padx=6, anchor="n")
        tk.Label(
            col, text=label, bg=cell_bg, fg=UI_FG, font=("Arial", 10, "bold"),
            anchor="center",
        ).pack(fill=tk.X)
        state = "normal" if editable else "readonly"
        cb = ttk.Combobox(
            col, textvariable=var, values=values, width=width, state=state, font=("Arial", 10, "bold")
        )
        cb.pack(anchor="center")
        return col, cb

    def _build_port_settings_scaffold(self, parent):
        """3rd blue box: Status/Port/Baud/Settings; Device; Open + Identify top-right."""
        wrap = tk.Frame(parent, bg=UI_HEADER)
        wrap.pack(fill=tk.BOTH, expand=True)

        self.settings_status_var = tk.StringVar(value="None Available")
        self.settings_port_var = tk.StringVar(value=NO_PORTS_LABEL)
        self.settings_baud_var = tk.StringVar(value="115.2K")
        self.settings_device_var = tk.StringVar(value="")
        self.settings_parity_var = tk.StringVar(value=DEFAULT_PARITY)
        self.settings_data_var = tk.StringVar(value="8")
        self.settings_stop_var = tk.StringVar(value="1")
        self.settings_flow_var = tk.StringVar(value="None")

        # Right: Open / Identify stacked
        right = tk.Frame(wrap, bg=UI_HEADER)
        right.pack(side=tk.RIGHT, anchor="n", padx=(8, 0))
        self.open_port_button = tk.Button(
            right,
            text="Open:",
            width=16,
            state=tk.DISABLED,
            bg=UI_BTN_GRAY,
            disabledforeground=UI_DISABLED,
            anchor="w",
            justify="left",
            relief=tk.RAISED,
            font=("Arial", 9, "bold"),
        )
        self.open_port_button.configure(command=self._on_open_port)
        self.open_port_button.pack(anchor="e", pady=(14, 2))
        self.identify_button = tk.Button(
            right,
            text="Identify",
            width=16,
            state=tk.DISABLED,
            bg=UI_BTN_GRAY,
            disabledforeground=UI_DISABLED,
            anchor="w",
            justify="left",
            relief=tk.RAISED,
            font=("Arial", 9, "bold"),
            command=self._on_connection_scan_device,
        )
        self.identify_button.pack(anchor="e")
        self.scan_device_button = self.identify_button

        left = tk.Frame(wrap, bg=UI_HEADER)
        left.pack(side=tk.LEFT, fill=tk.X, expand=True)

        row1 = tk.Frame(left, bg=UI_HEADER)
        row1.pack(fill=tk.X, anchor="w")

        # Status: display-only text box (not editable)
        status_col = tk.Frame(row1, bg=UI_HEADER)
        status_col.pack(side=tk.LEFT, padx=6, anchor="n")
        tk.Label(
            status_col,
            text="Status",
            bg=UI_HEADER,
            fg=UI_FG,
            font=("Arial", 10, "bold"),
            anchor="center",
        ).pack(fill=tk.X)
        self.settings_status_entry = tk.Entry(
            status_col,
            textvariable=self.settings_status_var,
            width=16,
            font=("Arial", 10, "bold"),
            relief=tk.SUNKEN,
            bd=2,
            state="readonly",
            readonlybackground="#FFFFFF",
            fg="#000000",
        )
        self.settings_status_entry.pack(anchor="center")

        # Port: dropdown + manual entry allowed; no '* Manual Entry *' item
        port_col = tk.Frame(row1, bg=UI_HEADER)
        port_col.pack(side=tk.LEFT, padx=6, anchor="n")
        tk.Label(
            port_col, text="Port", bg=UI_HEADER, fg=UI_FG, font=("Arial", 10, "bold"),
            anchor="center",
        ).pack(fill=tk.X)
        self.settings_port_combo = ttk.Combobox(
            port_col,
            textvariable=self.settings_port_var,
            values=[NO_PORTS_LABEL],
            width=14,
            state="normal",
            font=("Arial", 10, "bold"),
        )
        self.settings_port_combo.pack(anchor="center")
        self.settings_port_combo.bind(
            "<<ComboboxSelected>>", lambda _e: self._sync_port_selection_ui()
        )
        self.settings_port_var.trace_add(
            "write", lambda *_a: self._sync_port_selection_ui()
        )

        # Baud: dropdown + manual entry; no '* Manual Entry *' item
        baud_labels = [s for _, s in BAUD_SHORT]
        _, self.settings_baud_combo = self._labeled_combo(
            row1,
            "Baud",
            self.settings_baud_var,
            baud_labels,
            10,
            bg=UI_HEADER,
            editable=True,
        )

        settings_col = tk.Frame(row1, bg=UI_HEADER)
        settings_col.pack(side=tk.LEFT, padx=6, anchor="n")
        tk.Label(
            settings_col,
            text="Port Settings",
            bg=UI_HEADER,
            fg=UI_FG,
            font=("Arial", 10, "bold"),
            anchor="center",
        ).pack(fill=tk.X)
        self.settings_summary = tk.Button(
            settings_col,
            text=self._format_settings_summary(),
            command=self._open_port_settings_dialog,
            bg="#FFFFFF",
            activebackground="#FFFFFF",
            fg="#000000",
            disabledforeground=UI_DISABLED,
            anchor="w",
            justify="left",
            relief=tk.RAISED,
            padx=6,
            font=("Arial", 9, "bold"),
        )
        self.settings_summary.pack(anchor="center")
        self.settings_summary.bind(
            "<Configure>", self._schedule_device_combo_align
        )

        # Device: label left, dropdown right edge matches Settings button
        row2 = tk.Frame(left, bg=UI_HEADER)
        row2.pack(fill=tk.X, anchor="w", pady=(8, 0))
        tk.Label(
            row2, text="Device", bg=UI_HEADER, fg=UI_FG, font=("Arial", 10, "bold")
        ).pack(side=tk.LEFT, padx=(6, 4))
        device_names = [label for label, _device in self._device_entries]
        if not device_names:
            device_names = ["(no devices)"]
        self.settings_device_var.set(device_names[0])
        self._device_combo_host = tk.Frame(row2, bg=UI_HEADER, height=24)
        self._device_combo_host.pack(side=tk.LEFT)
        self._device_combo_host.pack_propagate(False)
        self.settings_device_combo = ttk.Combobox(
            self._device_combo_host,
            textvariable=self.settings_device_var,
            values=device_names,
            width=1,
            state="readonly",
            font=("Arial", 10, "bold"),
        )
        self.settings_device_combo.pack(fill=tk.BOTH, expand=True)
        self.settings_device_combo.bind(
            "<<ComboboxSelected>>", lambda _e: self._apply_selected_device_preferences()
        )
        self._schedule_device_combo_align()

    @staticmethod
    def _format_settings_text(data, stop, parity, flow):
        return format_settings_text(data, stop, parity, flow)

    def _format_settings_summary(self):
        return self._format_settings_text(
            self.settings_data_var.get(),
            self.settings_stop_var.get(),
            self.settings_parity_var.get(),
            self.settings_flow_var.get(),
        )

    def _rebuild_device_entries(self):
        devices = self.device_definitions.get("devices", [])
        bases = [self._connected_device_label(item) or "device" for item in devices]
        self._device_entries = list(zip(unique_device_labels(bases), devices))

    def _device_for_unique_label(self, label):
        return next(
            (item for unique, item in self._device_entries if unique == label),
            None,
        )

    def _unique_label_for_device(self, device, found_label=None, baud=None):
        if device is not None:
            for unique, item in self._device_entries:
                if item is device:
                    return unique
        if found_label:
            for unique, item in self._device_entries:
                if self._connected_device_label(item) != found_label:
                    continue
                item_baud = (item.get("serial_parameters") or {}).get("baudrate")
                if baud is None or item_baud == baud:
                    return unique
            return found_label
        return ""

    def _refresh_settings_summary(self):
        self.settings_summary.configure(text=self._format_settings_summary())
        self._schedule_device_combo_align()

    def _selected_port(self):
        port = (self.settings_port_var.get() or "").strip()
        if port in ("", "* All *", NO_PORTS_LABEL):
            return None
        return port

    def _port_row(self, port):
        for entry in self.port_data:
            if entry[1] == port:
                return entry
        return None

    def _include_in_use_ports(self):
        return bool(self.show_in_use_var.get() or self._show_in_use_once)

    def _set_combo_enabled(self, combo, enabled, editable=False):
        if combo is None:
            return
        if not enabled:
            combo.configure(state="disabled")
        else:
            combo.configure(state="normal" if editable else "readonly")

    def _set_button_enabled(self, button, enabled, **kwargs):
        if button is None:
            return
        button.configure(state=tk.NORMAL if enabled else tk.DISABLED, **kwargs)

    def _highlight_tree_port(self, port):
        tree = getattr(self, "tree", None)
        if tree is None or not port:
            return
        try:
            if tree.exists(port):
                current = tree.selection()
                if current != (port,):
                    tree.selection_set(port)
                tree.see(port)
        except tk.TclError:
            pass

    def _on_tree_select(self, _event=None):
        tree = getattr(self, "tree", None)
        if tree is None:
            return
        selection = tree.selection()
        if not selection:
            return
        port = selection[0]
        if self.settings_port_var.get() != port:
            self.settings_port_var.set(port)

    def _on_tree_double_click(self, _event=None):
        select_btn = getattr(self, "select_button", None)
        if select_btn is None:
            return
        if str(select_btn.cget("state")) == str(tk.DISABLED):
            return
        self._on_select_port()

    def _set_message_lines(self, port_text=None, device_text=None):
        if port_text is not None and getattr(self, "port_message_var", None) is not None:
            self.port_message_var.set(port_text)
        if device_text is not None and getattr(self, "device_message_var", None) is not None:
            self.device_message_var.set(device_text)

    def _sync_port_selection_ui(self):
        port = self._selected_port()
        row = self._port_row(port) if port else None
        visible = dropdown_ports(
            [(entry[0], entry[1]) for entry in self.port_data],
            self._include_in_use_ports(),
            extra=(port, self._held_port),
        )
        state = picker_control_state(
            has_ports=bool(visible or port),
            selected_port=port,
            port_status=row[0] if row else None,
            held=bool(port and self._held_port == port),
        )
        self.settings_status_var.set(state["status"])
        self._set_combo_enabled(
            getattr(self, "settings_port_combo", None), state["port"], editable=True
        )
        self._set_combo_enabled(
            getattr(self, "settings_baud_combo", None), state["baud"], editable=True
        )
        self._set_button_enabled(getattr(self, "settings_summary", None), state["settings"])
        self._set_button_enabled(
            getattr(self, "open_port_button", None),
            state["open"],
            text=state["open_label"],
        )
        self._set_combo_enabled(
            getattr(self, "settings_device_combo", None), state["device"]
        )
        self._set_button_enabled(getattr(self, "identify_button", None), state["identify"])
        self._set_button_enabled(getattr(self, "select_button", None), state["select"])
        self._highlight_tree_port(port)

    def _parse_baud(self, text):
        raw = (text or "").strip().upper().replace(" ", "")
        for value, label in BAUD_SHORT:
            if raw == label.upper() or raw == str(value):
                return value
        if raw.endswith("K"):
            return int(float(raw[:-1]) * 1000)
        return int(float(raw))

    def _serial_settings_from_ui(self):
        flow = self.settings_flow_var.get()
        stop_text = (self.settings_stop_var.get() or "1").strip()
        stop_map = {
            "1": serial.STOPBITS_ONE,
            "1.5": serial.STOPBITS_ONE_POINT_FIVE,
            "2": serial.STOPBITS_TWO,
        }
        return {
            "baudrate": self._parse_baud(self.settings_baud_var.get()),
            "parity": UI_TO_PARITY.get(self.settings_parity_var.get(), "N"),
            "bytesize": int(float(self.settings_data_var.get() or 8)),
            "stopbits": stop_map.get(stop_text, serial.STOPBITS_ONE),
            "xonxoff": flow == "XON/XOFF",
            "rtscts": flow == "RTS/CTS",
            "dsrdtr": flow == "DSR/DTR",
        }

    def _device_for_label(self, label):
        device = self._device_for_unique_label(label)
        if device is not None:
            return device
        return next(
            (
                item
                for item in self.device_definitions.get("devices", [])
                if self._connected_device_label(item) == label
            ),
            None,
        )

    def _apply_selected_device_preferences(self):
        if self._suppress_device_apply:
            return
        device = self._device_for_label(self.settings_device_var.get())
        if not device:
            return
        if self._held_port:
            self._set_message_lines(device_text=device_message_text(device))
            return
        params = device.get("serial_parameters") or {}
        baud = params.get("baudrate")
        if baud is not None:
            shown = self.format_baud(baud)
            if shown:
                self.settings_baud_var.set(shown)
        parity = PARITY_TO_UI.get(str(params.get("parity", "N")).upper(), "None")
        self.settings_parity_var.set(parity)
        self.settings_data_var.set(str(int(float(params.get("bytesize", 8)))))
        stop = params.get("stopbits", 1)
        stop_text = str(int(stop)) if float(stop) == int(float(stop)) else str(stop)
        self.settings_stop_var.set(stop_text)
        self.settings_flow_var.set("None")
        self._refresh_settings_summary()
        self._set_message_lines(device_text=device_message_text(device))

    def _release_serial(self):
        ser = self._open_serial
        self._open_serial = None
        if ser is None:
            return
        try:
            ser.close()
        except (serial.SerialException, OSError):
            pass

    def _set_port_row(self, port, *, status=None, device_name=None, baud=None, keep_device=False):
        new_data = []
        for row_status, row_port, vendor_id, name, description, row_baud in self.port_data:
            if row_port != port:
                new_data.append(
                    (row_status, row_port, vendor_id, name, description, row_baud)
                )
                continue
            new_data.append(
                (
                    status if status is not None else row_status,
                    row_port,
                    vendor_id,
                    name if keep_device else device_name,
                    description,
                    row_baud if keep_device else baud,
                )
            )
        self.port_data = new_data
        self.update_ports_from_data()
        self._sync_port_selection_ui()

    def _reopen_held(self, port):
        try:
            settings = self._serial_settings_from_ui()
            self._open_serial = serial.Serial(port, timeout=1, **settings)
            self._held_port = port
            return True
        except (serial.SerialException, OSError, ValueError) as exc:
            self._held_port = None
            self._log(f"Open {port} failed: {exc}")
            return False

    def _on_open_port(self):
        port = self._selected_port()
        if not port:
            return
        if self._held_port == port:
            self._release_serial()
            self._held_port = None
            self._log(f"Closed {port}")
            row = self._port_row(port)
            status = "Identified" if row and row[3] else "Available"
            self._set_port_row(port, status=status, keep_device=True)
            self._set_message_lines(port_text=port_event_message(port, "Closed"))
            return
        self._release_serial()
        self._held_port = None
        if not self._reopen_held(port):
            self._set_message_lines(port_text=f"Port: {port} open failed")
            return
        settings = self._serial_settings_from_ui()
        self._log(
            f"Opened {port} @ {settings['baudrate']} "
            f"{self._format_settings_summary()}"
        )
        self._set_port_row(port, status="Open", keep_device=True)
        self._set_message_lines(port_text=port_event_message(port, "Open"))

    def _apply_connection_scan(self, port, found, settings, was_open):
        if found:
            unique = self._unique_label_for_device(
                None, found_label=found, baud=settings.get("baudrate")
            )
            self._suppress_device_apply = True
            self.settings_device_var.set(unique)
            self._suppress_device_apply = False
            self._set_port_row(
                port,
                status="Identified",
                device_name=found,
                baud=settings.get("baudrate"),
            )
            device = self._device_for_label(unique) or self._device_for_label(found)
            self._set_message_lines(
                port_text=port_event_message(port, "Identified"),
                device_text=device_message_text(device),
            )
        else:
            self._set_message_lines(device_text="Device: not found")
        self._finish_device_scan()
        if was_open and self._reopen_held(port) and not found:
            self._set_port_row(port, status="Open", keep_device=True)
        elif was_open and found:
            self._sync_port_selection_ui()

    def _on_select_port(self):
        port = self._selected_port()
        if not port:
            return
        self._log(f"Selected port: {port}")
        self._on_exit()

    def _on_connection_scan_device(self):
        port = self._selected_port()
        if not port:
            return
        device = self._device_for_label(self.settings_device_var.get())
        if device is None:
            self._log("Select a device before Identify.")
            return
        try:
            settings = self._serial_settings_from_ui()
        except (ValueError, KeyError) as exc:
            self._log(f"Identify settings invalid: {exc}")
            return
        if not self._device_scan_lock.acquire(blocking=False):
            self._log("Device scan already in progress, skipping.")
            return
        self._device_scan_running = True
        was_open = self._held_port == port
        self._release_serial()
        threading.Thread(
            target=self._connection_scan_worker,
            args=(port, settings, device, was_open),
            daemon=True,
        ).start()

    def _probe_open_port(self, ser, device):
        pattern = (device.get("response") or {}).get("regex") or ""
        if not pattern:
            return False
        commands = device.get("commands") or {}
        for key in ("initialize", "identify"):
            command = commands.get(key) or {}
            if "message" not in command or "pause" not in command:
                continue
            ser.write(str(command["message"]).encode())
            time.sleep(command["pause"])
        response = ser.read(ser.in_waiting or 100).decode(errors="ignore")
        return re.search(pattern, response) is not None

    def _connection_scan_worker(self, port, settings, device, was_open):
        label = self._connected_device_label(device) or "device"
        self._log(f"Device scan {port} for {label}...")
        found = None
        try:
            with serial.Serial(port, timeout=2, **settings) as ser:
                if self._probe_open_port(ser, device):
                    found = label
            if found:
                self._log_cont(f"  {port}  FOUND  {found}")
            else:
                self._log_cont(f"  {port}  NOT FOUND")
            self._log_cont("Device scan Done")
        except (serial.SerialException, OSError, ValueError) as exc:
            self._log_cont(f"Device scan failed: {exc}")
        self.root.after(
            0, lambda: self._apply_connection_scan(port, found, settings, was_open)
        )

    def _schedule_device_combo_align(self, event=None):
        if self._device_align_after is not None or self._syncing_device_combo:
            return
        self._device_align_after = self.root.after(1, self._sync_device_combo_width)

    def _sync_device_combo_width(self):
        self._device_align_after = None
        host = getattr(self, "_device_combo_host", None)
        summary = getattr(self, "settings_summary", None)
        if not host or not summary:
            return
        try:
            if not host.winfo_ismapped() or not summary.winfo_ismapped():
                return
            target_right = summary.winfo_rootx() + summary.winfo_width()
            combo_left = host.winfo_rootx()
            width = target_right - combo_left
            if width < 40:
                return
            current = int(host.cget("width") or 0)
            if current == width:
                return
            self._syncing_device_combo = True
            host.configure(width=width)
            self._syncing_device_combo = False
        except tk.TclError:
            self._syncing_device_combo = False

    def _open_port_settings_dialog(self):
        if self._settings_dialog is not None and self._settings_dialog.winfo_exists():
            self._settings_dialog.lift()
            self._settings_dialog.focus_force()
            return

        win = tk.Toplevel(self.root)
        self._settings_dialog = win
        win.title("Port Settings")
        win.configure(bg=UI_BG)
        win.transient(self.root)
        win.resizable(False, False)

        parity_var = tk.StringVar(value=self.settings_parity_var.get())
        data_var = tk.StringVar(value=self.settings_data_var.get())
        stop_var = tk.StringVar(value=self.settings_stop_var.get())
        flow_var = tk.StringVar(value=self.settings_flow_var.get())
        preview_var = tk.StringVar(
            value=self._format_settings_text(
                data_var.get(), stop_var.get(), parity_var.get(), flow_var.get()
            )
        )
        applied_var = tk.StringVar(value=self._format_settings_summary())

        def sync_preview(*_args):
            preview_var.set(
                self._format_settings_text(
                    data_var.get(), stop_var.get(), parity_var.get(), flow_var.get()
                )
            )

        for var in (parity_var, data_var, stop_var, flow_var):
            var.trace_add("write", sync_preview)

        def close_dialog():
            if self._settings_dialog is win:
                self._settings_dialog = None
            win.destroy()

        def on_select():
            self.settings_parity_var.set(parity_var.get())
            self.settings_data_var.set(data_var.get())
            self.settings_stop_var.set(stop_var.get())
            self.settings_flow_var.set(flow_var.get())
            self._refresh_settings_summary()
            close_dialog()

        win.protocol("WM_DELETE_WINDOW", close_dialog)

        shell = tk.Frame(win, bg=UI_ORANGE, padx=3, pady=3)
        shell.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        inner = tk.Frame(shell, bg=UI_BG)
        inner.pack(fill=tk.BOTH, expand=True)

        blue = tk.Frame(
            inner,
            bg=UI_HEADER,
            padx=8,
            pady=6,
            highlightbackground="#000000",
            highlightthickness=1,
            highlightcolor="#000000",
        )
        blue.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        tk.Label(
            blue,
            text="Port Settings",
            bg=UI_HEADER,
            fg="#000000",
            font=("Arial", 11, "bold"),
            anchor="w",
        ).pack(anchor="w", pady=(0, 6))

        white = tk.Frame(blue, bg=UI_BG, padx=8, pady=8)
        white.pack(fill=tk.X)
        white.columnconfigure(0, weight=1)
        white.columnconfigure(1, weight=1)

        def labeled_combo(parent, label, var, values, right=False):
            cell = tk.Frame(parent, bg=UI_BG)
            group = tk.Frame(cell, bg=UI_BG)
            group.pack(side=tk.RIGHT if right else tk.LEFT)
            tk.Label(
                group,
                text=label,
                bg=UI_BG,
                fg=UI_FG,
                font=("Arial", 10, "bold"),
            ).pack(side=tk.LEFT)
            ttk.Combobox(
                group,
                textvariable=var,
                values=values,
                width=5,
                state="readonly",
                font=("Arial", 10, "bold"),
            ).pack(side=tk.LEFT, padx=(4, 0))
            return cell

        labeled_combo(white, "Data Bits:", data_var, DATA_BITS_CHOICES).grid(
            row=0, column=0, sticky="w", pady=2
        )
        labeled_combo(
            white, "Stop Bits:", stop_var, STOP_BITS_CHOICES, right=True
        ).grid(row=0, column=1, sticky="e", pady=2)
        labeled_combo(white, "Parity:", parity_var, PARITY_CHOICES).grid(
            row=1, column=0, sticky="w", pady=2
        )
        labeled_combo(white, "Flow:", flow_var, FLOW_CHOICES, right=True).grid(
            row=1, column=1, sticky="e", pady=2
        )

        select_row = tk.Frame(white, bg=UI_BG)
        select_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        tk.Button(
            select_row,
            text="Select",
            width=10,
            command=on_select,
            bg=UI_BTN_GRAY,
            activebackground="#A8A8A8",
            anchor="center",
            justify="center",
            relief=tk.RAISED,
            font=("Arial", 9, "bold"),
        ).pack(side=tk.RIGHT)
        tk.Entry(
            select_row,
            textvariable=preview_var,
            width=22,
            font=("Arial", 10, "bold"),
            relief=tk.SUNKEN,
            bd=2,
            state="readonly",
            readonlybackground=UI_GREEN,
            fg="#000000",
        ).pack(side=tk.LEFT, padx=(0, 8))

        bottom = tk.Frame(blue, bg=UI_HEADER)
        bottom.pack(fill=tk.X, pady=(8, 0))
        tk.Button(
            bottom,
            text="Exit",
            width=10,
            command=close_dialog,
            bg=UI_BTN_GRAY,
            activebackground="#A8A8A8",
            anchor="center",
            justify="center",
            relief=tk.RAISED,
            font=("Arial", 9, "bold"),
        ).pack(side=tk.RIGHT)
        tk.Entry(
            bottom,
            textvariable=applied_var,
            width=22,
            font=("Arial", 10, "bold"),
            relief=tk.SUNKEN,
            bd=2,
            state="readonly",
            readonlybackground=UI_CURRENT_SETTINGS,
            fg="#000000",
        ).pack(side=tk.LEFT, padx=(0, 8))

        win.bind("<Return>", lambda _e: on_select())
        win.bind("<Escape>", lambda _e: close_dialog())

        win.update_idletasks()
        px = self.root.winfo_rootx() + max(
            0, (self.root.winfo_width() - win.winfo_width()) // 2
        )
        py = self.root.winfo_rooty() + max(
            0, (self.root.winfo_height() - win.winfo_height()) // 2
        )
        win.geometry(f"+{px}+{py}")
        win.grab_set()
        win.focus_force()

    def _build_bottom_bar(self, parent):
        """White bar: message lines left; Exit then Select on the right."""
        self.select_button = tk.Button(
            parent,
            text="Select",
            width=10,
            state=tk.DISABLED,
            command=self._on_select_port,
            bg=UI_BTN_GRAY,
            disabledforeground=UI_DISABLED,
            anchor="center",
            justify="center",
            relief=tk.RAISED,
            font=("Arial", 9, "bold"),
        )
        self.select_button.pack(side=tk.RIGHT, padx=4)

        self.exit_button = tk.Button(
            parent,
            text="Exit",
            command=self._on_exit,
            width=10,
            bg=UI_BTN_GRAY,
            activebackground="#A8A8A8",
            anchor="center",
            justify="center",
            relief=tk.RAISED,
            font=("Arial", 9, "bold"),
        )
        self.exit_button.pack(side=tk.RIGHT, padx=4)

        messages = tk.Frame(parent, bg=UI_BOTTOM)
        messages.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 8))
        self.port_message_var = tk.StringVar(value="")
        self.device_message_var = tk.StringVar(value="")
        tk.Label(
            messages,
            textvariable=self.port_message_var,
            bg=UI_BOTTOM,
            fg=UI_FG,
            font=("Arial", 10, "bold"),
            anchor="w",
            justify="left",
        ).pack(fill=tk.X)
        tk.Label(
            messages,
            textvariable=self.device_message_var,
            bg=UI_BOTTOM,
            fg=UI_FG,
            font=("Arial", 10, "bold"),
            anchor="w",
            justify="left",
        ).pack(fill=tk.X)

    def _on_exit(self):
        self._clear_auto_scans()
        self._release_serial()
        self.root.destroy()

    # ------------------------------------------------------------- helpers
    @staticmethod
    def format_baud(baud):
        if baud is None:
            return None
        try:
            baud = int(baud)
        except (TypeError, ValueError):
            return str(baud)
        return BAUD_SHORT_BY_VALUE.get(baud, str(baud))

    def _id_baud_column(self, status, vendor_id, baud):
        """Port ID when no device; baud used to connect when Identified."""
        if status == "Identified" and baud is not None:
            return self.format_baud(baud)
        return vendor_id if vendor_id else "Unknown"

    def _driver_or_device_column(self, status, device_name, description):
        if status == "Identified" and device_name:
            return device_name
        return description or "Unknown"

    @staticmethod
    def _connected_device_label(device):
        """Identified column: Manufacturer model [- long_description]."""
        name = " ".join(
            p for p in (device.get("manufacturer"), device.get("model")) if p
        ).strip()
        long_desc = (device.get("long_description") or "").strip()
        if name and long_desc:
            return f"{name} - {long_desc}"
        return name or long_desc or None

    @staticmethod
    def _vendor_id_in_list(vendor_id, vendor_ids):
        vid = str(vendor_id)
        return vid in {str(v) for v in vendor_ids}

    def _cancel_auto_port_scan(self):
        if self._auto_port_after_id is not None:
            try:
                self.root.after_cancel(self._auto_port_after_id)
            except tk.TclError:
                pass
            self._auto_port_after_id = None

    def _cancel_auto_device_scan(self):
        if self._auto_device_after_id is not None:
            try:
                self.root.after_cancel(self._auto_device_after_id)
            except tk.TclError:
                pass
            self._auto_device_after_id = None

    def _clear_auto_scans(self):
        """Exit/shutdown: uncheck all and cancel scheduled loops."""
        self._stop_all_auto_repeat()

    def _stop_all_auto_repeat(self):
        in_use, scan_ports, scan_devices = apply_header_button_click(
            self.show_in_use_var.get(),
            self.auto_port_scan_var.get(),
            self.device_scan_var.get(),
        )
        self._suppress_auto_toggle = True
        try:
            self.show_in_use_var.set(in_use)
            self.auto_port_scan_var.set(scan_ports)
            self.device_scan_var.set(scan_devices)
        finally:
            self._suppress_auto_toggle = False
        self._cancel_auto_port_scan()
        self._cancel_auto_device_scan()
        self._device_scan_after_port = False

    def _refresh_settings_port_list(self):
        current = (self.settings_port_var.get() or "").strip()
        if current in ("", "* All *", NO_PORTS_LABEL):
            current = None
        ports = dropdown_ports(
            [(entry[0], entry[1]) for entry in self.port_data],
            self._include_in_use_ports(),
            extra=(current, self._held_port),
        )
        if not ports:
            self.settings_port_combo["values"] = [NO_PORTS_LABEL]
            if self.settings_port_var.get() != NO_PORTS_LABEL:
                self.settings_port_var.set(NO_PORTS_LABEL)
            else:
                self._sync_port_selection_ui()
            if not self.port_data:
                self._set_message_lines(
                    port_text=port_event_message(None, "Closed"),
                    device_text="Device:",
                )
            return
        self.settings_port_combo["values"] = ports
        if current in ports:
            self._sync_port_selection_ui()
            return
        available = next(
            (
                entry[1]
                for entry in self.port_data
                if entry[0] in ("Available", "Identified", "Open") and entry[1] in ports
            ),
            None,
        )
        self.settings_port_var.set(available or ports[0])

    def _log(self, msg, *, end="\n"):
        """Blank line, then the message."""
        with self._log_lock:
            print()
            print(msg, end=end, flush=True)

    def _log_cont(self, msg, *, end="\n"):
        """Continue the current message (no extra blank line)."""
        with self._log_lock:
            print(msg, end=end, flush=True)

    # ----------------------------------------------------- scan / refresh
    def start_initial_scan(self):
        self._log("Starting initial scan...")
        self.scan_ports(full=True)
        if self.auto_port_scan_var.get():
            self.start_auto_port_scan()

    def scan_ports(self, *, full=False):
        """Start a port scan on a background thread."""
        if self._device_scan_running:
            self._log("Port scan paused (device scan running).")
            return
        if not self._port_scan_lock.acquire(blocking=False):
            self._log("Port scan already in progress, skipping.")
            return
        self._port_scan_running = True
        self._port_scan_full = full
        threading.Thread(target=self._scan_ports_worker, daemon=True).start()

    def _comports_by_device(self):
        comports = list(list_ports.comports())
        return comports, {p.device: p for p in comports}

    def _scan_ports_worker(self):
        full = self._port_scan_full
        fast = self.auto_port_scan_var.get() and not full
        self._log("Scanning ports..." + (" (fast)" if fast else ""), end="")
        header_open = True

        def close_header():
            nonlocal header_open
            if header_open:
                print(" Done", flush=True)
                header_open = False

        try:
            comports, by_device = self._comports_by_device()
            current_ports = set(by_device)
            known_ports = set(self.known_ports)
            port_data = list(self.port_data)

            if fast and current_ports == known_ports:
                # Still refresh availability cheaply only on full/manual paths
                self.root.after(0, self._finish_port_scan)
                return

            new_ports = current_ports - known_ports
            known_ports = current_ports
            port_data = [entry for entry in port_data if entry[1] in current_ports]

            if not fast:
                for index, entry in enumerate(port_data):
                    status, port, vendor_id, device_name, description, baud = entry
                    if status in ("Identified", "Open"):
                        # Keep Identified until device scan demotes; keep our Open handle
                        continue
                    is_accessible = self.is_port_available(port)
                    updated_status = "Available" if is_accessible else "In Use"
                    port_data[index] = (
                        updated_status,
                        port,
                        vendor_id,
                        device_name,
                        description,
                        baud if updated_status == "Identified" else None,
                    )

            for port_info in comports:
                if port_info.device not in new_ports:
                    continue
                close_header()
                self._log(f"Testing new port: {port_info.device}")
                status = (
                    "In Use"
                    if not self.is_port_available(port_info.device)
                    else "Available"
                )
                vendor_id = format_vid_pid(port_info.vid, port_info.pid)
                description = port_info.description or "Unknown"
                self._log(
                    f"Adding new port: {port_info.device}, Status: {status}, "
                    f"ID: {vendor_id}, Description: {description}"
                )
                port_data.append(
                    (status, port_info.device, vendor_id, None, description, None)
                )

            self.root.after(
                0,
                lambda: self._apply_port_scan_result(known_ports, port_data),
            )
        except Exception as e:
            close_header()
            self._log(f"Port scan failed: {e}")
            self.root.after(0, self._finish_port_scan)
        finally:
            if header_open:
                print(" Done", flush=True)

    def _apply_port_scan_result(self, known_ports, port_data):
        self.known_ports = known_ports
        self.port_data = port_data
        self.update_ports_from_data()
        self._refresh_settings_port_list()
        self._finish_port_scan()

    def _finish_port_scan(self):
        self._port_scan_running = False
        if self._port_scan_lock.locked():
            self._port_scan_lock.release()
        if self._device_scan_after_port:
            self._device_scan_after_port = False
            if self.device_scan_var.get() and not self._device_scan_running:
                self.scan_available_ports()

    def is_port_available(self, port_name):
        try:
            ser = serial.Serial(port_name, timeout=PORT_OPEN_TIMEOUT)
            ser.close()
            return True
        except (serial.SerialException, OSError):
            return False

    def update_ports_from_data(self):
        selected = self._selected_port()
        extra = (selected, self._held_port)
        self.tree.delete(*self.tree.get_children())
        rows = visible_tree_rows(self.port_data, self._include_in_use_ports(), extra=extra)
        for status, port, vendor_id, device_name, description, baud in rows:
            id_baud = self._id_baud_column(status, vendor_id, baud)
            connected = self._driver_or_device_column(status, device_name, description)
            tags = ("identified",) if status == "Identified" else ()
            self.tree.insert(
                "",
                tk.END,
                iid=port,
                values=(status, port, id_baud, connected),
                tags=tags,
            )
        self._fit_fixed_tree_columns()
        if selected and self.tree.exists(selected):
            self._highlight_tree_port(selected)

    # ---------------------------------------------------- device identify
    def identify_device(self, port, vendor_id):
        return self._identify_device_with_defs(
            port, vendor_id, self.device_definitions
        )

    def _identify_device_with_defs(self, port, vendor_id, device_definitions):
        """Return (connected_device_label_or_None, baud_or_None)."""
        for device in device_definitions["devices"]:
            if not self._vendor_id_in_list(vendor_id, device["vendor_ids"]):
                continue
            baud = device["serial_parameters"]["baudrate"]
            try:
                with serial.Serial(
                    port,
                    baudrate=baud,
                    parity=device["serial_parameters"]["parity"],
                    stopbits=device["serial_parameters"]["stopbits"],
                    bytesize=device["serial_parameters"]["bytesize"],
                    timeout=2,
                ) as ser:
                    init_command = device["commands"]["initialize"]
                    if "message" in init_command and "pause" in init_command:
                        ser.write(init_command["message"].encode())
                        time.sleep(init_command["pause"])

                    id_command = device["commands"]["identify"]
                    if "message" in id_command and "pause" in id_command:
                        ser.write(id_command["message"].encode())
                        time.sleep(id_command["pause"])

                    response = ser.read(ser.in_waiting or 100).decode(errors="ignore")
                    pattern = (device.get("response") or {}).get("regex") or ""
                    if not pattern:
                        continue
                    match = re.search(pattern, response)
                    if match:
                        return self._connected_device_label(device), baud
            except (serial.SerialException, OSError, KeyError):
                continue
        return None, None

    def scan_available_ports(self):
        if not self._device_scan_lock.acquire(blocking=False):
            self._log("Device scan already in progress, skipping.")
            return
        self._device_scan_running = True
        threading.Thread(target=self._scan_devices_worker, daemon=True).start()

    def _scan_devices_worker(self):
        self._log("Device scan...")
        try:
            device_definitions = self.device_definitions
            _, by_device = self._comports_by_device()
            # port -> (device_name, baud) or None to demote
            updates = {}
            for status, port, vendor_id, device_name, description, baud in self.port_data:
                if status == "In Use":
                    self._log_cont(f"  {port}  skipped (In Use)")
                    continue
                if status not in ("Available", "Identified"):
                    continue
                p = by_device.get(port)
                vid = str(p.vid) if p and p.vid else vendor_id
                identified_device, found_baud = self._identify_device_with_defs(
                    port, vid, device_definitions
                )
                if identified_device:
                    self._log_cont(
                        f"  {port}  VID {vid}  FOUND  {identified_device} @ {found_baud}"
                    )
                    updates[port] = (identified_device, found_baud)
                else:
                    self._log_cont(f"  {port}  VID {vid}  NOT FOUND")
                    if status == "Identified":
                        updates[port] = None  # demote
            self._log_cont("Device scan Done")
            self.root.after(0, lambda u=updates: self._apply_device_scan_result(u))
        except Exception as e:
            self._log_cont(f"Device scan failed: {e}")
            self.root.after(0, self._finish_device_scan)

    def _apply_device_scan_result(self, updates):
        if updates:
            new_data = []
            for status, port, vendor_id, device_name, description, baud in self.port_data:
                if port not in updates:
                    new_data.append(
                        (status, port, vendor_id, device_name, description, baud)
                    )
                    continue
                result = updates[port]
                if result is None:
                    # demote Identified → Available
                    new_data.append(
                        ("Available", port, vendor_id, None, description, None)
                    )
                else:
                    name, found_baud = result
                    new_data.append(
                        (
                            "Identified",
                            port,
                            vendor_id,
                            name,
                            description,
                            found_baud,
                        )
                    )
            self.port_data = new_data
        self.update_ports_from_data()
        self._finish_device_scan()

    def _finish_device_scan(self):
        self._device_scan_running = False
        if self._device_scan_lock.locked():
            self._device_scan_lock.release()

    def retest_available_ports(self):
        """One-shot: refresh port availability + identify devices."""
        if self._device_scan_running:
            self._log("Device scan already in progress, skipping retest.")
            return
        if not self._port_scan_lock.acquire(blocking=False):
            self._log("Port scan already in progress, skipping retest.")
            return
        self._port_scan_running = True
        self._device_scan_running = True
        self._device_scan_after_port = False
        threading.Thread(target=self._retest_ports_worker, daemon=True).start()

    def _retest_ports_worker(self):
        self._log("Device scan...")
        try:
            with open("devices.json", "r") as f:
                device_definitions = json.load(f)

            comports, by_device = self._comports_by_device()
            known_ports = set(by_device)
            port_data = []
            held = self._held_port
            held_entry = next(
                (entry for entry in self.port_data if entry[1] == held),
                None,
            )

            for port_info in comports:
                if held and port_info.device == held and held_entry is not None:
                    port_data.append(held_entry)
                    self._log_cont(
                        f"  {port_info.device}  skipped (held open by this app)"
                    )
                    continue
                status = (
                    "In Use"
                    if not self.is_port_available(port_info.device)
                    else "Available"
                )
                vendor_id = format_vid_pid(port_info.vid, port_info.pid)
                match_vid = str(port_info.vid) if port_info.vid else vendor_id
                description = port_info.description or "Unknown"
                device_name = None
                baud = None
                if status == "In Use":
                    self._log_cont(
                        f"  {port_info.device}  VID {vendor_id}  skipped (In Use)"
                    )
                else:
                    identified, found_baud = self._identify_device_with_defs(
                        port_info.device, match_vid, device_definitions
                    )
                    if identified:
                        status = "Identified"
                        device_name = identified
                        baud = found_baud
                        self._log_cont(
                            f"  {port_info.device}  ID {vendor_id}  FOUND  "
                            f"{identified} @ {found_baud}"
                        )
                    else:
                        self._log_cont(
                            f"  {port_info.device}  ID {vendor_id}  NOT FOUND"
                        )
                port_data.append(
                    (
                        status,
                        port_info.device,
                        vendor_id,
                        device_name,
                        description,
                        baud,
                    )
                )

            self._log_cont("Device scan Done")
            self.root.after(
                0,
                lambda: self._apply_retest_result(
                    device_definitions, known_ports, port_data
                ),
            )
        except Exception as e:
            self._log_cont(f"Device scan failed: {e}")
            self.root.after(0, self._finish_retest_scan)

    def _apply_retest_result(self, device_definitions, known_ports, port_data):
        self.device_definitions = device_definitions
        self._rebuild_device_entries()
        names = [label for label, _device in self._device_entries] or ["(no devices)"]
        if getattr(self, "settings_device_combo", None) is not None:
            self.settings_device_combo["values"] = names
        self.known_ports = known_ports
        self.port_data = port_data
        self.update_ports_from_data()
        self._refresh_settings_port_list()
        self._finish_retest_scan()

    def _finish_retest_scan(self):
        self._device_scan_after_port = False
        self._finish_port_scan()
        self._finish_device_scan()

    # ------------------------------------------------------ control handlers
    def toggle_ports_in_use(self):
        if self._suppress_auto_toggle:
            return
        self._log(f"'In Use' checkbox toggled: {self.show_in_use_var.get()}")
        self._show_in_use_once = False
        self.update_ports_from_data()
        self._refresh_settings_port_list()
        if self.show_in_use_var.get() or self.auto_port_scan_var.get():
            self.start_auto_port_scan()
        elif not self.auto_port_scan_var.get():
            self._cancel_auto_port_scan()

    def toggle_auto_port_scan(self):
        if self._suppress_auto_toggle:
            return
        self._log(f"'Scan Ports' checkbox toggled: {self.auto_port_scan_var.get()}")
        if self.auto_port_scan_var.get() or self.show_in_use_var.get():
            self.start_auto_port_scan()
        else:
            self._cancel_auto_port_scan()

    def toggle_device_scan(self):
        if self._suppress_auto_toggle:
            return
        self._log(f"'Scan Devices' checkbox toggled: {self.device_scan_var.get()}")
        if self.device_scan_var.get():
            self.start_device_scan()
        else:
            self._device_scan_after_port = False
            self._cancel_auto_device_scan()
            # Leave Identified rows as-is; just stop auto

    def start_auto_port_scan(self):
        if not (self.auto_port_scan_var.get() or self.show_in_use_var.get()):
            self._auto_port_after_id = None
            return
        if self._device_scan_running:
            self._auto_port_after_id = self.root.after(
                AUTO_PORT_SCAN_MS, self.start_auto_port_scan
            )
            return
        if not self._port_scan_running:
            self.scan_ports(full=False)
        self._auto_port_after_id = self.root.after(
            AUTO_PORT_SCAN_MS, self.start_auto_port_scan
        )

    def start_device_scan(self):
        if not self.device_scan_var.get():
            self._auto_device_after_id = None
            return
        if not self._device_scan_running and not self._device_scan_after_port:
            if self.auto_port_scan_var.get():
                self._device_scan_after_port = True
                if not self._port_scan_running:
                    self.scan_ports(full=False)
            else:
                self.scan_available_ports()
        self._auto_device_after_id = self.root.after(
            AUTO_DEVICE_SCAN_MS, self.start_device_scan
        )

    def on_in_use_button(self):
        """One-shot: show In Use ports, then stop all auto-repeat."""
        self._log("In Use button clicked")
        self._stop_all_auto_repeat()
        self._show_in_use_once = True
        self.update_ports_from_data()
        self._refresh_settings_port_list()
        self.scan_ports(full=True)

    def on_scan_ports_button(self):
        self._log("Scan Ports button clicked")
        self._stop_all_auto_repeat()
        self._show_in_use_once = False
        self.scan_ports(full=True)

    def on_scan_devices_button(self):
        self._log("Scan Devices button clicked")
        self._stop_all_auto_repeat()
        self.retest_available_ports()


if __name__ == "__main__":
    root = tk.Tk()
    app = SerialPortApp(root)
    root.mainloop()
