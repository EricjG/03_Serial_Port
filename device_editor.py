import tkinter as tk
from tkinter import ttk, messagebox
import json
import os

class DeviceEditorApp:
    def __init__(self, root, json_file):
        self.root = root
        self.root.title("Serial Port Device Editor")
        self.root.geometry("480x600")
        self.root.iconbitmap("1871658-200.png")  # todo: Need to find a ICO file in order for this to work.
        self.json_file = json_file

        # Create a scrollable frame for device details
        main_frame = tk.Frame(root)
        main_frame.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(main_frame)
        scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=canvas.yview)
        self.scrollable_frame = tk.Frame(canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Load devices from JSON
        self.devices = self.load_devices()

        # Dropdown menu to select a device
        label_frame = tk.Frame(self.scrollable_frame)
        label_frame.pack(fill=tk.X, pady=5)
        tk.Label(label_frame, text="Devices", anchor="w").pack(side=tk.LEFT, padx=5)  # Align label directly above the dropdown
        self.device_names = [f"{device['manufacturer']} {device['model']}" for device in self.devices]
        self.selected_device = tk.StringVar(value=self.device_names[0] if self.device_names else "")
        self.device_dropdown = ttk.Combobox(label_frame, textvariable=self.selected_device, values=self.device_names, state="readonly", width=40)  # Make dropdown twice as wide
        self.device_dropdown.pack(side=tk.LEFT, pady=5)
        self.device_dropdown.bind("<<ComboboxSelected>>", self.load_device_details)

        # Frame for device details
        self.details_frame = tk.Frame(self.scrollable_frame)
        self.details_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Device details fields
        self.fields = {}
        self.create_device_fields()

        # Buttons
        button_frame = tk.Frame(root)  # Place buttons outside the scrollable area
        button_frame.pack(pady=10, side=tk.BOTTOM)

        self.save_button = tk.Button(button_frame, text="Save Changes", command=self.save_changes)
        self.save_button.pack(side=tk.LEFT, padx=5)

        self.new_button = tk.Button(button_frame, text="New Device", command=self.new_device)
        self.new_button.pack(side=tk.LEFT, padx=5)

        self.delete_button = tk.Button(button_frame, text="Delete Device", command=self.delete_device)
        self.delete_button.pack(side=tk.LEFT, padx=5)

        # Load the first device details if available
        if self.device_names and self.devices:
            self.device_dropdown.current(0)  # Ensure the first device is selected
            self.load_device_details()
        else:
            self.device_dropdown.set("")  # Clear the dropdown if no devices are available
            messagebox.showinfo("Info", "No devices available to load.")

    def load_devices(self):
        """Load devices from the JSON file."""
        if not os.path.exists(self.json_file):
            return []
        with open(self.json_file, "r") as f:
            data = json.load(f)
        return data.get("devices", [])

    def save_devices(self):
        """Save devices to the JSON file."""
        with open(self.json_file, "w") as f:
            json.dump({"devices": self.devices}, f, indent=2)

    def create_device_fields(self):
        """Create fields for device details."""
        dropdown_options = {
            "Baudrate": [300, 600, 1200, 2400, 4800, 9600, 14400, 19200, 38400, 57600, 115200, 230400, 460800],  # Standard baud rates
            "Parity": ["N", "E", "O", "M", "S"],
            "Stopbits": [1, 1.5, 2],
            "Bytesize": [5, 6, 7, 8]
        }

        # Create fields for Vendor IDs
        vendor_frame = tk.Frame(self.details_frame)
        vendor_frame.pack(fill=tk.X, pady=7)  # Reduced pady by 30%
        tk.Label(vendor_frame, text="Vendor IDs", width=10, anchor="w").pack(side=tk.LEFT, padx=2)  # Title text
        vendor_entry = tk.Entry(vendor_frame, width=10)  # Make the text box shorter
        vendor_entry.pack(side=tk.LEFT, padx=2)  # Align text box closer to the title
        self.fields["Vendor IDs"] = vendor_entry

        # Create a single row for Manufacturer and Model text boxes
        general_frame = tk.Frame(self.details_frame)
        general_frame.pack(fill=tk.X, pady=7)  # Reduced pady by 30%

        for label in ["Manufacturer", "Model"]:
            sub_frame = tk.Frame(general_frame)
            sub_frame.pack(side=tk.LEFT, padx=10, expand=True, fill=tk.X)
            tk.Label(sub_frame, text=label, anchor="w").pack(fill=tk.X)  # Title text above the text box
            entry = tk.Entry(sub_frame)
            entry.pack(fill=tk.X, expand=True, padx=5)
            self.fields[label] = entry

        # Create a section for Serial Port Settings
        serial_frame = tk.LabelFrame(self.details_frame, text="Serial Port Settings", padx=10, pady=10)
        serial_frame.pack(fill=tk.X, pady=7)  # Reduced pady by 30%

        for serial_label, options in dropdown_options.items():
            sub_frame = tk.Frame(serial_frame)
            sub_frame.pack(side=tk.LEFT, padx=10, expand=True, fill=tk.X)
            tk.Label(sub_frame, text=serial_label, anchor="w").pack(fill=tk.X)
            combo = ttk.Combobox(sub_frame, values=options, state="readonly", width=10)  # Adjust width for expected data
            combo.pack(fill=tk.X, expand=True)
            self.fields[serial_label] = combo

        # Create a section for Initialize commands
        init_frame = tk.LabelFrame(self.details_frame, text="Initialize", padx=10, pady=10)
        init_frame.pack(fill=tk.X, pady=7)  # Reduced pady by 30%
        for label in ["Initialize Command", "Initialize Pause"]:
            frame = tk.Frame(init_frame)
            frame.pack(fill=tk.X, pady=2)
            tk.Label(frame, text=label, width=20, anchor="w").pack(side=tk.LEFT)
            entry = tk.Entry(frame)
            entry.pack(fill=tk.X, expand=True, padx=5)
            self.fields[label] = entry

        # Create a section for Identify commands
        identify_frame = tk.LabelFrame(self.details_frame, text="Identify", padx=10, pady=10)
        identify_frame.pack(fill=tk.X, pady=7)  # Reduced pady by 30%
        for label in ["Identify Command", "Identify Pause"]:
            frame = tk.Frame(identify_frame)
            frame.pack(fill=tk.X, pady=2)
            tk.Label(frame, text=label, width=20, anchor="w").pack(side=tk.LEFT)
            entry = tk.Entry(frame)
            entry.pack(fill=tk.X, expand=True, padx=5)
            self.fields[label] = entry

        # Create a section for Response settings
        response_frame = tk.LabelFrame(self.details_frame, text="Response", padx=10, pady=10)
        response_frame.pack(fill=tk.X, pady=7)  # Reduced pady by 30%
        for label in ["Response Regex"]:
            frame = tk.Frame(response_frame)
            frame.pack(fill=tk.X, pady=2)
            tk.Label(frame, text=label, width=20, anchor="w").pack(side=tk.LEFT)
            entry = tk.Entry(frame)
            entry.pack(fill=tk.X, expand=True, padx=5)
            self.fields[label] = entry

    def load_device_details(self, event=None):
        """Load the details of the selected device into the fields."""
        selected_index = self.device_dropdown.current()
        if selected_index == -1:
            return
        device = self.devices[selected_index]

        # Safely load fields with default values if keys are missing
        self.fields["Manufacturer"].delete(0, tk.END)
        self.fields["Manufacturer"].insert(0, device.get("manufacturer", ""))
        self.fields["Model"].delete(0, tk.END)
        self.fields["Model"].insert(0, device.get("model", ""))
        if "Vendor IDs" in self.fields:
            self.fields["Vendor IDs"].delete(0, tk.END)
            self.fields["Vendor IDs"].insert(0, ",".join(device.get("vendor_ids", [])))
        if "Baudrate" in self.fields:
            self.fields["Baudrate"].set(device.get("serial_parameters", {}).get("baudrate", ""))
        if "Parity" in self.fields:
            self.fields["Parity"].set(device.get("serial_parameters", {}).get("parity", ""))
        if "Stopbits" in self.fields:
            self.fields["Stopbits"].set(device.get("serial_parameters", {}).get("stopbits", ""))
        if "Bytesize" in self.fields:
            self.fields["Bytesize"].set(device.get("serial_parameters", {}).get("bytesize", ""))
        if "Initialize Command" in self.fields:
            self.fields["Initialize Command"].delete(0, tk.END)
            self.fields["Initialize Command"].insert(0, repr(device.get("commands", {}).get("initialize", {}).get("message", "")))
        if "Initialize Pause" in self.fields:
            self.fields["Initialize Pause"].delete(0, tk.END)
            self.fields["Initialize Pause"].insert(0, device.get("commands", {}).get("initialize", {}).get("pause", ""))
        if "Identify Command" in self.fields:
            self.fields["Identify Command"].delete(0, tk.END)
            self.fields["Identify Command"].insert(0, repr(device.get("commands", {}).get("identify", {}).get("message", "")))
        if "Identify Pause" in self.fields:
            self.fields["Identify Pause"].delete(0, tk.END)
            self.fields["Identify Pause"].insert(0, device.get("commands", {}).get("identify", {}).get("pause", ""))
        if "Response Regex" in self.fields:
            self.fields["Response Regex"].delete(0, tk.END)
            self.fields["Response Regex"].insert(0, device.get("response", {}).get("regex", ""))

    def save_changes(self):
        """Save changes to the selected device."""
        selected_index = self.device_dropdown.current()
        if selected_index == -1:
            messagebox.showerror("Error", "No device selected.")
            return
        device = self.devices[selected_index]
        device["manufacturer"] = self.fields["Manufacturer"].get()
        device["model"] = self.fields["Model"].get()
        device["vendor_ids"] = self.fields["Vendor IDs"].get().split(",")
        device["serial_parameters"]["baudrate"] = int(self.fields["Baudrate"].get())
        device["serial_parameters"]["parity"] = self.fields["Parity"].get()
        device["serial_parameters"]["stopbits"] = float(self.fields["Stopbits"].get())
        device["serial_parameters"]["bytesize"] = int(self.fields["Bytesize"].get())
        device["commands"]["initialize"]["message"] = eval(self.fields["Initialize Command"].get())  # Use eval to parse escape characters
        device["commands"]["initialize"]["pause"] = int(self.fields["Initialize Pause"].get())
        device["commands"]["identify"]["message"] = eval(self.fields["Identify Command"].get())  # Use eval to parse escape characters
        device["commands"]["identify"]["pause"] = int(self.fields["Identify Pause"].get())
        device["response"]["regex"] = self.fields["Response Regex"].get()
        self.save_devices()
        messagebox.showinfo("Success", "Device updated successfully.")

    def new_device(self):
        """Create a new device."""
        new_device = {
            "vendor_ids": [],
            "manufacturer": "",
            "model": "",
            "serial_parameters": {
                "baudrate": 9600,
                "parity": "N",
                "stopbits": 1,
                "bytesize": 8
            },
            "commands": {
                "initialize": {
                    "message": "",
                    "pause": 1
                },
                "identify": {
                    "message": "",
                    "pause": 1
                }
            },
            "response": {
                "regex": "",
                "device_column": ""
            }
        }
        self.devices.append(new_device)
        self.device_names.append("New Device")
        self.device_dropdown["values"] = self.device_names
        self.device_dropdown.current(len(self.device_names) - 1)
        self.load_device_details()

    def delete_device(self):
        """Delete the selected device."""
        selected_index = self.device_dropdown.current()
        if selected_index == -1:
            messagebox.showerror("Error", "No device selected.")
            return
        confirm = messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this device?")
        if confirm:
            del self.devices[selected_index]
            del self.device_names[selected_index]
            self.device_dropdown["values"] = self.device_names
            if self.device_names:
                self.device_dropdown.current(0)
                self.load_device_details()
            else:
                self.device_dropdown.set("")
                for field in self.fields.values():
                    field.delete(0, tk.END)
            self.save_devices()
            messagebox.showinfo("Success", "Device deleted successfully.")

if __name__ == "__main__":
    root = tk.Tk()
    app = DeviceEditorApp(root, "devices.json")
    root.mainloop()
