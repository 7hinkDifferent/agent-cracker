from __future__ import annotations

"""Hermes tool registry + AST discovery demo core."""

import ast
import importlib.util
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


@dataclass
class ToolEntry:
    name: str
    toolset: str
    description: str
    handler: Callable[[dict], str]


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolEntry] = {}
        self._lock = threading.RLock()

    def register(self, name: str, toolset: str, description: str, handler: Callable[[dict], str]):
        with self._lock:
            existing = self._tools.get(name)
            if existing and existing.toolset != toolset:
                raise ValueError(f"Tool {name!r} already registered in toolset {existing.toolset!r}")
            self._tools[name] = ToolEntry(name, toolset, description, handler)

    def dispatch(self, name: str, args: dict) -> str:
        entry = self._tools.get(name)
        if not entry:
            return json.dumps({"error": f"Unknown tool: {name}"})
        try:
            return entry.handler(args)
        except Exception as exc:  # pragma: no cover - demo safety path
            return json.dumps({"error": f"Tool execution failed: {type(exc).__name__}: {exc}"})

    def visible_tools(self, enabled_toolsets: set[str]) -> list[ToolEntry]:
        return sorted(
            [entry for entry in self._tools.values() if entry.toolset in enabled_toolsets],
            key=lambda item: (item.toolset, item.name),
        )

    def clear(self):
        with self._lock:
            self._tools.clear()


registry = ToolRegistry()


def _is_registry_register_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and isinstance(node.value.func.value, ast.Name)
        and node.value.func.value.id == "registry"
        and node.value.func.attr == "register"
    )


def module_registers_tools(module_path: Path) -> bool:
    """Return True only for modules with a top-level `registry.register(...)` call."""
    try:
        tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    except (OSError, SyntaxError):
        return False
    return any(_is_registry_register_call(stmt) for stmt in tree.body)


def discover_builtin_tools(tools_dir: Path) -> list[str]:
    """Import only self-registering tool modules from a directory."""
    imported: list[str] = []
    for module_path in sorted(tools_dir.glob("*.py")):
        if module_path.name.startswith("_") or module_path.name == "__init__.py":
            continue
        if not module_registers_tools(module_path):
            continue
        module_name = f"demo_tool_{module_path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        imported.append(module_path.stem)
    return imported


def sample_tools_dir() -> Path:
    return Path(__file__).resolve().parent / "sample_tools"


def reset_and_discover() -> list[str]:
    registry.clear()
    return discover_builtin_tools(sample_tools_dir())
