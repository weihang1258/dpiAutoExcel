# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## ⚠️ 重要原则：禁止发散生成数据

**在处理代码迁移、数据填充、功能扩展时，必须遵守以下规则：**

1. **只保留原始文件中实际存在的数据** - 如果原始文件没有某个数据，必须先确认来源
2. **禁止"补充"或"完善"数据** - 遇到缺失数据时，不要自己做假设或推断
3. **不确定的数据直接删除** - 不要猜测或"合理推断"缺失的内容
4. **先确认，再行动** - 不清楚的事情必须先问用户或找到确切来源
5. **迁移时保持原样** - 从旧代码迁移到新代码时，只做结构重组，不做内容扩充

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

### Directory Structure
```
business/         # 主业务逻辑 (install, pcapdump, eu_policy, log_*, mirrorvlan, bzip)
core/             # 核心测试逻辑 (excel_reader, result, comparer, pcap, tcpdump)
data/             # 数据比对器 (xml_comparer, dict_comparer)
device/           # 设备通信层 (dpi, socket_linux, ssh, tcpdump, hengwei, webvisit)
io_handler/       # 文件 I/O 处理 (excel, ftp_client)
monitor/           # 状态监控 (dpistat, tcpdump)
protocol/          # 协议处理 (pcap_analyzer)
utils/             # 工具模块 (common, dpi_helper, log_handler, rdm_extractor 等)
```

### Two Communication Modes
The framework supports two ways to communicate with remote DPI devices:
- **Socket** (`device/socket_linux.py`): Binary protocol with length-prefixed JSON + gzip compression
- **SSH** (`device/ssh.py`): Standard SSH/SFTP for command execution and file transfer

### Class Hierarchy
```
SocketLinux  (device/socket_linux.py - base class)
├── Dpi       (device/dpi.py - DPI device control)
└── CheckDpiStat  (monitor/dpistat.py - stat file parsing)

SSHManager/VerificationSsh  (device/ssh.py - SSH operations)
```

### Data Flow
```
Excel Test Cases → core/excel_reader → business/* → core/result → Excel Report
                                         ↓
                                  device/socket_linux or device/ssh
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
| `business/install.py` | DPI 安装/升级流程 |
| `business/pcapdump.py` | PCAP 抓包测试 |
| `business/eu_policy.py` | EU 策略测试 |
| `core/excel_reader.py` | `parser_excel()` 解析 Excel 返回 dict |
| `core/result.py` | `result_deal()` 处理测试结果 |
| `core/comparer.py` | 期望值与实际值比对 |
| `device/dpi.py` | DPI 生命周期管理 |
| `device/socket_linux.py` | 二进制 Socket 通信客户端 |
| `device/ssh.py` | SSH/SFTP 客户端 |
| `io_handler/excel.py` | Excel 封装 (xlwings) |
| `io_handler/ftp_client.py` | FTP 客户端 |
| `monitor/dpistat.py` | 解析 `/dev/shm/xsa/*.stat` 文件 |
| `data/xml_comparer.py` | XML 格式比对 |
| `data/dict_comparer.py` | 字典格式比对 |
| `utils/rdm_extractor.py` | RDM 平台发布路径提取 |
| `utils/common.py` | 通用工具函数 |

## Development Notes

- **Windows only**: Uses xlwings which requires Excel and Windows
- **Base directory**: `get_base_dir()` handles both PyInstaller exe and source modes
- **Resource cleanup**: FTP, SSH connections use `__del__` for cleanup
- **NTP sync**: `ntpget()` syncs remote DPI time before tests
- **Binary protocol**: Messages are `<length><gzip(json)>` format, response is plain JSON
