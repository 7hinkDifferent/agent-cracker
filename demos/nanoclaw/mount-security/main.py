"""
NanoClaw Mount Security Demo

Demonstrates NanoClaw's mount validation system with 5 scenarios:
- Demo 1: Allowlist loading from external config
- Demo 2: Blocked pattern detection (.ssh/.env/credentials)
- Demo 3: Symlink traversal attack detection
- Demo 4: nonMainReadOnly enforcement
- Demo 5: No allowlist -- reject everything

Uses tempfile for test directories. Cleans up after all demos.

Run: uv run python main.py
"""

import json
import os
import tempfile
from pathlib import Path

from security import (
    BLOCKED_PATTERNS,
    AllowedRoot,
    MountAllowlist,
    MountValidationResult,
    clear_cache,
    load_allowlist,
    validate_additional_mounts,
    validate_mount,
)


def icon(result: MountValidationResult) -> str:
    return "ALLOW" if result.allowed else "DENY "


def print_result(path: str, result: MountValidationResult) -> None:
    ro = ""
    if result.allowed:
        ro = " [readonly]" if result.effective_readonly else " [read-write]"
    print(f"  [{icon(result)}] {path}{ro}")
    print(f"          -> {result.reason}")


def section(title: str) -> None:
    print(f"\n{'=' * 64}")
    print(f"  {title}")
    print(f"{'=' * 64}\n")


# ── Demo 1: Allowlist Loading ────────────────────────────────────

def demo_allowlist_loading(tmp: Path) -> MountAllowlist:
    """Demo 1: Load allowlist from an external JSON config file."""
    section("Demo 1: Allowlist Loading (from external config)")

    # Create a mock allowlist file (simulates ~/.config/nanoclaw/mount-allowlist.json)
    config_dir = tmp / "config" / "nanoclaw"
    config_dir.mkdir(parents=True)
    allowlist_path = config_dir / "mount-allowlist.json"

    allowlist_data = {
        "allowedRoots": [
            {
                "path": str(tmp / "projects"),
                "allowReadWrite": True,
                "description": "Development projects",
            },
            {
                "path": str(tmp / "shared-docs"),
                "allowReadWrite": False,
                "description": "Shared documents (read-only)",
            },
        ],
        "blockedPatterns": ["password", "token"],
        "nonMainReadOnly": True,
    }

    allowlist_path.write_text(json.dumps(allowlist_data, indent=2))
    print(f"  Allowlist file: {allowlist_path}")
    print(f"  (Simulates ~/.config/nanoclaw/mount-allowlist.json)\n")

    # Load with caching
    clear_cache()
    al = load_allowlist(str(allowlist_path))
    assert al is not None, "Failed to load allowlist"

    print(f"  Loaded successfully:")
    print(f"    Allowed roots: {len(al.allowed_roots)}")
    for root in al.allowed_roots:
        rw = "read-write" if root.allow_read_write else "read-only"
        print(f"      - {root.path} [{rw}] {root.description}")
    print(f"    Blocked patterns: {len(al.blocked_patterns)} total")
    print(f"      Defaults: {len(BLOCKED_PATTERNS)} (from DEFAULT_BLOCKED_PATTERNS)")
    print(f"      User-added: {[p for p in al.blocked_patterns if p not in BLOCKED_PATTERNS]}")
    print(f"    nonMainReadOnly: {al.non_main_read_only}")

    # Demonstrate caching -- second call returns cached value
    clear_cache()
    al1 = load_allowlist(str(allowlist_path))
    al2 = load_allowlist(str(allowlist_path))
    assert al1 is al2, "Cache should return same object"
    print(f"\n  Cache test: load_allowlist() called twice -> same object: {al1 is al2}")

    return al


# ── Demo 2: Blocked Patterns ────────────────────────────────────

def demo_blocked_patterns(tmp: Path, allowlist: MountAllowlist) -> None:
    """Demo 2: Sensitive paths blocked by pattern matching."""
    section("Demo 2: Blocked Patterns (.ssh / .env / credentials)")

    projects = tmp / "projects"
    projects.mkdir(exist_ok=True)

    # Create test directories that match blocked patterns
    sensitive_dirs = [
        ".ssh",
        ".gnupg",
        ".aws",
        ".docker",
        "credentials",
        ".env",
        "id_rsa",
        ".secret",
    ]

    for name in sensitive_dirs:
        d = projects / name
        d.mkdir(exist_ok=True)

    # Also create a safe directory
    safe_dir = projects / "my-app"
    safe_dir.mkdir(exist_ok=True)

    print("  Testing paths under allowed root (projects/):\n")

    all_paths = [str(projects / name) for name in sensitive_dirs] + [str(safe_dir)]
    for path in all_paths:
        result = validate_mount(path, "test-group", True, allowlist)
        print_result(os.path.basename(path), result)


# ── Demo 3: Symlink Traversal Detection ─────────────────────────

