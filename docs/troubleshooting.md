# Troubleshooting Guide

## Common Issues & Solutions

### 1. BIMCraft CLI Not Found
* **Symptom**: `BIMCraft CLI not found at 'C:\Program Files\BIMCraft\bimcraft-cli.exe'`
* **Resolution**: If BIMCraft is installed in a non-default location, edit `config/defaults.json` and update `bimcraft.cli_path` to point to the correct path, or add the folder containing `bimcraft-cli.exe` to your Windows system `PATH`.

### 2. IfcOpenShell Application Control Block
* **Symptom**: `ImportError: DLL load failed while importing _ifcopenshell_wrapper: An Application Control policy has blocked this file.`
* **Cause**: Windows Application Control / AppLocker blocks loading uncertified binary DLLs from user directories.
* **Resolution**: The skill automatically falls back to `bimcraft-cli info <file.ifc>` to validate IFC element counts, levels, types, and warnings without requiring the `ifcopenshell` C-extension.

### 3. Missing DXF Units
* **Symptom**: DXF header `$INSUNITS` is `0` (unspecified).
* **Resolution**: The skill will flag this during the `inspect` stage and prompt you to specify drawing units (e.g. millimeters or meters).
