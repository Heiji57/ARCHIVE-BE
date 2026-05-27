# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

This is an early-stage Python backend project (ARCHIVE-BE). The virtual environment uses Python 3.12. No application code or dependencies have been added yet.

## Environment Setup

```powershell
# Activate virtual environment (Windows)
.venv\Scripts\Activate.ps1

# Install dependencies (once a requirements.txt exists)
pip install -r requirements.txt
```

## Running

```powershell
python main.py
```

## Development Notes

- Python 3.12 via `.venv`
- No build system, test framework, or linter is configured yet — add these as the project grows
- Black is the intended formatter (configured in PyCharm)
