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

The picker uses `serial_ports.json` for Available / In Use "Serial Driver / Connected Device" text (`FTDI FT232R/RL/RQ`). The **Baud** dropdown is also driven by that file: a port whose VID/PID matches a chip lists that chip's `serial_parameters.baud_rates` (or `STANDARD_BAUD_RATES` clipped to `min_baud`..`max_baud` if `baud_rates` is missing). An unknown port uses the standard baud list (no 600). Selecting a device in Manual mode does not shrink the Baud list and does not change Baud or Port Settings; only automatic matching may apply the device's settings.

Scan Devices and Identify print a short log in the terminal. Ports are the outer loop: each port gets one `Port:` header (VID/PID, or `(no USB ID)`), then one `Device:` line per try (devices.json order, then that device's baud list). A VID/PID miss is a single `Skipped` line for that device, not one line per baud. A match stops further bauds for that device. Example:

```
Device Scanning...
Port: COM8 (0x10C4/0xEA60)
Device: SIMCom SIM7080 115200 8N1 (0x0403): Skipped, port ID doesn't match
Device: MUX Wiring MB607 460800 8N1 (0x10C4/0xEA60): No response
Device: MUX Wiring MB607 115200 8N1 (0x10C4/0xEA60): Matched
```

Results: `Matched`, `No response`, `No match: '<first ~30 chars, repr-escaped>'`, `Skipped, port ID doesn't match`, or `Error: <short msg>`. In Use ports still get a one-line skip under their `Port:` header. Ports this app has **Open** are never probed by Scan Ports, Scan Devices, auto-scan, or retest: one `Port:` header then `Skipped, port is Open`, and the Open row (status and device info) stays as-is. Identify on the open port still probes that one device.

Identified rows (and Open rows that still have that identified device) show manufacturer, model, and short description from `devices_info.json` when present (falling back field-by-field to `devices.json`). If `response.append_response` is true, the formatted `device_column` is appended after that name, separated by ` - ` (for example `MUX Wiring MB607 Body Control Module - Revision 1.01`). If it is false, the response text is never shown. The bottom Device Status field uses the same string.

**Select** prints JSON of the open-port specs plus the identified device, then quits. The object has only `port`, `baud`, `data_bits`, `stop_bits`, `parity`, `flow_control`, and `device`. `device` is `{manufacturer, model, short_description}` after Identify/Scan confirms a device, or `null` if none was identified. If no port is chosen, `"port"` is `null` and the window stays open. **Exit** (and the window X) still prints `{"result": null}`. Run from a terminal (`run.bat`) so you can see that JSON.

Example after identifying a SIM7080 on COM3:

```json
{
  "port": "COM3",
  "baud": 115200,
  "data_bits": 8,
  "stop_bits": 1,
  "parity": "None",
  "flow_control": "None",
  "device": {
    "manufacturer": "SIMCom",
    "model": "SIM7080",
    "short_description": ""
  }
}
```

## devices.json fields

Each item under `"devices"` describes how to find one piece of equipment. Old files still load: `pause` is treated as seconds, a single `baudrate` becomes a one-item list, and decimal VID/PID values are accepted. Do not strip `type` / `short_description` / `long_description` from this file; identify templates still use them. The Select JSON `device` block uses only `manufacturer`, `model`, and `short_description` (prefer a `devices_info.json` match, then these fields).

- `manufacturer`, `model` — name. `type` is optional free text (not a fixed list).
- `short_description`, `long_description` — notes. The Device dropdown shows `Manufacturer  model  115,200 Baud` (first listed baud). `long_description` is not in that dropdown.
- `controllers` — USB-serial chips this device may sit behind (one or more `{vid, pid?}` pairs). `vid` / `pid` are hex strings (`"0x10C4"`). Scan Devices and Identify only try that device on ports whose VID matches, and whose PID matches when the controller lists one. If `pid` is omitted on a controller, any product ID from that vendor matches. If `controllers` is missing, empty, null, or has no usable `vid` values, the device is tried on **every** available port. The Device dropdown lists the full catalog (it is not filtered by the open port). The device editor **Port VID:PID** field is comma-separated hex (`0403:6001, 10C4`); PID is optional; `0x` is optional; blank saves `[]`.
- `serial_parameters.baud_rates` — baud values tried in order (bps) when identifying the device. The picker's Baud **dropdown** is **not** this list; it comes from `serial_ports.json` as described above. Also `data_bits`, `parity` (`None` / `Even` / …), `stop_bits`, `flow_control`.
- `commands.reset` — optional. If present, Identify/Scan pulses a control line **before** initialize: set `reset_state`, wait `pulse_ms`, return to `run_state`, then read until `wait_for` is seen or `timeout_ms`. `wait_for` is a case-insensitive substring of the **accumulated** receive buffer (extra text around the prompt is fine; a match may span reads). Optional `wait_for_regex` is a case-insensitive regex on that same buffer. If both are set, both must match. MB607 uses substring only (`Press CR key for command Debug Mode`) — no regex. `line` is `DTR` or `RTS`. `run_state` / `reset_state` are TTL `High` / `Low` (pyserial inverts: `ser.dtr=True` / `ser.rts=True` drives the pin LOW). Devices without `reset` identify exactly as before. The Device Editor has a **Reset** box; blank **Reset Line** means no reset; **Wait For Regex** is optional.
- `commands.initialize` / `commands.identify` — `identify` is still `message` + `pause_ms` (empty message skipped). `initialize` may use that same old form, or a `steps` list of timed sends. Each step is `{"pause_ms": N}` and/or `{"send": "..."}` (send first when both are in one object). After the steps, `expect` is a case-insensitive substring of everything received during those sends/waits; if it is not there yet, Identify waits up to `timeout_ms` (or `pause_ms` if `timeout_ms` is omitted). If `steps` is present it is used instead of a single `message`. Other devices can keep `message` / `pause_ms` with no `steps`. The Device Editor has **Initialize Steps** (one `wait N` or `send ...` line per step, `\r` / `\n` allowed), plus **Initialize Expect** and **Initialize Timeout**.
- `response.regex` — pattern that must appear in the reply. Named groups like `(?P<revision>...)` are allowed.
- `response.device_column` — filled from regex groups and device fields (for example `Revision {revision}`). Used only when `append_response` is true.
- `response.append_response` — `true` or `false` (default `false`). When true, Connected Device / Device Status is `manufacturer model short_description - <device_column>`. When false, the response text is never shown. The device editor checkbox is **Show response after device name**.

Example:

```json
{
  "devices": [
    {
      "manufacturer": "MUX Wiring",
      "model": "MB607",
      "type": "Body Control Module",
      "controllers": [
        {"vid": "0x10C4", "pid": "0xEA60"},
        {"vid": "0x067B", "pid": "0x2303"}
      ],
      "serial_parameters": {
        "baud_rates": [460800, 115200],
        "data_bits": 8,
        "parity": "None",
        "stop_bits": 1,
        "flow_control": "None"
      },
      "commands": {
        "reset": {
          "line": "DTR",
          "run_state": "High",
          "reset_state": "Low",
          "pulse_ms": 100,
          "wait_for": "Press CR key for command Debug Mode",
          "timeout_ms": 1000
        },
        "initialize": {
          "steps": [
            {"pause_ms": 10},
            {"send": "\r"},
            {"pause_ms": 10},
            {"send": "debug\r"},
            {"pause_ms": 10},
            {"send": "\r"},
            {"pause_ms": 100}
          ],
          "expect": "Enter Command",
          "timeout_ms": 1000
        },
        "identify": {"message": "I\r", "pause_ms": 1000}
      },
      "response": {
        "regex": "RevP(?P<revision>\\d+\\.\\d+)\\s+(?P<date>\\d+/\\d+/\\d+)",
        "device_column": "Revision {revision}",
        "append_response": true
      }
    }
  ]
}
```
