# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## ⚠️ 重要原则：禁止发散生成数据

**在处理代码迁移、数据填充、功能扩展时，必须遵守以下规则：**

1. **只保留原始文件中实际存在的数据** - 如果原始文件没有某个数据，必须先确认来源
2. **禁止"补充"或"完善"数据** - 遇到缺失数据时，不要自己做假设或推断
3. **不确定的数据直接删除** - 不要猜测或"合理推断"缺失的内容
4. **先确认，再行动** - 不清楚的事情必须先问用户或找到确切来源
5. **迁移时保持原样** - 从旧代码迁移到新代码时，只做结构重组，不做内容扩充

**违规示例（禁止）：**
- ❌ "原始文件只有 4 个 action2policyfile 条目，我帮他补充完整"
- ❌ "这个字段看起来像省份代码，我来生成一个映射表"
- ❌ "这个配置可能需要默认值，我先写一个"

**正确做法：**
- ✅ 原始有 4 个条目 → 只保留这 4 个
- ✅ 原始没有某个字段 → 删除或标记为 None
- ✅ 不确定数据来源 → 询问用户确认

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
