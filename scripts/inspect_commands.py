import subprocess
import json

cli = r"C:\Program Files\BIMCraft\bimcraft-cli.exe"
proc = subprocess.run([cli, "commands"], capture_output=True, encoding="utf-8", check=True)
cmds = json.loads(proc.stdout)
targets = {"wall", "door", "window", "floor", "level", "roof", "save", "elements", "new", "open", "modify"}

for c in cmds:
    if c["id"] in targets:
        print(f"ID: {c['id']}")
        print(f"Label: {c.get('label')}")
        print(f"Params: {c.get('params')}")
        print("-" * 50)
