# Serial Port Application UI

Version: 3.0 — picker behavior from slides 2-3 and the shared theme (Decided items).

## Colors
- Window / panels: `#FFFFFF` (white)
- Section blue: `#D6E8F8`, black 1px outline
- Buttons: gray `#C0C0C0`
- **One** outer border: orange `#FF8C00`
- Disabled text: `#808080` (no hover)
- Selected list row: yellow `#FFFF00`
- Settings preview / Select (dialog new line): green `#90EE90`
- Current settings (dialog): cream `#FFF2CC`

## 1st — Header
- Light blue bar, black outline; white gap from orange border
- Left: **UART Connection Status** (black)
- Right: In Use / Scan Ports / Scan Devices — checkbox on top of each gray button
- A checked box means auto-repeat that action once a second
- Clicking a header button runs that action once and clears **all three** auto-repeat checkboxes
- **Scan Devices** (header) is unchanged; the bottom-panel button is **Identify**

## 2nd — Status list (own blue box)
- Untitled light-blue box, black outline
- Column titles in blue area; Status / Port # / ID/Baud fixed width
- Port names are the real Windows names (`COM4`), sorted naturally (`COM2` before `COM10`)
- IDs show as hex VID:PID, e.g. `0x10C4:0xEA60`
- Single-click a row to select that port (row turns yellow; Port box follows)
- Identified rows are bold
- Double-click a row is the same as **Select**
- In Use rows appear in the list and Port dropdown only when In Use is on (or after a one-shot In Use click)

## 3rd — Connection controls (own blue box)
- Bold UI text
- **Status** / **Port** / **Baud** / **Port Settings**: labels centered above their box
- **Status** words: **Available** / **In Use** / **Open** / **Identified**; **None Available** when there are no ports
- **Port** / **Baud**: editable combobox; no `* All *` or `* Manual Entry *` item
- **Port** shows `No Ports Available` until a port exists, then defaults to the first **Available** port
- Port dropdown lists Available / Open / Identified ports; In Use ports only when the In Use checkbox is on
- **Port Settings**: white button, default `8 - 1 - None - None` (Data - Stop - Parity - Flow); single-click opens the dialog
- **Device** dropdown labels are unique: a second copy of the same name gets ` (2)`
- Picking a Device while the port is **closed** applies that entry's baud and port settings
- Picking a Device while the port is **open** does not change the port settings
- **Open** is one button with three states:
  - `Open: COM4` when the port is free
  - `Close: COM4` when this app has it open (click closes it)
  - Grayed `In-Use: COM5` when another program holds the port
- **Identify** (was Scan Device) probes only the device shown in the Device dropdown, using the blue-box settings. Enabled only when this app has the port open
- **Select** prints `Selected port: COMx`, closes the open port, then quits
- **Exit** and the window X also close the open port before quitting
- **Device**: label + dropdown; dropdown right edge lines up with Settings button
- Top-right: **Open:** (left-aligned); under it **Identify**

### Enabled / disabled

| Control | List is empty | Port opened by this app |
|---|---|---|
| Port, Baud, Settings | Disabled | Disabled |
| Open | Disabled | Shows `Close: <port>` |
| Device, Identify, Select | Disabled | Enabled |

When the list is empty, only the header buttons and Exit stay enabled.

## 4th — Bottom
- White bar; two message lines on the left replace a Status box, e.g. `Port: COM4 is Closed` and `Device: {Manufacturer} {Model} {Short Description}`
- **Exit** then **Select** on the right (**Select** furthest right)
- Button text center-aligned

## Port Settings dialog
- Open by **single-click** on the main **Port Settings** value
- Orange 3px outer border; white gap; light-blue box with black 1px outline
- Title **Port Settings** upper-left in the blue box
- Defaults: Data Bits 8, Stop Bits 1, Parity None, Flow None
- White inner box:
  - Left: **Data Bits:** + dropdown; right: **Stop Bits:** + dropdown
  - Left: **Parity:** + dropdown; right: **Flow:** + dropdown
  - Green readonly box = live draft (Data - Stop - Parity - Flow); **Select** to the right (text centered)
- Below white box, still in blue: cream readonly current applied settings + **Exit** (text centered)
- **Select** applies values, updates main Settings, closes
- **Exit** / window X closes without applying
- Enter = Select, Escape = Exit

## Window
- Minimum size is large enough that the header, list, connection controls, message lines, and Exit/Select stay on screen