def demo_symlink_attack(tmp: Path, allowlist: MountAllowlist) -> None:
    """Demo 3: Symlink pointing outside allowed root is detected."""
    section("Demo 3: Symlink Traversal Attack Detection")

    projects = tmp / "projects"
    projects.mkdir(exist_ok=True)

    # Create a secret directory OUTSIDE allowed roots
    secrets = tmp / "secrets"
    secrets.mkdir(exist_ok=True)
    secret_file = secrets / "api-keys"
    secret_file.mkdir(exist_ok=True)

    # Create a symlink INSIDE projects/ that points to secrets/
    symlink = projects / "innocent-looking"
    try:
        symlink.symlink_to(secrets / "api-keys")
    except OSError:
        print("  (Skipping symlink test -- OS does not support symlinks)")
        return

    print(f"  Symlink created:")
    print(f"    {symlink}")
    print(f"    -> {symlink.resolve()}")
    print(f"  The symlink is inside projects/ but points outside.\n")

    # Validate the symlink path
    result = validate_mount(str(symlink), "test-group", True, allowlist)
    print_result("projects/innocent-looking (symlink)", result)
    print()

    # For comparison, validate the real target directly
    result_direct = validate_mount(str(secrets / "api-keys"), "test-group", True, allowlist)
    print_result("secrets/api-keys (direct)", result_direct)

    print(f"\n  Key insight: resolve(strict=True) follows symlinks before checking")
    print(f"  allowed roots. The resolved path {symlink.resolve()}")
    print(f"  is NOT under any allowed root, so the mount is rejected.")


# ── Demo 4: nonMainReadOnly Enforcement ──────────────────────────

def demo_non_main_readonly(tmp: Path, allowlist: MountAllowlist) -> None:
    """Demo 4: Non-main groups forced to read-only even on rw roots."""
    section("Demo 4: nonMainReadOnly Enforcement")

    projects = tmp / "projects"
    app_dir = projects / "my-app"
    app_dir.mkdir(parents=True, exist_ok=True)

    mount_path = str(app_dir)

    print(f"  Testing path: {os.path.basename(mount_path)}")
    print(f"  Root allows read-write: True")
    print(f"  nonMainReadOnly: {allowlist.non_main_read_only}\n")

    # Main group -- gets read-write
    result_main = validate_mount(mount_path, "main", is_main=True, allowlist=allowlist)
    print(f"  Main group (is_main=True):")
    print_result("my-app", result_main)

    # Non-main group -- forced read-only
    result_other = validate_mount(mount_path, "dev-team", is_main=False, allowlist=allowlist)
    print(f"\n  Non-main group (is_main=False):")
    print_result("my-app", result_other)

    print(f"\n  Key: projects/ root has allowReadWrite=True,")
    print(f"  but non-main group is forced to read-only by nonMainReadOnly policy.")
    print(f"  Main group: readonly={result_main.effective_readonly}")
    print(f"  Non-main:   readonly={result_other.effective_readonly}")


# ── Demo 5: No Allowlist ─────────────────────────────────────────

def demo_no_allowlist(tmp: Path) -> None:
    """Demo 5: Without allowlist, ALL mounts are rejected."""
    section("Demo 5: No Allowlist -- All Mounts Rejected")

    projects = tmp / "projects"
    safe_dir = projects / "my-app"
    safe_dir.mkdir(parents=True, exist_ok=True)

    test_paths = [
        str(safe_dir),
        str(projects),
        str(tmp),
    ]

    print("  When no allowlist file exists, every mount is blocked:")
    print("  (This is the fail-closed security default)\n")

    # Validate with no allowlist (pass None explicitly)
    for path in test_paths:
        result = validate_mount(path, "any-group", is_main=True, allowlist=None)
        print_result(os.path.basename(path), result)

    # Also test batch validation
    print(f"\n  Batch validation (validate_additional_mounts):")
    clear_cache()
    results = validate_additional_mounts(
        test_paths,
        group_name="test",
        is_main=True,
        allowlist=None,
    )
    print(f"    {len(results)} paths checked, {sum(1 for r in results if r.allowed)} allowed")


# ── Main ──────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 64)
    print("  NanoClaw Mount Security Demo")
    print("  Reproduces mount validation from src/mount-security.ts")
    print("=" * 64)

    with tempfile.TemporaryDirectory(prefix="nanoclaw-mount-demo-") as tmp_str:
        tmp = Path(tmp_str)
        print(f"\n  Temp directory: {tmp}")

        # Demo 1: Load allowlist
        allowlist = demo_allowlist_loading(tmp)

        # Demo 2: Blocked patterns
        demo_blocked_patterns(tmp, allowlist)

        # Demo 3: Symlink traversal
        clear_cache()
        allowlist = demo_reload_allowlist(tmp)
        demo_symlink_attack(tmp, allowlist)

        # Demo 4: nonMainReadOnly
        demo_non_main_readonly(tmp, allowlist)

        # Demo 5: No allowlist
        demo_no_allowlist(tmp)

    # Summary
    section("Summary")
    print("  Mount validation enforces 5 security rules:\n")
    print("    1. No allowlist?          -> Block ALL mounts (fail-closed)")
    print("    2. Under allowed root?    -> Must resolve under a configured root")
    print("    3. Blocked pattern match? -> .ssh/.env/credentials etc. always rejected")
    print("    4. Symlink resolved?      -> Real path checked, not symlink path")
    print("    5. nonMainReadOnly?       -> Non-main groups forced read-only")
    print()
    print("  Key design: allowlist at ~/.config/nanoclaw/mount-allowlist.json")
    print("  is OUTSIDE the project root, so container agents cannot modify it.")
    print()
    print("  Done!")


def demo_reload_allowlist(tmp: Path) -> MountAllowlist:
    """Reload allowlist for demos that need a fresh cache."""
    config_path = tmp / "config" / "nanoclaw" / "mount-allowlist.json"
    al = load_allowlist(str(config_path))
    assert al is not None
    return al


if __name__ == "__main__":
    main()
