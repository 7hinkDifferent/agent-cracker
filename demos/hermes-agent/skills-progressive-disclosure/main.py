from __future__ import annotations

from pathlib import Path

from skills_loader import SkillStore


def _chars(text: str) -> int:
    return len(text.replace("\n", ""))



def main():
    root = Path(__file__).resolve().parent / "sample_skills"
    store = SkillStore(root)
    summaries = store.list_skills()

    print("=" * 72)
    print("Hermes Skills Progressive Disclosure Demo")
    print("=" * 72)
    print("目标: 先给模型一个低成本索引，需要时再展开正文与引用。")

    print("\n[Level 0] skills_list()")
    index_chars = 0
    for summary in summaries:
        line = f"- {summary.name}: {summary.description}"
        index_chars += _chars(line)
        print(line)
    print(f"索引载荷约 {index_chars} chars（仅摘要，不读正文）")

    print("\n[Level 1] skill_view('python-workflow')")
    skill_body = store.skill_view("python-workflow")
    print(skill_body)
    print(f"正文载荷约 {_chars(skill_body)} chars")

    print("\n[Level 2] references for 'incident-triage'")
    refs = store.load_references("incident-triage")
    ref_chars = 0
    for name, content in refs.items():
        ref_chars += _chars(content)
        print(f"--- {name} ---")
        print(content)
    print(f"引用载荷约 {ref_chars} chars（只在真正需要模板时才读取）")


if __name__ == "__main__":
    main()
