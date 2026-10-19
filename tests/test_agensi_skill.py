"""Tests for Agensi.io Agent Skill packaging, frontmatter compliance, and security scan."""

import json
from pathlib import Path
import zipfile

from scripts.package_agensi_skill import (
    SKILL_DIR,
    SKILL_SLUG,
    build_skill_zip,
    run_8_point_security_scan,
    validate_frontmatter,
)


def test_agensi_skill_structure_and_frontmatter():
    """Verify SKILL.md, marketplace.json, and references exist and pass validation."""
    assert SKILL_DIR.exists()
    skill_md = SKILL_DIR / "SKILL.md"
    assert skill_md.exists()

    validate_frontmatter(skill_md)
    files = run_8_point_security_scan(SKILL_DIR)
    rel_names = {f.relative_to(SKILL_DIR).as_posix() for f in files}
    assert "SKILL.md" in rel_names
    assert "marketplace.json" in rel_names
    assert "references/client-configs.md" in rel_names
    assert "references/mcp-tools-reference.md" in rel_names


def test_agensi_marketplace_metadata():
    """Verify marketplace.json contains $9 single-tier pricing and all target agents."""
    marketplace_path = SKILL_DIR / "marketplace.json"
    data = json.loads(marketplace_path.read_text(encoding="utf-8"))

    assert data["skill"]["slug"] == SKILL_SLUG
    assert data["pricing"]["price_usd"] == 9.0
    assert data["pricing"]["tier"] == "Single Developer License"
    assert data["security_compliance"]["agensi_8_point_scan_verified"] is True

    agents = {a["agent"] for a in data["compatibility"]["supported_agents"]}
    assert "Claude Code" in agents
    assert "Cursor" in agents
    assert "GitHub Copilot / VS Code" in agents
    assert "Windsurf" in agents
    assert "OpenAI Codex CLI" in agents
    assert "ChatGPT Desktop & Custom GPT" in agents


def test_agensi_zip_archive_generation():
    """Verify the generated zip file has the expected root folder slug and contents."""
    zip_path = build_skill_zip()
    assert zip_path.exists()

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = set(zf.namelist())
        assert f"{SKILL_SLUG}/SKILL.md" in names
        assert f"{SKILL_SLUG}/marketplace.json" in names
        assert f"{SKILL_SLUG}/references/client-configs.md" in names
        assert f"{SKILL_SLUG}/references/mcp-tools-reference.md" in names
