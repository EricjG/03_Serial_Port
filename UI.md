# Serial Port Application UI

Version: 3.0 — aligned to cleaned Google Slides page 3

## Colors
- Window / panels: `#FFFFFF` (white)
- Section blue: `#D6E8F8`, black 1px outline
- Buttons: gray `#C0C0C0`
- **One** outer border: orange `#FF8C00`
- Settings preview (dialog): green `#90EE90`

## 1st — Header
- Light blue bar, black outline; white gap from orange border
- Left: **UART Connection Status** (black)
- Right: In Use / Scan Ports / Scan Devices — checkbox on top of each gray button

## 2nd — Status list (own blue box)
- Untitled light-blue box, black outline
- Column titles in blue area; Status / Port # / ID/Baud fixed width

## 3rd — Connection controls (own blue box)
- Bold UI text
- **Status** / **Port** / **Baud** / **Port Settings**: labels centered above their box
- **Status**: read-only; follows the selected port's list status
- **Port** / **Baud**: editable combobox; no `* All *` or `* Manual Entry *` item
- **Port** shows `No Ports Available` until a port exists, then defaults to the first **Available** port
- **Port Settings**: white button, default `Even - 8 - 1 - None `; single-click opens the dialog
- Picking a port sets Status from the list and enables **Open: COMx**, **Scan Device**, and **Select**
- **Device** dropdown applies that device's baud and port settings
- **Open:** opens the selected port with the blue-box baud and port settings; status becomes **Open**
- **Scan Device** probes only the device shown in the Device dropdown, using the blue-box settings
- **Select** prints `Selected port: COMx`, closes the open port, then quits
- **Exit** and the window X also close the open port before quitting
- **Device**: label + dropdown; dropdown right edge lines up with Settings button
- Top-right: **Open:** (left-aligned); under it **Scan Device**

## 4th — Bottom
- White bar; **Exit** then **Select** on the right (**Select** furthest right)
- Button text center-aligned

## Port Settings dialog
- Open by **single-click** on the main **Port Settings** value
- Orange 3px outer border; white gap; light-blue box with black 1px outline
- Title **Port Settings** upper-left in the blue box
- Defaults: Parity Even, Stop Bits 1, Data Bits 8, Flow None
- White inner box:
  - Left: **Parity:** + dropdown; right: **Stop Bits:** + dropdown
  - Left: **Data Bits:** + dropdown; right: **Flow:** + dropdown
  - Green readonly box (short) = live draft; **Select** to the right (text centered)
- Below white box, still in blue: short readonly current applied settings + **Exit** (text centered)
- **Select** applies values, updates main Settings, closes
- **Exit** / window X closes without applying
