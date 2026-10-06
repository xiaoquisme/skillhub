"""Data types for marketplace source fetching and catalog parsing (U2)."""

from dataclasses import dataclass, field
from typing import Optional


class FetchError(Exception):
    """A fetch failed in a reportable way (bad location, git failure, timeout)."""


class ParseError(Exception):
    """A fetched checkout has no usable catalog and cannot be interpreted."""


@dataclass
class SourceSpec:
    """A validated marketplace source location."""

    location: str
    ref: Optional[str] = None


@dataclass
class UpstreamSkill:
    """One skill discovered upstream, normalized across catalog formats."""

    name: str
    description: str
    path: str  # upstream_path: provenance key relative to the checkout root
    plugin: str  # plugin name, or "" for bare-tree skills
    version: Optional[str]
    files: dict[str, bytes] = field(default_factory=dict)  # relative path -> content
    warnings: list[str] = field(default_factory=list)


@dataclass
class ParseResult:
    """Skills and reportable warnings from one checkout parse."""

    skills: list[UpstreamSkill] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
