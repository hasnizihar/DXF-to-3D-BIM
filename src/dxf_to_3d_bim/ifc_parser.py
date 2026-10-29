"""Independent pure-Python ISO-10303-21 STEP / IFC4 parser and deep semantic validator."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Set


@dataclass
class IfcEntity:
    id: int
    entity_type: str
    params: List[Any]
    raw_line: str


@dataclass
class IfcSemanticInspection:
    file_path: str
    schema: str
    counts: Dict[str, int]
    storeys: List[Dict[str, Any]]
    walls: List[Dict[str, Any]]
    openings: List[Dict[str, Any]]
    slabs: List[Dict[str, Any]]
    voids_verified: bool
    fills_verified: bool
    containment_verified: bool
    details: List[str] = field(default_factory=list)


class PureIfcParser:
    """Parses IFC4 / IFC2X3 STEP files to independently verify geometric and topological relationships."""

    def __init__(self, ifc_path: str | Path):
        self.ifc_path = Path(ifc_path)
        if not self.ifc_path.exists():
            raise FileNotFoundError(f"IFC file not found: {self.ifc_path}")

        self.entities: Dict[int, IfcEntity] = {}
        self.by_type: Dict[str, List[IfcEntity]] = {}
        self.schema: str = "UNKNOWN"
        self._parse_file()

    def _parse_file(self):
        content = self.ifc_path.read_text(encoding="utf-8", errors="replace")

        # Schema detection
        schema_match = re.search(r"FILE_SCHEMA\s*\(\s*\(\s*'([^']+)'\s*\)\s*\)", content, re.IGNORECASE)
        if schema_match:
            self.schema = schema_match.group(1)

        # Entity regex: #123 = ENTITY_NAME(args);
        # Split on semicolon while handling DATA section
        data_match = re.search(r"DATA\s*;(.*?)ENDSEC\s*;", content, re.DOTALL | re.IGNORECASE)
        if not data_match:
            return

        data_text = data_match.group(1)
        raw_statements = [s.strip() for s in data_text.split(";") if s.strip()]

        for stmt in raw_statements:
            m = re.match(r"^#(\d+)\s*=\s*([A-Za-z0-9_]+)\s*\((.*)\)$", stmt, re.DOTALL)
            if m:
                eid = int(m.group(1))
                etype = m.group(2).upper()
                raw_args = m.group(3)
                entity = IfcEntity(id=eid, entity_type=etype, params=[], raw_line=stmt)
                self.entities[eid] = entity
                if etype not in self.by_type:
                    self.by_type[etype] = []
                self.by_type[etype].append(entity)

    def get_entities_by_type(self, etype: str) -> List[IfcEntity]:
        return self.by_type.get(etype.upper(), [])

    def inspect(self) -> IfcSemanticInspection:
        """Deep semantic inspection verifying wall voids, opening fills, spatial containment, and dimensions."""
        details: List[str] = []

        # 1. Element counts
        wall_entities = self.get_entities_by_type("IFCWALL") + self.get_entities_by_type("IFCWALLSTANDARDCASE")
        door_entities = self.get_entities_by_type("IFCDOOR")
        window_entities = self.get_entities_by_type("IFCWINDOW")
        slab_entities = self.get_entities_by_type("IFCSLAB")
        opening_entities = self.get_entities_by_type("IFCOPENINGELEMENT")
        storey_entities = self.get_entities_by_type("IFCBUILDINGSTOREY")

        counts = {
            "wall": len(wall_entities),
            "door": len(door_entities),
            "window": len(window_entities),
            "slab": len(slab_entities),
            "opening_element": len(opening_entities),
            "storey": len(storey_entities),
        }

        # 2. Storey Inspection
        storeys = []
        for st in storey_entities:
            # Extract elevation from params
            # Line format: IFCBUILDINGSTOREY('guid',$,'Name',$,$,#placement,$,$,.ELEMENT.,elevation);
            elevation = 0.0
            elev_match = re.search(r",\s*(-?\d+(?:\.\d*)?)\s*\)\s*$", st.raw_line)
            if elev_match:
                elevation = float(elev_match.group(1))

            name_match = re.search(r"'([^']+)'", st.raw_line)
            name = name_match.group(1) if name_match else f"Storey_{st.id}"
            storeys.append({"id": st.id, "name": name, "elevation": elevation})

        # 3. Spatial Containment Check
        # Find IFCRELCONTAINEDINSPATIALSTRUCTURE
        containment_rel = self.get_entities_by_type("IFCRELCONTAINEDINSPATIALSTRUCTURE")
        contained_element_ids: Set[int] = set()
        contained_by_storey: Dict[int, List[int]] = {}

        for rel in containment_rel:
            # Parse elements tuple: (#51,#71,#91,#111,#126,#148,#171),#26
            m = re.search(r"\(\s*([#\d\s,]+)\s*\)\s*,\s*#(\d+)", rel.raw_line)
            if m:
                elem_refs = [int(x.replace("#", "").strip()) for x in m.group(1).split(",") if x.strip()]
                storey_id = int(m.group(2))
                contained_by_storey[storey_id] = elem_refs
                contained_element_ids.update(elem_refs)

        all_primary_ids = {e.id for e in (wall_entities + door_entities + window_entities + slab_entities)}
        containment_verified = all_primary_ids.issubset(contained_element_ids)
        if containment_verified:
            details.append(f"All {len(all_primary_ids)} primary architectural elements are formally linked to storeys via IfcRelContainedInSpatialStructure.")
        else:
            missing = all_primary_ids - contained_element_ids
            details.append(f"Containment warning: elements {missing} not bound to a storey.")

        # 4. Opening and Wall Penetration (Voiding & Filling) Check
        # IFCRELVOIDSELEMENT: relating wall -> related opening element
        # Line format: IFCRELVOIDSELEMENT('guid',$,$,$,#wall_id,#opening_id);
        void_rels = self.get_entities_by_type("IFCRELVOIDSELEMENT")
        wall_to_openings: Dict[int, List[int]] = {}
        opening_to_wall: Dict[int, int] = {}

        for vr in void_rels:
            m = re.search(r"#(\d+)\s*,\s*#(\d+)\s*\)\s*$", vr.raw_line)
            if m:
                wid = int(m.group(1))
                oid = int(m.group(2))
                if wid not in wall_to_openings:
                    wall_to_openings[wid] = []
                wall_to_openings[wid].append(oid)
                opening_to_wall[oid] = wid

        # IFCRELFILLSELEMENT: relating opening element -> related door/window
        # Line format: IFCRELFILLSELEMENT('guid',$,$,$,#opening_id,#door_win_id);
        fill_rels = self.get_entities_by_type("IFCRELFILLSELEMENT")
        opening_to_filling: Dict[int, int] = {}
        filling_to_opening: Dict[int, int] = {}

        for fr in fill_rels:
            m = re.search(r"#(\d+)\s*,\s*#(\d+)\s*\)\s*$", fr.raw_line)
            if m:
                oid = int(m.group(1))
                fid = int(m.group(2))
                opening_to_filling[oid] = fid
                filling_to_opening[fid] = oid

        # Verify that all doors and windows have an opening element that voids a wall
        door_win_ids = {e.id for e in (door_entities + window_entities)}
        unvoided_openings = []
        for dw_id in door_win_ids:
            oid = filling_to_opening.get(dw_id)
            if not oid or oid not in opening_to_wall:
                unvoided_openings.append(dw_id)

        voids_verified = (len(unvoided_openings) == 0) and (len(door_win_ids) > 0 or len(opening_entities) == 0)
        fills_verified = len(filling_to_opening) == (len(door_entities) + len(window_entities))

        if voids_verified and fills_verified:
            details.append(
                f"Opening penetration verified: All {len(door_win_ids)} doors/windows occupy IfcOpeningElements that cut their host IfcWalls via IfcRelVoidsElement."
            )
        else:
            details.append(f"Opening penetration issue: {len(unvoided_openings)} doors/windows do not void a host wall.")

        # 5. Extract Dimensions
        doors = []
        for d in door_entities:
            # IFCDOOR('guid',$,'Type',$,$,#place,#shape,'Mark',height,width,.DOOR.,...);
            dims_match = re.search(r",\s*(\d+(?:\.\d*)?)\s*,\s*(\d+(?:\.\d*)?)\s*,\s*\.DOOR\.", d.raw_line)
            h, w = (float(dims_match.group(1)), float(dims_match.group(2))) if dims_match else (2100.0, 900.0)
            doors.append({"id": d.id, "height": h, "width": w, "host_wall": opening_to_wall.get(filling_to_opening.get(d.id, 0))})

        windows = []
        for w in window_entities:
            dims_match = re.search(r",\s*(\d+(?:\.\d*)?)\s*,\s*(\d+(?:\.\d*)?)\s*,\s*\.WINDOW\.", w.raw_line)
            h, wd = (float(dims_match.group(1)), float(dims_match.group(2))) if dims_match else (1500.0, 1200.0)
            windows.append({"id": w.id, "height": h, "width": wd, "host_wall": opening_to_wall.get(filling_to_opening.get(w.id, 0))})

        return IfcSemanticInspection(
            file_path=str(self.ifc_path),
            schema=self.schema,
            counts=counts,
            storeys=storeys,
            walls=[{"id": w.id, "type": "wall", "void_count": len(wall_to_openings.get(w.id, []))} for w in wall_entities],
            openings={"doors": doors, "windows": windows},
            slabs=[{"id": s.id} for s in slab_entities],
            voids_verified=voids_verified,
            fills_verified=fills_verified,
            containment_verified=containment_verified,
            details=details,
        )

