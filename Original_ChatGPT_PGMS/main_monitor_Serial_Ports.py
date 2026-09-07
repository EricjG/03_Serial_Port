import serial.tools.list_ports  # Before executing for the 1st time you will need to run 'pip install pyserial' in the terminal window.
import time
import multiprocessing


def monitor_ports(shared_data):
    """Background function to monitor serial port changes."""
    previous_ports = set()

    while True:
        current_ports = {port.device for port in serial.tools.list_ports.comports()}
        if current_ports != previous_ports:
            shared_data["ports_changed"] = True
            shared_data["available_ports"] = list(current_ports)
            print(f"Updated ports: {shared_data['available_ports']}")
            previous_ports = current_ports

        time.sleep(2)  # Check every 2 seconds


if __name__ == "__main__":
    with multiprocessing.Manager() as manager:
        shared_data = manager.dict(
            {"ports_changed": False, "available_ports": [], "monitoring": True}
        )

        monitor_process = multiprocessing.Process(
            target=monitor_ports, args=(shared_data,)
        )
        monitor_process.start()

        try:
            while True:
                time.sleep(2)  # Keep running
        except KeyboardInterrupt:
            print("Stopping Serial Monitor...")
            monitor_process.terminate()
