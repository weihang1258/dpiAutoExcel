#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2026/4/19
# @Author  : Claude Code
# @File    : constants.py
# @Desc    : 日志消息常量定义

"""
日志消息常量模块

统一管理所有日志消息，便于：
1. 消息格式一致性
2. 国际化支持
3. 消息内容集中管理

使用方式：
    from utils.constants import LogMsg
    logger.info(LogMsg.SHEET_EXECUTED.format(sheet_name="install"))
"""

from enum import Enum


class LogMsg(Enum):
    """日志消息枚举"""

    # =========================================================================
    # 会话相关
    # =========================================================================
    SESSION_START = "会话ID: {session_id}"
    SESSION_END = "测试执行完成"

    # =========================================================================
    # Sheet 执行相关
    # =========================================================================
    SHEET_EXECUTED = "sheet:{sheet_name}，执行耗时：{hours} 小时 {minutes} 分钟"
    SHEET_SKIPPED = "sheet:{sheet_name} 未找到对应的处理器，将直接跳过"
    SHEET_EXECUTE_FAILED = "执行 sheet {sheet_name} 失败: {error}"
    SHEET_LIST_PROCESSING = "处理 Sheet 列表: {sheets}"

    # =========================================================================
    # 报告相关
    # =========================================================================
    REPORT_CLEANUP = "整理报告sheet：{path}"
    REPORT_SHEET_DELETED = "删除 sheet {name} 失败：{error}"
    REPORT_CLEANUP_FAILED = "整理报告 sheet 失败：{error}"
    STATISTICS_START = "统计用例执行情况"
    STATISTICS_SUMMARY = (
        "sheet:{sheet_name}\tcount_exe:{exe}\tcount_pass:{pass_}\t"
        "count_fail:{fail}\tcount_noresult:{noresult}\tsuccess_rate:{rate:.2%}"
    )
    TOTAL_DURATION = "执行总耗时：{hours} 小时 {minutes} 分钟"

    # =========================================================================
    # Excel 相关
    # =========================================================================
    EXCEL_OPEN_FAILED = "打开 Excel 文件失败: {error}"
    EXCEL_SAVE_FAILED = "保存 Excel 文件失败: {error}"
    EXCEL_CLOSE_FAILED = "关闭 Excel 文件失败: {error}"

    # =========================================================================
    # 设备连接相关
    # =========================================================================
    DEVICE_CONNECTING = "正在连接设备: {ip}"
    DEVICE_CONNECTED = "设备连接成功: {ip}"
    DEVICE_CONNECT_FAILED = "设备连接失败: {ip}, 错误: {error}"
    DEVICE_DISCONNECTING = "断开设备连接: {ip}"

    # =========================================================================
    # 用例执行相关
    # =========================================================================
    CASE_START = "开始执行用例: {case_name}"
    CASE_PASS = "用例执行通过: {case_name}"
    CASE_FAILED = "用例执行失败: {case_name}, 原因: {reason}"
    CASE_SKIP = "跳过用例: {case_name}, 原因: {reason}"
    CASE_TIMEOUT = "用例执行超时: {case_name}, 超时时间: {timeout}秒"

    # =========================================================================
    # 版本相关
    # =========================================================================
    VERSION_GET = "获取版本信息: {version}"
    VERSION_NOT_FOUND = "未找到版本: {version}"
    VERSION_COMPARE = "比较版本: {v1} vs {v2}, 结果: {result}"

    # =========================================================================
    # 安装升级相关
    # =========================================================================
    INSTALL_START = "开始安装 DPI 版本: {version}"
    INSTALL_SUCCESS = "DPI 安装成功: {version}"
    INSTALL_FAILED = "DPI 安装失败: {version}, 错误: {error}"
    UPGRADE_START = "开始升级 DPI: {from_version} -> {to_version}"
    UPGRADE_SUCCESS = "DPI 升级成功: {to_version}"
    UPGRADE_FAILED = "DPI 升级失败: {to_version}, 错误: {error}"

    # =========================================================================
    # 模式切换相关
    # =========================================================================
    MODE_SWITCH_START = "开始模式切换: {from_mode} -> {to_mode}"
    MODE_SWITCH_SUCCESS = "模式切换成功: {to_mode}"
    MODE_SWITCH_FAILED = "模式切换失败: {to_mode}, 错误: {error}"
    MODE_SWITCH_SKIP = "模式已是目标模式，跳过切换: {mode}"

    # =========================================================================
    # FTP 下载相关
    # =========================================================================
    FTP_CONNECTING = "正在连接 FTP 服务器: {host}"
    FTP_CONNECTED = "FTP 服务器连接成功: {host}"
    FTP_CONNECT_FAILED = "FTP 服务器连接失败: {host}, 错误: {error}"
    FTP_DOWNLOAD_START = "开始下载文件: {path}"
    FTP_DOWNLOAD_SUCCESS = "文件下载成功: {path}"
    FTP_DOWNLOAD_FAILED = "文件下载失败: {path}, 错误: {error}"

    # =========================================================================
    # 备份恢复相关
    # =========================================================================
    BACKUP_START = "开始备份 DPI"
    BACKUP_SUCCESS = "DPI 备份成功"
    BACKUP_FAILED = "DPI 备份失败: {error}"
    BACKUP_RESTORE_START = "开始恢复 DPI 备份"
    BACKUP_RESTORE_SUCCESS = "DPI 备份恢复成功"
    BACKUP_RESTORE_FAILED = "DPI 备份恢复失败: {error}"
    BACKUP_NOT_FOUND = "未找到匹配的备份: 版本={version}, 模式={mode}"

    # =========================================================================
    # 错误相关
    # =========================================================================
    ERROR_GENERAL = "发生错误: {error}"
    ERROR_UNEXPECTED = "发生意外错误: {error}"
    ERROR_RETRY = "重试操作 ({retry}/{max_retry}): {operation}"

    # =========================================================================
    # 警告相关
    # =========================================================================
    WARNING_CONFIG_MISSING = "配置文件缺失: {path}"
    WARNING_PARAM_INVALID = "无效参数: {param}={value}, 原因: {reason}"
    WARNING_DEPRECATED = "功能已废弃: {feature}, 建议使用: {suggestion}"


