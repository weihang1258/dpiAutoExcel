#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2024/10/7
# @Author  : weihang
# @File    : pcapdump.py

"""
PCAP Dump 处理模块
处理 pcapdump 测试
"""

import copy
import datetime
import io
import os
import re
import time
from utils.common import logger, gettime, wait_until, wait_not_until
from core.result import result_deal
from device.socket_linux import SocketLinux
from device.dpi import Dpi
from monitor.dpistat import CheckDpiStat
from core.pcap import pcap_send
from device.tcpdump import Tcpdump
from scapy.all import rdpcap, wrpcap
from utils.dpi_helper import dpi_init
from utils.marex_helper import get_action_from_marex, get_xdrtxtlog2name_frommarex
from device.dpi_constants import (
    uploadfile, reportfile, house_ipsegsfile, pcip_ipsegsfile,
    comon_inifile, ydcommoninfo_rulefile, commoninfo_rulefile, fz_block_rulefile,
    action2policyfile
)


from protocol.pcap_analyzer import compare_pcap, Pcap2Flowtable, FlowTable


def pcapdump(p_excel: dict, sheets=("pcapdump",), path="用例", newpath=None):
    """处理 pcapdump 测试。

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
    socket_logserver = (
        config["ip_logserver"] if config["ip_logserver"] else config["ip_xsa"],
        int(config["port_logserver"])
    )

    logserver = SocketLinux(socket_logserver)
    dpi = Dpi(socket_xsa)
    dpistat = CheckDpiStat(socket_xsa)

    # 执行用例
    counter = 1
    for sheet_name in sheets:
        logger.info(f"---------------------开始执行excel：{path}，sheet：{sheet_name}---------------------")
        cases = sheet_name2cases[sheet_name]

        # DPI环境初始化
        if sum(list(map(lambda x: 1 if x[0]["执行状态"] and int(x[0]["执行状态"]) == 1 else 0, cases.values()))) > 0:
            devconfig_tmp = dict()
            tmp = config[sheet_name + "_devconfig"].split(",") if config[sheet_name + "_devconfig"] else []

            for i in tmp:
                if devconfig_tmp:
                    for _type, line in config_dev[i].items():
                        if _type not in devconfig_tmp:
                            devconfig_tmp[_type] = dict()
                        for key, val in line.items():
                            devconfig_tmp[_type][key] = val
                else:
                    devconfig_tmp = copy.deepcopy(config_dev[i])
            logger.info(devconfig_tmp)
            dpi_init(dpi, **devconfig_tmp)

            # 停止dpi_monitor和policyserver
            dpi.dpi_monitor(op="stop")
            dpi.policyserver(op="stop")
        else:
            continue

        # 获取流超时时间
        xsa_json_dict = dpi.json_get(path="/opt/dpi/xsaconf/xsa.json")
        timeout_flow = xsa_json_dict["flow"]["tcp_fin_timeout_ms"]
        pcapdump_sec = xsa_json_dict["pcapdump"]["sec"]

        # 更新house_ipsegs.txt
        ipsegs_list = config["house_ipsegs"].strip().split("\n")
        logger.info("house_ipsegs加载：\n%s" % ("\n".join(ipsegs_list)))
        houseid, houseid_inner, a, b = ipsegs_list[0].strip().split("|")
        ipsegs_list = list(map(lambda x: x.encode("utf-8"), ipsegs_list))
        dpi.marex_policy_update(policy=ipsegs_list, path=house_ipsegsfile)

        # 更新upload.rule
        uploadrule_list = config[sheet_name + "_uploadrule"].strip().split("\n")
        logger.info("upload策略加载：\n%s" % ("\n".join(uploadrule_list)))
        uploadmode, uploadip, uploadport, uploaduser, uploadpwd, uploaddst, uploadsrc, a, uploadex_field, uploadzippwd = \
            uploadrule_list[0].strip().split()
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

            try:
                # 获取策略
                hid = dpi.cmd(
                    "cat /opt/dpi/xsaconf/rule/house_ipsegs.txt |grep '|' |tail -n 1|awk -F '|' '{print $2}'").strip()
                policy = list(map(lambda x: re.sub(r"hid=\d+,", f"hid={hid},", x).encode("utf-8"),
                                  case[0]["策略"].strip().split("\n")))
                commandid = re.search(b"prex=(\\d+),", policy[0]).groups()[0].decode("utf-8")
                darea = re.search(b"darea=(\\d+),", policy[0]).groups()[0].decode("utf-8")
                way = re.search(b"way=(\\d+),", policy[0]).groups()[0].decode("utf-8")
                pcaptype = {"1": "0x04a1", "2": "0x04a5", "3": "0x04a3"}[darea]
                waytype = {"1": "12", "2": "13", "3": "14"}[way]
                logger.info(f"commandid:{commandid}")

                if uploadex_field == "1|9":
                    curdate = datetime.datetime.now().strftime('%Y-%m-%d')
                    path_log = config["sftppath_logserver"].strip().rstrip("/") + "/" + uploaddst.strip().strip("/") + f"/{houseid}/{waytype}/{curdate}/{commandid}"
                    spath_log = f"{uploadsrc}/{pcaptype}/{houseid}/{waytype}/{curdate}/{commandid}"

                logger.info("策略加载：\n%s" % (b"\n".join(policy)).decode("utf-8"))
                action = get_action_from_marex(policy[0].decode("utf-8"))

                # 清空策略
                dpi.marex_policy_update(policy=[], path=action2policyfile[action])
                wait_until(dpistat.get_policy_total, "0", 2, 60, action)
                dpi.marex_policy_update(policy=policy, path=action2policyfile[action])
                wait_until(dpistat.get_policy_total, str(len(policy)), 2, 60, action)
                time.sleep(4)

                # 统计pcapdump日志数量-开始量
                name = get_xdrtxtlog2name_frommarex(policy[0].decode("utf-8"))
                logcount_s = dpistat.xdrtxtlog22dict()[name]["total"]

                # 等待pcap文件写完
                cmd = "cat /dev/shm/xsa/pcapdump.stat|tail -n 1|awk '{print $10}'"
                wait_until(dpi.cmd, "0\n", 2, 60, cmd)

                # 统计pcap文件数量-开始量
                if logserver.isdir(path_log):
                    logfilecount_s = logserver.cmd(args="ls|wc -l", cwd=path_log)
                else:
                    logfilecount_s = '0\n'
                logger.info(f"{path_log}\t开始时上报文件数量：{logfilecount_s}")
                txtfilecount_s = logserver.cmd(args="ls %s*%s|wc -l" % (path_log, config[sheet_name + "_filetype"]))
                logger.info(f"{path_log}\t开始时pcap文件数量：{txtfilecount_s}")
                logger.info("ls *%s|tail -n 2" % config[sheet_name + "_filetype"])
                logger.info(logserver.cmd(args="ls %s*%s|tail -n 2" % (path_log, config[sheet_name + "_filetype"])))

                # 统计xsa上的fopen_ok数量
                cmd = "cat /dev/shm/xsa/pcapdump.stat|tail -n 1|awk '{print $6}'"
                count_fopen_ok = dpi.cmd(cmd)

                # 开启镜像抓包
                logger.info(f"开启镜像抓包,原始包：/home/tmp/tmp1.pcap")
                mytcpdump1 = Tcpdump(
                    client=(config["pcapdump_ip1"], int(config["pcapdump_port1"])),
                    eth=config["pcapdump_eth1"],
                    extended="port 8000",
                    tmppath="/home/tmp/tmp1.pcap"
                )
                flag_tcpdump_start = mytcpdump1.tcpdump_start()
                logger.info(flag_tcpdump_start)
                if not flag_tcpdump_start:
                    raise RuntimeError("tcpdump_start failed")

                # 记录开始时间
                time_s = gettime(2)

                # 获取发包前的采集报文数量
                pcapdump_pkts1 = int(dpistat.pcapdump2dict().get("write_blk", 0))
                logger.info(f"发包前 pcapdump采集包数：{pcapdump_pkts1}")

                # 发包
                if case[0].get("pcap", None):
                    path_flag = "/" if config["pcap_path"].startswith("/") else "\\"
                    pcaps = list(map(lambda x: config["pcap_path"].rstrip(path_flag) + path_flag + x.lstrip(path_flag),
                                     case[0]["pcap"].split()))
                    pcaps = list(map(lambda x: x.replace("/", path_flag), pcaps))
                    if path_flag == "\\":
                        pcaps = list(map(lambda x: x.replace("/", path_flag), pcaps))
                    pcap_send(
                        client=socket_scapy_send,
                        pcaps=pcaps,
                        uplink_iface=config["eth_scapy_send"],
                        downlink_iface=None,
                        uplink_vlan=None,
                        downlink_vlan=None,
                        mbps=50,
                        verbose=None,
                        force_ip_src=None,
                        force_ip_dst=None,
                        force_sport=None,
                        force_dport=None,
                        force_build_flow=None,
                        bufsize=1024
                    )

                # 等待流超时
                logger.info("等待流超时(%sms)" % timeout_flow)
                time.sleep(timeout_flow / 1000 * 2 + 2)

                # 获取发包后的采集报文数量
                pcapdump_pkts2 = int(dpistat.pcapdump2dict().get("write_blk", 0))
                logger.info(f"发包后 pcapdump采集包数：{pcapdump_pkts2}")
                logger.info(f"pcapdump实际采集包数：{pcapdump_pkts2 - pcapdump_pkts1}")

                # 停止抓包
                logger.info("停止抓包")
                mytcpdump1.tcpdump_stop()

                # 等待pcap文件开始生成
                logger.info("等待pcap文件开始生成:超时时间%ss" % int(pcapdump_sec + 2))
                cmd = "cat /dev/shm/xsa/pcapdump.stat|tail -n 1|awk '{print $6}'"
                logger.info(cmd)
                wait_not_until(dpi.cmd, count_fopen_ok, step=1, timeout=int(pcapdump_sec + 2), args=cmd)

                # 等待pcap文件生成
                logger.info(f"等待pcap文件生成:超时时间{pcapdump_sec * 2}s")
                cmd = "cat /dev/shm/xsa/pcapdump.stat|tail -n 1|awk '{print $10}'"
                logger.info(cmd)
                if not wait_until(dpi.cmd, expect_value="0\n", step=2, timeout=pcapdump_sec * 2, args=cmd):
                    result_deal(path, sheet_name, result_list, case[0]["row"], sheet_name2head2col[sheet_name],
                                [f"流超时后等待{pcapdump_sec * 2}s后，pcapdump.stat显示文件还没有关闭！"], newpath=newpath)
                    continue

                # 记录结束时间
                time_e = gettime(2)

                # 等待文件上报
                logger.info("等待文件上报:超时时间15s")
                cmd = "cd %s && ls|wc -l" % path_log
                logger.info(cmd)
                wait_not_until(logserver.cmd, '', step=1, timeout=15, args=cmd)
                wait_not_until(logserver.cmd, logfilecount_s, step=1, timeout=3, args=cmd)

                logger.info("等待文件上报完成:超时时间3s")
                cmd = f"ls {spath_log}|wc -l"
                logger.info(cmd)
                wait_until(dpi.cmd, "0\n", step=1, timeout=3, args=cmd)

                # 统计pcapdump日志数量-结束量
                logcount = int(dpistat.xdrtxtlog22dict()[name]["total"]) - int(logcount_s)

                # 初始化解压目录
                logger.info("初始化解压目录：/tmp/pcap")
                tmpdir = "/tmp/pcap"
                if logserver.isdir(tmpdir):
                    logserver.cmd("rm -rf %s" % tmpdir)
                logserver.mkdir(dir=tmpdir)

                # 解压缩文件
                if config.get(sheet_name + "_compression", None):
                    logger.info("解压缩文件")
                    logfilecount_e = logserver.cmd(args="ls|wc -l", cwd=path_log)
                    logger.info(f"{path_log}\t结束时上报文件数量：{logfilecount_e}")
                    logger.info([logfilecount_s, logfilecount_e])
                    cmd = "ls -rt *%s|tail -n %s" % (
                        config[sheet_name + "_compression"], int(int(logfilecount_e) - int(logfilecount_s))
                    )
                    response = logserver.cmd(args=cmd, cwd=path_log)
                    logger.info(cmd)
                    logger.info(response)
                    for name in response.strip().split():
                        if config[sheet_name + "_compression"] in ("zip", "zip_complete") and config.get(sheet_name + "_password"):
                            cmd = f"unzip -oP {int(config[sheet_name + '_password'])} {name} -d {tmpdir}"
                        elif config[sheet_name + "_compression"] in ("zip", "zip_complete"):
                            cmd = f"unzip -o {name} -d {tmpdir}"
                        else:
                            raise RuntimeError("不支持压缩方式：%s" % config.get(sheet_name + "_compression"))
                        logger.info([path_log, cmd])
                        res_unzip = logserver.cmd(args=cmd, cwd=path_log)
                        logger.info(res_unzip)
                        time.sleep(2)

                        if "Archive" in res_unzip and "inflating" not in res_unzip:
                            res_unzip = logserver.cmd(args=cmd, cwd=path_log)
                            logger.info(res_unzip)
                            time.sleep(2)

                # 提取pcap
                logger.info("提取pcap")
                cmd = "ls -v *%s" % config[sheet_name + "_filetype"]
                logger.info([tmpdir, cmd])
                response = logserver.cmd(args=cmd, cwd=tmpdir)

                logger.info("下载生成的pcap")
                if not os.path.isdir("out"):
                    os.mkdir("out")
                pcap_name_act = f"out/{case[0]['用例名']}_act{int(time.time())}.pcap"
                pkts_act = dpi.download_pcap(remotepath=tmpdir, localpath=pcap_name_act, return_pkts=True)

                # 下载预期pcap
                logger.info("下载预期pcap")
                fl_exp = mytcpdump1.pcap_getfo()
                mytcpdump1.client.close()
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
                    compare_pcap(pcap_exp=pkts_exp, pcap_act=pkts_act, flowsplit=True, ignore_syn=True)
                except Exception as e:
                    logger.info(e)
                    mark.append(str(e))

                tables = Pcap2Flowtable(pkts_exp)
                tables.pkts_parser()

                if logcount == len(tables.flowtable.tables):
                    result_list.append(
                        (case[0]["row"], sheet_name2head2col[sheet_name]["日志数量"], logcount, (255, 255, 255)))
                else:
                    result_list.append(
                        (case[0]["row"], sheet_name2head2col[sheet_name]["日志数量"], logcount, (255, 0, 0)))
                    mark.append(f"日志数量:期望条数{len(tables.flowtable.tables)},实际条数{logcount}")

                # 写结果到excel
                logger.info([result_list, mark])
                result_deal(path, sheet_name, result_list, case[0]["row"], sheet_name2head2col[sheet_name], mark, newpath=newpath)

                # 清空策略
                dpi.marex_policy_update(policy=[], path=action2policyfile[action])
                counter += 1

            except Exception as e:
                logger.info(e)
                result_deal(path, sheet_name, result_list, case[0]["row"], sheet_name2head2col[sheet_name], [str(e)], newpath=newpath)

    logserver.client.close()
    dpi.client.close()
    dpistat.client.close()
