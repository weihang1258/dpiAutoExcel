# dpiAutoExcel - DPI 自动化测试框架

## 项目概述

dpiAutoExcel 是一款基于 Excel 驱动的 DPI（Deep Packet Inspection，深度包检测）自动化测试框架。通过读取 Excel 测试用例文件，自动连接远程 DPI 设备执行测试，并支持回写测试结果（通过/失败状态）。

## 核心功能

- **Excel 驱动测试**：使用 Excel 文件管理测试用例，支持多 Sheet 并行/串行执行
- **远程设备控制**：支持 SSH 和 Socket 两种方式连接 DPI 设备
- **流量回放**：支持 Scapy 和 tcpreplay 两种方式进行 pcap 流量回放
- **结果比对**：支持 XML 和字典两种格式的期望值与实际值比对
- **版本管理**：通过 FTP 自动下载和升级 DPI 版本
- **状态监控**：实时监控 DPI 各项统计指标

## 项目结构

```
dpiAutoExcel/
├── main.py                      # 主入口程序
├── main_exe.spec                # PyInstaller 打包配置
├── requirements.txt              # Python 依赖
├── versions.json                 # DPI 版本配置
│
├── business/                     # 主业务逻辑
│   └── install.py               # DPI 安装/升级流程
│
├── core/                         # 核心测试逻辑
│   ├── excel_reader.py          # Excel 解析器
│   ├── result.py                 # 测试结果处理
│   ├── comparer.py               # 测试结果比对
│   ├── pcap.py                   # 流量回放核心
│   └── tcpdump.py               # tcpdump 封装
│
├── device/                       # 设备通信层
│   ├── dpi.py                   # DPI 设备控制类
│   ├── socket_linux.py          # Socket 通信客户端
│   ├── ssh.py                   # SSH/SFTP 客户端
│   ├── hengwei.py               # 恒威设备相关
│   └── webvisit.py              # Web 访问工具
│
├── io_handler/                   # 文件 I/O 处理
│   ├── excel.py                 # Excel 操作封装（xlwings）
│   └── ftp_client.py            # FTP 客户端
│
├── monitor/                      # 状态监控
│   └── dpistat.py               # DPI 状态解析
│
├── protocol/                      # 协议处理
│   └── flow_table.py            # 流表处理
│
├── data/                         # 数据模型
│   ├── xml_comparer.py          # XML 比对器
│   └── dict_comparer.py         # 字典比对器
│
├── utils/                        # 工具模块
│   ├── common.py                # 通用工具函数
│   ├── log_handler.py           # 动态日志处理器
│   ├── gzip_util.py             # Gzip 压缩工具
│   ├── ini_handler.py           # INI 文件处理
│   └── ip_range.py              # IP 范围处理
│
├── log/                          # 日志目录（运行时生成）
├── report/                       # 测试报告目录（运行时生成）
└── exec_ps1/                     # PowerShell 执行脚本（运行时生成）
```

## 模块说明

### 1. business/install.py - DPI 安装升级模块

负责 DPI 设备的软件安装和升级流程。

**主要功能**：
- FTP 连接版本服务器
- 下载 DPI 升级包
- 执行升级前检查（版本验证、配置备份）
- 执行 UPMS 升级
- 升级后验证

**关键函数**：
```python
install(p_excel, sheets, path, newpath, session_id)
```

### 2. core/excel_reader.py - Excel 解析器

解析 Excel 测试用例文件，提取配置和测试用例。

**主要功能**：
- 解析 Excel 配置 sheet
- 提取每个测试用例的数据
- 映射表头与列索引
- 生成设备初始化配置

**关键函数**：
```python
parser_excel(path) -> dict
```

**返回数据结构**：
```python
{
    'config': {...},                    # 全局配置
    'sheet_name2cases': {...},          # 每个 sheet 的用例
    'sheet_name2head2col': {...},      # 表头到列索引映射
    'sheet_name2heads': [...],          # 所有表头列表
    'config_dev': {...}                 # 设备配置
}
```

### 3. core/result.py - 测试结果处理

处理和回写测试结果到 Excel。

**主要功能**：
- 去重测试结果
- 批量写入 Excel
- 根据结果设置单元格颜色（绿色=通过，红色=失败）
- 生成统计摘要

**关键函数**：
```python
result_deal(case_result, row_num, sheet_index, path, workbook, wb)
```

### 4. core/comparer.py - 测试结果比对

对比期望值与实际值，支持多种数据类型。

**主要功能**：
- XML 格式比对
- 字典格式比对
- 支持忽略字段
- 支持时间范围验证
- 支持长度字段验证

