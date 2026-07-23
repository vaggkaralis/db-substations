"""Project-local PyInstaller Kivy hook.

Avoid probing optional providers that this app does not use, which prevents
noisy CRITICAL camera/spelling messages during analysis.
"""

from PyInstaller.utils.hooks import check_requirement

if check_requirement("kivy >= 1.9.1"):
    from kivy.tools.packaging.pyinstaller_hooks import add_dep_paths
    from kivy.tools.packaging.pyinstaller_hooks import datas  # noqa: F401
    from kivy.tools.packaging.pyinstaller_hooks import get_deps_minimal
    from kivy.tools.packaging.pyinstaller_hooks import get_factory_modules
    from kivy.tools.packaging.pyinstaller_hooks import kivy_modules

    add_dep_paths()

    deps = get_deps_minimal(
        camera=None,
        spelling=None,
        video=None,
        exclude_ignored=True,
    )

    hiddenimports = sorted(
        set(kivy_modules + get_factory_modules() + deps["hiddenimports"])
    )
    excludedimports = sorted(set(deps["excludes"]))
    binaries = deps.get("binaries", [])
