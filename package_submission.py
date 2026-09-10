import os
import sys
import zipfile
from pathlib import Path

def create_submission_zip():
    root = Path(r"d:\Voice AI").resolve()
    zip_path = root / "Miles_Hackathon_Submission.zip"
    
    # Remove existing zip if present
    if zip_path.exists():
        zip_path.unlink()
        
    exclude_dirs = {
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".git",
        ".venv",
        "data",
        "test_profile",
        ".vite"
    }
    
    exclude_extensions = {".pyc", ".zip", ".log"}
    exclude_files = {".DS_Store", "Thumbs.db"}
    
    included_count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for folder, dirs, files in os.walk(root):
            # Prune excluded directories in-place
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            
            for f in sorted(files):
                p = Path(folder) / f
                if p.suffix in exclude_extensions or p.name in exclude_files:
                    continue
                if p.resolve() == zip_path.resolve():
                    continue
                    
                arcname = p.relative_to(root)
                zf.write(p, arcname)
                included_count += 1
                
    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print("=" * 60)
    print("  MILES — SUBMISSION PACKAGE CREATED")
    print("=" * 60)
    print(f"  Target File    : {zip_path.name}")
    print(f"  Files Packaged : {included_count}")
    print(f"  Final ZIP Size : {size_mb:.2f} MB")
    print(f"  Status         : {'[PASSED] Under 50 MB limit!' if size_mb < 50 else '[FAILED]'}")
    print("=" * 60)

if __name__ == "__main__":
    create_submission_zip()
