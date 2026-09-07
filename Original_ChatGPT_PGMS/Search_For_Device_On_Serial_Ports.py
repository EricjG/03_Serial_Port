# 2025-04-04
import sys

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:
    print(
        "Error: Tkinter is not installed. Please install it using 'sudo apt-get install python3-tk' (Linux) or ensure your Python distribution includes Tkinter."
    )
    sys.exit(1)

import serial.tools.list_ports
import json
import time
import threading
import re


def load_device_config(file_path="devices.json"):
    try:
        with open(file_path, "r") as file:
            return json.load(file)
    except Exception as e:
        print(f"Error loading device config: {e}")
        return {}


def scan_ports():
    return list(
        serial.tools.list_ports.comports()
    )  # Return the list of ListPortInfo objects


def identify_device(port, device_config):
    try:
        with serial.Serial(port.device, baudrate=9600, timeout=2) as ser:
            for device in device_config:
                ser.write(device["init"].encode())
                time.sleep(device.get("wait_time", 1))
                ser.write(device["query"].encode())
                response = ser.read(100).decode(errors="ignore")
                if re.search(device["response_regex"], response):
                    return device["name"], device.get("format", response)
    except serial.SerialException as e:
        print(f"Serial error on {port.device}: {e}")
        return "In Use", "N/A"
    except Exception as e:
        print(f"Error identifying device on {port.device}: {e}")
    return "Unknown Device", "N/A"


def update_ports(check_unopened=False):
    global devices, known_ports, open_ports, port_status
    new_ports = scan_ports()
    results = []

    # Collect all ports, whether they are open, identified, or unknown
    for port in new_ports:
        if port.device in port_status and port_status[port.device] == "In Use":
            results.append(("In Use", port.device, "N/A", port.description))
            continue
        if check_unopened or port.device not in known_ports:
            device_name, formatted_response = identify_device(port, devices)
            port_status[port.device] = device_name
            results.append(
                (device_name, port.device, formatted_response, port.description)
            )
            known_ports.add(port.device)
        elif port.device not in port_status:
            results.append(("Unknown Device", port.device, "N/A", port.description))
            port_status[port.device] = "Unknown Device"

    results.sort(key=lambda x: (x[0] == "Unknown Device", x[0]))

    # Keep all ports in the list
    listbox.delete(*listbox.get_children())
    for name, port, device, driver in results:
        listbox.insert("", "end", values=(name, port, device, driver))

    adjust_column_widths()
    root.after(1000, update_ports)


def adjust_column_widths():
    for col in columns:
        max_width = 0
        for row in listbox.get_children():
            value = listbox.item(row)["values"][columns.index(col)]
            max_width = max(max_width, len(str(value)))
        listbox.column(
            col, width=max_width * 10
        )  # Adjust *10 for padding and better fit


def refresh_unopened():
    update_ports(check_unopened=True)


root = tk.Tk()
root.title("Serial Device Scanner")

frame = ttk.Frame(root)
frame.pack(padx=10, pady=10, fill="both", expand=True)

columns = ("Device Name", "Port #", "Device", "Driver")
listbox = ttk.Treeview(frame, columns=columns, show="headings")
for col in columns:
    listbox.heading(col, text=col)
    listbox.column(col, width=150)
listbox.pack(fill="both", expand=True)

refresh_button = ttk.Button(
    frame, text="Recheck Unopened Ports", command=refresh_unopened
)
refresh_button.pack(pady=5)

devices = load_device_config()
known_ports = set()
open_ports = set()
port_status = {}
update_ports()
root.mainloop()
