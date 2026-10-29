"""Hardened independent pure-Python ISO-10303-21 STEP / IFC4 parser and semantic validator."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Set


@dataclass
class IfcEntity:
    id: int
    entity_type: str
    args: List[Any]
    raw_statement: str


def tokenize_step_args(args_str: str) -> List[Any]:
    """Tokenizes comma-separated STEP arguments respecting nested parentheses and quoted strings."""
    tokens = []
    current = []
    depth = 0
    in_str = False
    i = 0
    n = len(args_str)

    while i < n:
        ch = args_str[i]
        if ch == "'":
            if in_str and i + 1 < n and args_str[i + 1] == "'":
                # Escaped apostrophe
                current.append("''")
                i += 2
                continue
            else:
                in_str = not in_str
                current.append(ch)
                i += 1
                continue

        if not in_str:
            if ch == "(":
                depth += 1
                current.append(ch)
            elif ch == ")":
                depth -= 1
                current.append(ch)
            elif ch == "," and depth == 0:
                token_val = "".join(current).strip()
                tokens.append(_parse_step_token(token_val))
                current = []
            else:
                current.append(ch)
        else:
            current.append(ch)
        i += 1

    if current:
        token_val = "".join(current).strip()
        tokens.append(_parse_step_token(token_val))

    return tokens


def _parse_step_token(token: str) -> Any:
    """Parses a primitive STEP token (entity reference, string, number, enum, null, or nested tuple)."""
    if not token or token == "$":
        return None
    if token == "*":
        return "*"
    if token.startswith("'") and token.endswith("'"):
        # Unescape '' to '
        return token[1:-1].replace("''", "'")
    if token.startswith("#"):
        try:
            return int(token[1:])
        except ValueError:
            return token
    if token.startswith(".") and token.endswith("."):
        return token
    if token.startswith("(") and token.endswith(")"):
        # Nested aggregate: recursively parse arguments inside
        inner = token[1:-1].strip()
        if not inner:
            return ()
        return tuple(tokenize_step_args(inner))
    # Number
    try:
        if "." in token or "e" in token.lower():
            return float(token)
        return int(token)
    except ValueError:
        return token


def split_step_statements(data_text: str) -> List[str]:
    """Splits STEP DATA section into individual statements on ';' ignoring semicolons inside strings."""
    statements = []
    current = []
    in_str = False
    i = 0
    n = len(data_text)

    while i < n:
        ch = data_text[i]
        if ch == "'":
            if in_str and i + 1 < n and data_text[i + 1] == "'":
                current.append("''")
                i += 2
                continue
            else:
                in_str = not in_str
                current.append(ch)
                i += 1
                continue

        if ch == ";" and not in_str:
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
        else:
            current.append(ch)
        i += 1

    if current:
        stmt = "".join(current).strip()
        if stmt:
            statements.append(stmt)

    return statements


@dataclass
class IfcSemanticInspection:
    file_path: str
    schema: str
    counts: Dict[str, int]
    storeys: List[Dict[str, Any]]
    walls: List[Dict[str, Any]]
    openings: Dict[str, List[Dict[str, Any]]]
    slabs: List[Dict[str, Any]]
    roofs: List[Dict[str, Any]] = field(default_factory=list)
    voids_verified: bool = False
    fills_verified: bool = False
    containment_verified: bool = False
    contained_by_storey: Dict[str, List[int]] = field(default_factory=dict)
    details: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class PureIfcParser:
    """Robust, token-aware ISO-10303-21 STEP/IFC parser with deep semantic relationship verification."""

    def __init__(self, ifc_path: str | Path):
        self.ifc_path = Path(ifc_path)
        if not self.ifc_path.exists():
            raise FileNotFoundError(f"IFC file not found: {self.ifc_path}")

        self.entities: Dict[int, IfcEntity] = {}
        self.by_type: Dict[str, List[IfcEntity]] = {}
        self.schema: str = "UNKNOWN"
        self.warnings: List[str] = []
        self._parse_file()

    def _parse_file(self):
        content = self.ifc_path.read_text(encoding="utf-8", errors="replace")

        # Schema detection
        schema_match = re.search(r"FILE_SCHEMA\s*\(\s*\(\s*'([^']+)'\s*\)\s*\)", content, re.IGNORECASE)
        if schema_match:
            self.schema = schema_match.group(1)

        # DATA section extraction
        data_match = re.search(r"DATA\s*;(.*?)ENDSEC\s*;", content, re.DOTALL | re.IGNORECASE)
        if not data_match:
            self.warnings.append("No DATA section found in IFC file.")
            return

        data_text = data_match.group(1)
        raw_statements = split_step_statements(data_text)

        for stmt in raw_statements:
            m = re.match(r"^#(\d+)\s*=\s*([A-Za-z0-9_]+)\s*\((.*)\)$", stmt, re.DOTALL)
            if m:
                eid = int(m.group(1))
                etype = m.group(2).upper()
                args_str = m.group(3)
                parsed_args = tokenize_step_args(args_str)

                entity = IfcEntity(id=eid, entity_type=etype, args=parsed_args, raw_statement=stmt)
                if eid in self.entities:
                    prev = self.entities[eid]
                    self.warnings.append(f"Duplicate entity ID #{eid} detected. Overwriting.")
                    if prev.entity_type in self.by_type and prev in self.by_type[prev.entity_type]:
                        self.by_type[prev.entity_type].remove(prev)
                self.entities[eid] = entity

                if etype not in self.by_type:
                    self.by_type[etype] = []
                self.by_type[etype].append(entity)
            else:
                self.warnings.append(f"Unparseable statement: {stmt[:60]}...")

    def get_entities_by_type(self, etype: str) -> List[IfcEntity]:
        return self.by_type.get(etype.upper(), [])

    def get_entity(self, eid: int) -> Optional[IfcEntity]:
        return self.entities.get(eid)

    def inspect(self) -> IfcSemanticInspection:
        """Deep semantic inspection verifying wall voids, opening fills, spatial containment, and dimensions."""
        details: List[str] = []

        wall_entities = self.get_entities_by_type("IFCWALL") + self.get_entities_by_type("IFCWALLSTANDARDCASE")
        door_entities = self.get_entities_by_type("IFCDOOR")
        window_entities = self.get_entities_by_type("IFCWINDOW")
        slab_entities = self.get_entities_by_type("IFCSLAB")
        roof_entities = self.get_entities_by_type("IFCROOF")
        opening_entities = self.get_entities_by_type("IFCOPENINGELEMENT")
        storey_entities = self.get_entities_by_type("IFCBUILDINGSTOREY")

        counts = {
            "wall": len(wall_entities),
            "door": len(door_entities),
            "window": len(window_entities),
            "slab": len(slab_entities),
            "roof": len(roof_entities),
            "opening_element": len(opening_entities),
            "storey": len(storey_entities),
        }

        # 1. Storey Details
        storeys = []
        for st in storey_entities:
            # IFCBUILDINGSTOREY: (GlobalId, OwnerHistory, Name, Description, ObjectType, ObjectPlacement, Representation, LongName, CompositionType, Elevation)
            name = st.args[2] if len(st.args) > 2 and isinstance(st.args[2], str) else f"Storey_{st.id}"
            elevation = st.args[9] if len(st.args) > 9 and isinstance(st.args[9], (int, float)) else 0.0
            storeys.append({"id": st.id, "name": name, "elevation": float(elevation)})

        # 2. Spatial Containment Check
        containment_rels = self.get_entities_by_type("IFCRELCONTAINEDINSPATIALSTRUCTURE")
        contained_element_ids: Set[int] = set()
        contained_by_storey: Dict[int, List[int]] = {}

        for rel in containment_rels:
            # IFCRELCONTAINEDINSPATIALSTRUCTURE: (GlobalId, OwnerHistory, Name, Description, RelatedElements, RelatingStructure)
            if len(rel.args) >= 6:
                related = rel.args[4]
                structure_ref = rel.args[5]
                structure_id = structure_ref if isinstance(structure_ref, int) else None

                elem_ids = []
                if isinstance(related, (tuple, list)):
                    for r in related:
                        if isinstance(r, int):
                            elem_ids.append(r)
                            contained_element_ids.add(r)

                if structure_id:
                    contained_by_storey[structure_id] = elem_ids

        all_primary_ids = {e.id for e in (wall_entities + door_entities + window_entities + slab_entities + roof_entities)}
        containment_verified = all_primary_ids.issubset(contained_element_ids) if all_primary_ids else True
        if containment_verified and all_primary_ids:
            details.append(f"Spatial containment verified: All {len(all_primary_ids)} primary building elements are linked to building storeys.")
        elif all_primary_ids:
            missing = all_primary_ids - contained_element_ids
            details.append(f"Containment warning: elements {missing} not bound to a storey.")

        contained_by_storey_named: Dict[str, List[int]] = {}
        for st in storeys:
            contained_by_storey_named[st["name"]] = contained_by_storey.get(st["id"], [])

        # 3. Opening and Wall Penetration (Voiding & Filling) Check
        void_rels = self.get_entities_by_type("IFCRELVOIDSELEMENT")
        wall_to_openings: Dict[int, List[int]] = {}
        opening_to_wall: Dict[int, int] = {}

        for vr in void_rels:
            # IFCRELVOIDSELEMENT: (GlobalId, OwnerHistory, Name, Description, RelatingBuildingElement, RelatedOpeningElement)
            if len(vr.args) >= 6:
                wid = vr.args[4]
                oid = vr.args[5]
                if isinstance(wid, int) and isinstance(oid, int):
                    if wid not in wall_to_openings:
                        wall_to_openings[wid] = []
                    wall_to_openings[wid].append(oid)
                    opening_to_wall[oid] = wid

        fill_rels = self.get_entities_by_type("IFCRELFILLSELEMENT")
        opening_to_filling: Dict[int, int] = {}
        filling_to_opening: Dict[int, int] = {}

        for fr in fill_rels:
            # IFCRELFILLSELEMENT: (GlobalId, OwnerHistory, Name, Description, RelatingOpeningElement, RelatedBuildingElement)
            if len(fr.args) >= 6:
                oid = fr.args[4]
                fid = fr.args[5]
                if isinstance(oid, int) and isinstance(fid, int):
                    opening_to_filling[oid] = fid
                    filling_to_opening[fid] = oid

        door_win_ids = {e.id for e in (door_entities + window_entities)}
        unvoided_openings = []
        for dw_id in door_win_ids:
            oid = filling_to_opening.get(dw_id)
            if not oid or oid not in opening_to_wall:
                unvoided_openings.append(dw_id)

        voids_verified = (len(unvoided_openings) == 0) and (len(door_win_ids) > 0 or len(opening_entities) == 0)
        fills_verified = len(filling_to_opening) == len(door_win_ids)

        if voids_verified and fills_verified and door_win_ids:
            details.append(
                f"Opening penetration verified: All {len(door_win_ids)} doors/windows occupy IfcOpeningElements that cut their host IfcWalls via IfcRelVoidsElement."
            )

        # 4. Extract Door Dimensions
        doors = []
        for d in door_entities:
            # IFCDOOR: (GlobalId, OwnerHistory, Name, Description, ObjectType, ObjectPlacement, Representation, Tag, OverallHeight, OverallWidth, PredefinedType, OperationType, UserDefinedOperationType)
            height = float(d.args[8]) if len(d.args) > 8 and isinstance(d.args[8], (int, float)) else 2100.0
            width = float(d.args[9]) if len(d.args) > 9 and isinstance(d.args[9], (int, float)) else 900.0
            oid = filling_to_opening.get(d.id)
            host_wall = opening_to_wall.get(oid) if oid else None
            doors.append({
                "id": d.id,
                "name": d.args[2] if len(d.args) > 2 and isinstance(d.args[2], str) else "Door",
                "height": height,
                "width": width,
                "opening_element_id": oid,
                "host_wall_id": host_wall,
            })

        # 5. Extract Window Dimensions
        windows = []
        for w in window_entities:
            # IFCWINDOW: (GlobalId, OwnerHistory, Name, Description, ObjectType, ObjectPlacement, Representation, Tag, OverallHeight, OverallWidth, PredefinedType, PartitioningType, UserDefinedPartitioningType)
            height = float(w.args[8]) if len(w.args) > 8 and isinstance(w.args[8], (int, float)) else 1500.0
            width = float(w.args[9]) if len(w.args) > 9 and isinstance(w.args[9], (int, float)) else 1200.0
            oid = filling_to_opening.get(w.id)
            host_wall = opening_to_wall.get(oid) if oid else None
            windows.append({
                "id": w.id,
                "name": w.args[2] if len(w.args) > 2 and isinstance(w.args[2], str) else "Window",
                "height": height,
                "width": width,
                "opening_element_id": oid,
                "host_wall_id": host_wall,
            })

        # 6. Extract Wall Details
        walls = []
        for w in wall_entities:
            walls.append({
                "id": w.id,
                "name": w.args[2] if len(w.args) > 2 and isinstance(w.args[2], str) else "Wall",
                "void_count": len(wall_to_openings.get(w.id, [])),
            })

        # 7. Extract Roof Details
        roofs = []
        for rf in roof_entities:
            # IFCROOF: (GlobalId, OwnerHistory, Name, Description, ObjectType, ObjectPlacement, Representation, Tag, PredefinedType)
            raw_predef = rf.args[8] if len(rf.args) > 8 else None
            predef_str = str(raw_predef).strip(".").upper() if raw_predef else "NOTDEFINED"
            has_rep = bool(rf.args[6]) if len(rf.args) > 6 else False
            host_st = None
            for st_name, elem_list in contained_by_storey_named.items():
                if rf.id in elem_list:
                    host_st = st_name
                    break
            roofs.append({
                "id": rf.id,
                "name": rf.args[2] if len(rf.args) > 2 and isinstance(rf.args[2], str) else "Roof",
                "predefined_type": predef_str,
                "has_representation": has_rep,
                "contained_in_storey": host_st,
            })

        return IfcSemanticInspection(
            file_path=str(self.ifc_path),
            schema=self.schema,
            counts=counts,
            storeys=storeys,
            walls=walls,
            openings={"doors": doors, "windows": windows},
            slabs=[{"id": s.id} for s in slab_entities],
            roofs=roofs,
            voids_verified=voids_verified,
            fills_verified=fills_verified,
            containment_verified=containment_verified,
            contained_by_storey=contained_by_storey_named,
            details=details,
            warnings=self.warnings,
        )
