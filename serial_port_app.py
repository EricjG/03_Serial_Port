
#! Before running make sure it's in .venv environment by running: .\.venv\Scripts\activate

import tkinter as tk
import tkinter.ttk as ttk
import tkinter.font as tkfont
from serial.tools import list_ports  # requires pyserial package: pip install pyserial
import serial  # requires pyserial package: pip install pyserial
import json
import re
import threading
import time

APP_VERSION = "3.0"
AUTO_PORT_SCAN_MS = 500  # port presence; feel fast without sub-100ms thrash
AUTO_DEVICE_SCAN_MS = 2500  # identify after port list already updated
PORT_OPEN_TIMEOUT = 0.15  # seconds; faster availability probe

# Page-3 look (cleaned Serial Port Application UI)
UI_BG = "#FFFFFF"  # window / content white
UI_PANEL = "#FFFFFF"
UI_BOTTOM = "#FFFFFF"
UI_HEADER = "#D6E8F8"  # light blue section bars/boxes
UI_BTN_GRAY = "#C0C0C0"
UI_ORANGE = "#FF8C00"
UI_FG = "#1a1a1a"

BAUD_SHORT = [
    (300, "300"),
    (600, "600"),
    (1200, "1.2K"),
    (9600, "9.6K"),
    (19200, "19.2K"),
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
        self.root.geometry("715x420")
        self.root.minsize(480, 320)
        self.root.configure(bg=UI_BG)

        # --- state ---
        self.known_ports = set()
        self.port_data = []  # (status, port, vendor_id, device_name, description, baud)
        self._port_scan_lock = threading.Lock()
        self._port_scan_running = False
        self._device_scan_lock = threading.Lock()
        self._device_scan_running = False
        self._port_scan_full = False
        self._auto_port_after_id = None
        self._auto_device_after_id = None

        with open("devices.json", "r") as f:
            self.device_definitions = json.load(f)

        style = ttk.Style()
        style.configure("Treeview", font=("Arial", 10, "bold"), rowheight=22)
        style.configure(
            "Treeview.Heading", font=("Arial", 10, "bold"), foreground="#000000"
        )
        style.configure("TCombobox", font=("Arial", 10, "bold"))

        self.show_in_use_var = tk.BooleanVar(value=False)
        self.auto_port_scan_var = tk.BooleanVar(value=True)
        self.device_scan_var = tk.BooleanVar(value=False)

        self._build_ui()
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

        self._tree_body_font = tkfont.Font(family="Arial", size=10, weight="bold")
        self._tree_header_font = tkfont.Font(family="Arial", size=10, weight="bold")
        self._fixed_tree_cols = ("Status", "Port #", "ID/Baud")

        self.tree.bind("<Configure>", self._sync_tree_header_widths)
        parent.bind("<Configure>", self._sync_tree_header_widths)
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
            col, text=label, bg=cell_bg, fg=UI_FG, font=("Arial", 10, "bold")
        ).pack(anchor="w")
        state = "normal" if editable else "readonly"
        cb = ttk.Combobox(
            col, textvariable=var, values=values, width=width, state=state, font=("Arial", 10, "bold")
        )
        cb.pack(anchor="w")
        return col, cb

    def _build_port_settings_scaffold(self, parent):
        """3rd blue box: Status/Port/Baud/Settings; Device; Open Port + Scan Device top-right."""
        wrap = tk.Frame(parent, bg=UI_HEADER)
        wrap.pack(fill=tk.BOTH, expand=True)

        self.settings_status_var = tk.StringVar(value="None Available")
        self.settings_port_var = tk.StringVar(value="* All *")
        self.settings_baud_var = tk.StringVar(value="115.2K")
        self.settings_device_var = tk.StringVar(value="")
        self.settings_parity_var = tk.StringVar(value="None")
        self.settings_data_var = tk.StringVar(value="1")
        self.settings_stop_var = tk.StringVar(value="1")
        self.settings_flow_var = tk.StringVar(value="None")

        # Right: Open Port / Scan Device stacked
        right = tk.Frame(wrap, bg=UI_HEADER)
        right.pack(side=tk.RIGHT, anchor="n", padx=(8, 0))
        self.open_port_button = tk.Button(
            right,
            text="Open:",
            width=12,
            state=tk.DISABLED,
            bg=UI_BTN_GRAY,
            disabledforeground="#000000",
            anchor="w",
            justify="left",
            relief=tk.RAISED,
            font=("Arial", 9, "bold"),
        )
        self.open_port_button.pack(anchor="e", pady=(14, 2))
        self.scan_device_button = tk.Button(
            right,
            text="Scan Device",
            width=12,
            state=tk.DISABLED,
            bg=UI_BTN_GRAY,
            disabledforeground="#000000",
            anchor="w",
            justify="left",
            relief=tk.RAISED,
            font=("Arial", 9, "bold"),
        )
        self.scan_device_button.pack(anchor="e")

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
        ).pack(anchor="w")
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
        self.settings_status_entry.pack(anchor="w")

        # Port: dropdown + manual entry allowed; no '* Manual Entry *' item
        port_col = tk.Frame(row1, bg=UI_HEADER)
        port_col.pack(side=tk.LEFT, padx=6, anchor="n")
        tk.Label(
            port_col, text="Port", bg=UI_HEADER, fg=UI_FG, font=("Arial", 10, "bold")
        ).pack(anchor="w")
        self.settings_port_combo = ttk.Combobox(
            port_col,
            textvariable=self.settings_port_var,
            values=["* All *"],
            width=14,
            state="normal",
            font=("Arial", 10, "bold"),
        )
        self.settings_port_combo.pack(anchor="w")

        # Baud: dropdown + manual entry; no '* Manual Entry *' item
        baud_labels = [s for _, s in BAUD_SHORT]
        self._labeled_combo(
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
            text="Settings",
            bg=UI_HEADER,
            fg=UI_FG,
            font=("Arial", 10, "bold"),
        ).pack(anchor="w")
        self.settings_summary = tk.Button(
            settings_col,
            text="None - 1 - 1 - None ",
            bg="#FFFFFF",
            activebackground="#FFFFFF",
            fg="#000000",
            anchor="w",
            justify="left",
            relief=tk.RAISED,
            padx=6,
            font=("Arial", 9, "bold"),
            command=lambda: None,
        )
        self.settings_summary.pack(anchor="w")

        # Device: label left, dropdown to the right
        row2 = tk.Frame(left, bg=UI_HEADER)
        row2.pack(fill=tk.X, anchor="w", pady=(8, 0))
        tk.Label(
            row2, text="Device", bg=UI_HEADER, fg=UI_FG, font=("Arial", 10, "bold")
        ).pack(side=tk.LEFT, padx=(6, 4))
        device_names = [
            f"{d.get('manufacturer', '?')} : {d.get('model', '?')}"
            for d in self.device_definitions.get("devices", [])
        ]
        if not device_names:
            device_names = ["(no devices)"]
        self.settings_device_var.set(device_names[0])
        self.settings_device_combo = ttk.Combobox(
            row2,
            textvariable=self.settings_device_var,
            values=device_names,
            width=28,
            state="readonly",
            font=("Arial", 10, "bold"),
        )
        self.settings_device_combo.pack(side=tk.LEFT)

    def _build_bottom_bar(self, parent):
        """White bar: Exit then Select on the right (Select furthest right); text centered."""
        # pack RIGHT first = furthest right
        tk.Button(
            parent,
            text="Select",
            width=10,
            state=tk.DISABLED,
            bg=UI_BTN_GRAY,
            disabledforeground="#000000",
            anchor="center",
            justify="center",
            relief=tk.RAISED,
            font=("Arial", 9, "bold"),
        ).pack(side=tk.RIGHT, padx=4)

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

    def _on_exit(self):
        self._clear_auto_scans()
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
    def _vendor_id_in_list(vendor_id, vendor_ids):
        vid = str(vendor_id)
        return vid in {str(v) for v in vendor_ids}

    def _clear_auto_scans(self):
        """Clear all three auto checkboxes and cancel scheduled loops."""
        self.show_in_use_var.set(False)
        self.auto_port_scan_var.set(False)
        self.device_scan_var.set(False)
        if self._auto_port_after_id is not None:
            try:
                self.root.after_cancel(self._auto_port_after_id)
            except tk.TclError:
                pass
            self._auto_port_after_id = None
        if self._auto_device_after_id is not None:
            try:
                self.root.after_cancel(self._auto_device_after_id)
            except tk.TclError:
                pass
            self._auto_device_after_id = None

    def _refresh_settings_port_list(self):
        ports = sorted({entry[1] for entry in self.port_data})
        values = ["* All *"] + ports
        self.settings_port_combo["values"] = values

    # ----------------------------------------------------- scan / refresh
    def start_initial_scan(self):
        print("Starting initial scan...")
        self.scan_ports(full=True)
        if self.auto_port_scan_var.get():
            self.start_auto_port_scan()

    def scan_ports(self, *, full=False):
        """Start a port scan on a background thread."""
        if not self._port_scan_lock.acquire(blocking=False):
            print("Port scan already in progress, skipping.")
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
        print("Scanning ports..." + (" (fast)" if fast else ""))
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
                    if status == "Identified":
                        # Keep Identified until device scan demotes
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
                print(f"Testing new port: {port_info.device}")
                status = (
                    "In Use"
                    if not self.is_port_available(port_info.device)
                    else "Available"
                )
                vendor_id = str(port_info.vid) if port_info.vid else "Unknown"
                description = port_info.description or "Unknown"
                print(
                    f"Adding new port: {port_info.device}, Status: {status}, "
                    f"Vendor ID: {vendor_id}, Description: {description}"
                )
                port_data.append(
                    (status, port_info.device, vendor_id, None, description, None)
                )

            self.root.after(
                0,
                lambda: self._apply_port_scan_result(known_ports, port_data),
            )
        except Exception as e:
            print(f"Port scan failed: {e}")
            self.root.after(0, self._finish_port_scan)

    def _apply_port_scan_result(self, known_ports, port_data):
        self.known_ports = known_ports
        self.port_data = port_data
        self.update_ports_from_data()
        self._refresh_settings_port_list()
        self._finish_port_scan()
        if self.device_scan_var.get():
            self.scan_available_ports()

    def _finish_port_scan(self):
        self._port_scan_running = False
        if self._port_scan_lock.locked():
            self._port_scan_lock.release()

    def is_port_available(self, port_name):
        try:
            ser = serial.Serial(port_name, timeout=PORT_OPEN_TIMEOUT)
            ser.close()
            return True
        except (serial.SerialException, OSError):
            return False

    def update_ports_from_data(self):
        self.tree.delete(*self.tree.get_children())
        status_rank = {"Identified": 0, "Available": 1, "In Use": 2}
        rows = list(self.port_data)
        rows.sort(key=lambda x: (status_rank.get(x[0], 9), x[1]))
        for status, port, vendor_id, device_name, description, baud in rows:
            if not self.show_in_use_var.get() and status == "In Use":
                continue
            id_baud = self._id_baud_column(status, vendor_id, baud)
            connected = self._driver_or_device_column(status, device_name, description)
            self.tree.insert(
                "", tk.END, values=(status, port, id_baud, connected)
            )
        self._fit_fixed_tree_columns()

    # ---------------------------------------------------- device identify
    def identify_device(self, port, vendor_id):
        return self._identify_device_with_defs(
            port, vendor_id, self.device_definitions
        )

    def _identify_device_with_defs(self, port, vendor_id, device_definitions):
        """Return (model_or_None, baud_or_None)."""
        print(f"Identifying device on port: {port} with Vendor ID: {vendor_id}")
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
                    print(f"Raw response from port {port}: {response}")

                    match = re.search(device["response"]["regex"], response)
                    if match:
                        print(f"Regex match found: {match.groupdict()}")
                        print(
                            f"Device identified: {device['manufacturer']} "
                            f"{device['model']} on port {port} @ {baud}"
                        )
                        return device["model"], baud
                    print(
                        f"No regex match for device: {device['manufacturer']} "
                        f"{device['model']} on port {port}"
                    )
            except (serial.SerialException, OSError, KeyError) as e:
                print(
                    f"Error testing device {device['manufacturer']} "
                    f"{device['model']} on port {port}: {e}"
                )
                continue
        print(f"No device identified on port {port}")
        return None, None

    def scan_available_ports(self):
        if not self._device_scan_lock.acquire(blocking=False):
            print("Device scan already in progress, skipping.")
            return
        self._device_scan_running = True
        threading.Thread(target=self._scan_devices_worker, daemon=True).start()

    def _scan_devices_worker(self):
        print("Scanning available ports for devices...")
        try:
            device_definitions = self.device_definitions
            _, by_device = self._comports_by_device()
            # port -> (device_name, baud) or None to demote
            updates = {}
            for status, port, vendor_id, device_name, description, baud in self.port_data:
                if status == "In Use":
                    print(f"Skipping port {port} as it is In Use.")
                    continue
                if status not in ("Available", "Identified"):
                    continue
                p = by_device.get(port)
                vid = str(p.vid) if p and p.vid else vendor_id
                print(f"Scanning device on port: {port} with Vendor ID: {vid}")
                identified_device, found_baud = self._identify_device_with_defs(
                    port, vid, device_definitions
                )
                if identified_device:
                    updates[port] = (identified_device, found_baud)
                elif status == "Identified":
                    updates[port] = None  # demote
            self.root.after(0, lambda u=updates: self._apply_device_scan_result(u))
        except Exception as e:
            print(f"Device scan failed: {e}")
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
        if not self._port_scan_lock.acquire(blocking=False):
            print("Port scan already in progress, skipping retest.")
            return
        self._port_scan_running = True
        threading.Thread(target=self._retest_ports_worker, daemon=True).start()

    def _retest_ports_worker(self):
        print("Retesting all available ports...")
        try:
            with open("devices.json", "r") as f:
                device_definitions = json.load(f)
            print("Reloaded device definitions from JSON file.")

            comports, by_device = self._comports_by_device()
            known_ports = set(by_device)
            port_data = []

            for port_info in comports:
                status = (
                    "In Use"
                    if not self.is_port_available(port_info.device)
                    else "Available"
                )
                vendor_id = str(port_info.vid) if port_info.vid else "Unknown"
                description = port_info.description or "Unknown"
                device_name = None
                baud = None
                if status == "Available":
                    identified, found_baud = self._identify_device_with_defs(
                        port_info.device, vendor_id, device_definitions
                    )
                    if identified:
                        status = "Identified"
                        device_name = identified
                        baud = found_baud
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

            self.root.after(
                0,
                lambda: self._apply_retest_result(
                    device_definitions, known_ports, port_data
                ),
            )
        except Exception as e:
            print(f"Retest failed: {e}")
            self.root.after(0, self._finish_port_scan)

    def _apply_retest_result(self, device_definitions, known_ports, port_data):
        self.device_definitions = device_definitions
        self.known_ports = known_ports
        self.port_data = port_data
        self.update_ports_from_data()
        self._refresh_settings_port_list()
        self._finish_port_scan()

    # ------------------------------------------------------ control handlers
    def toggle_ports_in_use(self):
        print(f"'In Use' checkbox toggled: {self.show_in_use_var.get()}")
        self.update_ports_from_data()

    def toggle_auto_port_scan(self):
        print(f"'Scan Ports' checkbox toggled: {self.auto_port_scan_var.get()}")
        if self.auto_port_scan_var.get():
            self.start_auto_port_scan()
        else:
            if self._auto_port_after_id is not None:
                try:
                    self.root.after_cancel(self._auto_port_after_id)
                except tk.TclError:
                    pass
                self._auto_port_after_id = None

    def toggle_device_scan(self):
        print(f"'Scan Devices' checkbox toggled: {self.device_scan_var.get()}")
        if self.device_scan_var.get():
            self.start_device_scan()
        else:
            if self._auto_device_after_id is not None:
                try:
                    self.root.after_cancel(self._auto_device_after_id)
                except tk.TclError:
                    pass
                self._auto_device_after_id = None
            # Leave Identified rows as-is; just stop auto

    def start_auto_port_scan(self):
        if not self.auto_port_scan_var.get():
            self._auto_port_after_id = None
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
        if not self._device_scan_running:
            self.scan_available_ports()
        self._auto_device_after_id = self.root.after(
            AUTO_DEVICE_SCAN_MS, self.start_device_scan
        )

    def on_in_use_button(self):
        """One-shot: show In Use ports; clear autos; uncheck Scan Ports."""
        print("In Use button clicked")
        was_show = self.show_in_use_var.get()
        self._clear_auto_scans()
        self.show_in_use_var.set(True)
        self.update_ports_from_data()
        # Brief emphasis: keep show_in_use True after button? Slide says button shows
        # ports in use and unchecks Scan Ports; checkbox is the include filter.
        # After one-shot, leave include checked so user sees them; they can uncheck.
        if not was_show:
            self.show_in_use_var.set(True)
        self.update_ports_from_data()

    def on_scan_ports_button(self):
        print("Scan Ports button clicked")
        self._clear_auto_scans()
        self.scan_ports(full=True)

    def on_scan_devices_button(self):
        print("Scan Devices button clicked")
        self._clear_auto_scans()
        self.retest_available_ports()


if __name__ == "__main__":
    root = tk.Tk()
    app = SerialPortApp(root)
    root.mainloop()
