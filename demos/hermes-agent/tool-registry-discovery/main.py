from __future__ import annotations

"""Run the Hermes tool-registry-discovery demo."""

from tool_registry import registry, reset_and_discover, sample_tools_dir


ENABLED_TOOLSETS = {"file", "terminal"}


def main():
    print("=" * 72)
    print("Hermes Tool Registry Discovery Demo")
    print("=" * 72)
    print(f"Scanning: {sample_tools_dir()}")
    imported = reset_and_discover()
    print(f"Discovered modules: {imported}")

    print("\nVisible tools for toolsets {'file', 'terminal'}:")
    for entry in registry.visible_tools(ENABLED_TOOLSETS):
        print(f"- {entry.toolset:8s} {entry.name:12s} :: {entry.description}")

    print("\nDispatch examples:")
    print("-", registry.dispatch("read_file", {"path": "README.md"}))
    print("-", registry.dispatch("terminal", {"command": "ls"}))
    print("-", registry.dispatch("memory", {"fact": "should be filtered from model visibility"}))

    print("\nObservation:")
    print("helper_only.py 没有被导入，因为 registry.register() 不在模块顶层。")


if __name__ == "__main__":
    main()
