Serial Port local Python Application

This is split into 2 different types of apps

1st one is designed as an app add on that help to locate a device on a serial port and then pass that info back to the application that requested it

2nd App allows user to test the port and/or to identfy a port.
In addition is has a develop and test to find a Device connected to a serial port.

## Setup

From this folder, create a local virtual environment and install the Python packages (Windows):

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

`run.bat` already uses `.venv\Scripts\python.exe`, so you only need to do the steps above once.

## How to run

- Serial port / device picker: double-click `run.bat`, or run `python serial_port_app.py`
- Device editor: `python device_editor.py`

## Tests

The tests do not need a serial cable or a window. From this folder:

```
python -m unittest discover -v
```

You can also run one file: `python -m unittest test_device_identity.py`

GitHub Actions runs the same command on every push and pull request (Ubuntu and Windows, Python 3.12).

## devices.json fields

Each item under `"devices"` describes one piece of equipment:

- `vendor_ids` — USB vendor ID(s) as decimal strings. A port is matched to definitions that list that vendor ID.
- `manufacturer`, `model`, `short_description`, `long_description` — name and notes. The Device/Driver column for an identified port uses manufacturer, model, and long description.
- `serial_parameters` — `baudrate`, `parity`, `stopbits`, `bytesize` used when talking to the device.
- `commands.initialize` / `commands.identify` — `message` to send and `pause` (seconds) to wait.
- `response.regex` — pattern that must appear in the device's reply to count as a match. Named groups like `(?P<model>...)` are allowed.
- `response.device_column` — template text stored with the device (for example `SIMCom {model}`).
