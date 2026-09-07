
#! Before running make sure it's in .venv environment by running: .\.venv\Scripts\activate

import tkinter as tk
import tkinter.ttk as ttk
from serial.tools import list_ports     # requires pyserial package: pip install pyserial
import serial                           # requires pyserial package: pip install pyserial
import json
import re
import threading
import time

APP_VERSION = "2.2"
AUTO_PORT_SCAN_MS = 1500  # interval when Auto Port Scan is enabled
PORT_OPEN_TIMEOUT = 0.15  # seconds; faster availability probe


class SerialPortApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Serial Port Application v{APP_VERSION}")
        self.root.geometry("720x320")

        # Pack bottom bar first so Exit stays at bottom-right
        bottom_frame = tk.Frame(root)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        self.exit_button = tk.Button(
            bottom_frame, text="Exit", command=self._on_exit, width=10
        )
        self.exit_button.pack(side=tk.RIGHT)

        self.label = tk.Label(root, text="Available Serial Ports")
        self.label.pack(pady=10)

        # Add checkboxes
        checkbox_frame = tk.Frame(root)
        checkbox_frame.pack(anchor="w", padx=10)

        self.show_in_use_var = tk.BooleanVar(value=False)
        self.show_in_use_checkbox = tk.Checkbutton(
            checkbox_frame,
            text="Ports in Use",
            variable=self.show_in_use_var,
            command=self.toggle_ports_in_use,
        )
        self.show_in_use_checkbox.pack(side=tk.LEFT, padx=5)

        self.auto_port_scan_var = tk.BooleanVar(value=False)
        self.auto_port_scan_checkbox = tk.Checkbutton(
            checkbox_frame,
            text="Auto Port Scan",
            variable=self.auto_port_scan_var,
            command=self.toggle_auto_port_scan,
        )
        self.auto_port_scan_checkbox.pack(side=tk.LEFT, padx=5)

        self.device_scan_var = tk.BooleanVar(value=False)
        self.device_scan_checkbox = tk.Checkbutton(
            checkbox_frame,
            text="Device Scan",
            variable=self.device_scan_var,
            command=self.toggle_device_scan,
        )
        self.device_scan_checkbox.pack(side=tk.LEFT, padx=5)

        self.tree = ttk.Treeview(
            root,
            columns=("Status", "Port #", "Device / Port ID", "Description"),
            show="headings",
        )
        self.tree.heading("Status", text="Status")
        self.tree.heading("Port #", text="Port #")
        self.tree.heading("Device / Port ID", text="Device / Port ID")
        self.tree.heading("Description", text="Description")
        self.tree.pack(pady=10, fill=tk.BOTH, expand=True)

        # Force geometry update before setting column widths
        self.tree.update_idletasks()

        # Configure column widths
        self.tree.column(
            "Status", width=200, minwidth=70, anchor="center", stretch=False
        )
        self.tree.column(
            "Port #", width=100, minwidth=70, anchor="center", stretch=False
        )
        self.tree.column(
            "Device / Port ID", width=140, minwidth=120, anchor="center", stretch=False
        )
        self.tree.column(
            "Description", width=1200, minwidth=1200, anchor="w", stretch=False
        )  # Set wide and prevent shrinking

        # Configure Treeview headers
        self.tree.heading("Status", text="Status", anchor="center")
        self.tree.heading("Port #", text="Port #", anchor="center")
        self.tree.heading("Device / Port ID", text="Device / Port ID", anchor="center")
        self.tree.heading(
            "Description", text="Description", anchor="w"
        )  # Ensure left justification for the header

        button_frame = tk.Frame(root)
        button_frame.pack(pady=10)

        self.refresh_button = tk.Button(
            button_frame, text="Rescan for Ports", command=self.refresh_ports
        )
        self.refresh_button.pack(side=tk.LEFT, padx=5)

        self.retest_button = tk.Button(
            button_frame, text="Rescan for Devices", command=self.retest_available_ports
        )
        self.retest_button.pack(side=tk.LEFT, padx=5)

        # Bind window resize event
        self.root.bind("<Configure>", self.adjust_column_widths)

        # Initialize known_ports before the first scan
        self.known_ports = set()
        self.port_data = []  # Store port information
        self._port_scan_lock = threading.Lock()
        self._port_scan_running = False
        self._device_scan_lock = threading.Lock()
        self._device_scan_running = False
        self._port_scan_full = False

        # Load device definitions
        with open("devices.json", "r") as f:
            self.device_definitions = json.load(f)

        # Configure Treeview style
        style = ttk.Style()
        style.configure("Treeview", font=("Arial", 10))  # Set consistent font for rows
        style.configure(
            "Treeview.Heading", font=("Arial", 10, "bold"), foreground="purple"
        )  # Bold purple header text

        # Initial scan will be triggered after the window is displayed
        self.root.after(100, self.start_initial_scan)

    def _on_exit(self):
        self.root.destroy()

    @staticmethod
    def _looks_like_vendor_id(value):
        """True if value is a numeric USB vendor ID string."""
        return str(value).isdigit()

    def _display_device_column(self, vendor_id, device_name):
        """Show device model when Device Scan is on, otherwise vendor/port ID."""
        if self.device_scan_var.get() and device_name:
            return device_name
        return vendor_id

    @staticmethod
    def _vendor_id_in_list(vendor_id, vendor_ids):
        vid = str(vendor_id)
        return vid in {str(v) for v in vendor_ids}

    def start_initial_scan(self):
        print("Starting initial scan...")
        self.scan_ports()

    def refresh_ports(self):
        print("Refreshing ports...")
        self.port_data = []
        self.known_ports = set()
        self.scan_ports(full=True)

    def scan_ports(self, *, full=False):
        """Start a port scan on a background thread (fast incremental when auto-scanning)."""
        if not self._port_scan_lock.acquire(blocking=False):
            print("Port scan already in progress, skipping.")
            return
        self._port_scan_running = True
        self._port_scan_full = full
        self.refresh_button.config(state=tk.DISABLED)
        self.retest_button.config(state=tk.DISABLED)
        threading.Thread(target=self._scan_ports_worker, daemon=True).start()

    def _comports_by_device(self):
        """Single list_ports call; map device name -> port info."""
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
                self.root.after(0, self._finish_port_scan)
                return

            new_ports = current_ports - known_ports
            known_ports = current_ports
            port_data = [entry for entry in port_data if entry[1] in current_ports]

            if not fast:
                for index, (status, port, vendor_id, device_name, description) in enumerate(
                    port_data
                ):
                    is_accessible = self.is_port_available(port)
                    updated_status = "Available" if is_accessible else "In use"
                    port_data[index] = (
                        updated_status,
                        port,
                        vendor_id,
                        device_name,
                        description,
                    )

            for port_info in comports:
                if port_info.device not in new_ports:
                    continue
                print(f"Testing new port: {port_info.device}")
                status = (
                    "In use"
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
                    (status, port_info.device, vendor_id, None, description)
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
        self.sort_treeview()
        self._finish_port_scan()
        if self.device_scan_var.get():
            self.scan_available_ports()

    def _finish_port_scan(self):
        self._port_scan_running = False
        self.refresh_button.config(state=tk.NORMAL)
        self.retest_button.config(state=tk.NORMAL)
        if self._port_scan_lock.locked():
            self._port_scan_lock.release()

    def scan_devices(self):
        """Scan for devices on ports marked as 'Available'."""
        print("Scanning devices on available ports...")
        _, by_device = self._comports_by_device()
        for index, (status, port, vendor_id, device_name, description) in enumerate(
            self.port_data
        ):
            if status == "Available":
                p = by_device.get(port)
                vid = str(p.vid) if p and p.vid else vendor_id
                print(f"Scanning device on port: {port} with Vendor ID: {vid}")
                identified = self.identify_device(port, vid)
                device_name = identified if identified != "Unknown" else device_name
                self.port_data[index] = (
                    status,
                    port,
                    vendor_id,
                    device_name,
                    description,
                )

        self.update_ports_from_data()

    def update_ports_from_data(self):
        """Update the treeview based on stored port data and the 'Ports in Use' checkbox."""
        self.tree.delete(*self.tree.get_children())  # Clear the treeview
        self.port_data.sort(key=lambda x: (x[0] != "Available", x[1]))
        for status, port, vendor_id, device_name, description in self.port_data:
            if not self.show_in_use_var.get() and status == "In use":
                continue
            display = self._display_device_column(vendor_id, device_name)
            self.tree.insert(
                "", tk.END, values=(status, port, display, description)
            )

    def sort_treeview(self):
        """Sort the treeview items to show 'Available' first, then 'In use', and sort by 'Port #'."""
        items = [
            (self.tree.item(item, "values"), item) for item in self.tree.get_children()
        ]
        # Sort by 'Status' (Available first) and then by 'Port #'
        items.sort(key=lambda x: (x[0][0] != "Available", x[0][1]))
        for index, (_, item) in enumerate(items):
            self.tree.move(item, "", index)

    def update_list_with_port(self, port):
        print(f"Updating list with port: {port}")
        _, by_device = self._comports_by_device()
        p = by_device.get(port)
        status = "In use" if not self.is_port_available(port) else "Available"
        vendor_id = str(p.vid) if p and p.vid else "Unknown"
        description = (p.description if p else None) or "Unknown"
        device_name = None
        if status == "Available" and self.device_scan_var.get():
            identified = self.identify_device(port, vendor_id)
            if identified != "Unknown":
                device_name = identified
        display = self._display_device_column(vendor_id, device_name)
        print(
            f"Port {port} status: {status}, Device / Port ID: {display}, "
            f"Description: {description}"
        )
        self.tree.insert("", tk.END, values=(status, port, display, description))

    def identify_device(self, port, vendor_id):
        return self._identify_device_with_defs(
            port, vendor_id, self.device_definitions
        )

    def is_port_available(self, port_name):
        try:
            ser = serial.Serial(port_name, timeout=PORT_OPEN_TIMEOUT)
            ser.close()
            return True
        except (serial.SerialException, OSError):
            return False

    def adjust_column_widths(self, event):
        for col in self.tree["columns"]:
            max_width = max(
                [
                    len(
                        str(
                            self.tree.item(item, "values")[
                                self.tree["columns"].index(col)
                            ]
                        )
                    )
                    for item in self.tree.get_children()
                ]
                + [len(col)]
            )
            calculated_width = (
                max_width * 10
            )  # Multiply by 10 for approximate character width
            self.tree.column(
                col, width=calculated_width, minwidth=calculated_width, stretch=False
            )

    def get_open_ports(self):
        # Placeholder for checking open ports. Extend this as needed.
        return []

    def retest_available_ports(self):
        if not self._port_scan_lock.acquire(blocking=False):
            print("Port scan already in progress, skipping retest.")
            return
        self._port_scan_running = True
        self.refresh_button.config(state=tk.DISABLED)
        self.retest_button.config(state=tk.DISABLED)
        threading.Thread(target=self._retest_ports_worker, daemon=True).start()

    def _retest_ports_worker(self):
        print("Retesting all available ports...")
        try:
            with open("devices.json", "r") as f:
                device_definitions = json.load(f)
            print("Reloaded device definitions from JSON file.")

            comports, by_device = self._comports_by_device()
            known_ports = set(self.known_ports)
            port_data = list(self.port_data)

            current_ports = set(by_device)
            new_ports = current_ports - known_ports
            known_ports = current_ports

            port_data = [entry for entry in port_data if entry[1] in current_ports]

            for port_info in comports:
                if port_info.device not in new_ports:
                    continue
                print(f"Adding new port: {port_info.device}")
                status = (
                    "In use"
                    if not self.is_port_available(port_info.device)
                    else "Available"
                )
                vendor_id = str(port_info.vid) if port_info.vid else "Unknown"
                description = port_info.description or "Unknown"
                port_data.append(
                    (status, port_info.device, vendor_id, None, description)
                )

            for index, (status, port, vendor_id, device_name, description) in enumerate(
                port_data
            ):
                is_accessible = self.is_port_available(port)
                updated_status = "Available" if is_accessible else "In use"
                port_data[index] = (
                    updated_status,
                    port,
                    vendor_id,
                    device_name,
                    description,
                )

            for index, (status, port, vendor_id, device_name, description) in enumerate(
                port_data
            ):
                if status != "Available":
                    print(f"Skipping device scan for port {port} as it is not accessible.")
                    continue
                print(f"Scanning device on port: {port}")
                p = by_device.get(port)
                vid = str(p.vid) if p and p.vid else vendor_id
                identified_device = self._identify_device_with_defs(
                    port, vid, device_definitions
                )
                if identified_device != "Unknown":
                    device_name = identified_device
                port_data[index] = (
                    status,
                    port,
                    vendor_id,
                    device_name,
                    description,
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
        self.sort_treeview()
        self._finish_port_scan()

    def _identify_device_with_defs(self, port, vendor_id, device_definitions):
        """Like identify_device but uses a passed-in definitions dict (thread-safe)."""
        print(f"Identifying device on port: {port} with Vendor ID: {vendor_id}")
        for device in device_definitions["devices"]:
            if not self._vendor_id_in_list(vendor_id, device["vendor_ids"]):
                continue
            try:
                with serial.Serial(
                    port,
                    baudrate=device["serial_parameters"]["baudrate"],
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
                            f"{device['model']} on port {port}"
                        )
                        return device["model"]
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
        return "Unknown"

    def toggle_auto_port_scan(self):
        """Handle the 'Auto Port Scan' checkbox toggle."""
        print(f"'Auto Port Scan' checkbox toggled: {self.auto_port_scan_var.get()}")
        self.root.update_idletasks()  # Refresh the UI immediately
        if self.auto_port_scan_var.get():
            print("Auto Port Scan enabled.")
            self.start_auto_port_scan()
        else:
            print("Auto Port Scan disabled.")

    def toggle_device_scan(self):
        """Handle the 'Device Scan' checkbox toggle."""
        print(f"'Device Scan' checkbox toggled: {self.device_scan_var.get()}")
        self.root.update_idletasks()
        if self.device_scan_var.get():
            print("Device Scan enabled.")
            self.start_device_scan()
        else:
            print("Device Scan disabled — showing vendor/port IDs.")
            self.update_ports_from_data()
            self.sort_treeview()

    def start_auto_port_scan(self):
        if self.auto_port_scan_var.get():
            if not self._port_scan_running:
                self.scan_ports(full=False)
            self.root.after(AUTO_PORT_SCAN_MS, self.start_auto_port_scan)

    def start_device_scan(self):
        if self.device_scan_var.get():
            if not self._device_scan_running:
                self.scan_available_ports()
            self.root.after(3000, self.start_device_scan)

    def scan_available_ports(self):
        """Scan for devices on available ports (background thread)."""
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
            device_updates = {}
            for status, port, vendor_id, device_name, description in self.port_data:
                if status != "Available":
                    print(f"Skipping port {port} as it is {status}.")
                    continue
                p = by_device.get(port)
                vid = str(p.vid) if p and p.vid else vendor_id
                print(f"Scanning device on port: {port} with Vendor ID: {vid}")
                identified_device = self._identify_device_with_defs(
                    port, vid, device_definitions
                )
                if identified_device != "Unknown":
                    device_updates[port] = identified_device
            self.root.after(
                0,
                lambda u=device_updates: self._apply_device_scan_result(u),
            )
        except Exception as e:
            print(f"Device scan failed: {e}")
            self.root.after(0, self._finish_device_scan)

    def _apply_device_scan_result(self, device_updates):
        """Merge identified device names into port_data."""
        if device_updates:
            self.port_data = [
                (
                    status,
                    port,
                    vendor_id,
                    device_updates.get(port, device_name),
                    description,
                )
                for status, port, vendor_id, device_name, description in self.port_data
            ]
        self.update_ports_from_data()
        self.sort_treeview()
        self._finish_device_scan()

    def _finish_device_scan(self):
        self._device_scan_running = False
        if self._device_scan_lock.locked():
            self._device_scan_lock.release()

    def toggle_ports_in_use(self):
        """Handle the 'Ports in Use' checkbox toggle."""
        print(f"'Ports in Use' checkbox toggled: {self.show_in_use_var.get()}")
        self.root.update_idletasks()  # Refresh the UI immediately
        self.update_ports_from_data()  # Update the treeview without rescanning
        self.sort_treeview()  # Sort the treeview by 'Status' and then by 'Port #'


if __name__ == "__main__":
    root = tk.Tk()
    app = SerialPortApp(root)
    root.mainloop()
