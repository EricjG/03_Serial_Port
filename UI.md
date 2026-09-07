# Serial Port Application UI

Version: 3.0 — aligned to cleaned Google Slides page 3

## Colors
- Window / panels: `#FFFFFF` (white)
- Section blue: `#D6E8F8`, black 1px outline
- Buttons: gray `#C0C0C0`
- **One** outer border: orange `#FF8C00`

## 1st — Header
- Light blue bar, black outline; white gap from orange border
- Left: **UART Connection Status** (black)
- Right: In Use / Scan Ports / Scan Devices — checkbox on top of each gray button

## 2nd — Status list (own blue box)
- Untitled light-blue box, black outline
- Column titles in blue area; Status / Port # / ID/Baud fixed width
- **Available / In Use:** ID/Baud = USB vendor ID; Serial Driver / Connected Device = pyserial adapter text
- **Identified:** ID/Baud = baud used to identify; Serial Driver / Connected Device = formatted `devices.json` `response.device_column` (not USB-serial driver text)

## 3rd — Connection controls (own blue box)
- Bold UI text
- **Status**: read-only text box
- **Port** / **Baud**: editable combobox; no `* Manual Entry *` item
- **Settings**: white button `None - 1 - 1 - None `
- **Device**: label + dropdown to the right
- Top-right: **Open:** (left-aligned, not wired); under it **Scan Device** (tree-selected port only)

## 4th — Bottom
- White bar; **Exit** then **Select** on the right (**Select** furthest right)
- Button text center-aligned
