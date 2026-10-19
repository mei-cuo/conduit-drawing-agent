"""Versioned task playbooks discovered from application-owned SKILL.md files."""

from dataclasses import dataclass

import yaml

from .config import ASSETS


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    triggers: list[str]
    version: str
    body: str


class SkillRegistry:
    def __init__(self, root=None):
        self.skills = {}
        for path in sorted((root or ASSETS / "skills").glob("*/SKILL.md")):
            parts = path.read_text(encoding="utf-8").split("---", 2)
            if len(parts) != 3:
                raise ValueError(f"Skill frontmatter 缺失：{path.name}")
            meta = yaml.safe_load(parts[1])
            skill = Skill(
                meta["name"],
                meta["description"],
                meta.get("triggers", []),
                str(meta["version"]),
                parts[2].strip(),
            )
            if skill.name in self.skills:
                raise ValueError("Skill 名称重复")
            self.skills[skill.name] = skill

    def select(self, text):
        return [s.name for s in self.skills.values() if any(t in text for t in s.triggers)]

    def load(self, name):
        if name not in self.skills:
            raise ValueError("未知 skill")
        skill = self.skills[name]
        return {
            "name": skill.name,
            "version": skill.version,
            "instructions": skill.body,
        }
