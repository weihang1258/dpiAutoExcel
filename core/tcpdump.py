#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2023/9/21 10:14
# @Author  : weihang
# @File    : tcpdump.py
# @Desc    : tcpdump 工具函数
"""tcpdump 抓包工具函数模块。

提供远程设备 tcpdump 抓包启动和停止功能。
"""

from utils.common import setup_logging

logger = setup_logging(log_file_path="log/tcpdump.log", logger_name="tcpdump")


def tcpdump_start(ssh, path, eth, extended=""):
    """启动 tcpdump 抓包。

    Args:
        ssh: SSHManager 客户端
        path: 保存路径
        eth: 网络接口
        extended: 扩展参数
    """
    cmd = "kill -9 `ps -ef|grep tcpdump|grep -v grep|awk '{print $2}'`"
    ssh.ssh_exec_cmd(cmd)
    cmd = "tcpdump -i %s -w %s %s &" % (eth, path, extended)
    ssh.ssh_exec_cmd(cmd)


def tcpdump_stop(ssh):
    """停止 tcpdump 抓包。

    Args:
        ssh: SSHManager 客户端
    """
    cmd = "kill -9 `ps -ef|grep tcpdump|grep -v grep|awk '{print $2}'`"
    ssh.ssh_exec_cmd(cmd)
