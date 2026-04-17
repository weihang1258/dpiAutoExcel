# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

dpiAutoExcel is an Excel-driven DPI (Deep Packet Inspection) automated testing framework. Test cases are defined in Excel files, executed against remote DPI devices, and results are written back with color-coded pass/fail status.

## Common Commands

```bash
# Run a test Excel file
python main.py -f 用例_移动.xlsx

# Run specific sheet
python main.py -f 用例_移动.xlsx -s install

# Generate batch execution scripts
python main.py -bat
python main.py -ps1

# Build Windows executable
pyinstaller main_exe.spec --clean

# Install dependencies
pip install -r requirements.txt
```

## Architecture

### Two Communication Modes
The framework supports two ways to communicate with remote DPI devices:
- **Socket** (`socket_linux.py`): Binary protocol with length-prefixed JSON + gzip compression
- **SSH** (`ssh.py`): Standard SSH/SFTP for command execution and file transfer

### Class Hierarchy
```
SocketLinux  (socket_linux.py - base class)
├── Dpi       (dpi.py - DPI device control)
└── CheckDpiStat  (dpistat.py - stat file parsing)

SSHManager/VerificationSsh  (ssh.py - SSH operations)
```

### Data Flow
```
Excel Test Cases → read_write_excel → comm.py → result_deal → Excel Report
                                    ↓
                             SocketLinux/SSH
                                    ↓
                           Remote DPI Device
```

### Key Patterns
- **Excel-driven**: All test case data, config, and results flow through Excel files
- **Socket Protocol**: Uses struct-packed binary protocol with gzip-compressed JSON payloads
- **Dynamic Logging**: `DynamicFileHandler` allows switching log files at runtime for per-case logging
- **Stat Files**: DPI health is checked via `/dev/shm/xsa/*.stat` shared memory files

## Important Modules

| Module | Purpose |
|--------|---------|
| `excel.py` | Excel wrapper with xlwings (read/write with color support) |
| `comm.py` | Test execution: `result_deal()`, `compare_exp()`, `pcap_send()` |
| `dpi.py` | DPI lifecycle: start/stop, upgrade, mode-switch, backup |
| `dpiinstall.py` | Installation module called by main.py for sheet "install" |
| `dpistat.py` | Parses `/dev/shm/xsa/*.stat` files for health checks |
| `socket_linux.py` | Binary socket client for remote agent communication |
| `read_write_excel.py` | `parser_excel()` returns dict with config, cases, headers |
| `xml_comparer.py` / `dict_comparer.py` | Compare expected vs actual with ignore/time/length fields |
| `versions.json` | Maps DPI product types to version numbers and FTP URLs |

## Development Notes

- **Windows only**: Uses xlwings which requires Excel and Windows
- **Base directory**: `get_base_dir()` handles both PyInstaller exe and source modes
- **Resource cleanup**: FTP, SSH connections use `__del__` for cleanup
- **NTP sync**: `ntpget()` syncs remote DPI time before tests
- **Binary protocol**: Messages are `<length><gzip(json)>` format, response is plain JSON
