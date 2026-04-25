#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2024/10/7
# @Author  : weihang
# @File    : mirrorvlan.py

"""
MirrorVLAN 镜像VLAN处理模块
处理镜像VLAN测试
"""

import copy
import datetime
import io
import random
import re
import time
from itertools import chain
from utils.common import gettime, wait_until, wait_not_until, get_flow_timeout, setup_logging
from core.excel_reader import parser_excel, casename2exp_log, act_log
from core.result import result_deal
from device.socket_linux import SocketLinux
from device.dpi import Dpi
from monitor.dpistat import CheckDpiStat
from core.pcap import pcap_send
from utils.ini_handler import INIHandler
from utils.dpi_helper import dpi_init
from utils.marex_helper import get_action_from_marex, get_xdrtxtlog2name_frommarex
from protocol.pcap_analyzer import compare_pcap, Pcap2Flowtable
from device.dpi_constants import (
    uploadfile, reportfile, house_ipsegsfile, pcip_ipsegsfile,
    comon_inifile, ydcommoninfo_rulefile, commoninfo_rulefile,
    access_log_rulefile, xsa_jsonfile, fz_block_rulefile,
    action2policyfile, src2logtype
)
from scapy.all import rdpcap, wrpcap

logger = setup_logging(log_file_path="log/mirrorvlan.log", logger_name="mirrorvlan")