**关键函数**：
```python
compare_exp(exp_dict, act_dict, time_fields=None, length_fields=None, ignore_fields=None)
```

### 5. device/dpi.py - DPI 设备控制类

继承自 `SocketLinux`，提供 DPI 设备的完整控制能力。

**主要功能**：
- DPI 生命周期管理（启动/停止/重启）
- 模式切换（IDS/IPS/IDS HA）
- 配置文件管理（JSON）
- 策略管理（eu_policy、pcapdump、mirrorvlan、vpn_block）
- 状态清理和等待
- Agent 管理

**关键方法**：
```python
class Dpi(SocketLinux):
    def start(self)           # 启动 DPI
    def stop(self)            # 停止 DPI
    def restart(self)         # 重启 DPI
    def mod_switch(self, mod) # 模式切换
    def upms_install(self, path, version, config_path)  # 升级安装
    def dpibak(self)          # 配置备份
    def json_get(self, name)  # 获取 JSON 配置
    def json_put(self, name, content)  # 写入 JSON 配置
    def clean_stat(self)     # 清理统计
```

### 6. device/socket_linux.py - Socket 通信客户端

基于自定义二进制协议的远程 Linux 服务器通信客户端。

**协议格式**：
```
[4字节长度前缀][JSON载荷][gzip压缩数据]
```

**主要功能**：
- 远程命令执行
- 文件传输（SFTP 风格，支持 gzip 压缩）
- Scapy pcap 发送
- 系统时间同步（NTP）
- 路由信息获取

**关键方法**：
```python
class SocketLinux:
    def cmd(self, command, cwd=None)  # 执行远程命令
    def get(self, remote_path, local_path)  # 下载文件
    def put(self, local_path, remote_path)  # 上传文件
    def scapy_send(self, pcap_path)  # 发送 pcap 包
    def update_systime(self, settime=None)  # 同步系统时间
    def md5(self, path)  # 计算 MD5
```

### 7. device/ssh.py - SSH/SFTP 客户端

基于 Paramiko 的 SSH 和 SFTP 客户端封装。

**主要功能**：
- SSH 命令执行
- SFTP 文件传输
- SSH 隧道（端口转发）
- 交互式 Shell 支持

**关键类**：
```python
class SSHManager:
    def exec_command(self, command)  # 执行命令
    def put_file(self, local_path, remote_path)  # 上传文件
    def get_file(self, remote_path, local_path)  # 下载文件

class VerificationSsh:
    def shell(self, command)  # 交互式 Shell
```

### 8. io_handler/excel.py - Excel 操作封装

基于 xlwings 的 Excel 操作封装，提供高性能读写能力。

**主要功能**：
- 读取 Excel 数据
- 批量写入（内存合并优化）
- 单元格样式设置（颜色、边框）
- 多 Sheet 管理

**关键方法**：
```python
class Excel:
    def head2value(self, sheet_name, key='用例ID')  # 按 key 分组读取
    def optimized_write(self, sheet, values, start_row)  # 批量写入优化
    def write_range_values(self, sheet_index, value, row1, col1)  # 写入范围值
    def get_config_from_book(self)  # 获取全局配置
```

### 9. io_handler/ftp_client.py - FTP 客户端

FTP/TLS 连接封装，支持安全和非安全两种模式。

**主要功能**：
- FTP_TLS 连接（自动降级到 FTP）
- 文件下载/上传
- 目录列表
- 文件/目录存在性检查

**关键方法**：
```python
class FTPclient:
    def download(self, remotefile, localfile)  # 下载文件
    def upload(self, localfile, remotefile)    # 上传文件
    def list_dir(self, remotedir)              # 列出目录
    def file_exists(self, remotefile) -> bool  # 检查文件是否存在
```

### 10. monitor/dpistat.py - DPI 状态解析

解析 DPI 共享内存统计文件，提供健康检查能力。

**统计文件**：
- `/dev/shm/xsa/xrt.stat` - XRT 统计
- `/dev/shm/xsa/flow.stat` - Flow 统计
- `/dev/shm/xsa/httpxdr.stat` - HTTP XDR 统计
- `/dev/shm/xsa/commem.stat` - 内存统计
- `/dev/shm/xsa/msgtask.stat` - 消息任务统计
- `/dev/shm/xsa/pcapdump.stat` - Pcap Dump 统计

**关键方法**：
```python
class CheckDpiStat(SocketLinux):
    def check_cpu(self) -> list     # CPU 健康检查
    def check_mem(self) -> list     # 内存健康检查
    def check_xrt(self) -> list     # XRT 健康检查
    def check_flow(self) -> list    # Flow 健康检查
```

### 11. data/xml_comparer.py - XML 比对器

