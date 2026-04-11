#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2026-04-11
# @Author  : weihang
# @File    : log_handler.py
"""
动态切换日志文件的 Handler

该模块提供 DynamicFileHandler 类，支持在运行时动态切换日志输出文件，
实现按用例或按 sheet 拆分日志文件的功能。
"""

import logging
import os


class DynamicFileHandler(logging.Handler):
    """
    动态切换输出文件的日志 Handler

    该 Handler 可以在运行时动态切换输出文件，支持：
    1. 按用例拆分日志：每个用例一个独立的日志文件
    2. 按 sheet 拆分日志：每个 sheet 一个日志文件
    """

    def __init__(self, log_dir="log"):
        """
        初始化 DynamicFileHandler

        Args:
            log_dir: 日志文件存放目录，默认为 "log"
        """
        super().__init__()
        self.log_dir = log_dir
        self.current_handler = None
        self.current_file = None

        # 确保日志目录存在
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

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

        # 创建新的 FileHandler
        self.current_handler = logging.FileHandler(log_file, encoding='utf-8')
        self.current_handler.setLevel(logging.DEBUG)

        # 设置格式（与 common.py 中的格式保持一致）
        formatter = logging.Formatter(
            '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.current_handler.setFormatter(formatter)

        self.current_file = log_file

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
