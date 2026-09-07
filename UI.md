# Serial Port Application UI

Version: 3.0 (page 3 — UART Connection Status)

## Colors / fonts
- Window background: `#E8E8E8`
- Section panels (`LabelFrame`): `#F5F5F5`, groove border, bold title
- Tree heading: Arial 10 bold, purple
- Tree rows: Arial 10

## Layout (grid)
```
+-------------------------------+------------------+
| UART Connection Status        | Port Settings    |
| (tree)                        | Ports / bits /   |
|                               | Bauds list / Open|
+-------------------------------+------------------+
| Devices                       | Connection       |
| (list preview)                | Select / Close   |
+-------------------------------+------------------+
| Scan Controls: In Use | Scan Ports | Scan Devices | Exit |
+----------------------------------------------------------+
```

## ID/Baud column
- No device found: Port ID (USB vendor/port ID)
- Device identified: baud used to connect (e.g. `115.2K`)

## Controls
- Checkbox = continuous auto action
- Button = one-shot; clears all three checkboxes / stops autos
- Port auto: 500 ms | Device auto: 2.5 s
