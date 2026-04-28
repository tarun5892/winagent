# PyInstaller spec for a single-file Windows winagent.exe
# Build with: pyinstaller winagent.spec
# (the GitHub Actions workflow at .github/workflows/build.yml runs this on
# every push to main and uploads the resulting .exe as a build artifact.)
# ruff: noqa
from PyInstaller.utils.hooks import collect_all

hiddenimports: list[str] = []
datas: list[tuple[str, str]] = []
binaries: list[tuple[str, str]] = []

# google.generativeai pulls a lot of submodules dynamically; collect_all
# ensures none are missed.
for pkg in ("google.generativeai", "google.ai.generativelanguage", "pydantic"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# pyautogui's PIL/mss/win32com/Pillow are picked up automatically, but be
# explicit so headless builds don't drop them.
hiddenimports += [
    "pyautogui",
    "mss",
    "PIL",
    "PIL.Image",
    "win32com",
    "win32com.client",
]

a = Analysis(
    ["winagent/__main__.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="winagent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI app; no terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
