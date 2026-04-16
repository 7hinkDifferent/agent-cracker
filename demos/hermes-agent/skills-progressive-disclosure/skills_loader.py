from __future__ import annotations

"""Skills progressive disclosure demo core for Hermes."""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class SkillSummary:
    name: str
    description: str
    path: Path


class SkillStore:
    def __init__(self, root: Path):
        self.root = root

    def list_skills(self) -> list[SkillSummary]:
        summaries: list[SkillSummary] = []
        for skill_dir in sorted(self.root.iterdir()):
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            lines = skill_file.read_text(encoding="utf-8").splitlines()
            description = next((line.removeprefix("description: ") for line in lines if line.startswith("description:")), "")
            summaries.append(SkillSummary(skill_dir.name, description, skill_file))
        return summaries

    def skill_view(self, name: str) -> str:
        return (self.root / name / "SKILL.md").read_text(encoding="utf-8")

    def load_references(self, name: str) -> dict[str, str]:
        refs_dir = self.root / name / "references"
        if not refs_dir.exists():
            return {}
        return {
            path.name: path.read_text(encoding="utf-8")
            for path in sorted(refs_dir.iterdir())
            if path.is_file()
        }
