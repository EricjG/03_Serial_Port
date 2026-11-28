import tkinter as tk
from tkinter import ttk, messagebox
import tkinter.font as tkfont
import json
import os

from app_icon import apply_window_icon, set_windows_app_user_model_id
from device_data import (
    TTL_LEVELS,
    RESET_LINES,
    controllers_field_text,
    format_init_steps_text,
    parse_controllers_text,
    parse_init_steps_text,
)

# Theme - Serial Port Apps (Iris): this field only.
UI_FG = "#1a1a1a"
UI_OUTLINE = "#A0A0A0"
UI_CONTROL_H = 24
UI_FONT_CANDIDATES = ("Segoe UI", "Noto Sans", "DejaVu Sans", "Arial")
UI_FONT_SIZE = 9
PORT_VID_PID_LABEL = "Port VID:PID"


class DeviceEditorApp:
    def __init__(self, root, json_file):
        self.root = root
        self.root.title("Serial Port Device Editor")
        self.root.geometry("480x600")
        set_windows_app_user_model_id()
        self._icon_photos = apply_window_icon(self.root, default=True)
        self.json_file = json_file
        self._init_fonts()

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

    def _init_fonts(self):
        """Segoe UI 9, same fallbacks as the picker."""
        try:
            available = set(tkfont.families())
        except (tk.TclError, TypeError, ValueError):
            available = set()
        family = next(
            (name for name in UI_FONT_CANDIDATES if name in available),
            "TkDefaultFont",
        )
        self._font_control = (family, UI_FONT_SIZE)
        self._font_label = (family, UI_FONT_SIZE, "bold")

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

        # Port VID:PID — comma-separated hex, PID optional (theme: 24px, 1px #A0A0A0)
        vendor_frame = tk.Frame(self.details_frame)
        vendor_frame.pack(fill=tk.X, pady=7)
        tk.Label(
            vendor_frame,
            text=PORT_VID_PID_LABEL,
            anchor="w",
            font=self._font_label,
            fg=UI_FG,
        ).pack(side=tk.LEFT, padx=2)
        wrap = tk.Frame(
            vendor_frame,
            bg="#FFFFFF",
            highlightbackground=UI_OUTLINE,
            highlightthickness=1,
            highlightcolor=UI_OUTLINE,
            bd=0,
            relief=tk.FLAT,
            height=UI_CONTROL_H,
        )
        wrap.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        wrap.pack_propagate(False)
        vendor_entry = tk.Entry(
            wrap,
            font=self._font_control,
            width=32,
            relief=tk.FLAT,
            bd=0,
            highlightthickness=0,
            fg=UI_FG,
            background="#FFFFFF",
        )
        vendor_entry.pack(fill=tk.BOTH, expand=True, padx=4, pady=0)
        self.fields[PORT_VID_PID_LABEL] = vendor_entry

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

        # Optional hardware reset pulse (DTR/RTS) before initialize
        reset_frame = tk.LabelFrame(self.details_frame, text="Reset", padx=10, pady=10)
        reset_frame.pack(fill=tk.X, pady=7)
        reset_dropdowns = {
            "Reset Line": ("",) + RESET_LINES,
            "Run State": ("",) + TTL_LEVELS,
            "Reset State": ("",) + TTL_LEVELS,
        }
        for label, options in reset_dropdowns.items():
            frame = tk.Frame(reset_frame)
            frame.pack(fill=tk.X, pady=2)
            tk.Label(frame, text=label, width=20, anchor="w").pack(side=tk.LEFT)
            combo = ttk.Combobox(
                frame, values=options, state="readonly", width=10
            )
            combo.pack(fill=tk.X, expand=True, padx=5)
            self.fields[label] = combo
        for label in ("Pulse (ms)", "Wait For", "Wait For Regex", "Reset Timeout (ms)"):
            frame = tk.Frame(reset_frame)
            frame.pack(fill=tk.X, pady=2)
            tk.Label(frame, text=label, width=20, anchor="w").pack(side=tk.LEFT)
            entry = tk.Entry(frame)
            entry.pack(fill=tk.X, expand=True, padx=5)
            self.fields[label] = entry

        # Create a section for Initialize commands
        init_frame = tk.LabelFrame(self.details_frame, text="Initialize", padx=10, pady=10)
        init_frame.pack(fill=tk.X, pady=7)  # Reduced pady by 30%
        for label in (
            "Initialize Command",
            "Initialize Pause",
            "Initialize Expect",
            "Initialize Timeout",
        ):
            frame = tk.Frame(init_frame)
            frame.pack(fill=tk.X, pady=2)
            tk.Label(frame, text=label, width=20, anchor="w").pack(side=tk.LEFT)
            entry = tk.Entry(frame)
            entry.pack(fill=tk.X, expand=True, padx=5)
            self.fields[label] = entry
        steps_frame = tk.Frame(init_frame)
        steps_frame.pack(fill=tk.X, pady=2)
        tk.Label(
            steps_frame, text="Initialize Steps", width=20, anchor="nw"
        ).pack(side=tk.LEFT)
        steps_text = tk.Text(steps_frame, height=8, width=36, wrap=tk.NONE)
        steps_text.pack(fill=tk.X, expand=True, padx=5)
        self.fields["Initialize Steps"] = steps_text

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
        self.append_response_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            response_frame,
            text="Show response after device name",
            variable=self.append_response_var,
            anchor="w",
        ).pack(fill=tk.X, pady=2)

    @staticmethod
    def _pause_field_value(command):
        """Show pause_ms when present; fall back to old pause (seconds)."""
        command = command or {}
        if command.get("pause_ms") is not None and command.get("pause_ms") != "":
            return str(command.get("pause_ms"))
        if command.get("pause") is not None and command.get("pause") != "":
            try:
                return str(int(round(float(command.get("pause")) * 1000)))
            except (TypeError, ValueError):
                return str(command.get("pause"))
        return ""

    @staticmethod
    def _pause_ms_from_field(text):
        text = (text or "").strip()
        if not text:
            return 0
        return int(float(text))

    def _save_reset_fields(self, device):
        line = (self.fields["Reset Line"].get() or "").strip().upper()
        if not line:
            device["commands"].pop("reset", None)
            return
        def _int_field(label, default=0):
            text = (self.fields[label].get() or "").strip()
            if not text:
                return default
            return int(float(text))

        device["commands"]["reset"] = {
            "line": line,
            "run_state": (self.fields["Run State"].get() or "High").strip() or "High",
            "reset_state": (self.fields["Reset State"].get() or "Low").strip() or "Low",
            "pulse_ms": _int_field("Pulse (ms)", 0),
            "wait_for": self.fields["Wait For"].get() if "Wait For" in self.fields else "",
            "timeout_ms": _int_field("Reset Timeout (ms)", 0),
        }
        if "Wait For Regex" in self.fields:
            regex = (self.fields["Wait For Regex"].get() or "").strip()
            if regex:
                device["commands"]["reset"]["wait_for_regex"] = regex

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
        if PORT_VID_PID_LABEL in self.fields:
            self.fields[PORT_VID_PID_LABEL].delete(0, tk.END)
            self.fields[PORT_VID_PID_LABEL].insert(0, controllers_field_text(device))
        if "Baudrate" in self.fields:
            self.fields["Baudrate"].set(device.get("serial_parameters", {}).get("baudrate", ""))
        if "Parity" in self.fields:
            self.fields["Parity"].set(device.get("serial_parameters", {}).get("parity", ""))
        if "Stopbits" in self.fields:
            self.fields["Stopbits"].set(device.get("serial_parameters", {}).get("stopbits", ""))
        if "Bytesize" in self.fields:
            self.fields["Bytesize"].set(device.get("serial_parameters", {}).get("bytesize", ""))
        commands = device.get("commands") or {}
        initialize = commands.get("initialize") or {}
        identify = commands.get("identify") or {}
        reset = commands.get("reset") if isinstance(commands.get("reset"), dict) else {}
        if "Reset Line" in self.fields:
            self.fields["Reset Line"].set(reset.get("line", ""))
        if "Run State" in self.fields:
            self.fields["Run State"].set(reset.get("run_state", ""))
        if "Reset State" in self.fields:
            self.fields["Reset State"].set(reset.get("reset_state", ""))
        if "Pulse (ms)" in self.fields:
            self.fields["Pulse (ms)"].delete(0, tk.END)
            pulse = reset.get("pulse_ms", "")
            self.fields["Pulse (ms)"].insert(0, "" if pulse in (None, "") else str(pulse))
        if "Wait For" in self.fields:
            self.fields["Wait For"].delete(0, tk.END)
            self.fields["Wait For"].insert(0, reset.get("wait_for", ""))
        if "Wait For Regex" in self.fields:
            self.fields["Wait For Regex"].delete(0, tk.END)
            self.fields["Wait For Regex"].insert(0, reset.get("wait_for_regex", ""))
        if "Reset Timeout (ms)" in self.fields:
            self.fields["Reset Timeout (ms)"].delete(0, tk.END)
            timeout = reset.get("timeout_ms", "")
            self.fields["Reset Timeout (ms)"].insert(
                0, "" if timeout in (None, "") else str(timeout)
            )
        if "Initialize Command" in self.fields:
            self.fields["Initialize Command"].delete(0, tk.END)
            self.fields["Initialize Command"].insert(0, repr(initialize.get("message", "")))
        if "Initialize Pause" in self.fields:
            self.fields["Initialize Pause"].delete(0, tk.END)
            self.fields["Initialize Pause"].insert(
                0, self._pause_field_value(initialize)
            )
        if "Initialize Expect" in self.fields:
            self.fields["Initialize Expect"].delete(0, tk.END)
            self.fields["Initialize Expect"].insert(0, initialize.get("expect", ""))
        if "Initialize Timeout" in self.fields:
            self.fields["Initialize Timeout"].delete(0, tk.END)
            init_timeout = initialize.get("timeout_ms", "")
            self.fields["Initialize Timeout"].insert(
                0, "" if init_timeout in (None, "") else str(init_timeout)
            )
        if "Initialize Steps" in self.fields:
            widget = self.fields["Initialize Steps"]
            try:
                widget.delete("1.0", tk.END)
                widget.insert("1.0", format_init_steps_text(initialize.get("steps")))
            except tk.TclError:
                widget.delete(0, tk.END)
                widget.insert(0, format_init_steps_text(initialize.get("steps")))
        if "Identify Command" in self.fields:
            self.fields["Identify Command"].delete(0, tk.END)
            self.fields["Identify Command"].insert(0, repr(identify.get("message", "")))
        if "Identify Pause" in self.fields:
            self.fields["Identify Pause"].delete(0, tk.END)
            self.fields["Identify Pause"].insert(0, self._pause_field_value(identify))
        if "Response Regex" in self.fields:
            self.fields["Response Regex"].delete(0, tk.END)
            self.fields["Response Regex"].insert(0, device.get("response", {}).get("regex", ""))
        if getattr(self, "append_response_var", None) is not None:
            self.append_response_var.set(
                bool((device.get("response") or {}).get("append_response", False))
            )

    def save_changes(self):
        """Save changes to the selected device."""
        selected_index = self.device_dropdown.current()
        if selected_index == -1:
            messagebox.showerror("Error", "No device selected.")
            return
        device = self.devices[selected_index]
        device["manufacturer"] = self.fields["Manufacturer"].get()
        device["model"] = self.fields["Model"].get()
        device["controllers"] = parse_controllers_text(
            self.fields[PORT_VID_PID_LABEL].get()
        )
        device.pop("vendor_ids", None)
        device["serial_parameters"]["baudrate"] = int(self.fields["Baudrate"].get())
        device["serial_parameters"]["parity"] = self.fields["Parity"].get()
        device["serial_parameters"]["stopbits"] = float(self.fields["Stopbits"].get())
        device["serial_parameters"]["bytesize"] = int(self.fields["Bytesize"].get())
        if "commands" not in device or not isinstance(device.get("commands"), dict):
            device["commands"] = {}
        if "initialize" not in device["commands"] or not isinstance(
            device["commands"].get("initialize"), dict
        ):
            device["commands"]["initialize"] = {}
        if "identify" not in device["commands"] or not isinstance(
            device["commands"].get("identify"), dict
        ):
            device["commands"]["identify"] = {}
        if "Initialize Command" in self.fields:
            device["commands"]["initialize"]["message"] = eval(
                self.fields["Initialize Command"].get()
            )  # Use eval to parse escape characters
        if "Initialize Pause" in self.fields:
            pause_ms = self._pause_ms_from_field(self.fields["Initialize Pause"].get())
            device["commands"]["initialize"]["pause_ms"] = pause_ms
            device["commands"]["initialize"].pop("pause", None)
        if "Initialize Expect" in self.fields:
            expect = (self.fields["Initialize Expect"].get() or "").strip()
            if expect:
                device["commands"]["initialize"]["expect"] = expect
            else:
                device["commands"]["initialize"].pop("expect", None)
        if "Initialize Timeout" in self.fields:
            timeout_text = (self.fields["Initialize Timeout"].get() or "").strip()
            if timeout_text:
                device["commands"]["initialize"]["timeout_ms"] = int(timeout_text)
            else:
                device["commands"]["initialize"].pop("timeout_ms", None)
        if "Initialize Steps" in self.fields:
            widget = self.fields["Initialize Steps"]
            try:
                steps_text = widget.get("1.0", "end")
            except TypeError:
                steps_text = widget.get()
            steps = parse_init_steps_text(steps_text)
            if steps:
                device["commands"]["initialize"]["steps"] = steps
            else:
                device["commands"]["initialize"].pop("steps", None)
        if "Identify Command" in self.fields:
            device["commands"]["identify"]["message"] = eval(
                self.fields["Identify Command"].get()
            )  # Use eval to parse escape characters
        if "Identify Pause" in self.fields:
            pause_ms = self._pause_ms_from_field(self.fields["Identify Pause"].get())
            device["commands"]["identify"]["pause_ms"] = pause_ms
            device["commands"]["identify"].pop("pause", None)
        if "Reset Line" in self.fields:
            self._save_reset_fields(device)
        if "response" not in device or not isinstance(device.get("response"), dict):
            device["response"] = {}
        device["response"]["regex"] = self.fields["Response Regex"].get()
        if getattr(self, "append_response_var", None) is not None:
            device["response"]["append_response"] = bool(
                self.append_response_var.get()
            )
        self.save_devices()
        messagebox.showinfo("Success", "Device updated successfully.")

    def new_device(self):
        """Create a new device."""
        new_device = {
            "controllers": [],
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
                    "pause_ms": 1000,
                },
                "identify": {
                    "message": "",
                    "pause_ms": 1000,
                }
            },
            "response": {
                "regex": "",
                "device_column": "",
                "append_response": False,
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
                    try:
                        field.delete(0, tk.END)
                    except tk.TclError:
                        try:
                            field.delete("1.0", tk.END)
                        except tk.TclError:
                            pass
            self.save_devices()
            messagebox.showinfo("Success", "Device deleted successfully.")

if __name__ == "__main__":
    set_windows_app_user_model_id()
    root = tk.Tk()
    app = DeviceEditorApp(root, "devices.json")
    root.mainloop()
