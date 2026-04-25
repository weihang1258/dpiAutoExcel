#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
日志系统统一配置模块

提供：
- 日志目录配置
- 日志拆分策略配置
- 日志轮转配置
- session_id 生成
"""
import os
import sys
from datetime import datetime

# 日志目录（相对于项目根目录）
LOG_DIR = "log"

# 日志拆分策略
LOG_STRATEGY = {
    # 按 sheet 名称映射策略
    "install": "by_case",      # 按用例拆分
    "upgrade": "by_sheet",     # 按 sheet 拆分
    "log_active": "by_case",
    "log_audit": "by_sheet",
    "log_key": "by_case",
    "pcapdump": "by_case",
    "eu_policy": "by_case",
    "mirrorvlan": "by_case",
    "bzip": "by_case",
    "default": "by_case"       # 默认按用例拆分
}

# 日志轮转配置
LOG_ROTATION = {
    "enabled": True,
    "when": "midnight",        # 每天零点轮转
    "interval": 1,
    "backup_count": 30          # 保留 30 天
}


def get_base_log_dir():
    """获取日志目录的绝对路径

    兼容 PyInstaller exe 和源码运行两种模式。

    Returns:
        str: 日志目录的绝对路径
    """
    if getattr(sys, 'frozen', False):
        # exe 模式：exe 文件所在目录
        base_dir = os.path.dirname(sys.executable)
    else:
        # 源码模式：项目根目录（utils 的上一级）
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, LOG_DIR)


def get_session_id():
    """生成会话 ID

    格式：YYYYMMDDHHMMSS（例如：20260425143025）

    Returns:
        str: 会话 ID
    """
    return datetime.now().strftime('%Y%m%d%H%M%S')


def get_log_strategy(sheet_name):
    """获取指定 sheet 的日志拆分策略

    Args:
        sheet_name: sheet 名称

    Returns:
        str: 策略名称，"by_case" 或 "by_sheet"
    """
    return LOG_STRATEGY.get(sheet_name, LOG_STRATEGY["default"])


def ensure_log_dir():
    """确保日志目录存在

    Returns:
        str: 日志目录路径
    """
    log_dir = get_base_log_dir()
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    return log_dir


def sanitize_case_name(case_name):
    """清理用例名称，移除或替换文件系统不支持的字段

    Args:
        case_name: 原始用例名称

    Returns:
        str: 清理后的用例名称
    """
    import re
    # 替换特殊字符为下划线（包括换行符、制表符等）
    sanitized = re.sub(r'[<>:"/\\|?*\r\n\t]', '_', case_name)
    # 限制文件名长度（Windows 限制 255 字符，留出余量给前缀和后缀）
    if len(sanitized) > 200:
        sanitized = sanitized[:200]
    return sanitized


def build_log_filename(session_id, sheet_name, case_name=None, strategy=None):
    """构建日志文件名

    Args:
        session_id: 会话 ID
        sheet_name: sheet 名称
        case_name: 用例名称（可选）
        strategy: 拆分策略，默认根据 sheet_name 自动获取

    Returns:
        str: 日志文件名
    """
    if strategy is None:
        strategy = get_log_strategy(sheet_name)

    if strategy == "by_case" and case_name:
        safe_case_name = sanitize_case_name(case_name)
        return f"{session_id}_{sheet_name}_{safe_case_name}.log"
    else:
        return f"{session_id}_{sheet_name}.log"
