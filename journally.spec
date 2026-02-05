# PyInstaller spec for Journally (Windows build from MSYS2)
# Run from MSYS2 MINGW64 shell: pyinstaller Journally.spec
# Requires: pacman -S mingw-w64-x86_64-gtk4 mingw-w64-x86_64-gtksourceview5 mingw-w64-x86_64-python-gobject
#           pip install pyinstaller requests

a = Analysis(
    ['gtk4-ai-editor.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['gi', 'gi.repository.Gtk', 'gi.repository.GtkSource', 'gi.repository.Gio', 'gi.repository.GLib', 'gi.repository.Pango'],
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
    name='Journally',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI app
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
    name='Journally',
)
