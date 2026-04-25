#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2024/10/7
# @Author  : weihang
# @File    : eu_policy.py

"""
EU策略处理模块
处理 eu_policy、block、fz_block 等策略测试
"""

import copy
import datetime
import io
import os
import re
import time
from utils.common import wait_until, get_flow_timeout, setup_logging
from core.result import result_deal
from device.dpi import Dpi
from monitor.dpistat import CheckDpiStat
from device.webvisit import Webvisit
from device.tcpdump import Tcpdump
from utils.dpi_helper import dpi_init
from device.hengwei import start_mirror, stop_mirror
from utils.marex_helper import get_action_from_marex, get_xdrtxtlog2name_frommarex
from protocol.pcap_analyzer import rst_check, extract_4tuple_from_pcap
from device.dpi_constants import (
    uploadfile, house_ipsegsfile, comon_inifile,
    ydcommoninfo_rulefile, commoninfo_rulefile, xsa_jsonfile, fz_block_rulefile,
    action2policyfile, fz_action_txtfile, fz_template_txtfile
)

logger = setup_logging(log_file_path="log/eu_policy.log", logger_name="eu_policy")


def eu_policy(p_excel: dict, sheets=("eu_policy",), path="用例", newpath=None):
    """处理 EU 策略测试。

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

    # 提取分流登录信息
    npb_host = config.get("NPB_host", None)
    npb_port = config.get("NPB_port", None)
    npb_username = config.get("NPB_username", None)
    npb_password = config.get("NPB_password", None)
    npb_inport = config.get("NPB_inport", None)
    npb_outport = config.get("NPB_outport", None)
    if not npb_host or not npb_port or not npb_username or not npb_password or not npb_inport or not npb_outport:
        raise RuntimeError("请检查配置文件中是否有分流登录信息")

    # Socket连接生成
    socket_xsa = (config["ip_xsa"], config["port_xsa"])
    socket_stationA = (config["ip_login_A"], int(config["port_login_A"]))
    socket_stationB = (config["ip_login_B"], int(config["port_login_B"]))
    xsa = Dpi(socket_xsa)
    dpistat = CheckDpiStat(socket_xsa)

    # 获取流超时时间
    timeout_flow = get_flow_timeout(xsa.json_get(path="/opt/dpi/xsaconf/xsa.json"), key="tcp_fin_timeout_ms")

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
                    for type, line in config_dev[i].items():
                        if type not in devconfig_tmp:
                            devconfig_tmp[type] = dict()
                        for key, val in line.items():
                            devconfig_tmp[type][key] = val
                else:
                    devconfig_tmp = copy.deepcopy(config_dev[i])
            logger.info(devconfig_tmp)
            dpi_init(xsa, **devconfig_tmp)

            # 停止dpi_monitor和policyserver
            logger.info("停止dpi_monitor和policyserver")
            xsa.dpi_monitor(op="stop")
            xsa.policyserver(op="stop")

            # 打开分流端口
            logger.info("打开分流端口")
            start_mirror(
                hostname=npb_host, port=npb_port, username=npb_username,
                password=npb_password, inport=npb_inport, outport=npb_outport
            )
        else:
            continue

        # 提取xsa.json为dict
        xsa_json2dict = xsa.json_get(path=xsa_jsonfile)

        # 更新house_ipsegs.txt
        ipsegs_list = config["house_ipsegs"].strip().split("\n")
        houseid, houseid_inner, a, b = ipsegs_list[0].strip().split("|")
        ip_tmp = config.get("ip_靶站B", None)
        if ip_tmp and ip_tmp not in config["house_ipsegs"]:
            ipsegs_list.append(f"{houseid}|{houseid_inner}|{ip_tmp}|{ip_tmp}")
        logger.info("house_ipsegs加载：\n%s" % ("\n".join(ipsegs_list)))
        ipsegs_list = list(map(lambda x: x.encode("utf-8"), ipsegs_list))
        xsa.marex_policy_update(policy=ipsegs_list, path=house_ipsegsfile)

        # 更新upload.rule
        uploadrule_list = config[sheet_name + "_uploadrule"].strip().split("\n")
        logger.info("upload策略加载：\n%s" % ("\n".join(uploadrule_list)))
        uploadmode, uploadip, uploadport, uploaduser, uploadpwd, uploaddst, uploadsrc, a, uploadex_field, uploadzippwd = \
            uploadrule_list[0].strip().split()
        uploadrule_list = list(map(lambda x: x.encode("utf-8"), uploadrule_list))
        xsa.marex_policy_update(policy=uploadrule_list, path=uploadfile)

        # 更新common.ini
        common_ini = config["common_ini"].strip()
        logger.info("common.ini加载")
        xsa.putfo(fl=io.BytesIO(common_ini.encode("utf-8")), remotepath=comon_inifile, overwrite=False)

        # 更新ydcommoninfo.rule
        ydcommoninfo_rule = config["ydcommoninfo_rule"].strip() if config["ydcommoninfo_rule"] else ""
        logger.info("ydcommoninfo.rule加载")
        xsa.putfo(fl=io.BytesIO(ydcommoninfo_rule.encode("utf-8")), remotepath=ydcommoninfo_rulefile, overwrite=False)

        # 更新commoninfo.rule
        commoninfo_rule = config["commoninfo_rule"].strip() if config["commoninfo_rule"] else ""
        logger.info("commoninfo.rule加载")
        xsa.putfo(fl=io.BytesIO(commoninfo_rule.encode("utf-8")), remotepath=commoninfo_rulefile, overwrite=False)

        # 清空策略
        logger.info("清空策略")
        if xsa.isfile(fz_block_rulefile):
            logger.info(f"清空idc_fz策略：{fz_block_rulefile}")
            xsa.marex_policy_update(policy=[], path=fz_block_rulefile)
        for policyfile in action2policyfile.values():
            xsa.marex_policy_update(policy=[], path=policyfile)

        for case_name, case in cases.items():
            if not case_name or str(case[0]["执行状态"]) not in ("1", "1.0"):
                continue

            if counter != 1:
                path = newpath

            logger.info("---------------------%s\t%s\t执行用例：%s---------------------" % (
                datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), counter, case_name))

            result = "Pass"
            mark = list()
            tmp_list = list()

            # 获取拨测端口，确定靶站ip
            if case[0].get('靶站A', None):
                url = case[0]['靶站A']
                dip = config["ip_靶站B"]
                sip = config["ip_靶站A"]
            else:
                url = case[0]['靶站B']
                dip = config["ip_靶站A"]
                sip = config["ip_靶站B"]

            protocol, tmp_url = url.split("//", 1)
            protocol = protocol[:-1]
            tmp_host, uri = tmp_url.split("/", 1)
            if ":" in tmp_host:
                port = tmp_host.split(":")[-1]
            elif protocol == "https":
                port = 443
            else:
                port = 80

            # 重新组成url
            if ":" in tmp_host:
                url = f"{protocol}://{dip}:{port}/{uri}"
                url_with_protocol = f"{dip}:{port}/{uri}"
                host = f"{dip}:{port}"
            else:
                url = f"{protocol}://{dip}/{uri}"
                url_with_protocol = f"{dip}/{uri}"
                host = dip

            # 定位分析用
            curdate = datetime.datetime.now().strftime('%Y-%m-%d')
            commond_id = case[0].get("策略ID", "0000")
            pacp_dir = f"/dev/shm/sess/pcap/0xffff/{houseid}/13/{curdate}/{commond_id}"
            if config.get(sheet_name + "_ispcapdump", "").lower() in ("true", "1"):
                logger.info("定位信息：增加pcapdump抓包")
                rules = [
                    f"0000006 ip.src=={sip}&&ip.dst=={dip} with action.do{{pcapdump,f=flow,hid={houseid_inner},p=1,prex={commond_id},darea=5,ct=1,lvl=9993,time=2022-07-20 00:00:00|2052-07-20 00:00:00}}",
                    f"0000007 ip.src=={dip}&&ip.dst=={sip} with action.do{{pcapdump,f=flow,hid={houseid_inner},p=1,prex={commond_id},darea=5,ct=1,lvl=9993,time=2022-07-20 00:00:00|2052-07-20 00:00:00}}"
                ]
                logger.info("\n".join(rules))
                rules = list(map(lambda x: x.encode("utf-8"), rules))
                xsa.marex_policy_update(policy=rules, path=action2policyfile["pcapdump"])
                wait_until(dpistat.get_policy_total, str(len(rules)), 2, 60, "pcapdump")

                xsa.wait_pcapdump_writeover(timeout=60)
                xsa.cleardir(path=pacp_dir)

            logcount_s = 0
            blockexe_s = 0
            send_eth_s = 0
            redirect_s = 0
            command_index = commond_id
            is_report = False

            # 更新idc反诈策略
            if case[0].get("fz_block.rule", None):
                logger.info("更新idc反诈策略")
                policy_action = case[0].get("fz_action.txt", "")
                policy_action = [] if policy_action in (None, "") else policy_action.strip().split("\n")
                logger.info("\n".join(policy_action))
                policy_action = list(map(lambda x: x.encode("utf-8"), policy_action))
                xsa.marex_policy_update(policy=policy_action, path=fz_action_txtfile, md5check=True)

                policy_template = case[0].get("fz_template.txt", "")
                policy_template = [] if policy_template in (None, "") else policy_template.strip().split("\n")
                logger.info("\n".join(policy_template))
                policy_template = list(map(lambda x: x.encode("utf-8"), policy_template))
                xsa.marex_policy_update(policy=policy_template, path=fz_template_txtfile, md5check=True)

                logger.info(f"清空fz_block策略：{fz_block_rulefile}")
                xsa.marex_policy_update(policy=[], path=fz_block_rulefile)
                wait_until(dpistat.adms_idc_debug2dict, "0", 2, 60, "adms_allrule_num")

                logger.info("fz_block策略组装：")
                hid = xsa.cmd("cat /opt/dpi/xsaconf/rule/house_ipsegs.txt |grep '|' |tail -n 1|awk -F '|' '{print $2}'").strip()
                policy_adms = []
                for rule in case[0].get("fz_block.rule", "").strip().split("\n"):
                    fields = rule.strip().split("|")
                    fields[0] = case[0].get("策略ID", "")
                    fields[3] = hid
                    if fields[4] == "9" and "-" not in fields[5]:
                        fields[5] = dip
                    elif fields[4] == "9" and "-" in fields[5]:
                        fields[5] = f"{dip}-{dip}"
                    elif fields[4] == "8" and "-" not in fields[5]:
                        fields[5] = sip
                    elif fields[4] == "8" and "-" in fields[5]:
                        fields[5] = f"{sip}-{sip}"
                    elif fields[4] == "2":
                        fields[5] = host
                    elif fields[4] == "1":
                        fields[5] = url_with_protocol
                    else:
                        raise RuntimeError(f"不支持策略类型：{fields[4]}")
                    policy_adms.append("|".join(fields))
                    if is_report == False and (fields[10] == "1" or fields[11] == "1"):
                        is_report = True
                logger.info("\n".join(policy_adms))

                logger.info("fz_block策略加载")
                policy_adms = list(map(lambda x: x.encode("utf-8"), policy_adms))
                xsa.marex_policy_update(policy=policy_adms, path=fz_block_rulefile, md5check=True)
                wait_until(dpistat.adms_idc_debug2dict, str(len(policy_adms)), 2, 60, "adms_allrule_num")
                time.sleep(2)
                logcount_s += int(dpistat.xdrtxtlog22dict().get("ADMS_BLOCK--ADMS_LOG", {}).get("total", "0"))
            else:
                if xsa.isfile(fz_block_rulefile) and xsa_json2dict.get("adms", {}).get("idc_flag", None) == 1:
                    xsa.marex_policy_update(policy=[], path=fz_block_rulefile)
                    wait_until(dpistat.adms_idc_debug2dict, "0", 2, 60, "adms_allrule_num")

            if case[0].get("策略", None):
                logger.info("eu_policy策略组装：")
                hid = xsa.cmd("cat /opt/dpi/xsaconf/rule/house_ipsegs.txt |grep '|' |tail -n 1|awk -F '|' '{print $2}'").strip()
                policy = list(map(lambda x: re.sub("hid=\\d+,", f"hid={hid},", x), case[0]["策略"].strip().split("\n")))
                policy = list(map(lambda x: re.sub(r"(?<=ip.dst==)\d+.\d+.\d+.\d+", dip, x), policy))
                policy = list(map(lambda x: re.sub(r"(?<=ip.src==)\d+.\d+.\d+.\d+", sip, x), policy))

                policy_tmp = list()
                for s in policy:
                    if is_report == False and ("report=enable" in s and "log=enable" in s):
                        is_report = True

                    match = re.search(r"4tuple=([\d\.]*)\|(\d*)\|([\d\.]*)\|(\d*)", s)
                    if match:
                        first_ip, first_port, second_ip, second_port = match.groups()
                        if first_ip:
                            first_ip = sip
                        if second_ip:
                            second_ip = dip
                        new_tuple = f"{first_ip}|{first_port}|{second_ip}|{second_port}"
                        s = s.replace(match.group(0), f"4tuple={new_tuple}")
                    policy_tmp.append(s)
                policy_eu = policy_tmp
                command_index = re.findall(r"^\d+", policy_eu[0])[0]
                policy_eu = list(map(lambda x: re.sub(r'(?<=http\.host~"\^)(\d+\\.\d+\\.\d+\\.\d+)(?=:|$)', dip.replace(".", r"\."), x), policy_eu))
                policy_eu = list(map(lambda x: re.sub(r'(?<=http\.url~"\^)(\d+\\.\d+\\.\d+\\.\d+)(?=:|/)', dip.replace(".", r"\."), x).encode("utf-8"), policy_eu))

                logger.info("eu_policy策略加载：\n%s" % (b"\n".join(policy_eu)).decode("utf-8"))
                action = get_action_from_marex(policy_eu[0].decode("utf-8"))

                xsa.marex_policy_update(policy=[], path=action2policyfile[action])
                wait_until(dpistat.get_policy_total, "0", 2, 60, action)
                xsa.marex_policy_update(policy=policy_eu, path=action2policyfile[action])
                wait_until(dpistat.get_policy_total, str(len(policy_eu)), 2, 60, action)
                time.sleep(2)

                name = get_xdrtxtlog2name_frommarex(policy_eu[0].decode("utf-8"))
                if name in dpistat.xdrtxtlog22dict():
                    logcount_s += int(dpistat.xdrtxtlog22dict()[name].get("total"), 0)
                else:
                    logcount_s = int(xsa.cmd("cat /dev/shm/xsa/eu_output.stat |grep 'all:' -A50|grep monitor_filterlog_succ_cnt|awk -F ':' '{print $2}'").strip())
            else:
                policy_eu = []
                action = "eu_plc"
                xsa.marex_policy_update(policy=policy_eu, path=action2policyfile[action])
                wait_until(dpistat.get_policy_total, "0", 2, 60, action)

            # 统计封堵包执行情况开始值
            eublock2dict_tmp = dpistat.eublock2dict()
            blockexe_s = int(eublock2dict_tmp.get("all", {}).get("blockExe", "0"))
            redirect_s = int(eublock2dict_tmp.get("all", {}).get("redirect", "0"))
            send_eth_s = int(eublock2dict_tmp.get("all", {}).get("send_eth", "0"))

            # 开启抓包
            logger.info("开启抓包")
            rst_tcpdump = Tcpdump(
                client=socket_xsa,
                eth=config_dev.get("rst", {}).get("xsa_json", {}).get("eublock.raw_port", {}),
                extended="tcp[13] == 0x1c",
                single_queue=False
            )
            tcpdumpA = Tcpdump(
                client=socket_stationA,
                eth=config.get("eth_A"),
                extended=f"host {dip} and port {port}"
            )
            tcpdumpB = Tcpdump(
                client=socket_stationB,
                eth=config.get("eth_B"),
                extended=f"host {dip} and port {port}"
            )
            rst_tcpdump.tcpdump_start()
            tcpdumpA.tcpdump_start()
            tcpdumpB.tcpdump_start()

            # 拨测
            flag_web = "A" if case[0]["靶站A"] else "B"
            c = int(float(case[0][f"靶站{flag_web}-拨测次数"]))
            t = int(float(case[0][f"靶站{flag_web}-线程数"]))
            logger.info(f"开始拨测，拨测客户端：{config[f'ip_靶站{flag_web}']}，拨测url：{url}")

            with Webvisit(eval(f"socket_station{flag_web}")) as wv:
                bocemode = case[0].get("封堵模式", None)
                res_dict = wv.boce(url=url, count=c, thread_count=t, mode=bocemode if bocemode else "封堵")
            logger.info(f"拨测结果：{res_dict}")

            # 等待流超时
            logger.info("等待流超时(%sms)" % timeout_flow)
            time.sleep(timeout_flow / 1000 * 2 + 2)

            # 查询命中情况
            block_count = dpistat.marex_eupolicy2dict().get("rule match", {}).get("data", {}).get(command_index, "0")
            logger.info(f"封堵策略命中次数，策略编号：{command_index}，命中次数：{block_count}")

            # 停止tcpdump
            logger.info("停止抓包")
            rst_tcpdump.tcpdump_stop()
            tcpdumpA.tcpdump_stop()
            tcpdumpB.tcpdump_stop()
            logger.info("下载pcap包")
            if not os.path.isdir("out"):
                os.mkdir("out")
            rst_pcap = rst_tcpdump.pcap_getfo()
            pcapname_localA = f"out/f{case[0]['用例名']}_A{int(time.time())}.pcap"
            pcapname_localB = f"out/f{case[0]['用例名']}_B{int(time.time())}.pcap"
            tcpdumpA.pcap_get(locatpath=pcapname_localA)
            tcpdumpB.pcap_get(locatpath=pcapname_localB)
            tmp_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["抓包A"],
                           f'=HYPERLINK("../{pcapname_localA}", "{pcapname_localA}")', (255, 255, 255)))
            tmp_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["抓包B"],
                           f'=HYPERLINK("../{pcapname_localB}", "{pcapname_localB}")', (255, 255, 255)))
            logger.info("下载pcap包完成")

            rst_tcpdump.client.close()
            tcpdumpA.client.close()
            tcpdumpB.client.close()

            # 下载pcapdump抓的pcap文件
            if config.get(sheet_name + "_ispcapdump", "").lower() in ("true", "1"):
                logger.info("下载pcapdump抓的pcap文件")
                pcapname_pcapdump = f"out/f{case[0]['用例名']}_pcapdump{int(time.time())}.pcap"
                logger.info(f"{pacp_dir}--->>{pcapname_pcapdump}")
                xsa.download_pcap(remotepath=pacp_dir, localpath=pcapname_pcapdump)
                tmp_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["pcapdump抓包"],
                               f'=HYPERLINK("../{pcapname_pcapdump}", "{pcapname_pcapdump}")', (255, 255, 255)))

            # 统计封堵日志数量
            logcount_e = 0
            if case[0].get("fz_block.rule", None):
                logcount_e += int(dpistat.xdrtxtlog22dict().get("ADMS_BLOCK--ADMS_LOG", {}).get("total", "0"))
            if case[0].get("策略", None):
                name = get_xdrtxtlog2name_frommarex(policy_eu[0].decode("utf-8"))
                if name in dpistat.xdrtxtlog22dict():
                    logcount_e += int(dpistat.xdrtxtlog22dict().get(name, {}).get("total", 0))
                else:
                    logcount_e += int(xsa.cmd("cat /dev/shm/xsa/eu_output.stat |grep 'all:' -A50|grep monitor_filterlog_succ_cnt|awk -F ':' '{print $2}'").strip())
            logcount = logcount_e - logcount_s
            logger.info(f"日志初始量：{logcount_s}，日志最终量：{logcount_e}，生成日志量：{logcount}")

            # 统计封堵包执行情况结束值
            eublock2dict_tmp = dpistat.eublock2dict()
            blockexe_e = int(eublock2dict_tmp.get("all", {}).get("blockExe", "0"))
            redirect_e = int(eublock2dict_tmp.get("all", {}).get("redirect", "0"))
            send_eth_e = int(eublock2dict_tmp.get("all", {}).get("send_eth", "0"))
            blockexe = blockexe_e - blockexe_s
            redirect = redirect_e - redirect_s
            send_eth = send_eth_e - send_eth_s
            logger.info(f"封堵动作初始量：{blockexe_s}，封堵动作最终量：{blockexe_e}，封堵动作执行量：{blockexe}")
            logger.info(f"重定向动作初始量：{redirect_s}，重定向动作最终量：{redirect_e}，重定向动作执行量：{redirect}")
            logger.info(f"封堵包发送初始量：{send_eth_s}，封堵包发送最终量：{send_eth_e}，封堵包发送执行量：{send_eth}")

            pcapcheck_errA = list()
            pcapcheck_errB = list()
            if case[0].get("封堵模式", None) in ("封堵", "重定向"):
                if ("kwd=1" not in str(case[0].get("策略", "")) and send_eth != int(res_dict["total"]) * 2) or ("kwd=1" in str(case[0].get("策略", "")) and send_eth < int(res_dict["total"]) * 2 * 0.95):
                    logger.error(f"封堵包发送初始量：{send_eth_s}，封堵包发送最终量：{send_eth_e}，封堵包发送执行量：{send_eth}，发送流数：{int(res_dict['total'])}")
                    mark.append(f"封堵包发送初始量：{send_eth_s}，封堵包发送最终量：{send_eth_e}，封堵包发送执行量：{send_eth}，发送流数：{int(res_dict['total'])}")

                logger.info("靶站A封堵包检查")
                try:
                    if not case[0]["靶站B"] and bocemode == "重定向":
                        logger.info(f"针对靶站A抓包，{case[0].get('封堵模式', '')}模式下不校对")
                    else:
                        pcapcheck_errA.extend(list(map(lambda x: f"抓包A：{x}", rst_check(pcap=pcapname_localA, direction=0 if case[0]["靶站B"] else 1))))
                except Exception as e:
                    logger.info(f"抓包Aerror：{e}")
                    mark.append(f"抓包Aerror：{e}")

                logger.info("靶站B封堵包检查")
                try:
                    if not case[0]["靶站A"] and bocemode == "重定向":
                        logger.info(f"针对靶站B抓包，{case[0].get('封堵模式', '')}模式下不校对")
                    else:
                        pcapcheck_errB.extend(list(map(lambda x: f"抓包A：{x}", rst_check(pcap=pcapname_localB, direction=0 if case[0]["靶站A"] else 1))))
                except Exception as e:
                    logger.info(f"抓包Berror：{e}")
                    mark.append(f"抓包Berror：{e}")

                # 误封堵检查
                # 计算拨测请求包中的四元组
                if case[0]['靶站A']:
                    boce_4tuple = extract_4tuple_from_pcap(pcapname_localA)
                else:
                    boce_4tuple = extract_4tuple_from_pcap(pcapname_localB)
                # 计算eu发送的封堵包中的四元组
                rst_4tuple = extract_4tuple_from_pcap(rst_pcap)
                logger.info(f"封堵包中检查实际发送的封堵包四元组数量：{len(rst_4tuple)}")
                # logger.info(str(rst_4tuple))
                err_tmplist = list()
                for item in rst_4tuple:
                    item_f = {'src_ip': item["dst_ip"], 'src_port': item["dst_port"], 'dst_ip': item["src_ip"],
                              'dst_port': item["src_port"]}
                    if item in boce_4tuple or item_f in boce_4tuple:
                        pass
                    else:
                        logger.info(f"误封：封堵包四元组匹配失败：{item}")
                        err_tmplist.append(item)
                if err_tmplist:
                    mark.append(f"误封：封堵包四元组匹配失败: {err_tmplist}")

            if case[0].get("封堵模式", None) in ("封堵",):
                if ("kwd=1" in str(case[0].get("策略", "")) and float(int(res_dict["success"]) / int(res_dict['total'])) <= 0.05) or ("kwd=1" not in str(case[0].get("策略", "")) and float(int(res_dict["success"]) / int(res_dict['total'])) <= 0.01):
                    tmp_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["成功率"], res_dict["success_ratio"], (255, 255, 255)))
                else:
                    mark.append(f"成功率：{(int(res_dict['success']) / int(res_dict['total'])):.2%}")
                    tmp_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["成功率"], res_dict["success_ratio"], (255, 0, 0)))

                if is_report == False or ("kwd=1" in str(case[0].get("策略", "")) and int(logcount) / int(res_dict["total"]) >= 0.95) or ("kwd=1" not in str(case[0].get("策略", "")) and int(logcount) / int(res_dict["total"]) >= 0.99):
                    tmp_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["日志数量"], logcount, (255, 255, 255)))
                else:
                    mark.append(f"日志率：{(int(logcount) / int(res_dict['total'])):.2%}")
                    tmp_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["日志数量"], logcount, (255, 0, 0)))

                if ("kwd=1" not in str(case[0].get("策略", "")) and blockexe != int(res_dict["total"])) or ("kwd=1" in str(case[0].get("策略", "")) and blockexe < int(res_dict["total"]) * 0.95):
                    logger.error(f"封堵动作初始量：{blockexe_s}，封堵动作最终量：{blockexe_e}，封堵动作执行量：{blockexe}，发送流数：{int(res_dict['total'])}")
                    mark.append(f"封堵动作初始量：{blockexe_s}，封堵动作最终量：{blockexe_e}，封堵动作执行量：{blockexe}，发送流数：{int(res_dict['total'])}")

            elif case[0].get("封堵模式", None) in ("重定向", "弹窗"):
                if float(int(res_dict["success"]) / int(res_dict['total'])) > 0.90:
                    tmp_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["成功率"], res_dict["success_ratio"], (255, 255, 255)))
                else:
                    mark.append(f"成功率：{(int(res_dict['success']) / int(res_dict['total'])):.2%}")
                    tmp_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["成功率"], res_dict["success_ratio"], (255, 0, 0)))

                if is_report == False or int(logcount) / int(res_dict["total"]) > 0.90:
                    tmp_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["日志数量"], logcount, (255, 255, 255)))
                else:
                    mark.append(f"日志率：{(int(logcount) / int(res_dict['total'])):.2%}")
                    tmp_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["日志数量"], logcount, (255, 0, 0)))

                if redirect != int(res_dict["total"]):
                    logger.error(f"重定向动作初始量：{redirect_s}，重定向动作最终量：{redirect_e}，重定向动作执行量：{redirect}，发送流数：{int(res_dict['total'])}")
                    mark.append(f"重定向动作初始量：{redirect_s}，重定向动作最终量：{redirect_e}，重定向动作执行量：{redirect}，发送流数：{int(res_dict['total'])}")

            else:
                tmp_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["成功率"], res_dict["success_ratio"], (255, 255, 255)))
                if logcount == 0:
                    tmp_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["日志数量"], logcount, (255, 255, 255)))
                else:
                    mark.append(f"日志数量不为0：{logcount}")
                    tmp_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["日志数量"], logcount, (255, 0, 0)))

            tmp_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["成功次数"], res_dict["success"], (255, 255, 255)))
            tmp_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["失败次数"], res_dict["fail"], (255, 255, 255)))
            tmp_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["耗时"], res_dict["time"], (255, 255, 255)))

            # 结果判定
            if case[0].get("封堵模式", None) in ("封堵",):
                if mark or ("kwd=1" in str(case[0].get("策略", "")) and max(len(pcapcheck_errA), len(pcapcheck_errB)) > int(res_dict["total"]) * 0.05) or ("kwd=1" not in str(case[0].get("策略", "")) and max(len(pcapcheck_errA), len(pcapcheck_errB)) > int(res_dict["total"]) * 0.01):
                    tmp_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["结果"], "Failed", (255, 0, 0)))
                else:
                    tmp_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["结果"], "Pass", (255, 255, 255)))
            elif case[0].get("封堵模式", None) in ("重定向",):
                if mark or max(len(pcapcheck_errA), len(pcapcheck_errB)) > int(res_dict["total"]) * 0.1:
                    tmp_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["结果"], "Failed", (255, 0, 0)))
                else:
                    tmp_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["结果"], "Pass", (255, 255, 255)))
            else:
                if mark or float(res_dict["success_ratio"].strip('%')) / 100 <= 0.99:
                    tmp_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["结果"], "Failed", (255, 0, 0)))
                else:
                    tmp_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["结果"], "Pass", (255, 255, 255)))

            tmp_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["备注"], "\n".join(mark + pcapcheck_errA + pcapcheck_errB), (255, 255, 255)))

            # 写结果到excel
            logger.info(tmp_list)
            result_deal(
                xls=path, sheet_index=sheet_name, result_list=tmp_list,
                row=case[0]["row"], head2col=sheet_name2head2col[sheet_name],
                mark=mark, only_write=True, newpath=newpath
            )

            # 清空策略
            xsa.marex_policy_update(policy=[], path=action2policyfile[action])
            counter += 1

        # 停止分流端口
        if sum(list(map(lambda x: 1 if x[0]["执行状态"] and int(x[0]["执行状态"]) == 1 else 0, cases.values()))) > 0:
            logger.info("关闭分流端口")
            stop_mirror(
                hostname=npb_host, port=npb_port, username=npb_username,
                password=npb_password, inport=npb_inport, outport=npb_outport
            )

    xsa.client.close()
    dpistat.client.close()
