import serial
from serial.tools import list_ports

# Print information about all available ports
for port in list_ports.comports():
    print(f"Device: {port.device}")
    print(f"Name: {port.name}")
    print(f"Description: {port.description}")
    print(f"Hardware ID: {port.hwid}")
    print(f"Vendor ID: {port.vid}")
    print(f"Product ID: {port.pid}")
    print(f"Serial Number: {port.serial_number}")
    print(f"Location: {port.location}")
    print(f"Manufacturer: {port.manufacturer}")
    print(f"Product: {port.product}")
    print(f"Interface: {port.interface}")
    print("-" * 40)

# Access COM8 with 115200 baud rate
try:
    with serial.Serial(port="COM8", baudrate=115200, timeout=2) as ser:
        print(f"Successfully opened port {ser.port} with baud rate {ser.baudrate}")
        # Example: Read data from the port
        ser.write(b"AT\r")  # Send a test command (e.g., AT command)
        response = ser.read(ser.in_waiting or 100).decode()
        print(f"Response from COM8: {response}")
except serial.SerialException as e:
    print(f"Error accessing COM8: {e}")