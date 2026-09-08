"""Generate exhaustive argparse documentation without importing scientific packages."""
from __future__ import annotations
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def literal(node: ast.AST) -> str:
    try:
        return str(ast.literal_eval(node))
    except (ValueError, TypeError):
        return ast.unparse(node)


def main() -> None:
    lines = ["# Complete CLI reference", "", "Generated from every production Python argparse declaration. Defaults shown as expressions refer to constants in that file.", "See [PARAMETERS.md](PARAMETERS.md) for units and scientific interpretation. Run each script with `--help` for runtime usage.", ""]
    paths = [ROOT / "crisprtrack2.py", *sorted((ROOT / "nucleus_segmentation").glob("*.py")), *sorted((ROOT / "trajectory_extraction").rglob("*.py"))]
    count = 0
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        calls = sorted((n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "add_argument"), key=lambda n: n.lineno)
        if not calls:
            continue
        rel = path.relative_to(ROOT).as_posix()
        lines.extend([f"## `{rel}`", "", "| Argument | Default / required | Type / choices | Help / source |", "|---|---|---|---|"])
        for call in calls:
            count += 1
            kw = {x.arg: x.value for x in call.keywords}
            names = ", ".join(literal(x) for x in call.args)
            default = literal(kw["default"]) if "default" in kw else ("false" if "store_true" in literal(kw.get("action", ast.Constant(""))) else "None")
            if "required" in kw and literal(kw["required"]) == "True" or not names.startswith("-"):
                default = "required"
            datatype = literal(kw["type"]) if "type" in kw else "str"
            if "choices" in kw:
                datatype += "; " + literal(kw["choices"])
            helptext = literal(kw["help"]) if "help" in kw else f"[definition](../{rel}#L{call.lineno})"
            row = [names, default, datatype, helptext]
            lines.append("| " + " | ".join(v.replace("|", "\\|").replace("\n", " ") for v in row) + " |")
        lines.append("")
    (ROOT / "docs/CLI_REFERENCE.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Documented {count} argument declarations across {len(paths)} scripts.")


if __name__ == "__main__":
    main()
