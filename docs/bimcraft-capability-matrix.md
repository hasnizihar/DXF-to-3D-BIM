# BIMCraft Capability Matrix

**Evaluated Engine:** BIMCraft CLI `0.9.0` (installed at `C:\Program Files\BIMCraft\bimcraft-cli.exe`)  
**Host System:** Windows 10/11 x64  
**Date Evaluated:** October 2026  

---

## 1. Executive Summary

BIMCraft provides a command-driven BIM core that operates headlessly via `bimcraft-cli` and interactively via `bimcraft.exe`. It supports native `.bimcraft` project serialization, IFC4 import/export, 2D plan rendering (`.png`, `.svg`), sheet printing (`.pdf`), and an integrated Model Context Protocol (MCP) server.

| Capability Area | Status | Verified Method | Notes |
| :--- | :--- | :--- | :--- |
| **CLI Command Execution** | **SUPPORTED** | `bimcraft-cli run --cmd 'ID {json}'` | Atomic JSON command sequence |
| **Script Execution** | **SUPPORTED** | `bimcraft-cli run --script <file>` | Line-separated JSON commands |
| **Native Project Save/Open** | **SUPPORTED** | `.bimcraft` | Verified save and reload |
| **IFC4 Export** | **SUPPORTED** | `--save <path>.ifc` | Verified IFC4 generation |
| **IFC4 Inspection** | **SUPPORTED** | `bimcraft-cli info <path>.ifc` | Returns element counts, levels, types in JSON |
| **2D Plan Preview Render** | **SUPPORTED** | `--save <path>.png` / `.svg` | High-resolution raster or vector view |
| **MCP Server Mode** | **SUPPORTED** | `bimcraft-cli mcp [--connect]` | Stdio MCP for agent integration |
| **Levels & Storeys** | **SUPPORTED** | `level` command | Elevation in mm, custom extent |
| **Walls** | **SUPPORTED** | `wall` command | Start/end [x,y] mm, type, level, height |
| **Floors / Slabs** | **SUPPORTED** | `floor` command | Boundary polygon [[x,y], ...], thickness |
| **Doors (Hosted)** | **SUPPORTED** | `door` command | Hosted on wall, width, height, handing |
| **Windows (Hosted)** | **SUPPORTED** | `window` command | Hosted on wall, width, height, sill |
| **Rooms** | **SUPPORTED** | `room` command | Area calculation, room labels |
| **Roofs** | **PARTIALLY SUPPORTED** | `roof` command | Boundary + pitch/hip; requires explicit slope inputs |
| **Structural Columns/Beams**| **SUPPORTED** | `column`, `beam` commands | Conceptual placement only (no engineering sizing) |
| **IfcOpenShell Inspection** | **UNVERIFIED / BLOCKED** | Python C-extension | Windows App Control blocks `_ifcopenshell_wrapper.pyd`; native `bimcraft-cli info` is used instead |

---

## 2. Coordinate & Unit Conventions

* **Length Unit:** Millimetres (`mm`).
* **Origin & Axes:**
  * `X`: East / Right (+)
  * `Y`: North / Up (+)
  * `Z`: Elevation (+)
* **Rule:** All DXF coordinates (whether metres, inches, or feet) must be converted into millimetres prior to issuing BIMCraft commands.

---

## 3. Verified Command Reference

### Level
```json
{"elevation": 0.0, "name": "Level 1"}
{"elevation": 3000.0, "name": "Level 2"}
```

### Wall
```json
{
  "start": [0, 0],
  "end": [6000, 0],
  "level": "Level 1",
  "height": 3000.0,
  "thickness": 200.0
}
```

### Floor / Slab
```json
{
  "boundary": [[0, 0], [6000, 0], [6000, 4000], [0, 4000]],
  "level": "Level 1",
  "thickness": 150.0
}
```

### Door & Window (Hosted)
```json
{
  "wall": "<wall_id_or_guid>",
  "at": [1500, 0],
  "width": 900.0,
  "height": 2100.0
}
```

---

## 4. Environment Limitations & Mitigations

1. **Third-Party C-Extension Execution:**
   * On Windows with Application Control policies enabled, dynamically compiled C-extensions like `_ifcopenshell_wrapper.pyd` installed in user site-packages are restricted.
   * **Mitigation:** The skill uses `bimcraft-cli info <file.ifc>` as the primary validation backend (which parses the IFC structure natively in Rust and outputs complete element counts, level definitions, and warnings) plus pure-Python STEP parser fallbacks.
2. **2D to 3D Vertical Extrusion:**
   * 2D CAD files lack vertical level, sill, and wall heights.
   * **Mitigation:** Mandatory human approval gate is enforced before issuing construction commands.
