name: Build Blossom

on:
  workflow_dispatch:
  push:
    tags:
      - "v*"

jobs:
  build:
    runs-on: windows-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v5

      - name: Set up Python
        uses: actions/setup-python@v6
        with:
          python-version: "3.12"

      - name: Find project files
        shell: pwsh
        run: |
          Write-Host "Repository files:"
          Get-ChildItem "$env:GITHUB_WORKSPACE" -Recurse -File |
            Select-Object FullName

      - name: Find Blossom.py
        shell: pwsh
        run: |
          $source = Get-ChildItem `
            -Path "$env:GITHUB_WORKSPACE" `
            -Recurse `
            -File `
            -Filter "Blossom.py" |
            Select-Object -First 1

          if (-not $source) {
            Write-Error "Blossom.py was not found."
            exit 1
          }

          Write-Host "Found:"
          Write-Host $source.FullName

      - name: Install dependencies
        shell: pwsh
        run: |
          python -m pip install --upgrade pip
          python -m pip install pymem requests PyQt6 pyinstaller

      - name: Verify pymem
        shell: pwsh
        run: |
          python -c "import pymem; print('pymem OK:', pymem.__file__)"

      - name: Build Blossom
        shell: pwsh
        run: |
          $source = Get-ChildItem `
            -Path "$env:GITHUB_WORKSPACE" `
            -Recurse `
            -File `
            -Filter "Blossom.py" |
            Select-Object -First 1

          $icon = Join-Path $source.Directory.FullName "assets\blossom.ico"

          Remove-Item "$env:GITHUB_WORKSPACE\build" -Recurse -Force -ErrorAction SilentlyContinue
          Remove-Item "$env:GITHUB_WORKSPACE\dist" -Recurse -Force -ErrorAction SilentlyContinue

          python -m PyInstaller `
            --clean `
            --noconfirm `
            --onefile `
            --windowed `
            --name Blossom `
            --distpath "$env:GITHUB_WORKSPACE\dist" `
            --workpath "$env:GITHUB_WORKSPACE\build" `
            --collect-all pymem `
            --collect-all PyQt6 `
            --icon "$icon" `
            "$source.FullName"

      - name: Verify EXE
        shell: pwsh
        run: |
          $exe = "$env:GITHUB_WORKSPACE\dist\Blossom.exe"

          if (-not (Test-Path $exe)) {
            Write-Error "Blossom.exe was not created."
            exit 1
          }

          Write-Host "Blossom.exe created successfully."
          Get-Item $exe | Select-Object FullName, Length, LastWriteTime

      - name: Upload EXE
        uses: actions/upload-artifact@v4
        with:
          name: Blossom-Windows
          path: dist/Blossom.exe

      - name: Create GitHub Release
        if: startsWith(github.ref, 'refs/tags/v')
        uses: softprops/action-gh-release@v2
        with:
          files: dist/Blossom.exe
          generate_release_notes: true
