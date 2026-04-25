#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2024/10/7
# @Author  : weihang
# @File    : tcpdump.py
"""Tcpdump 抓包模块。

基于 SocketLinux 的 tcpdump 功能，提供远程抓包能力。
"""

import json
import struct
from device.socket_linux import SocketLinux
from utils.common import logger


class Tcpdump(SocketLinux):
    """Tcpdump 抓包类，继承自 SocketLinux。

    提供远程 DPI 设备的 tcpdump 抓包功能。

    Attributes:
        eth: 网卡名称
        path: 远程保存路径
        extended: tcpdump 扩展参数
        single_queue: 是否单队列模式
    """

    def __init__(self, client, eth=None, extended="", tmppath="/home/tmp/tmp.pcap", single_queue=True):
        """初始化 Tcpdump。

        Args:
            client: Socket 连接元组 (host, port)
            eth: 网卡名称
            extended: tcpdump 扩展参数
            tmppath: 远程保存路径
            single_queue: 是否单队列模式
        """
        super().__init__(client)
        self.eth = eth
        self.path = tmppath
        self.extended = extended
        self.single_queue = single_queue

        # 创建目录
        dir = tmppath.rsplit("/", maxsplit=1)[0]
        if not self.isdir(dir=dir):
            self.mkdir(dir=dir)

        if not self.eth:
            self.eth = self.routeinfo().get("0.0.0.0", {}).get("Iface", None)

    def tcpdump_start(self, bufsize=1024):
        """启动 tcpdump 抓包。

        Args:
            bufsize: 缓冲区大小

        Returns:
            str: 抓包结果
        """
        self.tcpdump_stop()
        data = {"eth": self.eth, "path": self.path, "extended": self.extended, "single_queue": self.single_queue}
        logger.info(data)
        msg = struct.pack("i", 5) + json.dumps(obj=data).encode("utf-8")
        msg = struct.pack("i", len(msg)) + msg
        self.client.sendall(msg)
        data = self.client.recv(bufsize)
        data = json.loads(data)
        return data["res"]

    def tcpdump_stop(self, bufsize=1024):
        """停止 tcpdump 抓包。

        Args:
            bufsize: 缓冲区大小

        Returns:
            str: 停止结果
        """
        data = {"path": self.path}
        msg = struct.pack("i", 6) + json.dumps(obj=data).encode("utf-8")
        msg = struct.pack("i", len(msg)) + msg
        self.client.sendall(msg)
        data = self.client.recv(bufsize)
        data = json.loads(data)
        return data["res"]

    def pcap_get(self, locatpath):
        """下载 pcap 文件到本地。

        Args:
            locatpath: 本地保存路径
        """
        logger.info([self.path, locatpath])
        self.get(remotepath=self.path, locatpath=locatpath, gzip=True)

    def pcap_getfo(self):
        """获取 pcap 文件内容。

        Returns:
            文件对象
        """
        return self.getfo(remotepath=self.path, gzip=True)
