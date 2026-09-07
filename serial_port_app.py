
#! Before running make sure it's in .venv environment by running: .\.venv\Scripts\activate

import tkinter as tk
import tkinter.ttk as ttk
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

# Section panel look (slide "background boxes")
UI_BG = "#E8E8E8"
UI_PANEL = "#F5F5F5"
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
        self.root.geometry("1040x640")
        self.root.minsize(900, 560)
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
        style.configure("Treeview", font=("Arial", 10), rowheight=22)
        style.configure(
            "Treeview.Heading", font=("Arial", 10, "bold"), foreground="purple"
        )

        self.show_in_use_var = tk.BooleanVar(value=False)
        self.auto_port_scan_var = tk.BooleanVar(value=False)
        self.device_scan_var = tk.BooleanVar(value=False)

        self._build_ui()
        self.root.after(100, self.start_initial_scan)

    # ------------------------------------------------------------------ UI
    def _section(self, parent, title):
        """Labeled background box for a UI section (matches slide panels)."""
        box = tk.LabelFrame(
            parent,
            text=title,
            font=("Arial", 10, "bold"),
            bg=UI_PANEL,
            fg=UI_FG,
            bd=2,
            relief=tk.GROOVE,
            labelanchor="nw",
            padx=8,
            pady=6,
        )
        return box

    def _build_ui(self):
        # Outer grid:
        #   [ UART Connection Status | Port Settings ]
        #   [ Devices                | actions       ]
        #   [ Scan controls                        Exit ]
        main = tk.Frame(self.root, bg=UI_BG)
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)
        main.columnconfigure(0, weight=3)
        main.columnconfigure(1, weight=2)
        main.rowconfigure(0, weight=3)
        main.rowconfigure(1, weight=2)
        main.rowconfigure(2, weight=0)

        status_box = self._section(main, "UART Connection Status")
        status_box.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 6))
        self._build_status_tree(status_box)

        settings_box = self._section(main, "Port Settings")
        settings_box.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(0, 6))
        self._build_port_settings_scaffold(settings_box)

        devices_box = self._section(main, "Devices")
        devices_box.grid(row=1, column=0, sticky="nsew", padx=(0, 6), pady=(0, 6))
        self._build_devices_scaffold(devices_box)

        action_box = self._section(main, "Connection")
        action_box.grid(row=1, column=1, sticky="nsew", padx=(6, 0), pady=(0, 6))
        self._build_connection_actions(action_box)

        controls_box = self._section(main, "Scan Controls")
        controls_box.grid(row=2, column=0, columnspan=2, sticky="ew")
        self._build_scan_controls(controls_box)

    def _build_status_tree(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            parent,
            columns=("Status", "Port #", "ID/Baud", "Serial Driver / Connected Device"),
            show="headings",
            height=10,
        )
        for col, anchor in (
            ("Status", "center"),
            ("Port #", "center"),
            ("ID/Baud", "center"),
            ("Serial Driver / Connected Device", "w"),
        ):
            self.tree.heading(col, text=col, anchor=anchor)
        self.tree.column("Status", width=100, minwidth=80, anchor="center", stretch=False)
        self.tree.column("Port #", width=90, minwidth=70, anchor="center", stretch=False)
        self.tree.column("ID/Baud", width=100, minwidth=80, anchor="center", stretch=False)
        self.tree.column(
            "Serial Driver / Connected Device",
            width=360,
            minwidth=180,
            anchor="w",
            stretch=True,
        )
        scroll = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

    def _build_check_button(self, parent, label, var, on_toggle, on_button):
        cell = tk.Frame(parent, bg=UI_PANEL)
        cell.pack(side=tk.LEFT, padx=12)
        tk.Checkbutton(
            cell, variable=var, command=on_toggle, bg=UI_PANEL, activebackground=UI_PANEL
        ).pack(anchor="w")
        tk.Button(cell, text=label, command=on_button, width=12).pack(anchor="w")

    def _build_port_settings_scaffold(self, parent):
        """Visual-only Port Settings (no Open/Close logic this pass)."""
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)

        # Left: Ports + Parity/Data/Stop/Flow
        left = tk.Frame(parent, bg=UI_PANEL)
        left.grid(row=0, column=0, sticky="nw", padx=(0, 8))

        tk.Label(left, text="Ports:", bg=UI_PANEL, anchor="w").pack(anchor="w")
        self.settings_port_var = tk.StringVar(value="* All *")
        self.settings_port_combo = ttk.Combobox(
            left,
            textvariable=self.settings_port_var,
            values=["* All *", "* Manual Entry *"],
            width=18,
            state="readonly",
        )
        self.settings_port_combo.pack(anchor="w", pady=(0, 8))

        bits = tk.Frame(left, bg=UI_PANEL)
        bits.pack(anchor="w")
        self.settings_parity_var = tk.StringVar(value="None")
        self.settings_data_var = tk.StringVar(value="8")
        self.settings_stop_var = tk.StringVar(value="1")
        self.settings_flow_var = tk.StringVar(value="None")

        for r, (label, var, values, width) in enumerate(
            (
                ("Parity:", self.settings_parity_var, ["None", "Odd", "Even", "Mark", "Space"], 10),
                ("Data:", self.settings_data_var, ["8", "7", "6", "5"], 6),
                ("Stop:", self.settings_stop_var, ["1", "2"], 6),
                ("Flow:", self.settings_flow_var, ["None", "RTS/CTS", "xOff/xOn"], 10),
            )
        ):
            tk.Label(bits, text=label, bg=UI_PANEL).grid(row=r, column=0, sticky="w", pady=2)
            ttk.Combobox(
                bits, textvariable=var, values=values, width=width, state="readonly"
            ).grid(row=r, column=1, sticky="w", pady=2, padx=(4, 0))

        # Right: Baud list
        right = tk.Frame(parent, bg=UI_PANEL)
        right.grid(row=0, column=1, sticky="nsew")
        tk.Label(right, text="Bauds:", bg=UI_PANEL).pack(anchor="w")
        baud_labels = [f"{long:>7}    {short}" for long, short in (
            ("300", "300"),
            ("600", "600"),
            ("1,200", "1.2K"),
            ("9,600", "9.6K"),
            ("19,200", "19.2K"),
            ("57,600", "57.6K"),
            ("115,200", "115.2K"),
            ("230,400", "230.4K"),
            ("460,800", "460.8K"),
            ("921,600", "921.6K"),
        )] + ["* Manual Entry *"]
        self.settings_baud_var = tk.StringVar(value="115.2K")
        self.settings_baud_list = tk.Listbox(
            right, height=11, width=22, exportselection=False, font=("Consolas", 9)
        )
        for item in baud_labels:
            self.settings_baud_list.insert(tk.END, item)
        self.settings_baud_list.selection_set(6)  # 115.2K
        self.settings_baud_list.pack(anchor="w", fill=tk.Y)

        # Bottom of settings: summary + Open (scaffold)
        bottom = tk.Frame(parent, bg=UI_PANEL)
        bottom.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.settings_summary = tk.Label(
            bottom, text="None - 8 - 1 - None", bg=UI_PANEL, font=("Arial", 10)
        )
        self.settings_summary.pack(side=tk.LEFT)
        tk.Button(bottom, text="Open", width=10, state=tk.DISABLED).pack(side=tk.RIGHT)

    def _build_devices_scaffold(self, parent):
        """Placeholder Devices panel (list deferred; box present for layout feel)."""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        tk.Label(
            parent,
            text="Manufacture - Model - Baud - Settings",
            bg=UI_PANEL,
            fg="#555555",
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        self.devices_list = tk.Listbox(parent, height=6, font=("Arial", 10))
        self.devices_list.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        # Populate read-only preview from devices.json (no edit wiring yet)
        for device in self.device_definitions.get("devices", []):
            baud = self.format_baud(device.get("serial_parameters", {}).get("baudrate"))
            parity = device.get("serial_parameters", {}).get("parity", "N")
            stop = device.get("serial_parameters", {}).get("stopbits", 1)
            data = device.get("serial_parameters", {}).get("bytesize", 8)
            line = (
                f"{device.get('manufacturer', '?')} - {device.get('model', '?')} - "
                f"{baud} - {parity}-{data}-{stop}"
            )
            self.devices_list.insert(tk.END, line)
        tk.Label(
            parent,
            text="(Double-click edit deferred)",
            bg=UI_PANEL,
            fg="gray",
            anchor="w",
        ).grid(row=2, column=0, sticky="w", pady=(4, 0))

    def _build_connection_actions(self, parent):
        tk.Label(
            parent,
            text="Select a port in the list,\nthen Open / Close (not wired yet).",
            bg=UI_PANEL,
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(0, 8))
        tk.Button(parent, text="Select", width=12, state=tk.DISABLED).pack(
            anchor="w", pady=2
        )
        tk.Button(parent, text="Close", width=12, state=tk.DISABLED).pack(
            anchor="w", pady=2
        )
        tk.Label(
            parent,
            text="When port is In Use,\nsettings are grayed.",
            bg=UI_PANEL,
            fg="#555555",
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(12, 0))

    def _build_scan_controls(self, parent):
        trio = tk.Frame(parent, bg=UI_PANEL)
        trio.pack(side=tk.LEFT)
        self._build_check_button(
            trio,
            "In Use",
            self.show_in_use_var,
            self.toggle_ports_in_use,
            self.on_in_use_button,
        )
        self._build_check_button(
            trio,
            "Scan Ports",
            self.auto_port_scan_var,
            self.toggle_auto_port_scan,
            self.on_scan_ports_button,
        )
        self._build_check_button(
            trio,
            "Scan Devices",
            self.device_scan_var,
            self.toggle_device_scan,
            self.on_scan_devices_button,
        )
        self.exit_button = tk.Button(
            parent, text="Exit", command=self._on_exit, width=10
        )
        self.exit_button.pack(side=tk.RIGHT, padx=8, pady=4)
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
        values = ["* All *"] + ports + ["* Manual Entry *"]
        self.settings_port_combo["values"] = values

    # ----------------------------------------------------- scan / refresh
    def start_initial_scan(self):
        print("Starting initial scan...")
        self.scan_ports(full=True)

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
