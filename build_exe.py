"""Build the Windows SubstationManager bundle with PyInstaller."""

from __future__ import annotations

import os
import shutil
import tempfile
import textwrap
import time
from pathlib import Path

# Silence Kivy provider probe logs during PyInstaller analysis.
# These optional providers (camera/spelling/gstreamer) are not used by this app.
os.environ.setdefault("KIVY_NO_CONSOLELOG", "1")
os.environ.setdefault("KIVY_LOG_LEVEL", "error")
os.environ.setdefault("KIVY_NO_ARGS", "1")

import PyInstaller.__main__  # noqa: E402

from settings import DB_FILENAME  # noqa: E402

APP_NAME = "SubstationManager"
COMPANY_NAME = "Hellenic Electricity Distribution Network Operator S.A."
PRODUCT_NAME = "SubstationManager"
FILE_DESCRIPTION = "Substation maintenance management application"
SCRIPT_DIR = Path(__file__).resolve().parent
HOOKS_DIR = SCRIPT_DIR / "hooks"
OUTPUT_PARENT_DIR = Path("C:/")
OUTPUT_DIR = OUTPUT_PARENT_DIR / APP_NAME
VERSION_FILE = SCRIPT_DIR / "VERSION"
DATA_FILES = [
    "database.py",
    "app_settings.default.json",
    "importers.py",
    "popups.py",
    "templates.py",
    "logo_deddie.png",
    "deddie_logo.png",
    "DejaVuSans.ttf",
    "VERSION",
    "elements_import_template.xlsx",
    "επιθεωρήσεις_template.xlsx",
    DB_FILENAME,
]
HIDDEN_IMPORTS = [
    "kivy.core.window.window_sdl2",
    "kivy.core.image.img_sdl2",
    "kivy.core.text.text_sdl2",
    "pandas",
    "openpyxl",
    "sqlite3",
]
EXCLUDED_MODULES = [
    "pytest",
    "_pytest",
    "tests",
    "kivy.tests",
    "pandas.tests",
    "numpy._pytesttester",
    "kivy.core.camera",
    "kivy.core.camera.camera_picamera",
    "kivy.core.camera.camera_gi",
    "kivy.core.camera.camera_opencv",
    "kivy.core.spelling",
    "kivy.core.spelling.spelling_enchant",
    "kivy.lib.gstplayer",
    "kivy.lib.gstplayer._gstplayer",
    "cv2",
    "gi",
    "gi.repository",
    "picamera",
    "enchant",
]


def read_version() -> str:
    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    return version or "1.0.0"


def version_tuple(version: str) -> tuple[int, int, int, int]:
    parts = []
    for value in version.split("."):
        digits = "".join(character for character in value if character.isdigit())
        parts.append(int(digits or "0"))
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts[:4])


def build_version_info_text(version: str) -> str:
    major, minor, patch, build = version_tuple(version)
    return textwrap.dedent(
        f"""
        VSVersionInfo(
          ffi=FixedFileInfo(
            filevers=({major}, {minor}, {patch}, {build}),
            prodvers=({major}, {minor}, {patch}, {build}),
            mask=0x3F,
            flags=0x0,
            OS=0x40004,
            fileType=0x1,
            subtype=0x0,
            date=(0, 0)
          ),
          kids=[
            StringFileInfo([
              StringTable(
                '040904B0',
                [
                  StringStruct('CompanyName', '{COMPANY_NAME}'),
                  StringStruct('FileDescription', '{FILE_DESCRIPTION}'),
                  StringStruct('FileVersion', '{version}'),
                  StringStruct('InternalName', '{APP_NAME}'),
                  StringStruct('OriginalFilename', '{APP_NAME}.exe'),
                  StringStruct('ProductName', '{PRODUCT_NAME}'),
                  StringStruct('ProductVersion', '{version}')
                ]
              )
            ]),
            VarFileInfo([VarStruct('Translation', [1033, 1200])])
          ]
        )
        """
    ).strip()


def build_add_data_args() -> list[str]:
    add_data_args = []
    for file_name in DATA_FILES:
        file_path = SCRIPT_DIR / file_name
        if file_path.exists():
            add_data_args.append(f"--add-data={file_path};.")
    return add_data_args


