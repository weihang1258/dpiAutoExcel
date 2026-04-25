#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2023/9/21 10:14
# @Author  : weihang
# @File    : pcap.py
# @Desc    : PCAP 发包工具函数
"""PCAP 发包工具函数模块。

提供使用 scapy 和 tcpreplay 发送 pcap 包的功能。
"""

import os
from utils.common import setup_logging
from device.socket_linux import SocketLinux

logger = setup_logging(log_file_path="log/pcap.log", logger_name="pcap")


def pcap_send(client, pcaps, uplink_iface, downlink_iface=None, mbps=50,
              uplink_vlan=None, downlink_vlan=None, verbose=None,
              force_ip_src=None, force_ip_dst=None, force_sport=None, force_dport=None,
              force_build_flow=None, enable_pcap_cache=False, pcap_cache_dir="cached_pcaps",
              bufsize=1024):
    """使用 scapy 发送 pcap 包。

    Args:
        client: SocketLinux 客户端或 tuple
        pcaps: pcap 文件列表
        uplink_iface: 上行接口
        downlink_iface: 下行接口
        mbps: 速率(Mbps)，默认 50
        uplink_vlan: 上行 VLAN
        downlink_vlan: 下行 VLAN
        verbose: 详细输出
        force_ip_src: 强制源 IP
        force_ip_dst: 强制目的 IP
        force_sport: 强制源端口
        force_dport: 强制目的端口
        force_build_flow: 强制建流
        enable_pcap_cache: 启用 pcap 缓存
        pcap_cache_dir: pcap 缓存目录
        bufsize: 缓冲区大小
    """
    sl = SocketLinux(client) if type(client) == tuple else client
    dir_remote = "/tmp/pcap_auto"
    if not sl.isdir(dir_remote):
        sl.mkdir(dir_remote)
    # eth修改mtu为2000
    if uplink_iface == downlink_iface:
        sl.mtu(uplink_iface, value=2000)
    elif downlink_iface:
        sl.mtu(downlink_iface, value=2000)
    else:
        sl.mtu(uplink_iface, value=2000)

    pcaps_remote = list()
    for pcap in pcaps:
        # 传包到服务器
        if ":" in pcap or not pcap.startswith("/"):
            name = pcap.rsplit("\\", 1)[1]
            pcap_remote = dir_remote + "/" + name
            logger.info("传包到服务器")
            logger.info("%s --> %s" % (pcap, pcap_remote))
            if not os.path.isfile(pcap):
                raise RuntimeError("缺少包：%s,请检查！" % pcap)
            sl.put(pcap, pcap_remote)
        else:
            pcap_remote = pcap
        pcaps_remote.append(pcap_remote)

    for i in range(len(pcaps_remote)):
        pcap_remote = pcaps_remote[i]
        logger.info(f"发包 {i + 1}/{len(pcaps_remote)}：{pcap_remote}")
    logger.info((sl.scapy_send(pcaps=pcaps_remote, uplink_iface=uplink_iface,
                              downlink_iface=downlink_iface, uplink_vlan=uplink_vlan,
                              downlink_vlan=downlink_vlan, mbps=mbps, verbose=verbose,
                              force_ip_src=force_ip_src, force_ip_dst=force_ip_dst,
                              force_sport=force_sport, force_dport=force_dport,
                              force_build_flow=force_build_flow,
                              enable_pcap_cache=enable_pcap_cache,
                              pcap_cache_dir=pcap_cache_dir, bufsize=bufsize)))
    sl.client.close()


def tcpreplay(ssh, pcaps, eth, M=None, x=None, p=None, splitflag=None):
    """使用 tcpreplay 发送 pcap 包。

    Args:
        ssh: SSHManager 客户端
        pcaps: pcap 文件列表
        eth: 网络接口
        M: 速率 (Mbps)
        x: 倍数
        p: 包速率
        splitflag: 分隔符
    """
    from device.linux import Linux
    linux = Linux(ssh)
    dir_remote = "/tmp/pcap_auto"
    if not linux.exist_path(dir_remote):
        linux.mkdir(dir_remote)
    # eth修改mtu为2000
    linux.mtu(eth, value=2000)
    pcaps_remote = list()
    for pcap in pcaps.split(sep=splitflag):
        # 传包到服务器
        if ":" in pcap or not pcap.startswith("/"):
            name = pcap.rsplit("\\", 1)[1]
            pcap_remote = dir_remote + "/" + name
            logger.info("传包到服务器")
            logger.info("%s --> %s" % (pcap, pcap_remote))
            if not os.path.isfile(pcap):
                raise RuntimeError("缺少包：%s,请检查！" % pcap)
            ssh.check_remote_file(pcap, pcap_remote)
        else:
            pcap_remote = pcap
        pcaps_remote.append(pcap_remote)

    # tcpreplay发包
    cmd = "tcpreplay -i %s" % eth
    if M:
        cmd = f"{cmd} -M {M}"
    if x:
        cmd = f"{cmd} -x {x}"
    if p:
        cmd = f"{cmd} -p {p}"
    for i in range(len(pcaps_remote)):
        pcap_remote = pcaps_remote[i]
        cmd = f"{cmd} {pcap_remote}"
        logger.info(f"发包{i + 1}/{len(pcaps_remote)}：{cmd}")
        logger.info(ssh.ssh_exec_cmd(cmd, path="/tmp").decode("utf-8"))
