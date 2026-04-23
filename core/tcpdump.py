#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2023/9/21 10:14
# @Author  : weihang
# @File    : tcpdump.py
# @Desc    : tcpdump工具函数

from utils.common import setup_logging

logger = setup_logging(log_file_path="log/tcpdump.log", logger_name="tcpdump")


def tcpdump_start(ssh, path, eth, extended=""):
    """
    启动tcpdump抓包

    Args:
        ssh: SSHManager客户端
        path: 保存路径
        eth: 网络接口
        extended: 扩展参数
    """
    cmd = "kill -9 `ps -ef|grep tcpdump|grep -v grep|awk '{print $2}'`"
    ssh.ssh_exec_cmd(cmd)
    cmd = "tcpdump -i %s -w %s %s &" % (eth, path, extended)
    ssh.ssh_exec_cmd(cmd)


def tcpdump_stop(ssh):
    """
    停止tcpdump抓包

    Args:
        ssh: SSHManager客户端
    """
    cmd = "kill -9 `ps -ef|grep tcpdump|grep -v grep|awk '{print $2}'`"
    ssh.ssh_exec_cmd(cmd)
