"""
ExifCraft  ·  build script
Package ExifCraft.pyw into a single-file Windows executable with PyInstaller.

Usage:
    python build.py            # build + zip
    python build.py --zip      # build + zip (default behavior, kept for clarity)
    python build.py --no-zip   # build only, skip the zip bundle

Output:
    dist/ExifCraft.exe
    dist/ExifCraft_vX.Y_win_x64.zip
"""

import os
import sys
import shutil
import zipfile
import subprocess
import argparse

APP_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(APP_DIR)

APP_NAME  = "ExifCraft"
ENTRY     = "ExifCraft.pyw"
ICON      = "ExifCraft.ico"

MIN_PY = (3, 10)   # source uses `X | None` annotations — 3.9 exe would crash at startup


def check_env() -> None:
    """Fail fast with a readable message instead of a PyInstaller traceback."""
    if sys.version_info < MIN_PY:
        raise SystemExit(
            f"[error] Python {MIN_PY[0]}.{MIN_PY[1]}+ required, "
            f"you are running {sys.version.split()[0]}.\n"
            f"        Recreate the venv, e.g.:  py -3.12 -m venv .venv"
        )
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        raise SystemExit(
            "[error] PyInstaller is not installed in this environment.\n"
            "        Fix:  pip install pyinstaller"
        )

# ---- read version from the source file ----------------------------------
def read_version() -> str:
    with open(ENTRY, encoding="utf-8") as fp:
        for line in fp:
            if "APP_VER" in line and "=" in line:
                return line.split("=")[1].strip().strip('\'"')
    raise RuntimeError("APP_VER not found in " + ENTRY)


VERSION = read_version()
EXE_PATH = os.path.join("dist", f"{APP_NAME}.exe")
ZIP_PATH = os.path.join("dist", f"{APP_NAME}_v{VERSION}_win_x64.zip")


def clean() -> None:
    for d in ("build", "dist"):
        shutil.rmtree(d, ignore_errors=True)
    spec = f"{APP_NAME}.spec"
    if os.path.exists(spec):
        os.remove(spec)


def run_pyinstaller() -> None:
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        f"--name={APP_NAME}",
        f"--icon={ICON}",
        # icon for future windows (about dialogs, map picker)
        f"--add-data={ICON};.",
        "--clean",
        "--noconfirm",
        ENTRY,
    ]
    print(">", " ".join(cmd))
    subprocess.run(cmd, check=True)


def make_zip() -> None:
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.write(EXE_PATH, f"{APP_NAME}.exe")
        if os.path.exists("README.md"):
            z.write("README.md", "README.md")
        if os.path.exists("LICENSE"):
            z.write("LICENSE", "LICENSE")
    print(f"[zip] {ZIP_PATH}  ({os.path.getsize(ZIP_PATH) / 1024 / 1024:.1f} MB)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ExifCraft executable")
    parser.add_argument("--no-zip", action="store_true",
                        help="skip creating the zip bundle")
    args = parser.parse_args()

    check_env()
    print(f"[build] {APP_NAME} v{VERSION}")
    clean()
    run_pyinstaller()

    if not os.path.exists(EXE_PATH):
        raise SystemExit(f"[error] expected {EXE_PATH} but it was not produced")

    size_mb = os.path.getsize(EXE_PATH) / 1024 / 1024
    print(f"[ok] {EXE_PATH}  ({size_mb:.1f} MB)")

    if not args.no_zip:
        make_zip()

    print("[done]")


if __name__ == "__main__":
    main()
