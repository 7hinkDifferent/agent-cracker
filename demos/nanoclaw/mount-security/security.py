"""
NanoClaw Mount Security — Reusable Module

Reproduces NanoClaw's mount validation system:
- External allowlist loading with caching
- Blocked pattern matching (16 default patterns)
- Symlink resolution and re-validation
- nonMainReadOnly enforcement for non-main groups

Source: src/mount-security.ts (419 lines)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ── Default blocked patterns (16 patterns from original) ─────────

BLOCKED_PATTERNS: list[str] = [
    ".ssh",
    ".gnupg",
    ".gpg",
    ".aws",
    ".azure",
    ".gcloud",
    ".kube",
    ".docker",
    "credentials",
    ".env",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "id_rsa",
    "id_ed25519",
    "private_key",
    ".secret",
]

DEFAULT_ALLOWLIST_PATH = os.path.expanduser("~/.config/nanoclaw/mount-allowlist.json")


# ── Data classes ──────────────────────────────────────────────────

@dataclass
class AllowedRoot:
    """A directory root under which mounts are permitted."""
    path: str
    allow_read_write: bool = False
    description: str = ""


@dataclass
class MountAllowlist:
    """Security configuration loaded from external JSON file."""
    allowed_roots: list[AllowedRoot] = field(default_factory=list)
    blocked_patterns: list[str] = field(default_factory=list)
    non_main_read_only: bool = True


@dataclass
class MountValidationResult:
    """Result of validating a single mount request."""
    allowed: bool
    reason: str
    real_host_path: Optional[str] = None
    effective_readonly: bool = True


# ── Allowlist loading with cache ──────────────────────────────────

_cached_allowlist: Optional[MountAllowlist] = None
_cache_error: Optional[str] = None


def clear_cache() -> None:
    """Reset the allowlist cache (useful for testing)."""
    global _cached_allowlist, _cache_error
    _cached_allowlist = None
    _cache_error = None


def load_allowlist(path: str = DEFAULT_ALLOWLIST_PATH) -> Optional[MountAllowlist]:
    """
    Load mount allowlist from an external JSON file.
    Results are cached in memory -- subsequent calls return the cached value.
    Returns None if the file is missing or invalid.
    """
    global _cached_allowlist, _cache_error

    if _cached_allowlist is not None:
        return _cached_allowlist
    if _cache_error is not None:
        return None

    try:
        p = Path(path).expanduser()
        if not p.exists():
            _cache_error = f"Allowlist not found at {p}"
            return None

        data = json.loads(p.read_text(encoding="utf-8"))

        # Validate required fields
        if not isinstance(data.get("allowedRoots"), list):
            raise ValueError("allowedRoots must be an array")
        if not isinstance(data.get("blockedPatterns"), list):
            raise ValueError("blockedPatterns must be an array")
        if not isinstance(data.get("nonMainReadOnly"), bool):
            raise ValueError("nonMainReadOnly must be a boolean")

        roots = [
            AllowedRoot(
                path=r["path"],
                allow_read_write=r.get("allowReadWrite", False),
                description=r.get("description", ""),
            )
            for r in data["allowedRoots"]
        ]

        # Merge user patterns with defaults (deduplicated, preserving order)
        merged = list(dict.fromkeys(BLOCKED_PATTERNS + data["blockedPatterns"]))

        allowlist = MountAllowlist(
            allowed_roots=roots,
            blocked_patterns=merged,
            non_main_read_only=data["nonMainReadOnly"],
        )
        _cached_allowlist = allowlist
        return allowlist

    except Exception as e:
        _cache_error = str(e)
        return None


# ── Validation helpers ────────────────────────────────────────────

def _expand_path(p: str) -> str:
    """Expand ~ and resolve to absolute path."""
    return str(Path(p).expanduser().resolve())


def _matches_blocked_pattern(real_path: str, patterns: list[str]) -> Optional[str]:
    """Check if any path component matches a blocked pattern."""
    parts = Path(real_path).parts
    for pattern in patterns:
        # Check each path component
        for part in parts:
            if part == pattern or pattern in part:
                return pattern
        # Also check full path string
        if pattern in real_path:
            return pattern
    return None


def _find_allowed_root(
    real_path: str, roots: list[AllowedRoot],
) -> Optional[AllowedRoot]:
    """Find which allowed root (if any) contains the given path."""
    rp = Path(real_path)
    for root in roots:
        expanded = Path(_expand_path(root.path))
        if not expanded.exists():
            continue
        real_root = expanded.resolve()
        try:
            rp.relative_to(real_root)
            return root
        except ValueError:
            continue
    return None


# ── Core validation ──────────────────────────────────────────────

def validate_mount(
    host_path: str,
    group_name: str,
    is_main: bool,
    allowlist: Optional[MountAllowlist],
) -> MountValidationResult:
    """
    Validate a single mount path against the allowlist.

    Checks (in order):
      1. Allowlist exists? If not, block all.
      2. Path resolves and exists?
      3. Path matches blocked patterns? (on resolved path)
      4. Symlinks resolved and re-checked under allowed root.
      5. nonMainReadOnly enforced for non-main groups.
    """
    # Rule 1: No allowlist -> block everything
    if allowlist is None:
        return MountValidationResult(
            allowed=False,
            reason="No mount allowlist configured -- all additional mounts blocked",
        )

    # Expand and resolve (follows symlinks -- Rule 4)
    expanded = _expand_path(host_path)
    try:
        real_path = str(Path(expanded).resolve(strict=True))
    except (OSError, ValueError):
        return MountValidationResult(
            allowed=False,
            reason=f'Host path does not exist: "{host_path}" (expanded: "{expanded}")',
        )

    # Rule 3: Blocked pattern check (on resolved path)
    blocked = _matches_blocked_pattern(real_path, allowlist.blocked_patterns)
    if blocked is not None:
        return MountValidationResult(
            allowed=False,
            reason=f'Path matches blocked pattern "{blocked}": "{real_path}"',
        )

    # Rule 2+4: Must be under an allowed root (checked against resolved path)
    root = _find_allowed_root(real_path, allowlist.allowed_roots)
    if root is None:
        roots_str = ", ".join(_expand_path(r.path) for r in allowlist.allowed_roots)
        return MountValidationResult(
            allowed=False,
            reason=(
                f'Path "{real_path}" is not under any allowed root. '
                f'Allowed: {roots_str}'
            ),
        )

    # Rule 5: Determine effective readonly
    effective_readonly = True
    if root.allow_read_write:
        if not is_main and allowlist.non_main_read_only:
            effective_readonly = True  # Forced read-only for non-main
        else:
            effective_readonly = False

    desc = f" ({root.description})" if root.description else ""
    return MountValidationResult(
        allowed=True,
        reason=f'Allowed under root "{root.path}"{desc}',
        real_host_path=real_path,
        effective_readonly=effective_readonly,
    )


def validate_additional_mounts(
    mounts: list[str],
    group_name: str,
    is_main: bool,
    allowlist: Optional[MountAllowlist] = None,
) -> list[MountValidationResult]:
    """
    Batch-validate a list of mount paths.
    If allowlist is None, attempts to load from default location.
    """
    if allowlist is None:
        allowlist = load_allowlist()

    return [validate_mount(m, group_name, is_main, allowlist) for m in mounts]
