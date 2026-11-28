# Serial Port Application UI

Version: 3.17 — Per-device reset sequence on Identify; TEMP Reset (DTR) button removed (Nov 28, 2026).

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
- A checked **Scan Ports** or **Scan Devices** box means auto-repeat that action once a second. **In Use** is a view filter only: it shows or hides In Use ports already found and does not start or keep the auto port-scan loop
- The **In Use** header button label is `In Use xN` (`In Use x0`, `In Use x3`; no space after `x`). N is the number of In Use ports in the **full** port list, not the visible/filtered rows, so the count still shows when the checkbox is off. It updates on port-list refresh/rescan and when a port’s In Use state changes. The button is sized for two-digit counts (`In Use x99`) so the width does not jump or clip. Filter semantics are unchanged
- Clicking a header button runs that action once and clears the Scan Ports and Scan Devices auto-repeat checkboxes. Scan Ports / Scan Devices leave the In Use checkbox as-is. The In Use button checks In Use and unchecks Scan Ports. Ports this app has Open are never opened or identified by those scans.
- **Scan Devices** (header) is unchanged; the Manually-panel button is **Identify**. Scan Ports, Scan Devices, auto-scan, and retest never probe a port this app has **Open**. Each of those paths prints that port’s `Port:` header then `Skipped, port is Open`, and leaves the Open row’s Status and Connected Device text alone.
- Column titles and cells are left-anchored
- Fixed column widths: Status 80, Port # 64 (fits `COM99` plus 2px cell padding), ID/Baud 110; Serial Driver / Connected Device fills the rest. The Port *dropdown* stays sized from `/tmp/serialdemo/ttyUSB0`
- Flat 1px `#A0A0A0` border around the list (same as the white boxes), one line
- Default **6** rows, 2px cell padding, 24px row height. Extra or lost *window height* changes only this table (more or fewer visible rows). Minimum is **1** row. No maximum.
- Port names are the real Windows names (`COM4`), sorted naturally (`COM2` before `COM10`)
- IDs show as hex VID:PID, e.g. `0x10C4:0xEA60`
- Single-click a row to select that port (row turns yellow; Port box follows)
- Identified rows are bold
- Double-click a row is the same as **Select**
- In Use rows appear in the list and Port dropdown only when the In Use checkbox is on
- List Status column values stay **Available** / **In Use** / **Open** / **Identified** (not the bottom Port Status words)
- Serial Driver / Connected Device: Available / In Use rows (and Open rows with no identified device) show the matched `serial_ports.json` chip (`manufacturer` + `model`), or the OS description if none matches. Identified rows, and Open rows that already have an identified device, show manufacturer, model, and short description from `devices_info.json` when present (else `devices.json`). If that device’s `response.append_response` is true, the formatted identify `device_column` is appended after the name (` - `). If it is false, the response text is never shown. Clicking **Open** only changes the Status cell (Available/Identified → Open) and Port Status; it does not replace or clear the Connected Device text.

## Manually (port / device box)
- Titled light-blue box under Automated
- Two white boxes inside, 8px padding, 8px gap between them
- Labels above their control, left-aligned with the control’s left edge
- Panels, white boxes, and the Open/Identify column share one right edge; labels and controls share one left edge

