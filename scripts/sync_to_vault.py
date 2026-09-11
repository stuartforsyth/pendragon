#!/usr/bin/env python3
"""One-way sync: copy this project's rules_corpus/ and the extract-rule skill
out to the Obsidian vault, which holds a read-only mirror.

This project is the source of truth (see rules_corpus/README.md, "Mirrored
elsewhere"). Run this after any corpus/skill change you want reflected in the
vault:

    python3 scripts/sync_to_vault.py            # copy
    python3 scripts/sync_to_vault.py --dry-run   # show what would change

It never deletes a file the vault has that this project doesn't — that's
either vault-side drift (someone edited the mirror directly, which
shouldn't happen — see the README note) or a file this sync doesn't know
about yet. Either way it's surfaced as a warning, not auto-removed, so a
person decides.
"""
from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
VAULT_ROOT = Path(
    "/home/stuart/Documents/notes/MasterNotes/TTRPG/PENDRAGON"
)

# (source dir relative to this project, destination dir under the vault root)
SYNC_DIRS = [
    (HERE / "rules_corpus", VAULT_ROOT / "rules_corpus"),
    (
        HERE / ".claude" / "skills" / "extract-rule",
        VAULT_ROOT.parent.parent / ".claude" / "skills" / "extract-rule",
        # MasterNotes/.claude -> ~/code/claudesync/vaults/master-notes/.claude
        # (an existing symlink); writing through it lands in that repo.
    ),
]


def walk_files(root: Path) -> dict[Path, Path]:
    """relative path -> absolute path, for every file under root."""
    return {p.relative_to(root): p for p in root.rglob("*") if p.is_file()}


def sync_dir(src_root: Path, dst_root: Path, dry_run: bool) -> tuple[int, int, list[Path]]:
    src_files = walk_files(src_root)
    dst_root.mkdir(parents=True, exist_ok=True)
    dst_files = walk_files(dst_root)

    added, updated = 0, 0
    vault_only = sorted(set(dst_files) - set(src_files))

    for rel, src_path in sorted(src_files.items()):
        dst_path = dst_root / rel
        if not dst_path.exists():
            added += 1
            action = "add"
        elif not filecmp.cmp(src_path, dst_path, shallow=False):
            updated += 1
            action = "update"
        else:
            continue
        print(f"  {action}: {rel}")
        if not dry_run:
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dst_path)

    return added, updated, vault_only


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                     help="show what would change without writing anything")
    args = ap.parse_args()

    if not VAULT_ROOT.exists():
        print(f"Vault path not found: {VAULT_ROOT}", file=sys.stderr)
        return 1

    total_added = total_updated = 0
    all_vault_only: list[tuple[Path, Path]] = []

    for src, dst in SYNC_DIRS:
        print(f"\n{src.relative_to(HERE)} -> {dst}")
        added, updated, vault_only = sync_dir(src, dst, args.dry_run)
        total_added += added
        total_updated += updated
        for rel in vault_only:
            all_vault_only.append((dst, rel))
        if not (added or updated):
            print("  (already up to date)")

    print(f"\n{total_added} added, {total_updated} updated"
          f"{' (dry run — nothing written)' if args.dry_run else ''}.")

    if all_vault_only:
        print(f"\n{len(all_vault_only)} file(s) exist in the vault but not "
              "in this project — NOT deleted, investigate:")
        for dst_root, rel in all_vault_only:
            print(f"  {dst_root / rel}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
