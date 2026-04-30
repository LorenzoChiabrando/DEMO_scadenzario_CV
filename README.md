# DEMO_scadenzario_CV

## Requirements

You need Python 3.10 or higher and pip, which comes bundled with Python by default.

On Ubuntu / Debian, make sure `python3-venv` is available:
```bash
sudo apt install python3-venv
```

On Windows, download Python from [python.org](https://www.python.org/downloads/) and check **"Add Python to PATH"** during installation. `venv` is already included.

## Quick start

The `scripts/` folder contains launchers that take care of everything automatically. The first time you run them, they set up the virtual environment and install the dependencies. From the second run onwards, they just start the application.

### Linux / macOS

Make the script executable once:
```bash
chmod +x scripts/run.sh
```

Then run it:
```bash
bash scripts/run.sh
```

The first time you will see the installation progress in the terminal. The application opens automatically when it finishes.

### Windows

Open the project folder in File Explorer and double-click `scripts\run.bat`. A terminal window will appear showing the installation progress. The application opens automatically when it finishes.

If Windows shows a security warning, click **"Run anyway"**.

## Manual setup (development)

**Linux / macOS**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Windows (PowerShell)**

If script execution is blocked, run this once:
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Then:
```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**Windows (Command Prompt)**
```cmd
python -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt
```

## Daily use

Activate the virtual environment, then start the application.

**Linux / macOS**
```bash
source venv/bin/activate
python3 main.py
```

**Windows (PowerShell)**
```powershell
venv\Scripts\Activate.ps1
python main.py
```

**Windows (Command Prompt)**
```cmd
venv\Scripts\activate.bat
python main.py
```

When the environment is active, the prompt shows the `(venv)` prefix.

## Deactivate the virtual environment

```bash
deactivate
```

Works on all platforms. The `venv/` folder can be deleted and recreated at any time by repeating the setup steps.
