# Registral_Dispersion - Windows installation

**Repository:** https://github.com/LuisMRaimundo/Registral_Dispersion

## Standard installation (no Python required)

1. Download a **fresh** ZIP from GitHub (**Code -> Download ZIP**) or clone the repo.
2. Open **`install\windows`**.
3. Double-click **`INSTALL.bat`** or **`START-HERE.bat`**.
4. Wait for **SUCCESS** or **Done** (first run: **5-15 minutes**).
5. Optionally launch the app when prompted.

## After install

- **GUI:** `Launch-Registral-Dispersion.bat` (project root)
- **CLI summary:** `Summarize-Score.bat --score path\to\score.musicxml`

## Install log

`install.log` in the project root.

## Troubleshooting

| Issue | Action |
|-------|--------|
| No window / closes instantly | Re-download from GitHub; run **`INSTALL.bat`**. Never use `>>>` in batch echo lines. |
| PowerShell parse error | Old copy with Unicode characters; download fresh from GitHub. |
| Python error | Install Python 3.10+ from https://www.python.org/downloads/ with **Add to PATH**, then run **`INSTALL.bat`** again. |
| pip / install failed | Open `install.log`, delete `.venv`, retry. |
