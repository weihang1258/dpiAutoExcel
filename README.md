# dpiAutoExcel - DPI 自动化测试框架

## 项目概述

dpiAutoExcel 是一款基于 Excel 驱动的 DPI（Deep Packet Inspection，深度包检测）自动化测试框架。通过读取 Excel 测试用例文件，自动连接远程 DPI 设备执行测试，并支持回写测试结果。

## 核心功能

- **Excel 驱动测试**：使用 Excel 文件管理测试用例，支持多 Sheet 并行/串行执行
- **远程设备控制**：支持 SSH 和 Socket 两种方式连接 DPI 设备
- **流量回放**：支持 Scapy 和 tcpreplay 两种方式进行 pcap 流量回放
- **结果比对**：支持 XML 和字典两种格式的期望值与实际值比对
- **版本管理**：通过 FTP 自动下载和升级 DPI 版本
- **状态监控**：实时监控 DPI 各项统计指标
- **RDM 集成**：从 RDM 平台提取发布路径信息

## 项目结构

```
dpiAutoExcel/
├── main.py                      # 主入口程序
├── main_exe.spec                # PyInstaller 打包配置
├── requirements.txt              # Python 依赖
├── versions.json                 # DPI 版本配置
│
├── business/                     # 主业务逻辑
│   ├── install.py               # DPI 安装/升级流程
│   ├── pcapdump.py              # PCAP 抓包测试
│   ├── eu_policy.py             # EU 策略测试
│   ├── mirrorvlan.py            # 镜像 VLAN 测试
│   ├── log_active.py            # 日志激活测试
│   ├── log_audit.py             # 日志审计测试
│   ├── log_key.py               # 关键日志测试
│   └── bzip.py                  # BZIP 压缩测试
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
│   ├── tcpdump.py               # tcpdump 工具封装
│   ├── hengwei.py               # 恒威设备相关
│   ├── webvisit.py              # Web 访问工具
│   └── dpi_constants.py         # DPI 常量定义
│
├── io_handler/                   # 文件 I/O 处理
│   ├── excel.py                 # Excel 操作封装（xlwings）
│   └── ftp_client.py            # FTP 客户端
│
├── monitor/                      # 状态监控
│   ├── dpistat.py               # DPI 状态解析
│   └── tcpdump.py               # tcpdump 监控
│
├── protocol/                      # 协议处理
│   └── pcap_analyzer.py         # PCAP 分析和比对
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
│   ├── ip_range.py              # IP 范围处理
│   ├── dpi_helper.py            # DPI 辅助函数
│   ├── crypto_helper.py         # 加密辅助函数
│   ├── marex_helper.py          # Marex 策略辅助函数
│   ├── log_parser.py            # 日志解析器
│   ├── xml_helper.py            # XML 辅助函数
│   ├── rdm_extractor.py         # RDM 平台发布路径提取
│   └── constants.py             # 常量定义
│
├── tests/                        # 测试用例
│   ├── test_main_config.py     # 主配置测试
│   └── test_constants.py       # 常量测试
│
├── log/                          # 日志目录（运行时生成）
├── out/                          # 输出目录（运行时生成）
└── temp_files/                   # 临时文件（运行时生成）
```

## 常用命令

```bash
# 执行指定 Excel 文件的所有用例
python main.py -f 用例_移动.xlsx

# 执行指定 Excel 文件的特定 Sheet
python main.py -f 用例_移动.xlsx -s install

# 生成 PowerShell 执行脚本
python main.py -ps1

# 生成 BAT 执行脚本
python main.py -bat

# PyInstaller 打包
pyinstaller main_exe.spec --clean
```

## 主要模块说明

### 1. business/install.py - DPI 安装升级模块

负责 DPI 设备的软件安装和升级流程。

**关键函数**：
```python
install(p_excel, sheets, path, newpath, session_id)
```

### 2. core/excel_reader.py - Excel 解析器

解析 Excel 测试用例文件，提取配置和测试用例。

**返回数据结构**：
```python
{
    'config': {...},                    # 全局配置
    'sheet_name2cases': {...},          # 每个 sheet 的用例
    'sheet_name2head2col': {...},      # 表头到列索引映射
    'config_dev': {...}                # 设备配置
}
```

### 3. device/dpi.py - DPI 设备控制类

继承自 `SocketLinux`，提供 DPI 设备的完整控制能力。

**关键方法**：
```python
class Dpi(SocketLinux):
    def start()              # 启动 DPI
    def stop()               # 停止 DPI
    def restart()            # 重启 DPI
    def mod_switch(mod)      # 模式切换
    def upms_install(...)     # 升级安装
    def dpibak()             # 配置备份
```

### 4. device/socket_linux.py - Socket 通信客户端

基于自定义二进制协议的远程 Linux 服务器通信客户端。

**协议格式**：`[4字节长度前缀][JSON载荷][gzip压缩数据]`

**关键方法**：
```python
class SocketLinux:
    def cmd(command, cwd=None)           # 执行远程命令
    def get(remote_path, local_path)     # 下载文件
    def put(local_path, remote_path)    # 上传文件
    def scapy_send(pcap_path)          # 发送 pcap 包
```

### 5. io_handler/excel.py - Excel 操作封装

基于 xlwings 的 Excel 操作封装。

### 6. monitor/dpistat.py - DPI 状态解析

解析 DPI 共享内存统计文件（`/dev/shm/xsa/*.stat`）。

### 7. protocol/pcap_analyzer.py - PCAP 分析工具

PCAP 文件分析和比对工具，支持：
- 提取四元组
- 流表转换
- 包内容比对

### 8. utils/rdm_extractor.py - RDM 发布路径提取

从 RDM 平台提取发布路径信息。

**关键函数**：
```python
get_multiple_projects_release_paths(projects, ...)
save_versions_to_json(version_data, category, ...)
```

### 9. utils/common.py - 通用工具函数

**关键函数**：
```python
get_base_dir()                           # 获取程序基准目录（支持 PyInstaller）
setup_logging(log_file_path, logger_name) # 配置日志
gettime(n=4)                             # 获取当前时间
wait_until(func, expect_value, ...)       # 等待条件满足
md5(data)                               # 计算 MD5
```

## 依赖项

```
xlwings>=0.30.0       # Excel 操作
paramiko>=3.0.0       # SSH/SFTP
scapy>=2.5.0          # 流量回放
playwright>=1.40.0    # 浏览器自动化
beautifulsoup4>=4.12.0 # HTML 解析
ntplib>=0.4.0         # NTP 时间同步
```

## Excel 测试用例格式

Excel 文件包含多个 Sheet：
- `install` - 安装/升级用例
- `配置` - 设备配置
- `设备初始化配置` - 初始化参数
- 其他 Sheet - 测试用例

**每个用例 Sheet 包含列**：
- 用例ID - 用例唯一标识
- 执行状态 - 执行结果（自动填写）
- 结果 - Pass/Failed（自动填写）

## 通信协议

### Socket 协议（device/socket_linux.py）

```
[4字节网络字节序长度][JSON载荷][可选:gzip压缩数据]
```

### SSH 协议（device/ssh.py）

基于 Paramiko 的标准 SSH/SFTP 协议。

## 注意事项

1. **Windows only**：使用 xlwings，需要安装 Microsoft Excel
2. **Socket 通信**：需要远程设备运行对应的 Agent 服务
3. **SSH 通信**：需要配置 SSH 密钥或密码认证
4. **Base directory**：`get_base_dir()` 支持 PyInstaller exe 和源码运行两种模式
