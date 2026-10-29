# BIMCraft Capabilities & Runtime Discovery

## Engine Overview
* **CLI Executable**: `C:\Program Files\BIMCraft\bimcraft-cli.exe`
* **Version**: `0.9.0`
* **Command Mode**: `bimcraft-cli run [FILE] [--sample | --highrise] [--cmd 'ID {json}']... [--script FILE]... [--save PATH]...`
* **Model Units**: Millimetres (`mm`), X East, Y North, Z Up.

## Verified Commands & Output Formats
* **Project Formats**:
  * `.bimcraft`: Native project file containing elements, library, views, GUIDs.
  * `.ifc`: Industry Foundation Classes 4 (IFC4).
  * `.png` / `.svg`: Floor plan rendering of lowest or active level.
  * `.pdf`: Multi-page print of all sheets.
* **Commands**:
  * `level`: Define storeys `{elevation, name?, extent?}`.
  * `wall`: Define wall segments `{start, end, height, thickness, level}`.
  * `floor`: Define horizontal slab boundary `{boundary, level, thickness}`.
  * `door`: Host door onto wall segment `{wall, at, width, height}`.
  * `window`: Host window onto wall segment `{wall, at, width, height}`.
  * `room`: Define spatial envelope and name `{boundary, name, level}`.
  * `roof`: Define roof envelope `{boundary, type, pitch}`.

