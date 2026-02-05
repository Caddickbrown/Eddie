# Building Eddie

## Windows (standalone .exe)

The recommended way to build a Windows executable is to use **MSYS2** so GTK4, GtkSourceView 5, and PyGObject DLLs are correctly found.

### Prerequisites

1. Install [MSYS2](https://www.msys2.org/) on Windows.
2. Open the **MINGW64** (or UCRT64) shell from the MSYS2 start menu.
3. Install dependencies:

```bash
pacman -S mingw-w64-x86_64-gtk4 mingw-w64-x86_64-gtksourceview5 mingw-w64-x86_64-python-gobject
pip install pyinstaller requests
```

### Build

From the project directory in the MINGW64 shell:

```bash
pyinstaller eddie.spec
```

Output will be in `dist/Eddie/`. Run `dist/Eddie/Eddie.exe` to test. You can zip the `dist/Eddie` folder for distribution; end users do not need MSYS2 or Python installed.

### Optional: installer (NSIS)

To create an installer (e.g. "Eddie Setup.exe"):

1. Install [NSIS](https://nsis.sourceforge.io/) on Windows.
2. After running PyInstaller, use an NSIS script to package `dist/Eddie/` (copy to Program Files, add Start Menu shortcut, uninstaller). See [Quod Libet](https://quodlibet.readthedocs.io/) or [Hello World GTK](https://github.com/zevlee/hello-world-gtk) for examples.

### Troubleshooting

- **"Namespace Gtk not available"** — Build and run from the MSYS2 MINGW64 shell so the correct GTK/PyGObject runtime is used.
- **Missing DLLs** — Ensure all packages are installed via `pacman` in that shell; avoid mixing with a non-MSYS2 Python.
