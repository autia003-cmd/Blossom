# Blossom

Blossom is a Windows PyQt6 FFlag management application.

## Run from source

Install Python 3.12, then:

```powershell
python -m pip install -r requirements.txt
python Blossom.py
```

## Build the Windows EXE locally

```powershell
python -m pip install -r requirements.txt
python -m pip install pyinstaller
pyinstaller --clean --noconfirm Blossom.spec
```

The executable will be created at:

```text
dist/Blossom.exe
```

## GitHub Actions

The workflow in `.github/workflows/build.yml` builds the Windows executable on every push to `main` and when manually triggered.

To create a GitHub Release, create and push a version tag, for example:

```powershell
git tag v2.0.0
git push origin v2.0.0
```

The workflow attaches `Blossom.exe` to the release automatically.

## Runtime data

Blossom stores its local data under the Windows `%LOCALAPPDATA%\\Blossom` directory.

The executable does not require Python to be installed on the target machine because PyInstaller bundles the Python runtime and application dependencies.
