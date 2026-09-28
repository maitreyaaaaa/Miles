from __future__ import annotations

import os
import subprocess
import tempfile
import zipfile
from pathlib import Path

EXCLUDED_DIRS = {
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "data",
    "node_modules",
    "test_profile",
    ".vite",
}
EXCLUDED_SUFFIXES = {".log", ".pyc", ".zip"}


def submission_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    files = []
    for item in result.stdout.decode("utf-8").split("\0"):
        if not item:
            continue

        relative_path = Path(item)
        if EXCLUDED_DIRS.intersection(relative_path.parts):
            continue
        if relative_path.suffix.lower() in EXCLUDED_SUFFIXES:
            continue
        if relative_path.name.lower().startswith(".env") and relative_path.name.lower() != ".env.example":
            continue
        if relative_path.name in {".DS_Store", "Thumbs.db"}:
            continue

        path = root / relative_path
        if path.is_file() and not path.is_symlink():
            files.append(relative_path)
    return sorted(files, key=lambda path: path.as_posix().lower())


def create_submission_zip() -> Path:
    root = Path(__file__).resolve().parent
    zip_path = root / "Miles_Hackathon_Submission.zip"
    files = submission_files(root)
    fd, temp_name = tempfile.mkstemp(prefix=".miles-submission-", suffix=".tmp", dir=root)
    os.close(fd)
    temp_path = Path(temp_name)

    try:
        with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for relative_path in files:
                archive.write(root / relative_path, relative_path.as_posix())
        os.replace(temp_path, zip_path)
    finally:
        temp_path.unlink(missing_ok=True)

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print("=" * 60)
    print("  MILES — SUBMISSION PACKAGE CREATED")
    print("=" * 60)
    print(f"  Target File    : {zip_path.name}")
    print(f"  Files Packaged : {len(files)}")
    print(f"  Final ZIP Size : {size_mb:.2f} MB")
    print(f"  Status         : {'[PASSED] Under 50 MB limit!' if size_mb < 50 else '[FAILED]'}")
    print("=" * 60)
    return zip_path


if __name__ == "__main__":
    create_submission_zip()
