#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2024/4/17
# @Author  : weihang
# @File    : marex_helper.py
# @Desc    : Marex策略解析工具函数

import re


def get_action_from_marex(marex):
    """从 Marex 策略字符串中提取 action 名称。

    Args:
        marex (str): Marex 策略字符串

    Returns:
        str or None: action 名称，如 'eu_plc', 'pcapdump', 'mirr' 等

    Examples:
        >>> marex = 'eu_plc 0247546 proto.pid==5 with action.do{eu_plc,type=monit}'
        >>> get_action_from_marex(marex)
        'eu_plc'
    """
    response = re.search(r"action\.do\s*{(\w+),", marex)
    if response:
        res = response.group(1)
    else:
        res = None
    return res


def get_type_from_marex(marex):
    """从 Marex 策略字符串中提取 type 类型。

    Args:
        marex (str): Marex 策略字符串

    Returns:
        str or None: type 类型，如 'monit', 'filt' 等

    Examples:
        >>> marex = 'eu_plc 0247546 proto.pid==5 with action.do{eu_plc,type=monit}'
        >>> get_type_from_marex(marex)
        'monit'
    """
    response = re.search(r"action\.do\s*{\w+?,type=(\w+),", marex)
    if response:
        res = response.group(1)
    else:
        res = None
    return res


def get_xdrtxtlog2name_frommarex(marex):
    """从 Marex 策略字符串中提取 XDR 日志名称。

    根据 action 类型和 darea 参数，返回对应的 XDR 日志名称。

    Args:
        marex (str): Marex 策略字符串，支持以下类型:
            - eu_plc: 包含 type 参数 (monit/filt)
            - pcapdump: 包含 darea 参数
            - mirrorvlan: 包含 darea 参数

    Returns:
        str or None: XDR 日志名称，格式为 "ACTION--XDR"
            - eu_plc + monit: "MONITOR--MONITORXDR"
            - eu_plc + filt: "FILTER--MONITORXDR"
            - pcapdump + darea=1: "PCAPDUMP_IS--PCAPXDR"
            - pcapdump + darea=2: "PCAPDUMP_DS--PCAPXDR"
            - pcapdump + darea=3: "PCAPDUMP_NS--PCAPXDR"
            - mirrorvlan + darea=1: "MIRRORVLAN_IS--MIRRORXDR"
            - mirrorvlan + darea=2: "MIRRORVLAN_DS--MIRRORXDR"
            - mirrorvlan + darea=3: "MIRRORVLAN_NS--MIRRORXDR"

    Note:
        - darea 1: 信安
        - darea 2: 数安
        - darea 3: 网安
        - darea 4: 深度合成
    """
    action = get_action_from_marex(marex)
    if action == "eu_plc":
        response = re.search(r"%s,type=(\w+)," % action, marex)
        if response and response.group(1) == "monit":
            res = "MONITOR--MONITORXDR"
        elif response and response.group(1) == "filt":
            res = "FILTER--MONITORXDR"
        else:
            res = None
    elif action == "pcapdump":
        response = re.search(r"darea=(\w+),", marex)
        if response and response.group(1) == "1":
            res = "PCAPDUMP_IS--PCAPXDR"
        elif response and response.group(1) == "2":
            res = "PCAPDUMP_DS--PCAPXDR"
        elif response and response.group(1) == "3":
            res = "PCAPDUMP_NS--PCAPXDR"
        else:
            res = None
    elif action == "mirr":
        response = re.search(r"darea=(\w+),", marex)
        if response and response.group(1) == "1":
            res = "MIRRORVLAN_IS--MIRRORXDR"
        elif response and response.group(1) == "2":
            res = "MIRRORVLAN_DS--MIRRORXDR"
        elif response and response.group(1) == "3":
            res = "MIRRORVLAN_NS--MIRRORXDR"
        else:
            res = None
    else:
        res = None
    return res


if __name__ == '__main__':
    # 测试代码
    marex1 = 'eu_plc 0247546 proto.pid==5&&ip.dst==172.31.138.249 with action.do{eu_plc,type=monit,hid=66483,blk=disable,log=enable,lvl=3849,cid=1277,way=2,time=2022-07-19 20:21:18|2052-07-19 23:59:59}'
    print("Action:", get_action_from_marex(marex1))
    print("Type:", get_type_from_marex(marex1))
    print("XDR Name:", get_xdrtxtlog2name_frommarex(marex1))

    marex2 = '0028582 ip.dst==172.31.140.52&&pkt.dstport==8000 with action.do{pcapdump,f=flow,hid=66483,way=1,p=1,prex=1306,darea=2,ct=1,lvl=9992,time=2022-07-20 00:00:00|2022-07-20 00:00:00}'
    print("Action:", get_action_from_marex(marex2))
    print("XDR Name:", get_xdrtxtlog2name_frommarex(marex2))
