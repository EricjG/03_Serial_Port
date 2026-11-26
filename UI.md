# Serial Port Application UI

Version: 3.1 — layout from slides 2-3 (Nov 25, 2026) and the shared theme (Segoe UI, 6px padding, decided colors).

## Colors
- Window / panels: `#FFFFFF` (white)
- Section blue: `#D6E8F8`, black 1px outline
- Buttons: gray `#C0C0C0`
- **One** outer border: orange `#FF8C00`
- Disabled text: `#808080` (no hover)
- Selected list row: yellow `#FFFF00`
- Settings preview / Select (dialog new line): green `#90EE90`
- Current settings (dialog): cream `#FFF2CC`

## Fonts and spacing
- Segoe UI (Windows). If that face is missing, fall back to Noto Sans / DejaVu Sans / Arial.
- Body / list rows: Segoe UI 9 regular
- Labels, column headers, buttons: Segoe UI 9 bold
- Panel titles: Segoe UI 10 bold
- Header check-buttons keep size 8 bold so checkbox-on-button layout is not retuned
- Padding 6 px on section boxes, gaps, and control cells

## Title strip
- Light-blue bar, black outline; white gap from the orange border
- **Port & Device Identification**

## Automated (list box)
- Titled light-blue box under the title strip
- Left: **Automated**
- Right: In Use / Scan Ports / Scan Devices — checkbox on the left edge of each gray button; the button is sized from the real checkbox width plus the label so the text is never covered (Windows and Linux)
- A checked box means auto-repeat that action once a second
- Clicking a header button runs that action once and clears **all three** auto-repeat checkboxes
- **Scan Devices** (header) is unchanged; the Manually-panel button is **Identify** (slides say Scan Device; Identify is the agreed name)
- Column titles in the blue area: Status / Port # / ID/Baud / Serial Driver / Connected Device
- Port names are the real Windows names (`COM4`), sorted naturally (`COM2` before `COM10`)
- IDs show as hex VID:PID, e.g. `0x10C4:0xEA60`
- Single-click a row to select that port (row turns yellow; Port box follows)
- Identified rows are bold
- Double-click a row is the same as **Select**
- In Use rows appear in the list and Port dropdown only when In Use is on (or after a one-shot In Use click)
- List Status column values stay **Available** / **In Use** / **Open** / **Identified** (not the bottom Port Status words)

## Manually (port / device box)
- Titled light-blue box under Automated
- **Port** / **Baud** / **Settings**: labels centered above their box
- **Port** / **Baud**: editable combobox; no `* All *` or `* Manual Entry *` item. Baud lists the selected device's `baud_rates`; if that list is missing, the standard baud list is used (no 600)
- **Port** shows `No Ports Available` until a port exists, then defaults to the first **Available** port
- Port dropdown lists Available / Open / Identified ports; In Use ports only when the In Use checkbox is on
- **Settings**: white button, default `8 - 1 - None - None` (Data - Stop - Parity - Flow); width is computed from the longest legal string (`8 - 1 - Space - xOff/xOn`); single-click opens the dialog
- **Device** dropdown format: `Manufacturer  model  115.2K Baud` (two spaces between fields; baud is that device's first listed rate). Labels stay unique: a second copy of the same name gets ` (2)`
- Picking a Device while the port is **closed** applies that entry's baud and port settings, and sets Port Status to **Unknown**
- Picking a Device while the port is **open** does not change the port settings; Port Status becomes **Unknown**
- **Open** is one button with three states:
  - `Open: COM4` when the port is free
  - `Close: COM4` when this app has it open (click closes it)
  - Grayed `In-Use: COM5` when another program holds the port
- **Identify** (was Scan Device) probes only the device shown in the Device dropdown, using the blue-box settings. Enabled only when this app has the port open
- **Select** prints `Selected port: COMx`, closes the open port, then quits
- **Exit** and the window X also close the open port before quitting
- **Device**: label + dropdown; dropdown right edge lines up with Settings button
- Top-right: **Open:** (left-aligned); under it **Identify**
- No Status field in this box

### Enabled / disabled

| Control | List is empty | Port opened by this app |
|---|---|---|
| Port, Baud, Settings | Disabled | Disabled |
| Open | Disabled | Shows `Close: <port>` |
| Device, Identify, Select | Disabled | Enabled |

When the list is empty, only the header buttons and Exit stay enabled.

## Bottom row
- Still inside the orange frame, not in a blue box
- Left: **Port Status:** [value] and **Device Status:** [value]
- Right: **Select** then **Exit** (Select is left of Exit)
- Port Status words: **Closed** (default / after close), **Opened** (open succeeded), **Failed** (open failed / timeout), **Unknown** (selected device changed, or Port Settings / Baud changed)
- Device Status words: **Unidentified** until Identify or Scan Devices confirms the selected dropdown device on that port, then **Identified**. Picking a device in the dropdown does not identify it.
- If `devices.json` is missing or invalid, Device Status shows that error
- Button text center-aligned

## Port Settings dialog
- Open by **single-click** on the main **Settings** value
- Orange 3px outer border; white gap; light-blue box with black 1px outline
- Title **Port Settings** upper-left in the blue box
- Defaults: Data Bits 8, Stop Bits 1, Parity None, Flow None
- Lists (slide 3):
  - Data: 8, 7, 6, 5
  - Stop: 1, 2
  - Parity: None, Odd, Even, Mark, Space
  - Flow: None, RTS/CTS, xOff/xOn
- White inner box:
  - Left: **Data Bits:** + dropdown; right: **Stop Bits:** + dropdown
  - Left: **Parity:** + dropdown; right: **Flow:** + dropdown
  - Green readonly box = live draft (Data - Stop - Parity - Flow); **Select** to the right (text centered)
- Below white box, still in blue: cream readonly current applied settings + **Exit** (text centered)
- Preview lines are sized from the longest legal settings string
- **Select** applies values, updates main Settings, sets Port Status to **Unknown**, closes
- **Exit** / window X closes without applying
- Enter = Select, Escape = Exit

## Window
- Minimum size is large enough that the title strip, Automated list, Manually controls, status row, and Select/Exit stay on screen
