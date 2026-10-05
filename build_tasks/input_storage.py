"""Keep immutable input references valid across artifact and workspace disks."""
from pathlib import Path


def link_input(target: Path, source: Path) -> None:
    source=source.resolve(strict=True)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.unlink(missing_ok=True)
    if source.stat().st_dev==target.parent.stat().st_dev:
        target.hardlink_to(source)
    else:
        target.symlink_to(source)