def build_pyinstaller_args(
    version_info_path: Path,
    staging_parent_dir: Path,
    workpath_dir: Path,
    specpath_dir: Path,
) -> list[str]:
    args = [
        "DBrun.py",
        f"--name={APP_NAME}",
        "--onedir",
        "--windowed",
        "--noconfirm",
        "--clean",
        "--log-level=WARN",
        "--icon=NONE",
        f"--distpath={staging_parent_dir}",
        f"--workpath={workpath_dir}",
        f"--specpath={specpath_dir}",
        f"--additional-hooks-dir={HOOKS_DIR}",
        "--contents-directory=runtime",
        f"--version-file={version_info_path}",
    ]
    args.extend(f"--hidden-import={module_name}" for module_name in HIDDEN_IMPORTS)
    args.extend(f"--exclude-module={module_name}" for module_name in EXCLUDED_MODULES)
    args.extend(build_add_data_args())
    return args


def clean_old_outputs() -> None:
    return None


def remove_path_with_retries(path: Path, attempts: int = 10) -> None:
    if not path.exists():
        return

    last_error = None
    for attempt in range(attempts):
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            return
        except OSError as error:
            last_error = error
            if attempt == attempts - 1:
                break
            time.sleep(0.1 * (attempt + 1))

    raise OSError(f"Failed to remove {path}") from last_error


def replace_path_with_retries(
    source: Path, destination: Path, attempts: int = 10
) -> None:
    last_error = None
    for attempt in range(attempts):
        try:
            os.replace(source, destination)
            return
        except OSError as error:
            last_error = error
            if attempt == attempts - 1:
                break
            time.sleep(0.1 * (attempt + 1))

    raise OSError(f"Failed to replace {destination}") from last_error


def replace_directory(source: Path, destination: Path) -> None:
    temp_destination = destination.with_name(f"{destination.name}.new")
    backup_destination = destination.with_name(f"{destination.name}.old")

    remove_path_with_retries(temp_destination)
    remove_path_with_retries(backup_destination)
    shutil.copytree(source, temp_destination)

    if destination.exists():
        replace_path_with_retries(destination, backup_destination)
    replace_path_with_retries(temp_destination, destination)
    try:
        remove_path_with_retries(backup_destination)
    except OSError:
        pass


def deploy_staged_bundle(staging_dir: Path) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for source in staging_dir.iterdir():
        destination = OUTPUT_DIR / source.name
        if source.is_dir():
            replace_directory(source, destination)
        else:
            if destination.exists():
                remove_path_with_retries(destination)
            shutil.copy2(source, destination)


def run_pyinstaller_with_retries(args: list[str], attempts: int = 4) -> None:
    last_error = None
    for attempt in range(attempts):
        try:
            PyInstaller.__main__.run(args)
            return
        except Exception as error:  # PyInstaller can raise different exception types.
            message = str(error)
            is_permission_issue = isinstance(error, PermissionError) or (
                "PermissionError" in message
                or "[Errno 13]" in message
                or "WinError 32" in message
            )
            if (not is_permission_issue) or attempt == attempts - 1:
                raise
            last_error = error
            time.sleep(1.5 * (attempt + 1))

    if last_error is not None:
        raise last_error


def main() -> None:
    version = read_version()
    clean_old_outputs()

    with tempfile.TemporaryDirectory(prefix="substationmanager-build-") as temp_dir:
        temp_dir_path = Path(temp_dir)
        staging_parent_dir = temp_dir_path / "dist"
        staging_dir = staging_parent_dir / APP_NAME
        workpath_dir = temp_dir_path / "build"
        specpath_dir = temp_dir_path / "spec"
        version_info_path = temp_dir_path / "windows_version_info.txt"
        version_info_path.write_text(
            build_version_info_text(version),
            encoding="utf-8",
        )
        run_pyinstaller_with_retries(
            build_pyinstaller_args(
                version_info_path,
                staging_parent_dir,
                workpath_dir,
                specpath_dir,
            )
        )
        deploy_staged_bundle(staging_dir)

    print(f"Build output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
