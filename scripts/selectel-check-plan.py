"""Read a saved Selectel plan without credentials; print only resource counts."""
import json
import subprocess
from collections import Counter
from pathlib import Path
from selectel_plan import validate_creation

ROOT = Path(__file__).resolve().parents[1]
plan = ROOT / ".local/selectel.tfplan"
if not plan.exists():
    raise SystemExit("Сначала выполните tf-selectel.ps1 plan '-out=../.local/selectel.tfplan'.")
data = json.loads(subprocess.check_output([str(ROOT / ".tools/terraform.exe"),
    "-chdir=" + str(ROOT / "terraform-selectel"), "show", "-json", str(plan)]))
changes = [r for r in data.get("resource_changes", []) if r["mode"] == "managed"]
counts = Counter()
for item in changes:
    counts[(item["type"], ",".join(item["change"]["actions"]))] += 1
for (kind, actions), count in sorted(counts.items()):
    print(f"{kind}: {actions} x {count}")
try:
    validate_creation(data)
except ValueError as error:
    raise SystemExit(str(error)) from None
print("Пять ВМ; только create/no-op. Apply не выполнялся.")
