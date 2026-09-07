import serial.tools.list_ports
import time
import multiprocessing


def monitor_ports(shared_data):
    """Background function to monitor serial port changes."""
    previous_ports = []  # Start with an empty previous list

    while True:
        if not shared_data["monitoring"]:
            time.sleep(1)
            continue

        # Get the current sleep time from shared data
        sleep_time = shared_data["sleep_time"]

        # Get the list of currently available serial ports
        current_ports = []
        for port in serial.tools.list_ports.comports():
            current_ports.append(
                {
                    "device": port.device,  # e.g., COM3
                    "name": port.name,  # e.g., USB Serial Device
                    "description": port.description,  # e.g., FTDI USB Serial Device
                }
            )

        # Convert lists of dictionaries to sets of port names for quick comparison
        current_ports_set = {port["device"] for port in current_ports}
        previous_ports_set = {port["device"] for port in previous_ports}

        # Check if there is a change in the detected ports
        if current_ports_set != previous_ports_set:
            # shared_data["monitoring"] = False  # Stop monitoring
            shared_data["ports_changed"] = True
            shared_data["previous_ports"] = previous_ports  # Store previous list
            shared_data["available_ports"] = current_ports  # Store new list

            # Print previous and new ports
            print("\nPort Change Detected!")
            print("Previous Ports:")
            if previous_ports:
                for port in previous_ports:
                    print(
                        f"  - {port['device']} ({port['name']}, {port['description']})"
                    )
            else:
                print("  - None")

            print("\nNew Ports:")
            if current_ports:
                for port in current_ports:
                    print(
                        f"  - {port['device']} ({port['name']}, {port['description']})"
                    )
            else:
                print("  - None")

            # Update previous_ports to match current_ports for next comparison
            previous_ports = current_ports

        # Sleep for the specified time (shorter when searching, longer when idle)
        time.sleep(sleep_time)


if __name__ == "__main__":
    with multiprocessing.Manager() as manager:
        shared_data = manager.dict(
            {
                "ports_changed": False,
                "previous_ports": [],  # Ensure it's a list
                "available_ports": [],
                "monitoring": True,
                "sleep_time": 0.5,  # Default to 500ms for searching/selecting
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
