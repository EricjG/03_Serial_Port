# Serial Port Application UI

Version: 3.4 — Baud list from serial_ports.json (Nov 26, 2026).

## Colors
- Window / panels: `#FFFFFF` (white)
- Section blue: `#D6E8F8`, black 1px outline
- White inner boxes: white fill, flat 1px `#A0A0A0` outline
- Buttons: gray `#C0C0C0`, same 1px `#A0A0A0` outline
- **One** outer border: orange `#FF8C00`, 3px (padding is white inside it, not extra orange)
- Control outline (entries, combos, read-only fields): **one** flat 1px `#A0A0A0` line (no sunken / raised, no stacked ttk + wrap borders). Port / Baud / Device use a cloned flat arrow (clam/default), not the Windows boxed combobox button, so the wrap is the only outline.
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
- Fixed column widths: Status 80, Port # 64 (fits `COM99` plus 2px cell padding), ID/Baud 110; Serial Driver / Connected Device fills the rest. The Port *dropdown* stays sized from `/tmp/serialdemo/ttyUSB0`
- Flat 1px `#A0A0A0` border around the list (same as the white boxes), one line
- 6 rows, 2px cell padding, 24px row height
- Port names are the real Windows names (`COM4`), sorted naturally (`COM2` before `COM10`)
- IDs show as hex VID:PID, e.g. `0x10C4:0xEA60`
- Single-click a row to select that port (row turns yellow; Port box follows)
- Identified rows are bold
- Double-click a row is the same as **Select**
- In Use rows appear in the list and Port dropdown only when In Use is on (or after a one-shot In Use click)
- List Status column values stay **Available** / **In Use** / **Open** / **Identified** (not the bottom Port Status words)
- Serial Driver / Connected Device: Available / In Use / Open rows show the matched `serial_ports.json` chip (`manufacturer` + `model`), or the OS description if none matches. Identified rows show manufacturer, model, and short description from `devices_info.json` when present, otherwise the identify `device_column` text

## Manually (port / device box)
- Titled light-blue box under Automated
- Two white boxes inside, 8px padding, 8px gap between them
- Labels above their control, left-aligned with the control’s left edge
- Panels, white boxes, and the Open/Identify column share one right edge; labels and controls share one left edge

### White box 1
- One row: **Port** combo (wide enough for `/tmp/serialdemo/ttyUSB0`), **Baud** (~8 chars), **Settings**, **Open** at the right
- 16px between those groups
- **Port** / **Baud** / **Device**: editable (Port, Baud) or readonly (Device) combobox with the same single 1px outline as Settings. No `* All *` or `* Manual Entry *` item. Baud lists the selected port's `serial_ports.json` chip `baud_rates` (or `STANDARD_BAUD_RATES` clipped to that chip's `min_baud`..`max_baud` if `baud_rates` is missing). An unknown port (no VID/PID match) uses the standard baud list (no 600). Selecting a device does not shrink this list. The user may still type a rate. Do not add a divider.
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
- Picking a Device changes **Device Status** (back to **Unidentified**) and resets the Identify failure count. It does **not** change Settings or Port Status. The Baud *list* stays the chip/standard list (it does not shrink to the device's rates). If the device's first baud is already in that list, Baud preselects it; if not, the list is unchanged, nothing is added, Baud stays as shown, and a note is logged
- **Identify** probes only the device shown in the Device dropdown, using the current settings. Enabled only when this app has the port open. Identify failure does not change Port Status
- **Select** prints a JSON handoff object to stdout (indented), closes the open port, then quits. If no port is chosen, it prints JSON with `"port": null` and stays open
- **Exit** and the window X print `{"result": null}`, close the open port, then quit
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
- Status fields are 24px high with the same 1px outline, vertically centered with Select / Exit. They are Labels (not character-width entries). After `update_idletasks()`, wrap width is `winfo_reqwidth()` of a temp Label using the widget’s resolved font (`Font(font=widget.cget("font"))` / `nametofont`) for every value the field can show (**Unidentified**, **Identified**, **3rd Failure**, **Unknown Device**, … for Device Status; **Unknown** / **Closed** / **Opened** / **Failed** for Port Status), plus the 1px outline, then rounded up to the 8px grid. The window min size grows to that bottom-row width so the row cannot squeeze the last glyph.
- Port Status words: **Closed** (default / after close), **Opened** (open succeeded), **Failed** (open failed / timeout), **Unknown** (Port Settings / Baud changed). Picking a Device does **not** set Port Status to Unknown
- Device Status words: **Unidentified** until Identify or Scan Devices confirms the selected dropdown device on that port, then **Identified**. Picking a *different* device in the dropdown returns Device Status to **Unidentified** and clears the Identify failure count
- Identify button failures (same device, try-again): **Failed**, then **2nd Failure**, **3rd Failure**, **4th Failure**, … (normal English ordinals: 11th, 21st, 22nd, 23rd). A successful Scan Devices confirmation of the selected device sets **Identified** and clears the count. A Scan Devices miss does not increment this count
- If `devices.json` is missing or invalid, Device Status shows that error. Errors from `serial_ports.json` / `devices_info.json` are logged; they do not overwrite a devices.json error

## Port Settings dialog
- Open by **click** on the main **Settings** value
- Orange 3px outer border; 8px padding; light-blue box with black 1px outline
- Title **Port Settings** upper-left in the blue box
- Defaults: Data Bits 8, Stop Bits 1, Parity None, Flow None
- Lists (slide 3) — used when the port’s VID:PID has no `serial_ports.json` match and no device is identified. Baud’s unknown-port fallback is also `STANDARD_BAUD_RATES`, but a **matched chip** drives the Baud list (see White box 1). Data/Stop/Parity/Flow still ignore the chip catalog when no device is identified; an identified device’s own `serial_parameters` lists win when present:
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
- Default size fits the content: 3px orange frame, then 8px padding on every edge (including the bottom). No extra empty band below Port Status / Select / Exit
- Minimum size is that content size, so the title strip, Automated list (6 rows), Manually boxes, status row, and Select/Exit stay on screen
