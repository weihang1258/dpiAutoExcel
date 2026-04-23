#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2023/10/7 17:35
# @Author  : weihang
# @File    : ip_range.py
# @Desc    : IP范围集合处理器

import ipaddress


class IPRangeSet:
    """IP范围集合，支持IPv4和IPv6"""

    def __init__(self):
        self.ipv4_ranges = []
        self.ipv6_ranges = []

    def add_range(self, start_ip, end_ip):
        """
        添加IP范围

        Args:
            start_ip: 起始IP
            end_ip: 结束IP
        """
        ip_obj = ipaddress.ip_address(start_ip)
        if isinstance(ip_obj, ipaddress.IPv4Address):
            self.ipv4_ranges.append((ipaddress.IPv4Address(start_ip), ipaddress.IPv4Address(end_ip)))
        else:
            self.ipv6_ranges.append((ipaddress.IPv6Address(start_ip), ipaddress.IPv6Address(end_ip)))

    def contains(self, ip):
        """
        检查IP是否在范围内

        Args:
            ip: 要检查的IP地址

        Returns:
            bool: IP是否在范围内
        """
        ip_obj = ipaddress.ip_address(ip)
        ranges = self.ipv4_ranges if isinstance(ip_obj, ipaddress.IPv4Address) else self.ipv6_ranges
        return any(start <= ip_obj <= end for start, end in ranges)
