#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2023/10/7 17:35
# @Author  : weihang
# @File    : ip_range.py
# @Desc    : IP范围集合处理器

import ipaddress


class IPRangeSet:
    """IP 地址范围集合，支持 IPv4 和 IPv6。

    用于存储和查询 IP 地址是否在指定范围内。

    Attributes:
        ipv4_ranges (list): IPv4 地址范围列表，元素为 (IPv4Address, IPv4Address) 元组
        ipv6_ranges (list): IPv6 地址范围列表，元素为 (IPv6Address, IPv6Address) 元组
    """

    def __init__(self):
        """初始化空的 IP 范围集合。"""
        self.ipv4_ranges = []
        self.ipv6_ranges = []

    def add_range(self, start_ip, end_ip):
        """添加一个 IP 地址范围。

        Args:
            start_ip (str): 起始 IP 地址
            end_ip (str): 结束 IP 地址

        Examples:
            >>> ip_set = IPRangeSet()
            >>> ip_set.add_range("192.168.1.0", "192.168.1.255")
        """
        ip_obj = ipaddress.ip_address(start_ip)
        if isinstance(ip_obj, ipaddress.IPv4Address):
            self.ipv4_ranges.append((ipaddress.IPv4Address(start_ip), ipaddress.IPv4Address(end_ip)))
        else:
            self.ipv6_ranges.append((ipaddress.IPv6Address(start_ip), ipaddress.IPv6Address(end_ip)))

    def contains(self, ip):
        """检查 IP 地址是否在范围内。

        Args:
            ip (str): 要检查的 IP 地址

        Returns:
            bool: True 表示在范围内，False 表示不在范围内

        Examples:
            >>> ip_set = IPRangeSet()
            >>> ip_set.add_range("192.168.1.0", "192.168.1.255")
            >>> ip_set.contains("192.168.1.100")
            True
            >>> ip_set.contains("10.0.0.1")
            False
        """
        ip_obj = ipaddress.ip_address(ip)
        ranges = self.ipv4_ranges if isinstance(ip_obj, ipaddress.IPv4Address) else self.ipv6_ranges
        return any(start <= ip_obj <= end for start, end in ranges)
