"""Tests for marketplace git fetch (U2)."""

import shutil
import subprocess
from pathlib import Path

import pytest

from skillhub.marketplace.fetch import (
    FetchError,
    fetch_checkout,
    normalize_location,
)
from skillhub.marketplace.models import SourceSpec

git = shutil.which("git")
needs_git = pytest.mark.skipif(git is None, reason="git not installed")


def make_git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "upstream"
    repo.mkdir()
    (repo / "SKILL.md").write_text("---\nname: s\ndescription: d\n---\nbody\n")
    for cmd in (
        ["init", "-q", "-b", "main"],
        ["add", "."],
        ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
    ):
        subprocess.run(["git", *cmd], cwd=repo, check=True, capture_output=True)
    return repo


def test_normalize_owner_repo_shorthand():
    assert normalize_location("owner/repo") == "https://github.com/owner/repo.git"


def test_normalize_allows_https_ssh_file():
    assert normalize_location("https://example.com/a/b.git") == "https://example.com/a/b.git"
    assert normalize_location("ssh://git@example.com/a/b.git") == "ssh://git@example.com/a/b.git"
    assert normalize_location("file:///srv/repos/x") == "file:///srv/repos/x"


def test_normalize_rejects_bare_directory_path():
    with pytest.raises(FetchError):
        normalize_location("/srv/marketplaces/team")


def test_normalize_rejects_ext_transport():
    with pytest.raises(FetchError):
        normalize_location("ext::sh -c whoami")


def test_normalize_rejects_unknown_scheme():
    with pytest.raises(FetchError):
        normalize_location("ftp://example.com/a.git")


@needs_git
def test_fetch_clones_local_git_repo(tmp_path):
    repo = make_git_repo(tmp_path)
    spec = SourceSpec(location=f"file://{repo}")

    with fetch_checkout(spec) as checkout:
        assert (checkout / "SKILL.md").read_text().startswith("---")


@needs_git
def test_fetch_cleans_up_temp_dir(tmp_path):
    repo = make_git_repo(tmp_path)
    spec = SourceSpec(location=f"file://{repo}")

    with fetch_checkout(spec) as checkout:
        parent = checkout.parent
        assert parent.exists()

    assert not parent.exists()


@needs_git
def test_fetch_with_ref_checks_out_branch(tmp_path):
    repo = make_git_repo(tmp_path)
    subprocess.run(["git", "checkout", "-q", "-b", "feature"], cwd=repo, check=True)
    (repo / "SKILL.md").write_text("---\nname: s\ndescription: d\n---\nfeature\n")
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qam", "f"],
        cwd=repo,
        check=True,
    )
    subprocess.run(["git", "checkout", "-q", "main"], cwd=repo, check=True)
    spec = SourceSpec(location=f"file://{repo}", ref="feature")

    with fetch_checkout(spec) as checkout:
        assert "feature" in (checkout / "SKILL.md").read_text()


def test_ref_option_injection_rejected(tmp_path):
    spec = SourceSpec(location="https://example.com/a.git", ref="--upload-pack=touch /tmp/x")
    with pytest.raises(FetchError):
        with fetch_checkout(spec):
            pass


def test_fetch_failure_raises_fetch_error(tmp_path):
    spec = SourceSpec(location=f"file://{tmp_path}/does-not-exist")
    with pytest.raises(FetchError):
        with fetch_checkout(spec):
            pass
