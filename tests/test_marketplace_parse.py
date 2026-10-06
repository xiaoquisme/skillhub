"""Tests for marketplace catalog parsing (U2)."""

import json
from pathlib import Path

import pytest

from skillhub.marketplace.parse import parse_checkout
from skillhub.marketplace.models import ParseError


def write_skill(root: Path, rel: str, body: str = "# Skill\n") -> Path:
    skill_dir = root / rel
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: {}\ndescription: test skill\n---\n{}".format(
            rel.rstrip("/").split("/")[-1], body
        )
    )
    return skill_dir


def test_claude_catalog_with_relative_plugin_sources(tmp_path):
    catalog = {
        "name": "team-marketplace",
        "owner": {"name": "team"},
        "plugins": [
            {"name": "plugin-a", "source": "./plugins/plugin-a", "version": "1.2.0"},
            {"name": "plugin-b", "source": "./plugins/plugin-b"},
        ],
    }
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "marketplace.json").write_text(json.dumps(catalog))
    write_skill(tmp_path, "plugins/plugin-a/skills/alpha", "alpha body")
    write_skill(tmp_path, "plugins/plugin-b/skills/beta", "beta body")

    result = parse_checkout(tmp_path, revision="rev123456")

    names = {s.name for s in result.skills}
    assert names == {"alpha", "beta"}
    by_name = {s.name: s for s in result.skills}
    assert by_name["alpha"].path == "plugins/plugin-a/skills/alpha"
    assert by_name["alpha"].plugin == "plugin-a"
    assert by_name["alpha"].version == "1.2.0"  # entry version wins
    assert by_name["beta"].version == "rev123456"  # falls back to source revision
    assert b"alpha body" in by_name["alpha"].files["SKILL.md"]
    assert result.warnings == []


def test_codex_catalog_with_local_and_git_subdir_sources(tmp_path):
    catalog = {
        "name": "codex-market",
        "plugins": [
            {
                "name": "local-plugin",
                "source": {"source": "local", "path": "./plugins/local-plugin"},
            },
            {
                "name": "remote-plugin",
                "source": {
                    "source": "git-subdir",
                    "url": "https://example.com/mono.git",
                    "path": "packages/remote-plugin",
                    "ref": "main",
                },
            },
        ],
    }
    (tmp_path / ".agents" / "plugins").mkdir(parents=True)
    (tmp_path / ".agents" / "plugins" / "marketplace.json").write_text(
        json.dumps(catalog)
    )
    write_skill(tmp_path, "plugins/local-plugin/skills/loc", "local skill")

    fetched_root = tmp_path.parent / "fetched"
    write_skill(fetched_root, "packages/remote-plugin/skills/rem", "remote skill")

    def fake_fetch(location, ref=None):
        from contextlib import contextmanager

        @contextmanager
        def _checkout():
            yield fetched_root

        assert location == "https://example.com/mono.git"
        assert ref == "main"
        return _checkout()

    result = parse_checkout(tmp_path, revision="rev1", fetch=fake_fetch)

    names = {s.name for s in result.skills}
    assert names == {"loc", "rem"}
    rem = next(s for s in result.skills if s.name == "rem")
    assert rem.path == "packages/remote-plugin/skills/rem"
    assert rem.plugin == "remote-plugin"


def test_bare_tree_scan(tmp_path):
    write_skill(tmp_path, "skills/one", "one")
    write_skill(tmp_path, ".agents/skills/two", "two")

    result = parse_checkout(tmp_path, revision="rev2")

    names = {s.name for s in result.skills}
    assert names == {"one", "two"}
    one = next(s for s in result.skills if s.name == "one")
    assert one.path == "skills/one"
    assert one.plugin == ""


def test_root_skill_md_single_skill_plugin(tmp_path):
    catalog = {
        "name": "market",
        "owner": {"name": "team"},
        "plugins": [{"name": "solo-plugin", "source": "./plugins/solo-plugin"}],
    }
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "marketplace.json").write_text(json.dumps(catalog))
    plugin_dir = tmp_path / "plugins" / "solo-plugin"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "SKILL.md").write_text(
        "---\nname: solo\ndescription: single skill plugin\n---\nbody\n"
    )

    result = parse_checkout(tmp_path, revision="rev3")

    assert [s.name for s in result.skills] == ["solo"]
    assert result.skills[0].path == "plugins/solo-plugin"