class LogLevel:
    """日志级别常量"""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class MsgTemplate:
    """消息模板 - 用于需要动态组装的复杂消息"""

    # 用例分隔符
    CASE_SEPARATOR = "─" * 78
    CASE_SEPARATOR_START = f"\n{CASE_SEPARATOR}\n用例：{{case_name}}\n{CASE_SEPARATOR}\n"
    CASE_SEPARATOR_WITH_LOG = (
        f"\n{CASE_SEPARATOR}\n用例：{{case_name}}\n"
        f"{CASE_SEPARATOR}\n日志文件：{{log_file}}\n"
    )

    # 阶段分隔符
    STAGE_SEPARATOR = "═" * 78
    STAGE_SEPARATOR_START = (
        "\n╔" + STAGE_SEPARATOR + "╗\n"
        "║{stage_name:^" + str(len(STAGE_SEPARATOR)) + "}║\n"
        "╚" + STAGE_SEPARATOR + "╝\n"
    )

    # 统计表格头部
    STATS_TABLE_HEADER = [
        "sheet",
        "执行数量",
        "成功数量",
        "失败数量",
        "未执行数量",
        "成功率",
        "执行时间"
    ]

    # 时间格式
    TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
    DATE_FORMAT = "%Y-%m-%d"
    TIME_ONLY_FORMAT = "%H:%M:%S"
    FILENAME_TIME_FORMAT = "%Y%m%d%H%M%S"


class SheetGroup:
    """Sheet 分组常量"""

    LOG = "日志"
    POLICY = "策略"
    INSTALL = "安装"
    ACTIVE_LOG = "活跃日志"
    AUDIT = "审计"
    OTHER = "其他"


class SheetName:
    """Sheet 名称常量"""

    # 日志类
    ACCESSLOG = "accesslog"
    S_ACCESSLOG = "s_accesslog"
    MONITOR = "monitor"
    FILTER = "filter"
    MIRRORVLAN_LOG = "mirrorvlan_log"
    PCAPDUMP_LOG = "pcapdump_log"
    VPN_BLOCK = "vpn_block"
    VPN_BLOCK_KK = "vpn_block_kk"
    VPN_BLOCK_INNER = "vpn_block_inner"
    DNS_PARSE = "dns_parse"
    FZ_FILTER = "fz_filter"

    # 策略类
    BLOCK = "block"
    FZ_BLOCK = "fz_block"

    # 其他
    MIRRORVLAN = "mirrorvlan"
    PCAPDUMP = "pcapdump"
    BZIP = "bzip"

    # 特殊
    ACTDOMAIN = "actdomain发包"
    AUDIT = "audit"
    INSTALL = "install"

    # 系统配置
    DEVICE_CONFIG = "设备初始化配置"
    CONFIG = "配置"
    IP_SPEC = "IP规范"


class CaseStatus:
    """用例状态常量"""

    NOT_EXECUTED = 0
    PASS = "Pass"
    FAILED = "Failed"
    NO_RESULT = ""


class InstallType:
    """安装类型常量"""

    NEW_INSTALL = "全新安装"
    MODE_SWITCH = "模式切换"
    UPGRADE = "升级"
