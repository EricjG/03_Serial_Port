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

## Device data files

Three JSON files sit in this folder (a later change will move them to a shared devices folder):

| File | Role | Lookup |
|---|---|---|
| `devices.json` | How to identify a device on a port (commands, regex) | unchanged |
| `serial_ports.json` | USB-serial **chip** catalog (port hardware) | Port VID/PID. If `pid` is omitted, any PID from that VID matches |
| `devices_info.json` | What the **device** is and supports (no detection commands) | `manufacturer` + `model` (same strings as `devices.json`) |

`serial_ports.json` currently lists the FTDI FT232R on Eric's COM3 (`0x0403:0x6001`), the Prolific PL2303 on COM8 (`0x067B:0x2303`), and the Silicon Labs CP210x (`0x10C4:0xEA60`) used by the MB607. Matching is by VID/PID only; COM names in `documents.note_short` are notes for people, not keys.

A missing or invalid file shows a message and does not crash. If `devices.json` already has an error on Device Status, later file errors are logged and the app stays usable with a null match.

The picker uses `serial_ports.json` for Available / In Use "Serial Driver / Connected Device" text (`FTDI FT232R/RL/RQ`). The **Baud** dropdown is also driven by that file: a port whose VID/PID matches a chip lists that chip's `serial_parameters.baud_rates` (or `STANDARD_BAUD_RATES` clipped to `min_baud`..`max_baud` if `baud_rates` is missing). An unknown port uses the standard baud list (no 600). Selecting a device does not shrink the Baud list; it only preselects the device's first baud when that rate is already in the list.

Identified rows show manufacturer, model, and short description from `devices_info.json` when present, otherwise the existing identify `device_column` text.

**Select** prints a JSON preview of the current selection to stdout, then quits. **Exit** (and the window X) prints `{"result": null}`. Run from a terminal (`run.bat`) so you can see that JSON.

## devices.json fields

Each item under `"devices"` describes how to find one piece of equipment. Old files still load: `pause` is treated as seconds, a single `baudrate` becomes a one-item list, and decimal VID/PID values are accepted. Do not strip `type` / `short_description` / `long_description` from this file; identify templates still use them. When filling the Select payload, prefer a `devices_info.json` match and fall back to these fields.

- `manufacturer`, `model` — name. `type` is optional free text (not a fixed list).
- `short_description`, `long_description` — notes. The Device dropdown shows `Manufacturer  model  115.2K Baud` (first listed baud). `long_description` is not in that dropdown.
- `controllers` — USB-serial chips this device may sit behind. `vid` / `pid` are hex strings (`"0x10C4"`). If `pid` is omitted, any product ID from that vendor matches.
- `serial_parameters.baud_rates` — baud values tried in order (bps) when identifying the device. The picker's Baud **dropdown** is **not** this list; it comes from `serial_ports.json` as described above. Also `data_bits`, `parity` (`None` / `Even` / …), `stop_bits`, `flow_control`.
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
