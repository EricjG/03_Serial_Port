import multiprocessing
import time
import serial.tools.list_ports
import tkinter as tk
from tkinter import ttk


def get_serial_ports():
    """Retrieve the list of available serial ports with details."""
    ports = list(serial.tools.list_ports.comports())
    return [
        {"device": port.device, "description": port.description, "hwid": port.hwid}
        for port in ports
    ]


def monitor_serial_ports(shared_data):
    """Background process that monitors serial ports and detects changes."""
    shared_data["previous_ports"] = get_serial_ports()
    shared_data["available_ports"] = shared_data["previous_ports"]
    shared_data["ports_changed"] = False

    while True:
        if shared_data["monitoring"]:
            time.sleep(shared_data["search_sleep_time"])  # Adjustable scan interval

            new_ports = get_serial_ports()
            if new_ports != shared_data["available_ports"]:
                shared_data["previous_ports"] = shared_data["available_ports"]
                shared_data["available_ports"] = new_ports
                shared_data["ports_changed"] = True
                shared_data["monitoring"] = (
                    False  # Pause monitoring until GUI resets it
                )


def start_gui(shared_data):
    """Tkinter GUI that displays port changes and resumes monitoring."""
    root = tk.Tk()
    root.title("Serial Port Monitor")
    root.geometry("600x500")

    # Frame for port changes
    frame_changes = ttk.LabelFrame(root, text="Port Changes", padding=10)
    frame_changes.pack(fill="both", expand=True, padx=10, pady=5)

    listbox_changes = tk.Listbox(frame_changes, height=10, width=70)
    listbox_changes.pack(fill="both", expand=True)

    # Frame for available ports
    frame_available = ttk.LabelFrame(root, text="Current Ports", padding=10)
    frame_available.pack(fill="both", expand=True, padx=10, pady=5)

    listbox_available = tk.Listbox(frame_available, height=10, width=70)
    listbox_available.pack(fill="both", expand=True)

    # Resume/Pause Button
    btn_monitor = ttk.Button(
        root, text="Pause Monitoring", command=lambda: toggle_monitoring(btn_monitor)
    )
    btn_monitor.pack(pady=10)

    def update_gui():
        """Check shared memory and update GUI if changes are detected."""
        # Check if ports have changed and update the list
        if shared_data["ports_changed"]:
            listbox_changes.delete(0, tk.END)

            prev_ports = {p["device"]: p for p in shared_data["previous_ports"]}
            curr_ports = {p["device"]: p for p in shared_data["available_ports"]}

            added_ports = [curr_ports[p] for p in curr_ports if p not in prev_ports]
            removed_ports = [prev_ports[p] for p in prev_ports if p not in curr_ports]

            listbox_changes.insert(tk.END, "Port Change Detected!")

            if removed_ports:
                listbox_changes.insert(tk.END, "\nRemoved Ports:")
                for port in removed_ports:
                    listbox_changes.insert(
                        tk.END,
                        f"  - {port['device']} ({port['description']}) [REMOVED]",
                    )

            if added_ports:
                listbox_changes.insert(tk.END, "\nAdded Ports:")
                for port in added_ports:
                    listbox_changes.insert(
                        tk.END, f"  - {port['device']} ({port['description']}) [ADDED]"
                    )

            if not added_ports and not removed_ports:
                listbox_changes.insert(tk.END, "  - No actual changes detected")

            # Reset flag to allow monitoring to resume
            shared_data["ports_changed"] = False

        # Update the available ports listbox
        listbox_available.delete(0, tk.END)
        listbox_available.insert(tk.END, "Currently Available Ports:")
        for port in shared_data["available_ports"]:
            listbox_available.insert(
                tk.END, f"  - {port['device']} ({port['description']})"
            )

        # Update the button text based on monitoring state
        btn_monitor.config(
            text="Pause Monitoring"
            if shared_data["monitoring"]
            else "Resume Monitoring"
        )

        root.after(1000, update_gui)  # Call update_gui every 1000 ms

    def toggle_monitoring(button):
        """Toggle monitoring on/off and update button text."""
        shared_data["monitoring"] = not shared_data["monitoring"]

    update_gui()  # Start update loop
    root.mainloop()


if __name__ == "__main__":
    with multiprocessing.Manager() as manager:
        shared_data = manager.dict(
            {
                "ports_changed": False,
                "previous_ports": [],
                "available_ports": [],
                "monitoring": True,
                "search_sleep_time": 1.0,  # Faster when searching
                "idle_sleep_time": 5.0,  # Slower when stable
            }
        )

        monitor_process = multiprocessing.Process(
            target=monitor_serial_ports, args=(shared_data,)
        )
        monitor_process.start()

        start_gui(shared_data)  # Start the GUI in the main process

        monitor_process.join()
