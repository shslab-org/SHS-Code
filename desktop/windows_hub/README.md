# SHS Code Windows Hub

System tray companion app for SHS Code on Windows.

## Prerequisites

- Python 3.11+
- `pystray` — system tray icon library
- `Pillow` — image handling for tray icons
- `websockets` — WebSocket client for server connection

```bash
pip install pystray Pillow websockets
```

## Usage

```bash
python hub.py
```

### Tray Menu Actions

| Menu Item          | Description                                      |
|--------------------|--------------------------------------------------|
| **Open Chat**      | Opens the SHS Code web chat in your browser      |
| **Start Node**     | Registers this machine as a compute node         |
| **Settings**       | Opens the SHS Code configuration folder          |
| **Exit**           | Closes the tray app and all background tasks      |

## Configuration

The hub reads its connection settings from the environment or a local `.env` file:

| Variable               | Default        | Description                          |
|------------------------|----------------|--------------------------------------|
| `SHSCODE_SERVER_URL` | `ws://localhost:8765` | WebSocket URL of SHS Code server |
| `SHSCODE_API_KEY`    |                | API key for authentication            |
| `SHSCODE_DEVICE_ID`  | `auto`         | Unique device identifier              |

## Building an Executable

Use PyInstaller to create a standalone `.exe`:

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --icon=icon.ico --name SHSCodeHub hub.py
```

The resulting executable will be in `dist/SHSCodeHub.exe`.

## How It Works

1. The hub creates a system tray icon using `pystray`.
2. A background WebSocket client connects to the SHS Code server at `/ws/chat/{device_id}`.
3. Incoming messages trigger tray notifications.
4. Menu items open browser tabs or run local actions.
5. If the WebSocket disconnects, the client automatically reconnects with exponential backoff.