将 XML 转换为字典后进行深度比对。

**主要功能**：
- XML 转字典转换
- 支持忽略字段
- 支持时间字段（时间范围内有效）
- 支持长度字段

**关键方法**：
```python
class XMLComparer:
    def compare(self, xml_exp, xml_act) -> dict
```

### 12. data/dict_comparer.py - 字典比对器

深度字典比对，支持正则表达式路径匹配。

**主要功能**：
- 嵌套字典/列表比对
- 正则路径匹配
- 忽略字段支持
- 时间范围验证
- 长度字段验证

### 13. utils/common.py - 通用工具函数

提供日志、时间、列表处理等通用功能。

**关键函数**：
```python
get_base_dir()              # 获取程序基准目录（支持 PyInstaller）
setup_logging(log_file_path, logger_name)  # 配置日志
gettime(n=4)                # 获取当前时间（多种格式）
wait_until(func, expect_value, step, timeout)  # 等待条件满足
md5(data)                   # 计算 MD5
convert_unit_string(s, target_unit)  # 单位换算
```

### 14. utils/log_handler.py - 动态日志处理器

支持运行时动态切换日志输出文件的日志处理器。

**关键类**：
```python
class DynamicFileHandler(logging.Handler):
    def switch_file(self, path)  # 动态切换日志文件
```

## 通信协议

### Socket 协议（SocketLinux）

使用二进制协议进行通信：
```
[4字节网络字节序长度][JSON载荷][可选:gzip压缩数据]
```

**JSON 载荷格式**：
```json
{
    "cmd": "命令",
    "path": "工作目录",
    "data": "数据"
}
```

**支持的命令**：
- `cmd` - 执行 shell 命令
- `get` - 下载文件
- `put` - 上传文件
- `putfo` - 上传文件对象
- `getfo` - 下载文件对象
- `scapy_send` - 发送 pcap
- `md5` - 计算 MD5
- `update_systime` - 同步时间
- `routeinfo` - 路由信息

### SSH 协议（SSHManager）

基于 Paramiko 的标准 SSH/SFTP 协议：
- `exec_command` - 执行单个命令
- `invoke_shell` - 交互式 Shell
- SFTP - 文件传输

## 依赖项

```
xlwings>=0.30.0      # Excel 操作
paramiko>=3.0.0      # SSH/SFTP
sshtunnel>=0.4.0      # SSH 隧道
ntplib>=0.4.0        # NTP 时间同步
scapy>=2.5.0         # 流量回放
playwright>=1.40.0   # 浏览器自动化
beautifulsoup4>=4.12.0  # HTML 解析
```

## 使用方法

### 1. 命令行参数

```bash
# 执行指定 Excel 文件的所有用例
python main.py -f 用例_升级.xlsx

# 执行指定 Excel 文件的特定 Sheet
python main.py -f 用例_升级.xlsx -s install

# 生成 PowerShell 执行脚本
python main.py -ps1

# 生成 BAT 执行脚本
python main.py -bat
```

### 2. Excel 测试用例格式

Excel 文件包含多个 Sheet：
- `install` - 安装/升级用例
- `配置` - 设备配置
- `设备初始化配置` - 初始化参数
- 其他 Sheet - 测试用例

**每个用例 Sheet 包含列**：
- 用例ID - 用例唯一标识
- 用例描述 - 测试说明
- 预期日志 - 期望的输出结果
- 执行状态 - 执行结果（自动填写）
- 结果 - Pass/Failed（自动填写）

### 3. 版本配置 (versions.json)

```json
{
  "信息安全执行单元": {
    "V1.0.5.0": {
      "ftp_path": "ftp://server/path/package.tar.gz",
      "version": "V1.0.5.0"
    }
  }
}
```

## PyInstaller 打包

```bash
pyinstaller main_exe.spec
```

打包后生成 `main_exe.exe`，可独立运行。

## 注意事项

1. **Socket 通信**：需要远程设备运行对应的 Agent 服务
2. **SSH 通信**：需要配置 SSH 密钥或密码认证
3. **xlwings**：需要安装 Microsoft Excel
4. **管理员权限**：部分操作需要 root 权限

## 开发指南

### 添加新的测试类型

1. 在 `core/` 下创建新的测试模块
2. 在 `main.py` 的 `run()` 函数中添加对应的 Sheet 处理逻辑
3. 在 Excel 中添加对应的用例 Sheet

### 添加新的设备支持

1. 在 `device/` 下创建新的设备控制类
2. 继承 `SocketLinux` 或 `SSHManager`
3. 实现设备特定的控制方法

## 许可证

私有项目 - 仅供内部使用
