from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
ARCHITECTURE_FILE = ROOT / "ARCHITECTURE.md"

PROJECT_SECTIONS = ("routers", "services", "schemas", "database", "prompts")
SUPABASE_TABLE_RE = re.compile(r"(?:\.\s*)?table\s*\(\s*['\"]([^'\"]+)['\"]\s*\)")


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def module_name(path: Path) -> str:
    return rel(path.with_suffix("")).replace("/", ".")


def module_to_file(module: str, modules: dict[str, Path]) -> Path | None:
    if module in modules:
        return modules[module]

    init_module = f"{module}.__init__"
    if init_module in modules:
        return modules[init_module]

    parts = module.split(".")
    while len(parts) > 1:
        candidate = ".".join(parts)
        if candidate in modules:
            return modules[candidate]
        parts.pop()

    return None


def resolve_relative_module(current_module: str, import_module: str | None, level: int) -> str:
    parts = current_module.split(".")[:-1]
    if level > 0:
        parts = parts[: max(0, len(parts) - level + 1)]
    if import_module:
        parts.extend(import_module.split("."))
    return ".".join(parts)


def read_python_files() -> list[Path]:
    if not APP_DIR.exists():
        return []
    return sorted(APP_DIR.rglob("*.py"))


def build_tree(paths: list[Path]) -> str:
    tree: dict[str, dict] = {}

    for path in paths:
        current = tree
        for part in path.relative_to(APP_DIR).parts:
            current = current.setdefault(part, {})

    lines = ["- app/"]

    def walk(node: dict[str, dict], depth: int) -> None:
        for name in sorted(node):
            suffix = "/" if node[name] else ""
            lines.append(f"{'  ' * depth}- {name}{suffix}")
            if node[name]:
                walk(node[name], depth + 1)

    walk(tree, 1)
    return "\n".join(lines)


def collect_section_files(py_files: list[Path]) -> dict[str, list[Path]]:
    sections: dict[str, list[Path]] = {section: [] for section in PROJECT_SECTIONS}

    for path in py_files:
        parts = path.relative_to(APP_DIR).parts
        if parts and parts[0] in sections:
            sections[parts[0]].append(path)

    prompts_dir = APP_DIR / "prompts"
    if prompts_dir.exists():
        prompt_files = sorted(path for path in prompts_dir.rglob("*") if path.is_file())
        sections["prompts"] = prompt_files

    return sections


def collect_imports(py_files: list[Path]) -> dict[str, set[str]]:
    modules = {module_name(path): path for path in py_files}
    dependencies: dict[str, set[str]] = {rel(path): set() for path in py_files}

    for path in py_files:
        source = path.read_text(encoding="utf-8", errors="ignore")
        current_module = module_name(path)

        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            candidate_modules: list[str] = []

            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("app."):
                        candidate_modules.append(alias.name)

            if isinstance(node, ast.ImportFrom):
                if node.level:
                    base_module = resolve_relative_module(current_module, node.module, node.level)
                else:
                    base_module = node.module or ""

                if base_module.startswith("app"):
                    candidate_modules.append(base_module)
                    for alias in node.names:
                        if alias.name != "*":
                            candidate_modules.append(f"{base_module}.{alias.name}")

            for candidate in candidate_modules:
                target = module_to_file(candidate, modules)
                if target and target != path:
                    dependencies[rel(path)].add(rel(target))

    return dependencies


def collect_supabase_tables(py_files: list[Path]) -> dict[str, set[str]]:
    tables: dict[str, set[str]] = {}
    for path in py_files:
        source = path.read_text(encoding="utf-8", errors="ignore")
        found = set(SUPABASE_TABLE_RE.findall(source))
        if found:
            tables[rel(path)] = found
    return tables


def bullet_list(paths: list[Path]) -> str:
    if not paths:
        return "- Не найдено"
    return "\n".join(f"- `{rel(path)}`" for path in sorted(paths))


def dependency_list(dependencies: dict[str, set[str]]) -> str:
    lines: list[str] = []
    for source, targets in sorted(dependencies.items()):
        if not targets:
            continue
        for target in sorted(targets):
            lines.append(f"- `{source}` -> `{target}`")
    return "\n".join(lines) if lines else "- Внутренние зависимости не найдены"


def table_list(tables: dict[str, set[str]]) -> str:
    lines: list[str] = []
    for source, names in sorted(tables.items()):
        lines.append(f"- `{source}`: " + ", ".join(f"`{name}`" for name in sorted(names)))
    return "\n".join(lines) if lines else "- Таблицы Supabase не найдены"


def generate_markdown() -> str:
    py_files = read_python_files()
    sections = collect_section_files(py_files)
    dependencies = collect_imports(py_files)
    tables = collect_supabase_tables(py_files)

    return f"""# Architecture

## Краткое описание

PULS backend - FastAPI-сервис для автомобильной диагностики. Он принимает запросы с сайта, маршрутизирует их через routers, вызывает services для диалога, поиска, парсера и базы знаний, а затем возвращает структурированный ответ клиенту.

## Структура папок

```text
{build_tree(py_files)}
```

## Routers

{bullet_list(sections["routers"])}

## Services

{bullet_list(sections["services"])}

## Schemas

{bullet_list(sections["schemas"])}

## Database Files

{bullet_list(sections["database"])}

## Prompts

{bullet_list(sections["prompts"])}

## Зависимости между файлами

{dependency_list(dependencies)}

## Таблицы Supabase

{table_list(tables)}

## Поток запроса

```mermaid
flowchart LR
    Frontend[Frontend] --> FastAPI[FastAPI]
    FastAPI --> Routers[Routers]
    Routers --> Services[Services]
    Services --> ParserKB[Parser / KB]
    ParserKB --> Supabase[Supabase]
    Supabase --> Response[Response]
```
"""


def main() -> None:
    ARCHITECTURE_FILE.write_text(generate_markdown(), encoding="utf-8")
    print(f"Updated {ARCHITECTURE_FILE}")


if __name__ == "__main__":
    main()
