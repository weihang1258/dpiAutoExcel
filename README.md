# dpiAutoExcel - DPI 自动化测试框架

基于 Excel 驱动的 DPI（深度包检测）自动化测试执行框架。

## 项目概述

dpiAutoExcel 是一个企业级 DPI 设备自动化测试框架，通过 Excel 文件定义测试用例，自动执行测试并生成详细测试报告。框架支持远程 DPI 设备管理、流量重放、状态监控和结果分析。

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        main.py (入口点)                          │
├─────────────────────────────────────────────────────────────────┤
│  Excel 测试用例 ──▶ read_write_excel ──▶ comm.py ──▶ result_deal │
└─────────────────────────────────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
    socket_linux.py    ssh.py        dpi.py
    (Socket 协议)  (SSH)        (DPI 控制)
         │               │               │
         ▼               ▼               ▼
    远程 Linux 服务器 (DPI 设备)
```

## 核心模块

### 1. excel.py
Excel 操作封装类，提供测试数据的读取和结果的写入。

```python
from excel import Excel

xls = Excel("test.xlsx")
# 读取表头
heads = xls.get_head()
# 读取数据
data = xls.read_data()
# 写入结果（带颜色）
xls.write_result(row, col, "Pass", color="green")
```

**主要功能：**
- `head2value()` - 将表头与数据映射为字典
- `optimized_write()` - 批量写入，内存合并优化
- `write_row_values()` - 写入行数据（支持颜色和边框）
- `get_config_from_book()` - 读取配置 sheet

### 2. comm.py
测试执行核心模块，处理测试流程和结果比较。

```python
from comm import result_deal, compare_exp

# 处理测试结果
result_deal(case_name, result, expected, actual)

# 比较期望值与实际值
compare_exp(exp_log, act_log, ignore_fields=["timestamp"])
```

**主要功能：**
- `result_deal()` - 结果写入、去重、颜色标记
- `compare_exp()` - 期望/实际值比较
- `pcap_send()` - Scapy 流量发送
- `tcpreplay()` - Tcpreplay 重放

### 3. dpi.py
DPI 设备控制模块，继承自 SocketLinux。

```python
from dpi import Dpi

dpi = Dpi(("172.31.140.81", 9000))
dpi.start()           # 启动 DPI
dpi.restart()         # 重启 DPI
dpi.mod_switch("proxy") # 模式切换
dpi.upms_install()     # 升级安装
```

**主要功能：**
- `start()/stop()/restart()` - DPI 生命周期管理
- `mod_switch()` - 模式切换（proxy/transparent/bridge）
- `upms_install()` - UPMS 升级
- `dpibak()` - 配置备份
- `modify_xsajson()` - 配置修改
- `marex_policy_update()` - 策略更新
- `clean_stat()` / `wait_flow_timeout()` - 状态管理

### 4. socket_linux.py
基于 Socket 的远程 Linux 操作客户端。

```python
from socket_linux import SocketLinux

sl = SocketLinux(("172.31.140.81", 9000))
result = sl.cmd("ls -la")
sl.putfo(local_file, remote_path)
sl.scapy_send(pcap_file)
```

**主要功能：**
- `cmd()` - 远程命令执行
- `getfo()/putfo()` - 文件传输（gzip 压缩）
- `scapy_send()` - Scapy pcap 重放
- `isdir()/isfile()/mkdir()` - 文件系统操作
- `download_pcap()` - PCAP 下载
- `md5()` - MD5 校验
- `update_systime()` - NTP 时间同步

### 5. ssh.py
基于 SSH 的远程 Linux 操作客户端。

```python
from ssh import SSHManager

ssh = SSHManager(host, port, username, password)
ssh.connect()
ssh.exec_command("ls -la")
ssh.sftp_put(local_file, remote_file)
```

**两种连接方式：**
- `SSHManager` - paramiko exec_command + SFTP
- `VerificationSsh` - 交互式 shell

### 6. dpistat.py
DPI 状态文件解析和健康检查。

```python
from dpistat import CheckDpiStat

stat = CheckDpiStat(("172.31.140.81", 9000))
stat.check_xrt()
stat.check_flow()
stat.check_httpxdr()
stat.health_check()
```

**解析的 stat 文件：**
- xrt.stat - 运行时统计
- flow.stat - 流量统计
- httpxdr.stat - HTTP XDR
- commem.stat - 内存通信
- msgtask.stat - 消息任务
- mirrorvlan.stat - 镜像 VLAN
- pcapdump.stat - PCAP 转储
- xdrtxtlog.stat - XML 日志

### 7. read_write_excel.py
Excel 测试用例解析器。

```python
from read_write_excel import parser_excel, casename2exp_log

p_excel = parser_excel(path="用例.xlsx")
config = p_excel["config"]
sheet_name2cases = p_excel["sheet_name2cases"]
sheet_name2heads = p_excel["sheet_name2heads"]
```

### 8. xml_comparer.py
XML 比较器，支持忽略字段、时间字段、长度字段。

```python
from xml_comparer import XMLComparer

