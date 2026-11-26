
#! Run from this folder: .\run.bat
#! PowerShell venv: .\.venv\Scripts\Activate.ps1   then   python .\serial_port_app.py

import tkinter as tk
import tkinter.ttk as ttk
import tkinter.font as tkfont
from serial.tools import list_ports  # requires pyserial package: pip install pyserial
import serial  # requires pyserial package: pip install pyserial
import re
import threading
import time

from device_data import (
    baud_rates_for_device,
    command_steps,
    connected_device_label,
    default_baud,
    device_matches_ids,
    format_device_column,
    load_device_file,
    migrate_device,
    parse_usb_id,
)
from picker_logic import (
    BAUD_SHORT,
    DATA_BITS_CHOICES,
    DEFAULT_PARITY,
    FLOW_CHOICES,
    FLOW_XOFF_XON,
    PARITY_CHOICES,
    PORT_STATUS_CLOSED,
    PORT_STATUS_FAILED,
    PORT_STATUS_OPENED,
    PORT_STATUS_UNKNOWN,
    DEVICE_STATUS_UNIDENTIFIED,
    STOP_BITS_CHOICES,
    apply_header_button_click,
    check_button_char_width,
    dropdown_ports,
    format_baud_label,
    format_settings_text,
    format_vid_pid,
    identified_device_message,
    longest_settings_text,
    normalize_flow_choice,
    picker_control_state,
    picker_device_label,
    unique_device_labels,
    visible_tree_rows,
)

DEVICES_JSON = "devices.json"

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

PARITY_TO_UI = {"N": "None", "E": "Even", "O": "Odd", "M": "Mark", "S": "Space"}
UI_TO_PARITY = {label: code for code, label in PARITY_TO_UI.items()}
UI_PAD = 8
UI_GAP = 8
UI_GROUP_GAP = 16
UI_CONTROL_H = 24
UI_BTN_W = 96
UI_TITLE_H = 28
UI_OUTLINE = "#A0A0A0"
UI_TREE_ROWS = 6
UI_TREE_CELL_PAD = 2
UI_TREE_COL_WIDTHS = {
    "Status": 80,
    "Port #": 170,
    "ID/Baud": 110,
}
LONGEST_PORT_SAMPLE = "/tmp/serialdemo/ttyUSB0"
UI_FONT_CANDIDATES = ("Segoe UI", "Noto Sans", "DejaVu Sans", "Arial")
UI_FONT_SIZE = 9


class SerialPortApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Serial Port Application v{APP_VERSION}")
        self.root.geometry("780x560")
        self.root.minsize(740, 500)
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
        self._identified_device_by_port = {}
        self._port_bottom_status_by_port = {}
        self._suppress_port_status_event = False
        self._devices_load_error = None

        self.device_definitions, self._devices_load_error = load_device_file(
            DEVICES_JSON
        )
        self._rebuild_device_entries()

        self._init_fonts()
        style = ttk.Style()
        style.configure(
            "Treeview",
            font=self._font_control,
            rowheight=UI_CONTROL_H,
            borderwidth=0,
            relief=tk.FLAT,
            padding=UI_TREE_CELL_PAD,
            background="#FFFFFF",
            fieldbackground="#FFFFFF",
            foreground=UI_FG,
        )
        style.configure(
            "Treeview.Heading", font=self._font_label, foreground="#000000"
        )
        style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        style.configure(
            "Picker.TCombobox",
            font=self._font_control,
            fieldbackground="#FFFFFF",
            background="#FFFFFF",
            foreground=UI_FG,
            relief=tk.FLAT,
            borderwidth=0,
            padding=1,
        )
        style.map(
            "Treeview",
            background=[("selected", UI_ROW_SELECTED)],
            foreground=[("selected", "#000000")],
        )
        style.map(
            "Picker.TCombobox",
            foreground=[("disabled", UI_DISABLED)],
            fieldbackground=[("disabled", "#F0F0F0"), ("readonly", "#FFFFFF")],
            arrowcolor=[("disabled", UI_DISABLED)],
        )

        self.show_in_use_var = tk.BooleanVar(value=False)
        self.auto_port_scan_var = tk.BooleanVar(value=True)
        self.device_scan_var = tk.BooleanVar(value=False)

        self._build_ui()
        self.root.update_idletasks()
        self._size_settings_summary()
        req_w = max(740, self.root.winfo_reqwidth())
        req_h = max(500, self.root.winfo_reqheight())
        self.root.minsize(req_w, req_h)
        self.root.after(100, self.start_initial_scan)

    # ------------------------------------------------------------------ UI
    def _init_fonts(self):
        """Segoe UI on Windows; a close sans-serif if that face is missing."""
        try:
            available = set(tkfont.families())
        except tk.TclError:
            available = set()
        family = next(
            (name for name in UI_FONT_CANDIDATES if name in available),
            "TkDefaultFont",
        )
        self._font_family = family
        self._font_control = (family, UI_FONT_SIZE)
        self._font_label = (family, UI_FONT_SIZE, "bold")
        self._font_title = (family, UI_FONT_SIZE, "bold")
        self._font_button = (family, UI_FONT_SIZE, "bold")
        self._font_body = self._font_control
        self._control_font = tkfont.Font(family=family, size=UI_FONT_SIZE)
        self._label_font = tkfont.Font(family=family, size=UI_FONT_SIZE, weight="bold")

    def _outline_box(self, parent, bg="#FFFFFF", height=None, width=None):
        box = tk.Frame(
            parent,
            bg=bg,
            highlightbackground=UI_OUTLINE,
            highlightthickness=1,
            highlightcolor=UI_OUTLINE,
            bd=0,
            relief=tk.FLAT,
        )
        if height is not None:
            box.configure(height=height)
        if width is not None:
            box.configure(width=width)
        return box

    def _blue_box(self, parent, padx=UI_PAD, pady=UI_PAD):
        return tk.Frame(
            parent,
            bg=UI_HEADER,
            padx=padx,
            pady=pady,
            highlightbackground="#000000",
            highlightthickness=1,
            highlightcolor="#000000",
        )

    def _white_box(self, parent):
        return tk.Frame(
            parent,
            bg="#FFFFFF",
            padx=UI_PAD,
            pady=UI_PAD,
            highlightbackground=UI_OUTLINE,
            highlightthickness=1,
            highlightcolor=UI_OUTLINE,
            bd=0,
            relief=tk.FLAT,
        )

    def _field_label(self, parent, text, bg):
        return tk.Label(
            parent,
            text=text,
            bg=bg,
            fg=UI_FG,
            font=self._font_label,
            anchor="w",
            justify="left",
        )

    def _chars_for_text(self, text, extra_px=0):
        avg = max(self._control_font.measure("0"), 1)
        need = self._control_font.measure(str(text)) + extra_px
        return max(4, (need + avg - 1) // avg)

    def _lock_control_size(self, wrap, inner, extra_w=4):
        """Freeze 24px height from the inner widget's character width, then pack."""
        try:
            inner.update_idletasks()
            width = max(int(inner.winfo_reqwidth()) + extra_w, 48)
        except tk.TclError:
            width = 48
        wrap.configure(width=width, height=UI_CONTROL_H)
        wrap.pack_propagate(False)

    def _outlined_combo(self, parent, var, values, width, editable=False, bg="#FFFFFF"):
        wrap = self._outline_box(parent, bg=bg)
        state = "normal" if editable else "readonly"
        combo = ttk.Combobox(
            wrap,
            textvariable=var,
            values=values,
            width=width,
            state=state,
            font=self._font_control,
            style="Picker.TCombobox",
        )
        self._lock_control_size(wrap, combo)
        combo.pack(fill=tk.BOTH, expand=True, padx=2, pady=0)
        return wrap, combo

    def _outlined_entry(self, parent, var, width, readonly=True, bg="#FFFFFF"):
        wrap = self._outline_box(parent, bg=bg)
        entry = tk.Entry(
            wrap,
            textvariable=var,
            width=width,
            font=self._font_control,
            relief=tk.FLAT,
            bd=0,
            highlightthickness=0,
            fg=UI_FG,
            disabledforeground=UI_DISABLED,
            readonlybackground=bg,
            background=bg,
        )
        if readonly:
            entry.configure(state="readonly")
        self._lock_control_size(wrap, entry)
        entry.pack(fill=tk.BOTH, expand=True, padx=4, pady=0)
        return wrap, entry

    def _flat_button(self, parent, text, command=None, width_px=UI_BTN_W):
        wrap = self._outline_box(parent, bg=UI_BTN_GRAY, height=UI_CONTROL_H, width=width_px)
        wrap.pack_propagate(False)
        button = tk.Button(
            wrap,
            text=text,
            command=command,
            bg=UI_BTN_GRAY,
            activebackground="#A8A8A8",
            disabledforeground=UI_DISABLED,
            fg=UI_FG,
            font=self._font_button,
            relief=tk.FLAT,
            bd=0,
            highlightthickness=0,
            anchor="center",
            justify="center",
            padx=0,
            pady=0,
        )
        button.pack(fill=tk.BOTH, expand=True)
        return wrap, button

    def _button_column(self, parent, bg, text, command=None):
        """Label spacer + 96px button so the button lines up with fields below labels."""
        col = tk.Frame(parent, bg=bg)
        self._field_label(col, " ", bg).pack(anchor="w")
        wrap, button = self._flat_button(col, text, command=command)
        wrap.pack(anchor="e")
        return col, wrap, button

    def _build_ui(self):
        # One orange border around the whole UI; 8px padding inside it.
        shell = tk.Frame(self.root, bg=UI_ORANGE, padx=3, pady=3)
        shell.pack(fill=tk.BOTH, expand=True)

        main = tk.Frame(shell, bg=UI_BG)
        main.pack(fill=tk.BOTH, expand=True, padx=UI_PAD, pady=UI_PAD)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=0)
        main.rowconfigure(1, weight=0)
        main.rowconfigure(2, weight=0)
        main.rowconfigure(3, weight=0)

        title_strip = self._blue_box(main, padx=UI_PAD, pady=0)
        title_strip.configure(height=UI_TITLE_H)
        title_strip.pack_propagate(False)
        title_strip.grid(row=0, column=0, sticky="ew", pady=(0, UI_GAP))
        tk.Label(
            title_strip,
            text="Port & Device Identification",
            bg=UI_HEADER,
            fg="#000000",
            font=self._font_title,
            anchor="w",
        ).pack(side=tk.LEFT, fill=tk.Y)

        status_box = self._blue_box(main)
        status_box.grid(row=1, column=0, sticky="ew", pady=(0, UI_GAP))
        self._build_status_tree(status_box)

        settings_box = self._blue_box(main)
        settings_box.grid(row=2, column=0, sticky="ew", pady=(0, UI_GAP))
        self._build_port_settings_scaffold(settings_box)

        # Match Open/Identify inset: blue pad + white outline + white pad.
        bottom_inset = 1 + UI_PAD + 1 + UI_PAD
        bottom = tk.Frame(main, bg=UI_BOTTOM)
        bottom.grid(row=3, column=0, sticky="ew", padx=bottom_inset)
        self._build_bottom_bar(bottom)
        self._sync_port_selection_ui()
        self._refresh_device_ui(apply_baud=True)
        self._refresh_identified_device_message()
        if self._devices_load_error:
            self._set_message_lines(device_text=self._devices_load_error)

    def _build_status_tree(self, parent):
        """Automated box: title + check-buttons, then column titles and the port list."""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=0)

        header = tk.Frame(parent, bg=UI_HEADER)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, UI_GAP))
        self._build_status_header(header)

        cols = (
            ("Status", "w", UI_TREE_COL_WIDTHS["Status"]),
            ("Port #", "w", UI_TREE_COL_WIDTHS["Port #"]),
            ("ID/Baud", "w", UI_TREE_COL_WIDTHS["ID/Baud"]),
            ("Serial Driver / Connected Device", "w", 280),
        )
        self._tree_cols = [c[0] for c in cols]

        self._tree_header = tk.Frame(parent, bg=UI_HEADER)
        self._tree_header.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, UI_TREE_CELL_PAD))
        self._tree_header_labels = []
        for i, (name, anchor, _width) in enumerate(cols):
            lbl = tk.Label(
                self._tree_header,
                text=name,
                bg=UI_HEADER,
                fg="#000000",
                font=self._font_label,
                anchor=anchor,
                justify="left",
            )
            lbl.grid(
                row=0,
                column=i,
                sticky="nsew",
                padx=(UI_TREE_CELL_PAD, 0),
            )
            self._tree_header_labels.append(lbl)
        self._tree_header_scroll_pad = tk.Frame(self._tree_header, bg=UI_HEADER, width=18)
        self._tree_header_scroll_pad.grid(row=0, column=len(cols), sticky="ns")

        tree_host = tk.Frame(
            parent, bg="#FFFFFF", height=UI_TREE_ROWS * UI_CONTROL_H
        )
        tree_host.grid(row=2, column=0, sticky="ew")
        tree_host.pack_propagate(False)
        self.tree = ttk.Treeview(
            tree_host,
            columns=self._tree_cols,
            show="",  # titles are in blue area above
            height=UI_TREE_ROWS,
        )
        for name, anchor, width in cols:
            stretch = name not in UI_TREE_COL_WIDTHS
            self.tree.column(
                name,
                width=width,
                minwidth=width if name in UI_TREE_COL_WIDTHS else 40,
                anchor=anchor,
                stretch=stretch,
            )
        self.tree.pack(fill=tk.BOTH, expand=True)

        scroll = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.grid(row=2, column=1, sticky="ns")
        self._tree_host = tree_host
        self._tree_scrollbar = scroll

        self._tree_body_font = self._control_font
        self._tree_header_font = self._label_font
        self._tree_identified_font = self._label_font
        self.tree.tag_configure("identified", font=self._tree_identified_font)
        self._fixed_tree_cols = ("Status", "Port #", "ID/Baud")

        self.tree.bind("<Configure>", self._sync_tree_header_widths)
        parent.bind("<Configure>", self._sync_tree_header_widths)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Double-1>", self._on_tree_double_click)
        self.root.after(50, self._apply_tree_column_widths)
        self.root.after(60, self._sync_tree_header_widths)

    def _text_px(self, text, bold=False):
        font = self._tree_header_font if bold else self._tree_body_font
        return font.measure(str(text))

    def _apply_tree_column_widths(self):
        """Fixed Iris widths: Status 80, Port 170, ID/Baud 110; driver fills the rest."""
        if not getattr(self, "tree", None):
            return
        try:
            for col, width in UI_TREE_COL_WIDTHS.items():
                self.tree.column(col, width=width, minwidth=width, stretch=False)
            self._sync_tree_header_widths()
            self._fit_tree_host()
        except tk.TclError:
            pass

    def _fit_tree_host(self):
        """Keep the list viewport at exactly 6 data rows, no leftover heading strip."""
        host = getattr(self, "_tree_host", None)
        tree = getattr(self, "tree", None)
        if host is None or tree is None:
            return
        try:
            tree.update_idletasks()
            row_h = UI_CONTROL_H
            for iid in tree.get_children():
                bbox = tree.bbox(iid)
                if bbox and bbox[3]:
                    row_h = bbox[3]
                    break
            host.configure(height=row_h * UI_TREE_ROWS)
        except tk.TclError:
            pass

    def _fit_fixed_tree_columns(self):
        self._apply_tree_column_widths()

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

    def _build_check_button(self, parent, label, var, on_toggle, on_button, bg=None, padx=(0, 0)):
        """Checkbox on the button's left edge; label fully to the right of it."""
        cell_bg = bg if bg is not None else UI_PANEL
        cell = tk.Frame(parent, bg=cell_bg)
        cell.pack(side=tk.LEFT, padx=padx)
        btn_font = self._label_font
        avg_char = max(btn_font.measure("0"), 1)
        gap_px = btn_font.measure(" ")
        wrap = self._outline_box(cell, bg=UI_BTN_GRAY)
        cb = tk.Checkbutton(
            wrap,
            variable=var,
            command=on_toggle,
            bg=UI_BTN_GRAY,
            activebackground=UI_BTN_GRAY,
            selectcolor=UI_BOTTOM,
            highlightthickness=0,
            bd=0,
        )
        try:
            cb.update_idletasks()
            checkbox_px = max(int(cb.winfo_reqwidth()), 1)
        except tk.TclError:
            checkbox_px = 16
        width_chars = check_button_char_width(
            btn_font.measure(label),
            checkbox_px,
            gap_px,
            avg_char,
        )
        inner_w = max(
            width_chars * avg_char + 8,
            checkbox_px + btn_font.measure(label) + 16,
        )
        btn = tk.Button(
            wrap,
            text=label,
            command=on_button,
            font=self._font_button,
            bg=UI_BTN_GRAY,
            activebackground="#A8A8A8",
            disabledforeground=UI_DISABLED,
            fg=UI_FG,
            anchor="e",
            justify="right",
            relief=tk.FLAT,
            bd=0,
            highlightthickness=0,
            padx=4,
            pady=0,
        )
        wrap.configure(width=inner_w, height=UI_CONTROL_H)
        wrap.pack_propagate(False)
        wrap.pack()
        btn.pack(fill=tk.BOTH, expand=True)
        if not hasattr(self, "_header_check_wraps"):
            self._header_check_wraps = []
        self._header_check_wraps.append(wrap)

        def _place_checkbox():
            try:
                wrap.update_idletasks()
                btn.update_idletasks()
                y = max(0, (int(btn.winfo_height()) - int(cb.winfo_reqheight())) // 2)
            except tk.TclError:
                y = 1
            cb.place(in_=btn, x=4, y=y, anchor="nw")
            # Created before the Button, so lift it or Tk draws it underneath.
            cb.lift(btn)

        _place_checkbox()
        self.root.after(1, _place_checkbox)

    def _build_status_header(self, parent):
        """Automated title left; checkbox-on-button controls right-aligned, 16px apart."""
        tk.Label(
            parent,
            text="Automated",
            bg=UI_HEADER,
            fg="#000000",
            font=self._font_title,
            anchor="w",
        ).pack(side=tk.LEFT, fill=tk.Y)

        trio = tk.Frame(parent, bg=UI_HEADER)
        # Align with Open/Identify: white-box outline + inner pad.
        trio.pack(side=tk.RIGHT, padx=(0, 1 + UI_PAD))
        self._build_check_button(
            trio,
            "In Use",
            self.show_in_use_var,
            self.toggle_ports_in_use,
            self.on_in_use_button,
            bg=UI_HEADER,
            padx=(0, UI_GROUP_GAP),
        )
        self._build_check_button(
            trio,
            "Scan Ports",
            self.auto_port_scan_var,
            self.toggle_auto_port_scan,
            self.on_scan_ports_button,
            bg=UI_HEADER,
            padx=(0, UI_GROUP_GAP),
        )
        self._build_check_button(
            trio,
            "Scan Devices",
            self.device_scan_var,
            self.toggle_device_scan,
            self.on_scan_devices_button,
            bg=UI_HEADER,
            padx=(0, 0),
        )

    def _build_port_settings_scaffold(self, parent):
        """Manually box: white Port row, white Device row. No Status field."""
        tk.Label(
            parent,
            text="Manually",
            bg=UI_HEADER,
            fg="#000000",
            font=self._font_title,
            anchor="w",
        ).pack(anchor="w", pady=(0, UI_GAP))

        self.settings_port_var = tk.StringVar(value=NO_PORTS_LABEL)
        self.settings_baud_var = tk.StringVar(value="115.2K")
        self.settings_device_var = tk.StringVar(value="")
        self.settings_summary_var = tk.StringVar(value="")
        self.settings_parity_var = tk.StringVar(value=DEFAULT_PARITY)
        self.settings_data_var = tk.StringVar(value="8")
        self.settings_stop_var = tk.StringVar(value="1")
        self.settings_flow_var = tk.StringVar(value="None")
        self.settings_summary_var.set(self._format_settings_summary())

        white = "#FFFFFF"
        box1 = self._white_box(parent)
        box1.pack(fill=tk.X)
        box1.columnconfigure(0, weight=1)

        port_col = tk.Frame(box1, bg=white)
        port_col.grid(row=0, column=0, sticky="nsew")
        self._field_label(port_col, "Port", white).pack(anchor="w")
        port_width = self._chars_for_text(LONGEST_PORT_SAMPLE, extra_px=18)
        port_wrap, self.settings_port_combo = self._outlined_combo(
            port_col,
            self.settings_port_var,
            [NO_PORTS_LABEL],
            port_width,
            editable=True,
        )
        port_wrap.pack(fill=tk.X)
        self.settings_port_combo.bind(
            "<<ComboboxSelected>>", lambda _e: self._sync_port_selection_ui()
        )
        self.settings_port_var.trace_add(
            "write", lambda *_a: self._sync_port_selection_ui()
        )

        baud_col = tk.Frame(box1, bg=white)
        baud_col.grid(row=0, column=1, sticky="nw", padx=(UI_GROUP_GAP, 0))
        self._field_label(baud_col, "Baud", white).pack(anchor="w")
        baud_wrap, self.settings_baud_combo = self._outlined_combo(
            baud_col,
            self.settings_baud_var,
            self._baud_labels_for_device(None),
            8,
            editable=True,
        )
        baud_wrap.pack(anchor="w")
        self.settings_baud_combo.bind(
            "<<ComboboxSelected>>", lambda _e: self._mark_port_status_unknown()
        )

        settings_col = tk.Frame(box1, bg=white)
        settings_col.grid(row=0, column=2, sticky="nw", padx=(UI_GROUP_GAP, 0))
        self._field_label(settings_col, "Settings", white).pack(anchor="w")
        settings_width = self._chars_for_text(longest_settings_text(), extra_px=8)
        settings_wrap, self.settings_summary = self._outlined_entry(
            settings_col, self.settings_summary_var, settings_width
        )
        settings_wrap.pack(anchor="w")
        self.settings_summary.bind("<Button-1>", self._on_settings_field_click)

        open_col, self._open_wrap, self.open_port_button = self._button_column(
            box1, white, "Open", command=self._on_open_port
        )
        open_col.grid(row=0, column=3, sticky="ne", padx=(UI_GROUP_GAP, 0))
        self.open_port_button.configure(state=tk.DISABLED)

        box2 = self._white_box(parent)
        box2.pack(fill=tk.X, pady=(UI_GAP, 0))
        box2.columnconfigure(0, weight=1)

        device_col = tk.Frame(box2, bg=white)
        device_col.grid(row=0, column=0, sticky="nsew")
        self._field_label(device_col, "Device", white).pack(anchor="w")
        device_names = [label for label, _device in self._device_entries]
        if not device_names:
            device_names = ["(no devices)"]
        self.settings_device_var.set(device_names[0])
        device_wrap, self.settings_device_combo = self._outlined_combo(
            device_col,
            self.settings_device_var,
            device_names,
            1,
            editable=False,
        )
        device_wrap.pack(fill=tk.X)
        self.settings_device_combo.bind(
            "<<ComboboxSelected>>", lambda _e: self._apply_selected_device_preferences()
        )
        self._device_combo_host = device_wrap

        identify_col, self._identify_wrap, self.identify_button = self._button_column(
            box2, white, "Identify", command=self._on_connection_scan_device
        )
        identify_col.grid(row=0, column=1, sticky="ne", padx=(UI_GROUP_GAP, 0))
        self.identify_button.configure(state=tk.DISABLED)
        self.scan_device_button = self.identify_button

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

    def _char_width_for_text(self, text, font, extra_px=None):
        """Tk width= chars so `text` plus padding still fits."""
        if extra_px is None:
            extra_px = 2 * UI_PAD
        avg = max(font.measure("0"), 1)
        need = font.measure(str(text)) + extra_px
        return max(4, (need + avg - 1) // avg)

    def _size_settings_summary(self):
        field = getattr(self, "settings_summary", None)
        if field is None:
            return
        field.configure(width=self._chars_for_text(longest_settings_text(), extra_px=8))
        self._lock_control_size(field.master, field)

    def _on_settings_field_click(self, _event=None):
        field = getattr(self, "settings_summary", None)
        if field is None or str(field.cget("state")) == str(tk.DISABLED):
            return
        self._open_port_settings_dialog()

    def _rebuild_device_entries(self):
        devices = self.device_definitions.get("devices", [])
        bases = []
        for item in devices:
            baud = default_baud(item)
            bases.append(picker_device_label(item, self.format_baud(baud)) or "device")
        self._device_entries = list(zip(unique_device_labels(bases), devices))

    def _baud_labels_for_device(self, device):
        labels = []
        for baud in baud_rates_for_device(device):
            shown = self.format_baud(baud)
            labels.append(shown if shown else str(baud))
        return labels

    def _refresh_baud_dropdown(self, device=None, *, apply_default=False):
        combo = getattr(self, "settings_baud_combo", None)
        if combo is None:
            return
        if device is None:
            device = self._device_for_label(self.settings_device_var.get())
        labels = self._baud_labels_for_device(device)
        combo["values"] = labels
        if apply_default and labels:
            default = default_baud(device)
            shown = self.format_baud(default) if default is not None else None
            self.settings_baud_var.set(shown or labels[0])

    def _refresh_device_ui(self, *, apply_baud=False):
        self._rebuild_device_entries()
        names = [label for label, _device in self._device_entries] or ["(no devices)"]
        combo = getattr(self, "settings_device_combo", None)
        if combo is not None:
            current = self.settings_device_var.get()
            combo["values"] = names
            if current not in names:
                self.settings_device_var.set(names[0])
        device = self._device_for_label(self.settings_device_var.get())
        self._refresh_baud_dropdown(
            device, apply_default=apply_baud and not self._held_port
        )

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
                item_bauds = (item.get("serial_parameters") or {}).get("baud_rates") or []
                if baud is None or baud in item_bauds:
                    return unique
            return found_label
        return ""

    def _refresh_settings_summary(self):
        text = self._format_settings_summary()
        if getattr(self, "settings_summary_var", None) is not None:
            self.settings_summary_var.set(text)
        field = getattr(self, "settings_summary", None)
        if field is not None and isinstance(field, tk.Button):
            field.configure(text=text)

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
        if isinstance(button, tk.Entry):
            extra = {key: value for key, value in kwargs.items() if key != "text"}
            button.configure(
                state="readonly" if enabled else tk.DISABLED,
                **extra,
            )
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
        port_var = getattr(self, "port_status_var", None) or getattr(
            self, "port_message_var", None
        )
        device_var = getattr(self, "device_status_var", None) or getattr(
            self, "device_message_var", None
        )
        if port_text is not None and port_var is not None:
            port_var.set(port_text)
        if device_text is not None and device_var is not None:
            if self._devices_load_error and not self._device_entries:
                device_var.set(self._devices_load_error)
            else:
                device_var.set(device_text)

    def _store_bottom_port_status(self, port, status):
        if port:
            self._port_bottom_status_by_port[port] = status
        self._set_message_lines(port_text=status)

    def _show_bottom_port_status(self, port=None):
        if port is None:
            port = self._selected_port()
        status = (
            self._port_bottom_status_by_port.get(port, PORT_STATUS_CLOSED)
            if port
            else PORT_STATUS_CLOSED
        )
        self._set_message_lines(port_text=status)

    def _mark_port_status_unknown(self):
        if self._suppress_port_status_event:
            return
        port = self._selected_port()
        if not port:
            return
        self._store_bottom_port_status(port, PORT_STATUS_UNKNOWN)

    def _set_identified_device(self, port, device):
        if not port:
            return
        if not hasattr(self, "_identified_device_by_port"):
            self._identified_device_by_port = {}
        if device:
            self._identified_device_by_port[port] = device
        else:
            self._identified_device_by_port.pop(port, None)

    def _refresh_identified_device_message(self):
        if getattr(self, "_devices_load_error", None) and not getattr(
            self, "_device_entries", None
        ):
            self._set_message_lines(device_text=self._devices_load_error)
            return
        port = self._selected_port()
        identified_map = getattr(self, "_identified_device_by_port", None) or {}
        identified = identified_map.get(port) if port else None
        selected = None
        if getattr(self, "settings_device_var", None) is not None:
            selected = self._device_for_label(self.settings_device_var.get())
        self._set_message_lines(
            device_text=identified_device_message(identified, selected)
        )

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
        self._show_bottom_port_status(port)
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
        self._refresh_identified_device_message()

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
            "xonxoff": flow == FLOW_XOFF_XON,
            "rtscts": flow == "RTS/CTS",
            "dsrdtr": False,
        }

    def _device_for_label(self, label):
        device = self._device_for_unique_label(label)
        if device is not None:
            return device
        return next(
            (
                item
                for item in self.device_definitions.get("devices", [])
                if connected_device_label(item) == label
            ),
            None,
        )

    def _apply_selected_device_preferences(self):
        if self._suppress_device_apply:
            return
        device = self._device_for_label(self.settings_device_var.get())
        if not device:
            self._refresh_baud_dropdown(None, apply_default=False)
            self._mark_port_status_unknown()
            self._refresh_identified_device_message()
            return
        if self._held_port:
            self._refresh_baud_dropdown(device, apply_default=False)
            self._mark_port_status_unknown()
            self._refresh_identified_device_message()
            return
        params = device.get("serial_parameters") or {}
        self._refresh_baud_dropdown(device, apply_default=True)
        parity = PARITY_TO_UI.get(str(params.get("parity", "N")).upper(), "None")
        self.settings_parity_var.set(parity)
        self.settings_data_var.set(str(int(float(params.get("bytesize", 8)))))
        stop = params.get("stopbits", 1)
        stop_text = str(int(stop)) if float(stop) == int(float(stop)) else str(stop)
        if stop_text not in STOP_BITS_CHOICES:
            stop_text = "1"
        self.settings_stop_var.set(stop_text)
        self.settings_flow_var.set(normalize_flow_choice(params.get("flow_control")))
        self._refresh_settings_summary()
        self._mark_port_status_unknown()
        self._refresh_identified_device_message()

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
            self._store_bottom_port_status(port, PORT_STATUS_CLOSED)
            return
        self._release_serial()
        self._held_port = None
        if not self._reopen_held(port):
            self._store_bottom_port_status(port, PORT_STATUS_FAILED)
            return
        settings = self._serial_settings_from_ui()
        self._log(
            f"Opened {port} @ {settings['baudrate']} "
            f"{self._format_settings_summary()}"
        )
        self._set_port_row(port, status="Open", keep_device=True)
        self._store_bottom_port_status(port, PORT_STATUS_OPENED)

    def _apply_connection_scan(self, port, found, settings, was_open, device=None):
        if found:
            unique = self._unique_label_for_device(
                device, found_label=connected_device_label(device), baud=settings.get("baudrate")
            )
            self._suppress_device_apply = True
            self.settings_device_var.set(unique)
            self._suppress_device_apply = False
            self._refresh_baud_dropdown(device, apply_default=False)
            device = device or self._device_for_label(unique) or self._device_for_label(found)
            self._set_identified_device(port, device)
            self._set_port_row(
                port,
                status="Identified",
                device_name=found,
                baud=settings.get("baudrate"),
            )
            self._refresh_identified_device_message()
        else:
            self._set_identified_device(port, None)
            self._refresh_identified_device_message()
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

    def _probe_match(self, ser, device):
        migrated, error = migrate_device(device)
        if error or migrated is None:
            return None
        pattern = (migrated.get("response") or {}).get("regex") or ""
        if not pattern:
            return None
        for message, pause_s in command_steps(migrated):
            ser.write(str(message).encode())
            time.sleep(pause_s)
        response = ser.read(ser.in_waiting or 100).decode(errors="ignore")
        return re.search(pattern, response)

    def _probe_open_port(self, ser, device):
        return self._probe_match(ser, device) is not None

    def _connection_scan_worker(self, port, settings, device, was_open):
        label = connected_device_label(device) or "device"
        self._log(f"Device scan {port} for {label}...")
        found = None
        try:
            with serial.Serial(port, timeout=2, **settings) as ser:
                match = self._probe_match(ser, device)
                if match:
                    found = format_device_column(device, match.groupdict())
            if found:
                self._log_cont(f"  {port}  FOUND  {found}")
            else:
                self._log_cont(f"  {port}  NOT FOUND")
            self._log_cont("Device scan Done")
        except (serial.SerialException, OSError, ValueError) as exc:
            self._log_cont(f"Device scan failed: {exc}")
        self.root.after(
            0,
            lambda: self._apply_connection_scan(
                port, found, settings, was_open, device
            ),
        )

    def _schedule_device_combo_align(self, event=None):
        return

    def _sync_device_combo_width(self):
        return

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
            self._mark_port_status_unknown()
            close_dialog()

        win.protocol("WM_DELETE_WINDOW", close_dialog)

        shell = tk.Frame(win, bg=UI_ORANGE, padx=3, pady=3)
        shell.pack(fill=tk.BOTH, expand=True)
        inner = tk.Frame(shell, bg=UI_BG)
        inner.pack(fill=tk.BOTH, expand=True, padx=UI_PAD, pady=UI_PAD)

        blue = self._blue_box(inner)
        blue.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            blue,
            text="Port Settings",
            bg=UI_HEADER,
            fg="#000000",
            font=self._font_title,
            anchor="w",
        ).pack(anchor="w", pady=(0, UI_GAP))

        white = self._white_box(blue)
        white.pack(fill=tk.X)
        white.columnconfigure(0, weight=1)
        white.columnconfigure(1, weight=1)

        def combo_width(values):
            return max(5, max(len(str(value)) for value in values) + 1)

        def labeled_combo(parent, label, var, values):
            cell = tk.Frame(parent, bg="#FFFFFF")
            self._field_label(cell, label, "#FFFFFF").pack(anchor="w")
            wrap, _combo = self._outlined_combo(
                cell, var, values, combo_width(values), editable=False
            )
            wrap.pack(anchor="w")
            return cell

        labeled_combo(white, "Data Bits", data_var, DATA_BITS_CHOICES).grid(
            row=0, column=0, sticky="nw", padx=(0, UI_GROUP_GAP), pady=(0, UI_GAP)
        )
        labeled_combo(white, "Stop Bits", stop_var, STOP_BITS_CHOICES).grid(
            row=0, column=1, sticky="nw", pady=(0, UI_GAP)
        )
        labeled_combo(white, "Parity", parity_var, PARITY_CHOICES).grid(
            row=1, column=0, sticky="nw", padx=(0, UI_GROUP_GAP), pady=(0, UI_GAP)
        )
        labeled_combo(white, "Flow", flow_var, FLOW_CHOICES).grid(
            row=1, column=1, sticky="nw", pady=(0, UI_GAP)
        )

        preview_width = self._chars_for_text(longest_settings_text(), extra_px=8)

        select_row = tk.Frame(white, bg="#FFFFFF")
        select_row.grid(row=2, column=0, columnspan=2, sticky="ew")
        _, select_btn = self._flat_button(select_row, "Select", command=on_select)
        select_btn.master.pack(side=tk.RIGHT)
        preview_wrap, _preview = self._outlined_entry(
            select_row, preview_var, preview_width, bg=UI_GREEN
        )
        preview_wrap.pack(side=tk.LEFT)

        bottom = tk.Frame(blue, bg=UI_HEADER)
        bottom.pack(fill=tk.X, pady=(UI_GAP, 0))
        _, exit_btn = self._flat_button(bottom, "Exit", command=close_dialog)
        exit_btn.master.pack(side=tk.RIGHT)
        applied_wrap, _applied = self._outlined_entry(
            bottom, applied_var, preview_width, bg=UI_CURRENT_SETTINGS
        )
        applied_wrap.pack(side=tk.LEFT)

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
        """Port Status / Device Status inline left; Select then Exit on the right."""
        parent.configure(height=UI_CONTROL_H)
        parent.pack_propagate(False)

        exit_wrap, self.exit_button = self._flat_button(
            parent, "Exit", command=self._on_exit
        )
        exit_wrap.pack(side=tk.RIGHT)

        select_wrap, self.select_button = self._flat_button(
            parent, "Select", command=self._on_select_port
        )
        self.select_button.configure(state=tk.DISABLED)
        select_wrap.pack(side=tk.RIGHT, padx=(0, UI_GAP))
        self._select_wrap = select_wrap
        self._exit_wrap = exit_wrap

        status_row = tk.Frame(parent, bg=UI_BOTTOM, height=UI_CONTROL_H)
        status_row.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        status_row.pack_propagate(False)
        self.port_status_var = tk.StringVar(value=PORT_STATUS_CLOSED)
        self.device_status_var = tk.StringVar(value=DEVICE_STATUS_UNIDENTIFIED)
        self.port_message_var = self.port_status_var
        self.device_message_var = self.device_status_var
        self._status_wraps = []

        def status_group(label, var, width):
            group = tk.Frame(status_row, bg=UI_BOTTOM, height=UI_CONTROL_H)
            group.pack(side=tk.LEFT, padx=(0, UI_GROUP_GAP), fill=tk.Y)
            tk.Label(
                group,
                text=label,
                bg=UI_BOTTOM,
                fg=UI_FG,
                font=self._font_label,
                anchor="w",
            ).pack(side=tk.LEFT, padx=(0, UI_GAP), fill=tk.Y)
            wrap, _entry = self._outlined_entry(group, var, width)
            wrap.pack(side=tk.LEFT, pady=0)
            self._status_wraps.append(wrap)

        status_group("Port Status:", self.port_status_var, 12)
        status_group("Device Status:", self.device_status_var, 14)

    def _on_exit(self):
        self._clear_auto_scans()
        self._release_serial()
        self.root.destroy()

    # ------------------------------------------------------------- helpers
    @staticmethod
    def format_baud(baud):
        return format_baud_label(baud)

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
        """Identity name: Manufacturer model [- long_description]."""
        return connected_device_label(device)

    @staticmethod
    def _vendor_id_in_list(vendor_id, vendor_ids):
        vid = parse_usb_id(vendor_id)
        if vid is None:
            return False
        return any(parse_usb_id(item) == vid for item in vendor_ids)

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
                self._show_bottom_port_status(None)
                self._refresh_identified_device_message()
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
        self._identified_device_by_port = {
            port: device
            for port, device in self._identified_device_by_port.items()
            if port in known_ports
        }
        self._port_bottom_status_by_port = {
            port: status
            for port, status in self._port_bottom_status_by_port.items()
            if port in known_ports
        }
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
        self._fit_tree_host()
        if selected and self.tree.exists(selected):
            self._highlight_tree_port(selected)

    # ---------------------------------------------------- device identify
    def identify_device(self, port, vendor_id, product_id=None):
        label, baud, _device = self._identify_device_with_defs(
            port, vendor_id, self.device_definitions, product_id
        )
        return label, baud

    def _canonical_devices(self, device_definitions):
        raw = []
        if isinstance(device_definitions, dict):
            raw = device_definitions.get("devices") or []
        devices = []
        for item in raw:
            migrated, error = migrate_device(item)
            if migrated is not None and not error:
                devices.append(migrated)
        return devices

    def _identify_device_with_defs(
        self, port, vendor_id, device_definitions, product_id=None
    ):
        """Return (device_column_text_or_None, baud_or_None, device_or_None)."""
        for device in self._canonical_devices(device_definitions):
            if not device_matches_ids(device, vendor_id, product_id):
                continue
            params = device.get("serial_parameters") or {}
            bauds = baud_rates_for_device(device)
            for baud in bauds:
                try:
                    with serial.Serial(
                        port,
                        baudrate=baud,
                        parity=params.get("parity", "N"),
                        stopbits=params.get("stopbits", 1),
                        bytesize=params.get("bytesize", 8),
                        timeout=2,
                    ) as ser:
                        match = self._probe_match(ser, device)
                        if match:
                            return (
                                format_device_column(device, match.groupdict()),
                                baud,
                                device,
                            )
                except (serial.SerialException, OSError, KeyError, ValueError):
                    continue
        return None, None, None

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
                vid = p.vid if p and p.vid is not None else vendor_id
                pid = p.pid if p and p.pid is not None else None
                identified_device, found_baud, found_def = self._identify_device_with_defs(
                    port, vid, device_definitions, pid
                )
                if identified_device:
                    self._log_cont(
                        f"  {port}  VID {vid}  FOUND  {identified_device} @ {found_baud}"
                    )
                    updates[port] = (identified_device, found_baud, found_def)
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
                    self._set_identified_device(port, None)
                    new_data.append(
                        ("Available", port, vendor_id, None, description, None)
                    )
                else:
                    name, found_baud, found_def = result
                    self._set_identified_device(port, found_def)
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
        self._refresh_identified_device_message()
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
            device_definitions, load_error = load_device_file(DEVICES_JSON)

            comports, by_device = self._comports_by_device()
            known_ports = set(by_device)
            port_data = []
            identified_map = {}
            held = self._held_port
            held_entry = next(
                (entry for entry in self.port_data if entry[1] == held),
                None,
            )

            for port_info in comports:
                if held and port_info.device == held and held_entry is not None:
                    port_data.append(held_entry)
                    if held in self._identified_device_by_port:
                        identified_map[held] = self._identified_device_by_port[held]
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
                match_vid = port_info.vid if port_info.vid is not None else vendor_id
                match_pid = port_info.pid
                description = port_info.description or "Unknown"
                device_name = None
                baud = None
                found_def = None
                if status == "In Use":
                    self._log_cont(
                        f"  {port_info.device}  VID {vendor_id}  skipped (In Use)"
                    )
                else:
                    identified, found_baud, found_def = self._identify_device_with_defs(
                        port_info.device, match_vid, device_definitions, match_pid
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
                        found_def = None
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
                if found_def is not None:
                    identified_map[port_info.device] = found_def

            self._log_cont("Device scan Done")
            self.root.after(
                0,
                lambda: self._apply_retest_result(
                    device_definitions,
                    known_ports,
                    port_data,
                    load_error,
                    identified_map,
                ),
            )
        except Exception as e:
            self._log_cont(f"Device scan failed: {e}")
            self.root.after(0, self._finish_retest_scan)

    def _apply_retest_result(
        self,
        device_definitions,
        known_ports,
        port_data,
        load_error=None,
        identified_map=None,
    ):
        self.device_definitions = device_definitions
        self._devices_load_error = load_error
        self._identified_device_by_port = dict(identified_map or {})
        self._refresh_device_ui(apply_baud=not self._held_port)
        self.known_ports = known_ports
        self.port_data = port_data
        self.update_ports_from_data()
        self._refresh_settings_port_list()
        if load_error:
            self._set_message_lines(device_text=load_error)
        else:
            self._refresh_identified_device_message()
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
