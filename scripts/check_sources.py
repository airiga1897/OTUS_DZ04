"""Локальные проверки исходников, YAML и шаблонов без облачных операций."""
import ast
from pathlib import Path
import yaml
from jinja2 import Environment, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]

def main() -> None:
    for directory in ("scripts", "app", "tests"):
        for path in (ROOT/directory).rglob("*.py"):
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for path in (ROOT/"ansible").rglob("*.yml"):
        list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    env = Environment(undefined=StrictUndefined)
    for path in (ROOT/"ansible").rglob("*.j2"):
        env.parse(path.read_text(encoding="utf-8"))
    print("Python AST, YAML и синтаксис Jinja проверены. Это не Linux-интеграция и не ansible --syntax-check.")

if __name__ == "__main__":
    main()

