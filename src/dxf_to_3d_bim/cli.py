"""Command line interface for DXF-to-3D-BIM."""

import sys

def main():
    print("DXF-to-3D-BIM CLI v0.1.0")
    if len(sys.argv) > 1 and sys.argv[1] == "--version":
        return 0
    return 0

if __name__ == "__main__":
    sys.exit(main())
