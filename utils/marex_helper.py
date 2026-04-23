#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2024/4/17
# @Author  : weihang
# @File    : marex_helper.py
# @Desc    : Marex策略解析工具函数

import re


def get_action_from_marex(marex):
    """
    从Marex策略中获取action名称

    :param marex: Marex策略字符串
        示例: eu_plc 0247546 proto.pid==5&&ip.dst==172.31.138.249 with action.do{eu_plc,type=monit,hid=66483,blk=disable,log=enable,lvl=3849,cid=1277,way=2,time=2022-07-19 20:21:18|2052-07-19 23:59:59}
    :return: action名称，如 'eu_plc', 'pcapdump', 'mirr' 等
    """
    response = re.search(r"action\.do\s*{(\w+),", marex)
    if response:
        res = response.group(1)
    else:
        res = None
    return res


def get_type_from_marex(marex):
    """
    从Marex策略中获取type类型

    :param marex: Marex策略字符串
        示例: eu_plc 0247546 proto.pid==5&&ip.dst==172.31.138.249 with action.do{eu_plc,type=monit,hid=66483,blk=disable,log=enable,lvl=3849,cid=1277,way=2,time=2022-07-19 20:21:18|2052-07-19 23:59:59}
    :return: type类型，如 'monit', 'filt' 等
    """
    response = re.search(r"action\.do\s*{\w+?,type=(\w+),", marex)
    if response:
        res = response.group(1)
    else:
        res = None
    return res


def get_xdrtxtlog2name_frommarex(marex):
    """
    从Marex策略中获取XDR日志名称

    :param marex: Marex策略字符串，支持以下格式:
        eu_plc类型:
            eu_plc 0247546 proto.pid==5&&ip.dst==172.31.138.249 with action.do{eu_plc,type=monit,hid=66483,blk=disable,log=enable,lvl=3849,cid=1277,way=2,time=2022-07-19 20:21:18|2052-07-19 23:59:59}
            5721070 http.url~"^172\\.31\\.140\\.52:8000/MiitDataCheck/page/dialingTest/targetFile/test\\.ogg$" with action.do{eu_plc,type=filt,hid=66483,blk=enable,log=enable,lvl=3200,cid=1290,way=1,time=2022-07-20 15:14:46|2052-07-20 23:59:59}

        pcapdump类型:
            0028582 ip.dst==172.31.140.52&&pkt.dstport==8000 with action.do{pcapdump,f=flow,hid=66483,way=1,p=1,prex=1306,darea=2,ct=1,lvl=9992,time=2022-07-20 00:00:00|2022-07-20 00:00:00}

        mirrorvlan类型:
            0028639 ip.dst==172.31.140.52&&pkt.dstport==8000 with action.do{mirr,uid=0,g=1,time=2022-07-21 00:00:00|2022-07-21 00:00:00,d=both,f=flow,t=sip+sport+dip+dport,match-offset=0,match-method=include,match-len=1024,match-ctnt-len=1024,cut=10000,way=1,cid=1322,darea=2,p=1,hid=66483,ct=1,lvl=9992}

    :return: XDR日志名称，格式为 "ACTION--XDR"，如:
        - eu_plc + monit: "MONITOR--MONITORXDR"
        - eu_plc + filt: "FILTER--MONITORXDR"
        - pcapdump + darea=1: "PCAPDUMP_IS--PCAPXDR"
        - pcapdump + darea=2: "PCAPDUMP_DS--PCAPXDR"
        - pcapdump + darea=3: "PCAPDUMP_NS--PCAPXDR"
        - mirrorvlan + darea=1: "MIRRORVLAN_IS--MIRRORXDR"
        - mirrorvlan + darea=2: "MIRRORVLAN_DS--MIRRORXDR"
        - mirrorvlan + darea=3: "MIRRORVLAN_NS--MIRRORXDR"

    注意:
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