def mirrorvlan(p_excel: dict, sheets=("mirrorvlan",), path="用例", newpath=None):
    """处理 MirrorVLAN 镜像VLAN测试。

    Args:
        p_excel: Excel 解析结果
        sheets: sheet 名称列表
        path: Excel 文件路径
        newpath: 新 Excel 文件路径
    """
    sheet_name2cases = p_excel["sheet_name2cases"]
    sheet_name2head2col = p_excel["sheet_name2head2col"]
    config = p_excel["config"]
    config_dev = p_excel["config_dev"]

    # Socket连接生成
    socket_xsa = (config["ip_xsa"], int(config["port_xsa"]))
    socket_scapy_send = (config["host_scapy_send"], int(config["port_scapy_send"]))

    dpi = Dpi(socket_xsa)
    dpistat = CheckDpiStat(socket_xsa)

    # MTU设置
    mirrorvlan1 = SocketLinux((config["mirrorvlan_ip1"], int(config["mirrorvlan_port1"])))
    mirrorvlan2 = SocketLinux((config["mirrorvlan_ip2"], int(config["mirrorvlan_port2"])))
    mirrorvlan1.mtu(eth=config["mirrorvlan_eth1"], value=2000)
    mirrorvlan2.mtu(eth=config["mirrorvlan_eth2"], value=2000)

    counter = 1
    for sheet_name in sheets:
        logger.info(f"---------------------开始执行excel：{path}，sheet：{sheet_name}---------------------")
        if sheet_name != sheets[0]:
            path = newpath
        cases = sheet_name2cases[sheet_name]

        # DPI环境初始化
        if sum(list(map(lambda x: 1 if x[0]["执行状态"] and int(x[0]["执行状态"]) == 1 else 0, cases.values()))) > 0:
            devconfig_tmp = dict()
            tmp = config.get(sheet_name + "_devconfig", "").split(",") if config.get(sheet_name + "_devconfig", None) else []

            for i in tmp:
                if devconfig_tmp:
                    for ini_config_name, line in config_dev[i].items():
                        if ini_config_name not in devconfig_tmp:
                            devconfig_tmp[ini_config_name] = dict()
                        for key, val in line.items():
                            devconfig_tmp[ini_config_name][key] = val
                else:
                    devconfig_tmp = copy.deepcopy(config_dev[i])
            logger.info(devconfig_tmp)
            dpi_init(dpi, **devconfig_tmp)

            # 停止dpi_monitor和policyserver
            logger.info("停止dpi_monitor和policyserver")
            dpi.dpi_monitor(op="stop")
            dpi.policyserver(op="stop")
        else:
            continue

        # 获取流超时时间
        xsa_json_dict = dpi.json_get(path="/opt/dpi/xsaconf/xsa.json")
        timeout_flow = xsa_json_dict["flow"]["tcp_fin_timeout_ms"]

        # 更新house_ipsegs.txt
        ipsegs_list = config["house_ipsegs"].strip().split("\n")
        logger.info("house_ipsegs加载：\n%s" % ("\n".join(ipsegs_list)))
        houseid, houseid_inner, a, b = ipsegs_list[0].strip().split("|")
        ipsegs_list = list(map(lambda x: x.encode("utf-8"), ipsegs_list))
        dpi.marex_policy_update(policy=ipsegs_list, path=house_ipsegsfile)

        # 更新upload.rule
        uploadrule_list = config.get(sheet_name + "_uploadrule", "").strip().split("\n")
        logger.info("upload策略加载：\n%s" % ("\n".join(uploadrule_list)))
        uploadrule_split = uploadrule_list[0].strip().split()
        if len(uploadrule_split) >= 8:
            uploadmode, uploadip, uploadport, uploaduser, uploadpwd, uploaddst, uploadsrc, a = uploadrule_split[:8]
            uploadex_field = uploadrule_split[8] if len(uploadrule_split) > 8 else "0|1|1"
            uploadzippwd = uploadrule_split[9] if len(uploadrule_split) > 9 else None
        uploadrule_list = list(map(lambda x: x.encode("utf-8"), uploadrule_list))
        dpi.marex_policy_update(policy=uploadrule_list, path=uploadfile)

        # 更新common.ini
        common_ini = config["common_ini"].strip()
        logger.info("common.ini加载")
        dpi.putfo(fl=io.BytesIO(common_ini.encode("utf-8")), remotepath=comon_inifile, overwrite=False)

        # 更新ydcommoninfo.rule
        ydcommoninfo_rule = config["ydcommoninfo_rule"].strip() if config["ydcommoninfo_rule"] else ""
        logger.info("ydcommoninfo.rule加载")
        dpi.putfo(fl=io.BytesIO(ydcommoninfo_rule.encode("utf-8")), remotepath=ydcommoninfo_rulefile, overwrite=False)

        # 更新commoninfo.rule
        commoninfo_rule = config["commoninfo_rule"].strip() if config["commoninfo_rule"] else ""
        logger.info("commoninfo.rule加载")
        dpi.putfo(fl=io.BytesIO(commoninfo_rule.encode("utf-8")), remotepath=commoninfo_rulefile, overwrite=False)

        # 清空策略
        logger.info("清空策略")
        if dpi.isfile(fz_block_rulefile):
            logger.info(f"清空idc_fz策略：{fz_block_rulefile}")
            dpi.marex_policy_update(policy=[], path=fz_block_rulefile)
        for policyfile in action2policyfile.values():
            dpi.marex_policy_update(policy=[], path=policyfile)

        for case_name, case in cases.items():
            if not case_name or str(case[0]["执行状态"]) not in ("1", "1.0"):
                continue

            if counter != 1:
                path = newpath
            logger.info("%s\t执行用例：%s\t%s\t%s" % (
                datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), sheet_name, counter, case_name))
            result = "Pass"
            mark = list()
            result_list = list()

            # 获取策略
            hid = dpi.cmd(
                args="cat /opt/dpi/xsaconf/rule/house_ipsegs.txt |grep '|' |tail -n 1|awk -F '|' '{print $2}'").strip()
            policy = list(map(lambda x: re.sub("hid=\\d+,", f"hid={hid},", x).encode("utf-8"),
                              case[0]["策略"].strip().split("\n")))
            g = re.search(b"g=(\\d+),", policy[0]).groups()[0].decode("utf-8")
            vlan = int(xsa_json_dict["mirrorvlan"]["vlantab"].split(",")[2 ** int(g) - 1])
            logger.info(f"hid:{hid},g:{g},vlan:{vlan}")
            logger.info("策略加载：\n%s" % (b"\n".join(policy)).decode("utf-8"))
            action = get_action_from_marex(policy[0].decode())

            # 清空策略
            dpi.marex_policy_update(policy=[], path=action2policyfile[action])
            # 等待状态更新
            wait_until(dpistat.get_policy_total, "0", 2, 60, action)
            # 添加策略
            dpi.marex_policy_update(policy=policy, path=action2policyfile[action])
            # 等待状态更新
            wait_until(dpistat.get_policy_total, str(len(policy)), 2, 60, action)
            time.sleep(2)

            # 统计mirrorvlan日志数量-开始量
            name = get_xdrtxtlog2name_frommarex(policy[0].decode())
            logcount_s = dpistat.xdrtxtlog22dict()[name]["total"]

            # 开启镜像抓包
            logger.info(f"开启镜像抓包,原始包：/home/tmp/tmp1.pcap，镜像包：/home/tmp/tmp2.pcap")
            from monitor.tcpdump import Tcpdump
            mytcpdump1 = Tcpdump(client=(config["mirrorvlan_ip1"], int(config["mirrorvlan_port1"])),
                                 eth=config["mirrorvlan_eth1"], extended="port 8000", tmppath="/home/tmp/tmp1.pcap")
            flag_tcpdump_start = mytcpdump1.tcpdump_start()
            logger.info(flag_tcpdump_start)
            if not flag_tcpdump_start:
                raise RuntimeError("tcpdump_start failed")

            mytcpdump2 = Tcpdump(client=(config["mirrorvlan_ip2"], int(config["mirrorvlan_port2"])),
                                 eth=config["mirrorvlan_eth2"], extended="port 8000", tmppath="/home/tmp/tmp2.pcap")
            flag_tcpdump_start = mytcpdump2.tcpdump_start()
            logger.info(flag_tcpdump_start)
            if not flag_tcpdump_start:
                raise RuntimeError("tcpdump_start failed")

            # 获取发包前的采集报文数量和发包数量
            tx_pkts1 = dpistat.xrt2dict().get("total", {}).get("TX_pkts", 0)
            mirror_pktinfo1 = dpistat.mirrorvlan2dict().get("detail", {}).get(str(pow(2, int(g))), {})
            logger.info(f"发包前 tx包数：{tx_pkts1}，mirrorvlan采集包信息：{mirror_pktinfo1}")

            # 发包
            if case[0].get("pcap", None):
                path_flag = "/" if config["pcap_path"].startswith("/") else "\\"
                pcaps = list(map(lambda x: config["pcap_path"].rstrip(path_flag) + path_flag + x.lstrip(path_flag),
                                 case[0]["pcap"].split()))
                if path_flag == "\\":
                    pcaps = list(map(lambda x: x.replace("/", path_flag), pcaps))
                pcap_send(client=socket_scapy_send, pcaps=pcaps, uplink_iface=config["eth_scapy_send"],
                          downlink_iface=None, uplink_vlan=None, downlink_vlan=None, mbps=50, verbose=None,
                          force_ip_src=None, force_ip_dst=None, force_sport=None, force_dport=None,
                          force_build_flow=None, bufsize=1024)

            # 等待流超时
            logger.info("等待流超时(%sms)" % timeout_flow)
            time.sleep(timeout_flow / 1000 * 2 + 2)

            # 统计mirrorvlan日志数量-结束量
            logcount = int(dpistat.xdrtxtlog22dict()[name]["total"]) - int(logcount_s)

            # 获取发包后的采集报文数量和发包数量
            tx_pkts2 = dpistat.xrt2dict().get("total", {}).get("TX_pkts", 0)
            mirror_pktinfo2 = dpistat.mirrorvlan2dict().get("detail", {}).get(str(pow(2, int(g))), {})
            logger.info(f"发包后 tx包数：{tx_pkts2}，mirrorvlan采集包信息：{mirror_pktinfo2}")
            logger.info(f"xrt实际发包包数：{int(tx_pkts2) - int(tx_pkts1)}，mirrorvlan实际采集包数：{int(mirror_pktinfo2.get('mirror', 0)) - int(mirror_pktinfo1.get('mirror', 0))}")

            # 停止抓包
            logger.info("停止抓包")
            mytcpdump1.tcpdump_stop()
            mytcpdump2.tcpdump_stop()

            logger.info("下载预期pcap")
            fl_exp = mytcpdump1.pcap_getfo()
            logger.info("下载镜像的pcap")
            fl_act = mytcpdump2.pcap_getfo()

            mytcpdump1.client.close()
            mytcpdump2.client.close()

            # 文件日志名
            pcap_name_act = f"out/{case[0]['用例名']}_act{int(time.time())}.pcap"
            with open(pcap_name_act, "wb") as f:
                f.write(fl_act.read())
            fl_act.seek(0)
            pkts_act = rdpcap(fl_act)

            # 下载预期pcap
            pkts_exp = rdpcap(fl_exp)
            pcap_name_exp = f"out/{case[0]['用例名']}_exp{int(time.time())}.pcap"
            wrpcap(pcap_name_exp, pkts_exp)

            result_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["原始包"],
                                f'=HYPERLINK("../{pcap_name_exp}", "{pcap_name_exp}")', (255, 255, 255)))
            result_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["抓包"],
                                f'=HYPERLINK("../{pcap_name_act}", "{pcap_name_act}")', (255, 255, 255)))

            # pcap包对比检查
            logger.info("pcap包对比检查")
            try:
                compare_pcap(pcap_exp=pkts_exp, pcap_act=pkts_act, flowsplit=True, Dot1Q={"vlan": vlan},
                             ignore_syn=False)
            except Exception as e:
                logger.info(e)
                mark.append(e)

            tables = Pcap2Flowtable(pkts_exp)
            tables.pkts_parser()

            if logcount == len(tables.flowtable.tables):
                result_list.append(
                    (case[0]["row"], sheet_name2head2col[sheet_name]["日志数量"], logcount, (255, 255, 255)))
            else:
                result_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["日志数量"], logcount, (255, 0, 0)))
                mark.append(f"日志数量:期望条数{len(tables.flowtable.tables)},实际条数{logcount}")

            # 写结果到excel
            logger.info([result_list, mark])
            result_deal(path, sheet_name, result_list, case[0]["row"], sheet_name2head2col[sheet_name], mark,
                        newpath=newpath)

            # 清空策略
            dpi.marex_policy_update(policy=[], path=action2policyfile[action])
            counter += 1

    dpi.client.close()
    dpistat.client.close()
