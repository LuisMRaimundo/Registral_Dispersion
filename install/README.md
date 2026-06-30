# One-click installers

**Registral_Dispersion** — symbolic-score registral dispersion tool.

You do **not** need to know Python. Run the installer for your system once; then use the launcher in the project folder.

| System | First-time install | After install |
|--------|-------------------|---------------|
| **Windows 10/11** | Double-click `install/windows/INSTALL.bat` | `Launch-Registral-Dispersion.bat` (at repo root; run installer first) |
| **macOS** | Double-click `install/macos/INSTALL.command` (if blocked: right-click → Open) | `Launch-Registral-Dispersion.command` |
| **Linux** | In a terminal: `chmod +x install/linux/install.sh && ./install/linux/install.sh` | `./launch-registral-dispersion.sh` |

Installers will:

1. Find or help install **Python 3.10+**
2. Create a local virtual environment (`.venv`)
3. Install the package and dependencies
4. Create launcher scripts at the repository root

**One-number summary (optional):** use `Summarize-Score.bat` (Windows) or `summarize-score.sh` (macOS/Linux) with `--score yourfile.musicxml`.

See the main [README](../README.md) for research parameters and limitations, and [docs/PARAMETERIZATION_GUIDE.md](../docs/PARAMETERIZATION_GUIDE.md) for advised static vs moving workflows.

Copyright © 2026 Luís Raimundo. See [COPYRIGHT.md](../COPYRIGHT.md).
