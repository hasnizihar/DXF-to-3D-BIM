# BIM Element Mapping Reference

| Intermediate Model Element | BIMCraft Command | Key Parameters |
| :--- | :--- | :--- |
| **Level** | `level` | `elevation` (mm), `name`, `extent` |
| **Exterior Wall** | `wall` | `start`, `end`, `height`, `thickness`, `level` |
| **Interior Wall** | `wall` | `start`, `end`, `height`, `thickness`, `level` |
| **Hosted Door** | `door` | `wall`, `at` [x, y], `width`, `height` |
| **Hosted Window** | `window` | `wall`, `at` [x, y], `width`, `height`, `sill` |
| **Slab** | `floor` | `boundary` [[x, y], ...], `thickness`, `level` |
| **Room** | `room` | `boundary` [[x, y], ...], `name`, `level` |
| **Roof** | `roof` | `boundary` [[x, y], ...], `type`, `pitch` |