### White box 1
- One row: **Port** combo (sized from `/tmp/serialdemo/ttyUSB0`, then shortened by the Baud grow), **Baud** (1.5× the old 8-char width), **Settings**, **Open** at the right. Port shrinks by the same pixel amount Baud grows, so the row width and Open stay put.
- 16px between those groups
- **Port** / **Baud** / **Device**: editable (Port, Baud) or readonly (Device) combobox with the same single 1px outline as Settings. No `* All *` or `* Manual Entry *` item. Baud lists the selected port's `serial_ports.json` chip `baud_rates` (or `STANDARD_BAUD_RATES` clipped to that chip's `min_baud`..`max_baud` if `baud_rates` is missing) as full integers with comma thousands separators (`9,600`, `115,200`, `1,000,000`). Typed values strip commas (old `115.2K` still parses). An unknown port (no VID/PID match) uses the standard baud list (no 600). Selecting a device does not shrink this list. The user may still type a rate. Do not add a divider. The Baud box is sized so `1,000,000` fits.
- **Port** shows `No Ports Available` until a port exists, then defaults to the first **Available** port
- Port dropdown lists Available / Open / Identified ports; In Use ports only when the In Use checkbox is on
- **Settings**: read-only field with the same 1px outline, default `8 - N - 1 - N` (data bits, parity letter, stop bits, flow letter, each joined with ` - `). Parity: **N** None, **E** Even, **O** Odd, **M** Mark, **S** Space. Flow: **N** none, **R** RTS/CTS, **X** XON/XOFF. Width is computed from the longest legal string (`8 - N - 1 - N` / `8 - S - 2 - X`); click opens the dialog
- **Open** is one 96px button with three states (no port path in the label):
  - `Open` when the port is free
  - `Close` when this app has it open (click closes it)
  - Grayed `In Use` when another program holds the port
- Every app open (manual Open, scan/identify, availability probe) goes through `open_serial_idle_dtr`: construct closed, `dtr=False`, `open()`, `dtr=False` again so DTR idles HIGH. pyserial polarity: `ser.dtr = True` / `ser.rts = True` drives the adapter TTL pin LOW; False is HIGH. RTS is not changed on open. Some drivers/OSes still pulse DTR on open; the line is undriven while no port is open.
- **Identify** / Scan Devices: if that device’s `commands.reset` is present, the worker thread (same as today’s pause_ms sleeps — the Tk main loop is not blocked extra) pulses the configured line, waits for `wait_for`, sends initialize (and waits for `expect` when set), then runs the existing identify command + regex. Logs e.g. `COM8 - DTR reset pulse 100 ms`, `COM8 - Received: Press CR key for command Debug Mode`, `COM8 - Sent: CR CR`, `COM8 - Received: Enter command`. A wait timeout is an identify failure for that baud. Devices without `reset` are unchanged.

