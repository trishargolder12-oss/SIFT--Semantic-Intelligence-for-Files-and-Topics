"""Permission checks shared by discovery, previews, and native file actions."""
from __future__ import annotations

import os
import stat
from pathlib import Path


def safe_path(path: str, root: str, available: bool = True) -> bool:
    """Reject every symlink/reparse point, including links inside the approved root."""
    candidate, approved = Path(path), Path(root)
    try:
        if not candidate.is_absolute() or not approved.is_absolute():
            return False
        relative = candidate.relative_to(approved)
        if '..' in relative.parts or approved.resolve(strict=True) != approved:
            return False
        for item in [approved, *[approved.joinpath(*relative.parts[:i]) for i in range(1, len(relative.parts) + 1)]]:
            try:
                info = item.lstat()
            except FileNotFoundError:
                if not available:
                    continue
                return False
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400):
                return False
        if candidate.resolve(strict=available) != candidate:
            return False
        if available:
            if not stat.S_ISREG(candidate.stat().st_mode):
                return False
            # A successful read-only open establishes readability; do not read original content here.
            with candidate.open('rb'):
                pass
        return True
    except (OSError, ValueError, RuntimeError):
        return False


def permitted_file(connection, file_id: int, available: bool = True, current: bool = False):
    row = connection.execute(
        "SELECT f.*,r.path AS root_path,r.state AS root_state,d.title FROM files f "
        "JOIN roots r ON r.id=f.root_id LEFT JOIN documents d ON d.file_id=f.id WHERE f.id=?", (file_id,),
    ).fetchone()
    if not row or row['root_state'] not in ('active', 'paused') or (available and row['status'] != 'indexed'):
        return None
    if not safe_path(row['path'], row['root_path'], available):
        return None
    if current:
        try:
            info = os.stat(row['path'], follow_symlinks=False)
            if info.st_size != row['size'] or info.st_mtime_ns != row['modified_ns']:
                return None
        except OSError:
            return None
    return row
