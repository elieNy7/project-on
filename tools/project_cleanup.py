from __future__ import annotations

import argparse
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _inside_root(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT)
    except ValueError:
        return False
    return True


def _size_bytes(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _cleanup_targets() -> list[Path]:
    targets: list[Path] = []

    pycache_dirs = [path for path in ROOT.rglob("__pycache__") if path.is_dir()]
    targets.extend(pycache_dirs)
    targets.extend(
        path
        for pattern in ("*.pyc", "*.pyo")
        for path in ROOT.rglob(pattern)
        if not any(parent.name == "__pycache__" for parent in path.parents)
    )

    for relative in ("build", "dist", "installer/Output"):
        target = ROOT / relative
        if target.exists():
            targets.append(target)

    data_dir = ROOT / "data"
    if data_dir.exists():
        targets.extend(data_dir.glob("*.bak*"))
        targets.extend(data_dir.glob("*before_*.db"))

    return sorted({target.resolve() for target in targets if target.exists()})


def cleanup(dry_run: bool = False) -> None:
    targets = _cleanup_targets()
    if not targets:
        print("Nothing to clean.")
        return

    bad_targets = [target for target in targets if not _inside_root(target)]
    if bad_targets:
        raise RuntimeError(
            "Refusing to remove paths outside project root: "
            + ", ".join(str(target) for target in bad_targets)
        )

    total_size = sum(_size_bytes(target) for target in targets)
    action = "Would remove" if dry_run else "Removing"
    print(f"{action} {len(targets)} generated/heavy item(s).")
    for target in targets:
        rel = target.relative_to(ROOT)
        print(f" - {rel} ({_size_bytes(target) / 1024 / 1024:.2f} MB)")
        if dry_run:
            continue
        if not target.exists():
            continue
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()

    print(f"{'Would free' if dry_run else 'Freed'} about {total_size / 1024 / 1024:.2f} MB.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean generated Project-On files.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without deleting anything.",
    )
    args = parser.parse_args()
    cleanup(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