### White box 2
- One row: **Device** combo stretching across, **Identify** at the right
- Identify is 96px, same width as Open, right edges aligned
- **Device** dropdown format: `Manufacturer  model  115,200 Baud` (two spaces between fields; baud is that device's first listed rate, full integer with comma thousands separators). Labels stay unique: a second copy of the same name gets ` (2)`
- Picking a Device in **Manual** mode changes **Device Status** (back to **Nothing Identified**) and resets the Identify failure count. It does **not** change Baud, Settings (data bits, stop bits, parity, flow control), or Port Status. The Baud *list* stays the chip/standard list (it does not shrink to the device's rates). Only **automatic** mode may apply that device's Port Settings (Scan Devices probes with the device's baud/frame). **Identify** still uses the current Port Settings.
- **Identify** probes only the device shown in the Device dropdown, using the current settings. Enabled only when this app has the port open. Identify failure does not change Port Status
- **Select** prints JSON (indented) of the open-port specs (`port`, `baud`, `data_bits`, `stop_bits`, `parity`, `flow_control`) plus `device` (`manufacturer`, `model`, `short_description` after Identify/Scan, otherwise `null`), closes the open port, then quits. If no port is chosen, it prints JSON with `"port": null` and stays open
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
- Status fields are 24px high with the same 1px outline, vertically centered with Select / Exit. They are Labels (not character-width entries). After `update_idletasks()`, wrap width is `winfo_reqwidth()` of a temp Label using the widget’s resolved font (`Font(font=widget.cget("font"))` / `nametofont`) for every value the field can show (**Nothing Identified**, **Identified**, **3rd Failure**, **Unknown Device**, plus every Identified device label from `devices.json` + `devices_info.json`, including appended `device_column` text when `append_response` is true, for Device Status; **COM256**, **COM256   1,000,000   8 - S - 2 - X**, **COM256 - Failed to open**, … for Port Status), plus the 1px outline, then rounded up to the 8px grid. Device Status stretches into the free space between Port Status and Select/Exit. If that leftover is still too narrow for the longest label, the window minimum width grows so the text is never clipped.
- Port Status: clicking a list row (or picking the port) shows just the port, e.g. `COM8`. After Identify/Scan confirms a device on that port, it shows `COM8   115,200   8 - N - 1 - N` — three spaces between groups: port, comma baud (`300`, `1,200`, `9,600`, `19,200`, `115,200`, `460,800`, `921,600`, `1,000,000`, …), then the same Settings string (data - parity - stop - flow). After Open succeeds, the same format uses the settings the port was opened with. If Open fails: `COM8 - Failed to open`. Picking a Device does **not** change Port Status. Changing Baud / Port Settings does **not** overwrite an Identified or Opened line.
- Device Status words: **Nothing Identified** until Identify or Scan Devices confirms the selected dropdown device on that port, then the same text as that row’s **Serial Driver / Connected Device** cell (manufacturer, model, and short description; plus the formatted `device_column` when `response.append_response` is true). Picking a *different* device in the dropdown returns Device Status to **Nothing Identified** and clears the Identify failure count. Opening an already-identified port does not change Device Status.
- Identify button failures (same device, try-again): **Failed**, then **2nd Failure**, **3rd Failure**, **4th Failure**, … (normal English ordinals: 11th, 21st, 22nd, 23rd). A successful Scan Devices confirmation of the selected device sets **Identified** and clears the count. A Scan Devices miss does not increment this count
- If `devices.json` is missing or invalid, Device Status shows that error. Errors from `serial_ports.json` / `devices_info.json` are logged; they do not overwrite a devices.json error

## Port Settings dialog
- Open by **click** on the main **Settings** value
- Orange 3px outer border; 8px padding; light-blue box with black 1px outline
- Title **Port Settings** upper-left in the blue box
- Defaults: Data Bits 8, Parity None, Stop Bits 1, Flow None
- Lists (slide 3) — used when the port’s VID:PID has no `serial_ports.json` match and no device is identified. Baud’s unknown-port fallback is also `STANDARD_BAUD_RATES`, but a **matched chip** drives the Baud list (see White box 1). Data/Parity/Stop/Flow still ignore the chip catalog when no device is identified; an identified device’s own `serial_parameters` lists win when present:
  - Data: 8, 7, 6, 5
  - Parity: None, Odd, Even, Mark, Space
  - Stop: 1, 2
  - Flow: None, RTS/CTS, xOff/xOn
- White inner box, labels above controls, 2×2 reading order:
  - **Data Bits** / **Parity** on the first row, **Stop Bits** / **Flow** on the second
  - Green readonly box = live draft (`8 - N - 1 - N`, same helper as the main Settings field); **Select** (96px) to the right
- Below white box, still in blue: cream readonly current applied settings + **Exit** (96px)
- Preview lines are sized from the longest legal settings string (`8 - N - 1 - N`)
- **Select** applies values, updates main Settings, sets Port Status to **Unknown**, closes
- **Exit** / window X closes without applying
- Enter = Select, Escape = Exit

## Window
- Default size fits the content at 6 Automated rows: 3px orange frame, then 8px padding on every edge (including the bottom). No extra empty band below Port Status / Select / Exit
- Minimum *width* still fits that content (Device Status labels, Port dropdown, Open/Identify). Minimum *height* is the same layout with the Automated table showing exactly **one** row. No maximum height. Title strip, Manually boxes, and the bottom bar keep their height; only the table row has grid weight.
- Title-bar icon is a drawn DE-9 (DB9) connector face (Iris orange, 5+4 pins), not the default Tk feather. Files in `assets/` (`serial_icon_16/24/32/48/256.png`, `serial_icon.png`, multi-size `serial_icon.ico` with BMP 16/24/32/48 plus PNG 256). Path is relative to the script, or `sys._MEIPASS` when frozen. Linux uses `iconphoto`. Windows uses `root.iconbitmap(default=…)` plus `SetCurrentProcessExplicitAppUserModelID` so the title bar and taskbar show the DE-9. The Settings pop-up and device editor get the same icon. A failed load is logged and PNG `iconphoto` is the fallback.