comp = XMLComparer()
result = comp.compare(xml1, xml2, 
                     ignore_fields=["createTime"],
                     time_fields=["timestamp"],
                     time_range=60)
```

### 9. dict_comparer.py
字典深度比较器，支持正则匹配和嵌套结构。

```python
from dict_comparer import DictComparer

comp = DictComparer()
result = comp.compare(exp_dict, act_dict,
                    ignore=["*.timestamp"],
                    length=["data.size"])
```

### 10. ftp.py
FTP 客户端，支持文件上传下载。

```python
from ftp import FTPclient

ftp = FTPclient(host, user, password)
ftp.download(remote_file, local_file)
ftp.upload(local_file, remote_file)
ftp.list_dir(remote_dir)
```

### 11. common.py
通用工具函数模块。

```python
from common import gettime, setup_logging, get_base_dir
from common import wait_until, ntpget, md5

# 时间获取
time_now = gettime(5)  # 20240415123045
date = gettime(6)   # 20240415

# 日志配置
logger = setup_logging("log/app.log", "myapp")

# 基础目录
base_dir = get_base_dir()
```

### 12. log_handler.py
动态日志处理器，支持运行时切换日志文件。

```python
from log_handler import DynamicFileHandler
import logging

handler = DynamicFileHandler()
logger.addHandler(handler)
# 切换日志文件
handler.switch_file("new_log.log")
```

### 13. dpiinstall.py
DPI 安装升级模块。

```python
from dpiinstall import install

install(p_excel=excel_data, sheets=["install"], path=output_file)
```

## 使用方法

### 命令行参数

```bash
# 执行特定 Excel 文件
python main.py -f 用例_移动.xlsx

# 执行指定 sheet
python main.py -f 用例_移动.xlsx -s install

# 生成 BAT 执行脚本
python main.py -bat

# 生成 PowerShell 执行脚本
python main.py -ps1
```

### Excel 测试用例格式

```excel
| 用例名称 | 执行状态 | 期望结果 | 实际结果 | 结果 |
|---------|---------|---------|---------|------|
| test_01 | 1      | PASS    | PASS   | Pass |
```

### 配置 sheet 格式

```excel
| 参数     | 值              |
|----------|----------------|
| DPI_HOST | 172.31.140.81 |
| DPI_PORT | 9000          |
| FTP_HOST | 172.31.128.180|
| FTP_USER | weihang       |
```

## ��赖

```
xlwings>=0.30.0       # Excel 操作
paramiko>=3.0.0       # SSH 连接
sshtunnel>=0.4.0     # SSH 隧道
ntplib>=0.4.0        # NTP 客户端
scapy>=2.5.0         # 数据包处理
playwright>=1.40.0     # Web 自动化
beautifulsoup4>=4.12.0# HTML 解析 ftplib (标准库)          # FTP 客户端
```

## 构建可执行文件

```bash
# 安装 PyInstaller
pip install pyinstaller

# 生成 spec 文件
pyinstaller main_exe.spec

# 构建
pyinstaller main_exe.spec --clean
```

## 日志输出

- `log/common.log` - 通用日志
- `log/ftp.log` - FTP 操作日志
- `log/install.log` - 安装日志
- `report/` - 测试报告输出目录

## 版本管理

`versions.json` 定义了 DPI 产品版本与 FTP 下载路径的映射：

- 信息安全执行单元
- 网络安全执行单元
- 数据安全执行单元

## 测试流程

```
1. 解析 Excel 测试用例
2. 连接 DPI 设备
3. 执行测试用例
4. 比对期望/实际结果
5. 写入测试报告（带颜色标记）
6. 生成统计报告
```

## 注意事项

1. Windows 平台运行（xlwings 依赖）
2. 需要 DPI 设备运行 Socket 代理服务
3. Excel 文件需要 `.xlsx` 格式
4. 测试结果自动标记：绿色=PASS，红色=FAILED

## 项目结构

```
dpiAutoExcel/
├── main.py              # 主入口
├── main_exe.spec       # PyInstaller 配置
├── excel.py            # Excel 封装
├── comm.py             # 测试核心
├── dpi.py              # DPI 控制
├── dpiinstall.py        # 安装模块
├── dpistat.py          # 状态监控
├── socket_linux.py     # Socket 连接
├── ssh.py              # SSH 连接
├── ftp.py              # FTP 客户端
├── linux.py            # Linux 操作
├── read_write_excel.py  # Excel 解析
├── xml_comparer.py     # XML 比较
├── dict_comparer.py    # 字典比较
├── common.py           # 通用工具
├── log_handler.py     # 日志处理
├── versions.json      # 版本配置
└── requirements.txt  # 依赖列表
```

## 许可证

内部使用