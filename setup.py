from pathlib import Path

ROOT = Path(__file__).parent
EXCLUDED_MODULES = {
    "build_exe",
    "changelog",
    "clear_maintenance_history",
}


def build_setup_kwargs():
    # avoid importing setuptools at module import time — import inside the function
    from setuptools import find_namespace_packages, find_packages

    py_modules = sorted(
        path.stem
        for path in ROOT.glob("*.py")
        if path.stem not in EXCLUDED_MODULES and not path.stem.startswith("test_")
    )
    namespace_packages = find_namespace_packages(
        include=["ui", "ui.*"],
        exclude=["tests", "tests.*", "scripts", "scripts.*", "tools", "tools.*"],
    )
    regular_packages = find_packages(
        include=["dbsubstations", "dbsubstations.*"],
        exclude=["tests", "tests.*", "scripts", "scripts.*", "tools", "tools.*"],
    )
    return {
        "name": "dbsubstations",
        "version": "0.7.0",
        "py_modules": py_modules,
        "packages": sorted(set(namespace_packages + regular_packages)),
        "include_package_data": True,
    }


if __name__ == "__main__":
    # import setup only when the script is executed directly
    from setuptools import setup

    setup(**build_setup_kwargs())
