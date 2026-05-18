# dpiAutoExcel

基于 Excel 驱动的 DPI（Deep Packet Inspection）自动化测试框架。通过 Excel 文件定义测试用例，自动连接远程 DPI 设备执行测试，并将结果以颜色标记回写到 Excel 报告中。

## 功能特性

- **Excel 驱动测试** - 在 Excel 中编写测试用例，支持多 Sheet 并行/串行执行
- **DPI 安装/升级** - 自动从 FTP 下载安装包，支持全新安装、版本升级、模式切换
- **版本自动获取** - 集成 RDM 平台，自动获取最新版本发布路径（`versions.json`）
- **日志测试** - 支持 accesslog、s_accesslog、monitor、filter、vpn_block 等多种日志类型
- **策略测试** - EU 策略（block、fz_block）自动化验证
- **流量回放与抓包** - 支持 Scapy 和 tcpreplay 两种 PCAP 回放方式，自动抓包比对
- **镜像 VLAN 测试** - 镜像端口 VLAN 配置验证
- **BZIP 压缩测试** - BZIP/IP 压缩策略测试
- **结果统计报告** - 自动生成带颜色标记的测试报告，包含成功率、执行时间等统计信息
- **批量脚本生成** - 一键生成 BAT / PowerShell 批量执行脚本

## 快速开始

### 环境要求

- Windows 系统（依赖 xlwings，需安装 Microsoft Excel）
- Python 3.8+

### 安装依赖

```bash
pip install -r requirements.txt
```

### 下载最新版本

前往 [Releases](https://github.com/weihang1258/dpiAutoExcel/releases) 页面下载最新可执行文件（免安装 Python 环境）。

## 使用方法

### 基本用法

```bash
# 执行指定 Excel 文件的所有用例
python main.py -f 用例_移动.xlsx

# 执行指定 Excel 文件的特定 Sheet
python main.py -f 用例_移动.xlsx -s install

# 执行指定 Excel 文件的多个 Sheet（逗号分隔）
python main.py -f 用例_移动.xlsx -s install,accesslog
```

### 生成批量执行脚本

根据当前目录下的 Excel 文件自动生成执行脚本：

```bash
# 生成 BAT 脚本（保存到 exec_bat/ 目录）
python main.py -bat

# 生成 PowerShell 脚本（保存到 exec_ps1/ 目录）
python main.py -ps1
```

生成的脚本格式为 `main_exe-{Excel文件名}.bat` 和 `main_exe-{Excel文件名}-{Sheet名}.bat`，双击即可执行。

### 命令行参数

| 参数 | 说明 |
|------|------|
| `-f, --file` | Excel 文件路径，例如 `用例_移动.xlsx` |
| `-s, --sheet` | 指定执行的 Sheet 名称，不指定则执行所有可执行用例 |
| `-bat` | 生成 BAT 批量执行脚本 |
| `-ps1` | 生成 PowerShell 批量执行脚本 |

## Excel 测试用例格式

### 文件结构

Excel 文件包含以下几类 Sheet：

| Sheet 类型 | 说明 |
|------------|------|
| `配置` | 全局配置（设备 IP、账号密码、FTP 路径等） |
| `设备初始化配置` | 设备初始化参数 |
| `IP规范` | IP 地址规范定义 |
| `install` | DPI 安装/升级用例 |
| `accesslog` 等 | 日志类测试用例 |
| `block` / `fz_block` | EU 策略测试用例 |
| `mirrorvlan` | 镜像 VLAN 测试用例 |
| `pcapdump` | PCAP 抓包测试用例 |
| `bzip` | BZIP 压缩测试用例 |

### 配置项说明

在 `配置` Sheet 中定义全局配置，关键配置项：

| 配置项 | 说明 | 示例 |
|--------|------|------|
| `ip` | DPI 设备 IP 地址 | `192.168.1.100` |
| `port` | DPI 设备端口 | `6000` |
| `username` / `password` | 设备登录凭证 | - |
| `dpiversion_s` | 源版本号（升级/切换时） | `1.0.6.0-1` |
| `dpiversion_d` | 目标版本号 | `1.0.6.0-2` |
| `dpimode_s` / `dpimode_d` | 源/目标 DPI 模式 | `ise`、`nse` |
| `target_version` | 自动获取最新版本 | `target_version` |

### 测试结果

执行完成后，程序会在 `report/` 目录下生成测试报告 Excel，包含：

- 每条用例的 **Pass/Failed** 结果（绿色/红色标记）
- **结果统计** Sheet，汇总各 Sheet 的执行数量、成功率、耗时

## 依赖项

| 库 | 用途 |
|----|------|
| xlwings >= 0.30.0 | Excel 操作 |
| paramiko >= 3.0.0 | SSH/SFTP 连接 |
| sshtunnel >= 0.4.0 | SSH 隧道 |
| scapy >= 2.5.0 | 流量回放 |
| ntplib >= 0.4.0 | NTP 时间同步 |
| playwright >= 1.40.0 | 浏览器自动化 |
| beautifulsoup4 >= 4.12.0 | HTML 解析 |

## 打包为 EXE

```bash
pyinstaller main_exe.spec --clean
```

打包后的 `versions.json` 需与 exe 放在同一目录。

## 最新版本

**v1.1.0** - [下载](https://github.com/weihang1258/dpiAutoExcel/releases/tag/v1.1.0)

### 更新日志

- feat: 统一日志系统架构，为各模块添加独立 logger
- feat: 添加项目文档（README.md、CLAUDE.md）
- refactor: 重构项目结构，分离核心模块到独立目录
- refactor: 移动 extract_release_path.py 到 utils/ 目录并重命名
- fix: 修复 IPv6 key 匹配问题和 bzip 日志提取设备选择错误
- fix: 修复多个执行流程和打包配置问题
- fix: 更新 bzip ipsegs 文件路径为 zcip_ipsegs.txt
- chore: 更新 .gitignore，移除运行时目录和敏感文件的 git 追踪
