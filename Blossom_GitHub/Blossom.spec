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
        uses: actions/checkout@v7

      - name: Set up Python
        uses: actions/setup-python@v7
        with:
          python-version: "3.12"

      - name: Show project files
        shell: pwsh
        run: |
          Write-Host "Workspace: $env:GITHUB_WORKSPACE"
          Get-ChildItem -Path $env:GITHUB_WORKSPACE -Recurse -File |
            Select-Object FullName

      - name: Install dependencies
        shell: pwsh
        run: |
          python -m pip install --upgrade pip
          python -m pip install pymem requests PyQt6
          python -m pip install pyinstaller

      - name: Verify pymem
        shell: pwsh
        run: |
          python -c "import pymem; print('pymem loaded from:', pymem.__file__)"

      - name: Check Python syntax
        shell: pwsh
        run: |
          python -m py_compile "$env:GITHUB_WORKSPACE\Blossom.py"

      - name: Build Blossom
        shell: pwsh
        run: |
          Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

          pyinstaller `
            --clean `
            --noconfirm `
            --onefile `
            --windowed `
            --name Blossom `
            --icon "$env:GITHUB_WORKSPACE\assets\blossom.ico" `
            --collect-all pymem `
            --collect-all PyQt6 `
            "$env:GITHUB_WORKSPACE\Blossom.py"

      - name: Verify EXE
        shell: pwsh
        run: |
          $exe = "$env:GITHUB_WORKSPACE\dist\Blossom.exe"

          if (-not (Test-Path $exe)) {
            Write-Error "Blossom.exe was not created."
            exit 1
          }

          Write-Host "Blossom.exe created successfully:"
          Write-Host $exe
          Get-Item $exe | Select-Object FullName, Length, LastWriteTime

      - name: Upload EXE
        uses: actions/upload-artifact@v6
        with:
          name: Blossom-Windows
          path: dist/Blossom.exe

      - name: Create GitHub Release
        if: startsWith(github.ref, 'refs/tags/v')
        uses: softprops/action-gh-release@v2
        with:
          files: dist/Blossom.exe
          generate_release_notes: true
