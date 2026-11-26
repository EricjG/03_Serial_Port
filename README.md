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

Each item under `"devices"` describes how to find one piece of equipment. Old files still load: `pause` is treated as seconds, a single `baudrate` becomes a one-item list, and decimal VID/PID values are accepted.

- `manufacturer`, `model` — name. `type` is optional free text (not a fixed list).
- `short_description`, `long_description` — notes. The Device dropdown shows `Manufacturer  model  115.2K Baud` (first listed baud). `long_description` is not in that dropdown.
- `controllers` — USB-serial chips this device may sit behind. `vid` / `pid` are hex strings (`"0x10C4"`). If `pid` is omitted, any product ID from that vendor matches.
- `serial_parameters.baud_rates` — baud values tried in order (bps). The picker's Baud dropdown shows this list; if it is missing, the standard baud list is used. Also `data_bits`, `parity` (`None` / `Even` / …), `stop_bits`, `flow_control`.
- `commands.initialize` / `commands.identify` — `message` to send and `pause_ms` to wait (milliseconds). An empty message is skipped.
- `response.regex` — pattern that must appear in the reply. Named groups like `(?P<revision>...)` are allowed.
- `response.device_column` — text for an identified row, filled from regex groups and device fields (for example `Revision {revision}`).

Example:

```json
{
  "devices": [
    {
      "manufacturer": "MUX Wiring",
      "model": "MB607",
      "type": "Body Control Module",
      "controllers": [{"vid": "0x10C4", "pid": "0xEA60"}],
      "serial_parameters": {
        "baud_rates": [460800, 115200],
        "data_bits": 8,
        "parity": "None",
        "stop_bits": 1,
        "flow_control": "None"
      },
      "commands": {
        "initialize": {"message": "\r\r", "pause_ms": 1000},
        "identify": {"message": "I\r", "pause_ms": 1000}
      },
      "response": {
        "regex": "RevPK(?P<revision>\\d+\\.\\d+ \\d{2}/\\d{2}/\\d{2})",
        "device_column": "Revision {revision}"
      }
    }
  ]
}
```
