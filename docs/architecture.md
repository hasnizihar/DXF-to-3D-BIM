# DXF-to-3D-BIM Architecture

## Architectural Principles
1. **Engine Independence**: The interpretation layer extracts drawing entities into a normalized, versioned intermediate model (`bim-model.schema.json`). The geometry reconstruction does not directly depend on BIMCraft specifics.
2. **Deterministic Geometry**: Centerline pairing, polygon closing, snapping, and host projection are handled mathematically via Shapely and computational geometry algorithms, not probabilistic model guesses.
3. **Mandatory Approval Gate**: An intermediate model must be approved before BIMCraft commands are synthesized.
4. **Adapter Pattern**: The `BIMCraftAdapter` translates the approved intermediate model into atomic BIMCraft CLI commands or scripts.

## System Diagram

```mermaid
flowchart TD
    subgraph Input ["Input Layer"]
        DXF["2D DXF Floor Plan"]
        JSON["Sketch-to-CAD JSON (Optional)"]
        UserPref["User Building Preferences"]
    end

    subgraph Core ["DXF to 3D-BIM Core"]
        Parser["DXF Parser (ezdxf)"]
        Normalizer["Unit & Coordinate Normalizer"]
        Classifier["Layer Classifier"]
        Reconstruct["Geometry Reconstructor (Shapely)"]
        ModelBuilder["Intermediate Model Builder"]
    end

    subgraph Gate ["Approval Gate"]
        Proposal["Model Proposal Summary"]
        ApprovalCheck{"User Approved?"}
        ApprovedModel["Approved BIM Intermediate Model"]
    end

    subgraph Backend ["BIM Backend"]
        Adapter["BIMCraft Adapter"]
        CLI["BIMCraft CLI (0.9.0)"]
    end

    subgraph Deliverables ["Outputs"]
        BIMCraftFile[".bimcraft Native Project"]
        IFCFile["IFC4 Model (.ifc)"]
        PNGFile["Plan Preview (.png)"]
        Report["Validation Report"]
    end

    DXF --> Parser
    JSON -.-> ModelBuilder
    UserPref -.-> ModelBuilder
    Parser --> Normalizer --> Classifier --> Reconstruct --> ModelBuilder
    ModelBuilder --> Proposal --> ApprovalCheck
    ApprovalCheck -- "Yes" --> ApprovedModel
    ApprovalCheck -- "No" --> UserPref
    ApprovedModel --> Adapter --> CLI
    CLI --> BIMCraftFile
    CLI --> IFCFile
    CLI --> PNGFile
    BIMCraftFile & IFCFile --> Report
```

