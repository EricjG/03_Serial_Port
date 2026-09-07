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


# Load the device configuration from the devices.json file
def load_device_config(file_path="devices.json"):
    try:
        with open(file_path, "r") as file:
            return json.load(file)
    except Exception as e:
        print(f"Error loading device config: {e}")
        return {}


# Function to scan the available serial ports
def scan_ports():
    return list(serial.tools.list_ports.comports())


# Function to identify the device based on serial port settings
def identify_device(port_info, device_config):
    try:
        # Loop through the device configurations and find the matching port
        for device in device_config:
            # Open the serial port with attributes from the JSON config
            with serial.Serial(
                port_info.device,
                baudrate=device["baudrate"],
                parity=device["parity"],
                stopbits=device["stopbits"],
                bytesize=device["bytesize"],
                timeout=2,
            ) as ser:
                # Send init command to the device
                ser.write(device["init"].encode())
                time.sleep(device.get("wait_time", 1))

                # Send query command and get the response
                ser.write(device["query"].encode())
                response = ser.read(100).decode(errors="ignore")

                # Check if the response matches the expected pattern using regex
                if re.search(device["response_regex"], response):
                    return device[
                        "name"
                    ], response  # Return the device name and response data
    except serial.SerialException as e:
        print(f"Serial error on {port_info.device}: {e}")
        return "In Use", "-"
    except Exception as e:
        print(f"Error identifying device on {port_info.device}: {e}")
    return "Unknown Device", "N/A"


# Function to update the serial ports and show the results in the GUI
def update_ports():
    global devices, known_ports, open_ports
    new_ports = scan_ports()
    current_ports = {port_info.device for port_info in new_ports}
    new_ports_detected = current_ports - known_ports

    # Only check new ports that have been added
    if new_ports_detected:
        results = []
        for port_info in new_ports:
            if port_info.device in new_ports_detected:
                # Check if the port is already in use or if it is unknown
                if port_info.device in open_ports:
                    results.append(("In Use", port_info.device, "-", "N/A"))
                else:
                    # Identify the device and fetch information
                    device_name, formatted_response = identify_device(
                        port_info, devices
                    )
                    # Get driver information - this will be a fallback placeholder in this case
                    driver_info = (
                        port_info.description
                        if hasattr(port_info, "description")
                        else "Unknown Driver"
                    )
                    # Add results to the list
                    results.append(
                        (
                            device_name or "Unknown Device",
                            port_info.device,
                            formatted_response or "N/A",
                            driver_info,
                        )
                    )
                    open_ports.add(port_info.device)
                # Add the port to known_ports to avoid rechecking
                known_ports.add(port_info.device)

        # Sort the results by device name, with unknown devices at the end
        results.sort(key=lambda x: (x[0] == "Unknown Device", x[0]))

        # Update the listbox with the new results
        for device_name, port, info, driver in results:
            # Check if the port is already in the list
            existing_items = [
                item
                for item in listbox.get_children()
                if listbox.item(item)["values"][1] == port
            ]
            if existing_items:
                # Update the existing item
                listbox.item(
                    existing_items[0], values=(device_name, port, info, driver)
                )
            else:
                # Insert a new item
                listbox.insert("", "end", values=(device_name, port, info, driver))

    # Re-check in 5 seconds for new ports only
    root.after(5000, update_ports)


# Function to refresh and check unopened serial ports
def refresh_unopened():
    update_ports()


# Create the main Tkinter window
root = tk.Tk()
root.title("Serial Device Scanner")

# Create a frame for the GUI elements
frame = ttk.Frame(root)
frame.pack(padx=10, pady=10, fill="both", expand=True)

# Define the columns for the listbox
columns = ("Device Name", "Port", "Device", "Driver")
listbox = ttk.Treeview(frame, columns=columns, show="headings")
for col in columns:
    listbox.heading(col, text=col)
    listbox.column(col, width=150)
listbox.pack(fill="both", expand=True)

# Button to refresh and recheck unopened serial ports
refresh_button = ttk.Button(
    frame, text="Recheck Unopened Ports", command=refresh_unopened
)
refresh_button.pack(pady=5)

# Load the device configuration from the JSON file
devices = load_device_config()

# Initialize known and open ports sets
known_ports = set()
open_ports = set()

# Start the port scanning and updating process
update_ports()

# Start the Tkinter main loop
root.mainloop()
