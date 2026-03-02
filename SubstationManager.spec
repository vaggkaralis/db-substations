# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['DBrun.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Users\\e.karalis\\OneDrive - Hellenic Electricity Distribution Network Operator S.A\\60_Projects\\DB Substations\\database.py', '.'), ('C:\\Users\\e.karalis\\OneDrive - Hellenic Electricity Distribution Network Operator S.A\\60_Projects\\DB Substations\\importers.py', '.'), ('C:\\Users\\e.karalis\\OneDrive - Hellenic Electricity Distribution Network Operator S.A\\60_Projects\\DB Substations\\popups.py', '.'), ('C:\\Users\\e.karalis\\OneDrive - Hellenic Electricity Distribution Network Operator S.A\\60_Projects\\DB Substations\\templates.py', '.'), ('C:\\Users\\e.karalis\\OneDrive - Hellenic Electricity Distribution Network Operator S.A\\60_Projects\\DB Substations\\logo_deddie.png', '.'), ('C:\\Users\\e.karalis\\OneDrive - Hellenic Electricity Distribution Network Operator S.A\\60_Projects\\DB Substations\\DejaVuSans.ttf', '.'), ('C:\\Users\\e.karalis\\OneDrive - Hellenic Electricity Distribution Network Operator S.A\\60_Projects\\DB Substations\\VERSION', '.'), ('C:\\Users\\e.karalis\\OneDrive - Hellenic Electricity Distribution Network Operator S.A\\60_Projects\\DB Substations\\elements_import_template.xlsx', '.'), ('C:\\Users\\e.karalis\\OneDrive - Hellenic Electricity Distribution Network Operator S.A\\60_Projects\\DB Substations\\επιθεωρήσεις_template.xlsx', '.'), ('C:\\Users\\e.karalis\\OneDrive - Hellenic Electricity Distribution Network Operator S.A\\60_Projects\\DB Substations\\substations.db', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SubstationManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SubstationManager',
)
