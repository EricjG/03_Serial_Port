import serial.tools.list_ports
import serial
import time
import multiprocessing
import re


def check_port_status(port_name):
    """Check if a serial port is currently open (in use)."""
    try:
        with serial.Serial(port_name, baudrate=9600, timeout=1) as ser:
            return "[AVAILABLE]"
    except (serial.SerialException, OSError):
        return "[IN USE]"


def extract_com_number(port_name):
    """Extract numerical part of COM port for sorting (e.g., 'COM3' -> 3)."""
    match = re.search(r"COM(\d+)", port_name)
    return (
        int(match.group(1)) if match else float("inf")
    )  # Default to inf for non-standard ports


def monitor_ports(shared_data):
    """Background function to monitor serial port changes."""
    previous_ports = []  # Start with an empty previous list

    while True:
        if not shared_data["monitoring"]:
            time.sleep(1)
            continue

        # Use appropriate sleep time based on the flag status
        sleep_time = (
            shared_data["search_sleep_time"]
            if not shared_data["ports_changed"]
            else shared_data["idle_sleep_time"]
        )

        # Get the list of currently available serial ports
        current_ports = []
        for port in serial.tools.list_ports.comports():
            status = check_port_status(port.device)
            current_ports.append(
                {
                    "device": port.device,  # e.g., COM3
                    "name": port.name,  # e.g., USB Serial Device
                    "description": port.description,  # e.g., FTDI USB Serial Device
                    "status": status,  # Shows if it's available or in use
                }
            )

        # Sort by availability first, then by COM port number
        current_ports.sort(
            key=lambda p: (
                p["status"] != "[AVAILABLE]",
                extract_com_number(p["device"]),
            )
        )

        # Convert lists of dictionaries to sets of device names for quick comparison
        current_ports_set = {port["device"] for port in current_ports}
        previous_ports_set = {port["device"] for port in previous_ports}

        # Check if there is a change in the detected ports
        if current_ports_set != previous_ports_set:
            # shared_data["monitoring"] = False  # Stop monitoring
            shared_data["ports_changed"] = True
            shared_data["previous_ports"] = previous_ports  # Store previous list
            shared_data["available_ports"] = current_ports  # Store new list

            # Find added and removed ports
            added_ports = [
                port
                for port in current_ports
                if port["device"] not in previous_ports_set
            ]
            removed_ports = [
                port
                for port in previous_ports
                if port["device"] not in current_ports_set
            ]

            # Print previous ports (sorted)
            print("\nPort Change Detected!")
            print("Previous Ports:")
            if previous_ports:
                for port in sorted(
                    previous_ports,
                    key=lambda p: (
                        p["status"] != "[AVAILABLE]",
                        extract_com_number(p["device"]),
                    ),
                ):
                    print(
                        f"  - {port['device']} ({port['name']}, {port['description']}) {port['status']}"
                    )
            else:
                print("  - None")

            # Print only changed ports
            print("\nPorts Changed:")
            if added_ports or removed_ports:
                for port in removed_ports:
                    print(
                        f"  - {port['device']} ({port['name']}, {port['description']}) [REMOVED]"
                    )
                for port in added_ports:
                    print(
                        f"  - {port['device']} ({port['name']}, {port['description']}) {port['status']} [ADDED]"
                    )
            else:
                print("  - No changes")

            # Update previous_ports to match current_ports for next comparison
            previous_ports = current_ports

        # Sleep for the appropriate time
        time.sleep(sleep_time)


if __name__ == "__main__":
    with multiprocessing.Manager() as manager:
        shared_data = manager.dict(
            {
                "ports_changed": False,
                "previous_ports": [],  # Ensure it's a list
                "available_ports": [],
                "monitoring": True,
                "search_sleep_time": 1.0,  # Default to 1 second when searching
                "idle_sleep_time": 5.0,  # Default to 5 seconds when idle
            }
        )

        # Start the monitoring process
        monitor_process = multiprocessing.Process(
            target=monitor_ports, args=(shared_data,)
        )
        monitor_process.start()

        try:
            while True:
                time.sleep(1)  # Keep running
        except KeyboardInterrupt:
            print("Stopping Serial Monitor...")
            shared_data["monitoring"] = False
            monitor_process.terminate()