def test_unsupported_sources_skipped_with_warning(tmp_path):
    catalog = {
        "name": "market",
        "owner": {"name": "team"},
        "plugins": [
            {"name": "npm-plugin", "source": {"source": "npm", "package": "x"}},
            {"name": "archive-plugin", "source": {"source": "archive", "url": "https://e/x.zip"}},
            {
                "name": "command-plugin",
                "source": {"source": "command", "command": "make"},
            },
            {"name": "good-plugin", "source": "./plugins/good"},
        ],
    }
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "marketplace.json").write_text(json.dumps(catalog))
    write_skill(tmp_path, "plugins/good/skills/ok", "ok")

    result = parse_checkout(tmp_path, revision="rev4")

    assert [s.name for s in result.skills] == ["ok"]
    assert len(result.warnings) == 3
    assert any("npm-plugin" in w for w in result.warnings)
    assert any("archive-plugin" in w for w in result.warnings)
    assert any("command-plugin" in w for w in result.warnings)


def test_missing_catalog_and_no_skills_raises(tmp_path):
    with pytest.raises(ParseError):
        parse_checkout(tmp_path, revision="rev5")


def test_invalid_manifest_raises_parse_error(tmp_path):
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "marketplace.json").write_text("{not json")

    with pytest.raises(ParseError):
        parse_checkout(tmp_path, revision="rev6")


def test_escaping_plugin_source_path_is_skipped(tmp_path):
    catalog = {
        "name": "market",
        "owner": {"name": "team"},
        "plugins": [
            {"name": "escape", "source": "./../../outside"},
            {"name": "good", "source": "./plugins/good"},
        ],
    }
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "marketplace.json").write_text(json.dumps(catalog))
    write_skill(tmp_path, "plugins/good/skills/ok", "ok")

    result = parse_checkout(tmp_path, revision="rev7")

    assert [s.name for s in result.skills] == ["ok"]
    assert any("escape" in w for w in result.warnings)


def test_unsafe_filename_is_skipped_with_warning(tmp_path):
    catalog = {
        "name": "market",
        "owner": {"name": "team"},
        "plugins": [{"name": "p", "source": "./plugins/p"}],
    }
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "marketplace.json").write_text(json.dumps(catalog))
    skill_dir = write_skill(tmp_path, "plugins/p/skills/s", "body")
    (skill_dir / "bad\\name.txt").write_text("x")

    result = parse_checkout(tmp_path, revision="rev8")

    assert [s.name for s in result.skills] == ["s"]
    assert "bad\\name.txt" not in result.skills[0].files
    assert any("bad" in w for w in result.warnings)


def test_symlinked_skill_files_are_skipped(tmp_path):
    catalog = {
        "name": "market",
        "owner": {"name": "team"},
        "plugins": [{"name": "p", "source": "./plugins/p"}],
    }
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "marketplace.json").write_text(json.dumps(catalog))
    skill_dir = write_skill(tmp_path, "plugins/p/skills/s", "body")
    secret = tmp_path / "secret.txt"
    secret.write_text("server secret")
    (skill_dir / "leak.txt").symlink_to(secret)

    result = parse_checkout(tmp_path, revision="rev9")

    assert [s.name for s in result.skills] == ["s"]
    assert "leak.txt" not in result.skills[0].files
    assert any("leak.txt" in w for w in result.warnings)


def test_version_resolution_prefers_plugin_json(tmp_path):
    catalog = {
        "name": "market",
        "owner": {"name": "team"},
        "plugins": [{"name": "p", "source": "./plugins/p", "version": "entry-version"}],
    }
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "marketplace.json").write_text(json.dumps(catalog))
    plugin_dir = tmp_path / "plugins" / "p"
    write_skill(plugin_dir, "skills/s", "body")
    (plugin_dir / ".claude-plugin").mkdir()
    (plugin_dir / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "p", "version": "manifest-version"})
    )

    result = parse_checkout(tmp_path, revision="rev10")

    assert result.skills[0].version == "manifest-version"
