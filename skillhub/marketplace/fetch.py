"""Git fetch for marketplace sources (U2, KTD1).

Shallow-clones a git location into a temporary directory with a hardened
argv list: ``--`` before the location, scheme allowlist, and the git ``ext::``
transport disabled so a crafted location cannot execute commands on the
server. Callers off the event loop should run ``fetch_checkout`` in a
threadpool (``asyncio.create_subprocess_exec`` alternative is not needed
because git work is bounded by the timeout).
"""

import re
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse

from skillhub.marketplace.models import FetchError, SourceSpec

FETCH_TIMEOUT_SECONDS = 120

_ALLOWED_SCHEMES = {"https", "ssh", "file"}
_GITHUB_SHORTHAND = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SAFE_REF = re.compile(r"^[A-Za-z0-9_./-]+$")


def normalize_location(location: str) -> str:
    """Validate a source location and normalize owner/repo shorthand to a URL."""
    if not location or not location.strip():
        raise FetchError("Empty source location")
    location = location.strip()

    if _GITHUB_SHORTHAND.match(location):
        return f"https://github.com/{location}.git"

    parsed = urlparse(location)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise FetchError(
            f"Unsupported source location scheme {parsed.scheme!r}; "
            "allowed: https, ssh, file"
        )
    return location


def _validate_ref(ref: str) -> None:
    if not _SAFE_REF.match(ref) or ".." in ref or ref.startswith("-"):
        raise FetchError(f"Unsafe source ref {ref!r}")


@contextmanager
def fetch_checkout(spec: SourceSpec) -> Iterator[Path]:
    """Shallow-clone the source; yield the checkout root; always clean up."""
    location = normalize_location(spec.location)
    if spec.ref:
        _validate_ref(spec.ref)

    temp_root = Path(tempfile.mkdtemp(prefix="skillhub-marketplace-"))
    checkout = temp_root / "checkout"
    try:
        cmd = [
            "git",
            "-c", "protocol.ext.allow=never",
            "clone",
            "--depth", "1",
            "--single-branch",
        ]
        if spec.ref:
            cmd += ["--branch", spec.ref]
        cmd += ["--", location, str(checkout)]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=FETCH_TIMEOUT_SECONDS,
            )
        except FileNotFoundError as exc:
            raise FetchError("git is not installed on the server") from exc
        except subprocess.TimeoutExpired as exc:
            raise FetchError(
                f"git clone timed out after {FETCH_TIMEOUT_SECONDS}s"
            ) from exc
        if result.returncode != 0:
            raise FetchError(
                f"git clone failed: {result.stderr.strip() or 'unknown error'}"
            )
        yield checkout
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
