# Serial Port Application UI

Version: 3.2 — slides 2-3 layout plus Iris 8px grid / 24px controls (Nov 26, 2026).

## Colors
- Window / panels: `#FFFFFF` (white)
- Section blue: `#D6E8F8`, black 1px outline
- White inner boxes: white fill, flat 1px `#A0A0A0` outline
- Buttons: gray `#C0C0C0`, same 1px `#A0A0A0` outline
- **One** outer border: orange `#FF8C00`
- Control outline (entries, combos, read-only fields): flat 1px `#A0A0A0` (no sunken / raised)
- Disabled text: `#808080` (no hover)
- Selected list row: yellow `#FFFF00`, dark text
- Settings preview / Select (dialog new line): green `#90EE90`
- Current settings (dialog): cream `#FFF2CC`

## Fonts and spacing
- Segoe UI (Windows). If that face is missing, fall back to Noto Sans / DejaVu Sans / Arial.
- One control font: Segoe UI 9. Labels and buttons are 9 bold. Panel titles are 9 bold.
- 8px grid: 8px padding inside the orange border, 8px padding inside each blue panel and white box, 8px gaps between panels and between controls
- 16px gap between control groups in a row
- Every entry, combobox, read-only field, and button is 24px high
- Action buttons (Open, Identify, Select, Exit, dialog Select/Exit) are 96px wide, centered text, flat

## Title strip
- Light-blue bar, black outline; 8px gap from the orange border
- Single ~28px line: **Port & Device Identification**

## Automated (list box)
- Titled light-blue box under the title strip, 8px gap
- Left: **Automated**, vertically centered with the check-buttons
- Right: In Use / Scan Ports / Scan Devices, right-aligned on the title row, 16px apart, 24px high
- Checkbox sits on the button (`place(in_=btn)` then `cb.lift(btn)`); the button is sized from the real checkbox width plus the label so the text is never covered
- A checked box means auto-repeat that action once a second
- Clicking a header button runs that action once and clears **all three** auto-repeat checkboxes
- **Scan Devices** (header) is unchanged; the Manually-panel button is **Identify**
- Column titles and cells are left-anchored
- Fixed column widths: Status 80, Port # 170, ID/Baud 110; Serial Driver / Connected Device fills the rest
- 6 rows, 2px cell padding, 24px row height
- Port names are the real Windows names (`COM4`), sorted naturally (`COM2` before `COM10`)
- IDs show as hex VID:PID, e.g. `0x10C4:0xEA60`
- Single-click a row to select that port (row turns yellow; Port box follows)
- Identified rows are bold
- Double-click a row is the same as **Select**
- In Use rows appear in the list and Port dropdown only when In Use is on (or after a one-shot In Use click)
- List Status column values stay **Available** / **In Use** / **Open** / **Identified** (not the bottom Port Status words)

## Manually (port / device box)
- Titled light-blue box under Automated
- Two white boxes inside, 8px padding, 8px gap between them
- Labels above their control, left-aligned with the control’s left edge
- Panels, white boxes, and the Open/Identify column share one right edge; labels and controls share one left edge

### White box 1
- One row: **Port** combo (wide enough for `/tmp/serialdemo/ttyUSB0`), **Baud** (~8 chars), **Settings**, **Open** at the right
- 16px between those groups
- **Port** / **Baud**: editable combobox; no `* All *` or `* Manual Entry *` item. Baud lists the selected device's `baud_rates`; if that list is missing, the standard baud list is used (no 600)
- **Port** shows `No Ports Available` until a port exists, then defaults to the first **Available** port
- Port dropdown lists Available / Open / Identified ports; In Use ports only when the In Use checkbox is on
- **Settings**: read-only field with the same 1px outline, default `8 - 1 - None - None` (Data - Stop - Parity - Flow); width is computed from the longest legal string (`8 - 1 - Space - xOff/xOn`); click opens the dialog
- **Open** is one 96px button with three states (no port path in the label):
  - `Open` when the port is free
  - `Close` when this app has it open (click closes it)
  - Grayed `In Use` when another program holds the port

### White box 2
- One row: **Device** combo stretching across, **Identify** at the right
- Identify is 96px, same width as Open, right edges aligned
- **Device** dropdown format: `Manufacturer  model  115.2K Baud` (two spaces between fields; baud is that device's first listed rate). Labels stay unique: a second copy of the same name gets ` (2)`
- Picking a Device while the port is **closed** applies that entry's baud and port settings, and sets Port Status to **Unknown**
- Picking a Device while the port is **open** does not change the port settings; Port Status becomes **Unknown**
- **Identify** probes only the device shown in the Device dropdown, using the current settings. Enabled only when this app has the port open
- **Select** prints `Selected port: COMx`, closes the open port, then quits
- **Exit** and the window X also close the open port before quitting
- No Status field in this box

### Enabled / disabled

| Control | List is empty | Port opened by this app |
|---|---|---|
| Port, Baud, Settings | Disabled | Disabled |
| Open | Disabled | Shows `Close` |
| Device, Identify, Select | Disabled | Enabled |

When the list is empty, only the header buttons and Exit stay enabled.

## Bottom row
- Still inside the orange frame, not in a blue box
- Left: **Port Status:** [value] and **Device Status:** [value] inline (exception to labels-above)
- Right: **Select** then **Exit**, each 96px, 8px apart; Exit’s right edge is the common right edge
- Status fields are 24px high with the same 1px outline, vertically centered with Select / Exit
- Port Status words: **Closed** (default / after close), **Opened** (open succeeded), **Failed** (open failed / timeout), **Unknown** (selected device changed, or Port Settings / Baud changed)
- Device Status words: **Unidentified** until Identify or Scan Devices confirms the selected dropdown device on that port, then **Identified**. Picking a device in the dropdown does not identify it.
- If `devices.json` is missing or invalid, Device Status shows that error

## Port Settings dialog
- Open by **click** on the main **Settings** value
- Orange 3px outer border; 8px padding; light-blue box with black 1px outline
- Title **Port Settings** upper-left in the blue box
- Defaults: Data Bits 8, Stop Bits 1, Parity None, Flow None
- Lists (slide 3):
  - Data: 8, 7, 6, 5
  - Stop: 1, 2
  - Parity: None, Odd, Even, Mark, Space
  - Flow: None, RTS/CTS, xOff/xOn
- White inner box, labels above controls:
  - **Data Bits** / **Stop Bits** / **Parity** / **Flow** dropdowns
  - Green readonly box = live draft (Data - Stop - Parity - Flow); **Select** (96px) to the right
- Below white box, still in blue: cream readonly current applied settings + **Exit** (96px)
- Preview lines are sized from the longest legal settings string
- **Select** applies values, updates main Settings, sets Port Status to **Unknown**, closes
- **Exit** / window X closes without applying
- Enter = Select, Escape = Exit

## Window
- Minimum size is large enough that the title strip, Automated list (6 rows), Manually boxes, status row, and Select/Exit stay on screen
