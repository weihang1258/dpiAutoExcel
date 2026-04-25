#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2026-04-11
# @Author  : weihang
# @File    : log_handler.py
"""
动态切换日志文件的 Handler

该模块提供 DynamicFileHandler 类，支持在运行时动态切换日志输出文件，
实现按用例或按 sheet 拆分日志文件的功能。

支持特性：
1. 按用例拆分日志：每个用例一个独立的日志文件
2. 按 sheet 拆分日志：每个 sheet 一个日志文件
3. 日志轮转：支持按天/按小时自动轮转
"""

import logging
import os
from logging.handlers import TimedRotatingFileHandler
from utils.common import LOG_FORMAT, LOG_DATE_FORMAT


class DynamicFileHandler(logging.Handler):
    """
    动态切换输出文件的日志 Handler

    该 Handler 可以在运行时动态切换输出文件，支持：
    1. 按用例拆分日志：每个用例一个独立的日志文件
    2. 按 sheet 拆分日志：每个 sheet 一个日志文件
    3. 日志轮转：支持按天/按小时自动轮转
    """

    def __init__(self, log_dir="log", level=logging.DEBUG, rotation=None):
        """
        初始化 DynamicFileHandler

        Args:
            log_dir: 日志文件存放目录，默认为 "log"
            level: 日志级别，默认为 DEBUG
            rotation: 轮转配置，None 或 dict{
                "when": "midnight",   # 轮转时间点
                "interval": 1,        # 轮转间隔
                "backup_count": 30    # 保留历史文件数
            }
        """
        super().__init__()
        self.log_dir = log_dir
        self.level = level
        self.rotation = rotation
        self.current_handler = None
        self.current_file = None

        # 确保日志目录存在
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

    def _create_handler(self, log_file):
        """创建 FileHandler 或 TimedRotatingFileHandler

        Args:
            log_file: 日志文件路径

        Returns:
            logging.FileHandler 或 TimedRotatingFileHandler
        """
        if self.rotation:
            handler = TimedRotatingFileHandler(
                log_file,
                when=self.rotation.get("when", "midnight"),
                interval=self.rotation.get("interval", 1),
                backupCount=self.rotation.get("backup_count", 30),
                encoding='utf-8'
            )
            handler.suffix = "%Y%m%d"
        else:
            handler = logging.FileHandler(log_file, encoding='utf-8', mode='a')

        handler.setLevel(self.level)
        formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
        handler.setFormatter(formatter)
        return handler

    def switch_file(self, log_file):
        """
        切换到新的日志文件

        Args:
            log_file: 日志文件名（相对路径或绝对路径）
        """
        # 如果是相对路径，添加日志目录前缀
        if not os.path.isabs(log_file):
            log_file = os.path.join(self.log_dir, log_file)

        # 如果目标文件与当前文件相同，不切换
        if self.current_file == log_file:
            return

        # 关闭当前 handler（先 flush 避免日志丢失）
        if self.current_handler:
            self.current_handler.flush()
            self.current_handler.close()

        # 创建新的 Handler（支持轮转）
        try:
            self.current_handler = self._create_handler(log_file)
            self.current_file = log_file
        except (IOError, OSError) as e:
            # 降级处理：使用默认日志文件
            error_log_file = os.path.join(self.log_dir, 'error.log')
            try:
                self.current_handler = self._create_handler(error_log_file)
                self.current_file = error_log_file
                # 记录错误（使用临时 handler）
                import sys
                print(f"无法创建日志文件 {log_file}: {e}，使用降级日志文件 {error_log_file}", file=sys.stderr)
            except Exception as fallback_error:
                # 如果连降级日志文件都无法创建，抛出异常
                raise RuntimeError(f"无法创建日志文件 {log_file}，降级日志文件 {error_log_file} 也创建失败: {fallback_error}")

    def emit(self, record):
        """
        发送日志记录到当前文件

        Args:
            record: 日志记录
        """
        if self.current_handler:
            self.current_handler.emit(record)

    def close(self):
        """关闭 Handler，释放资源"""
        if self.current_handler:
            self.current_handler.flush()
            self.current_handler.close()
        super().close()
