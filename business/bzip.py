#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2024/10/7
# @Author  : weihang
# @File    : bzip.py

"""
BZIP 日志处理模块
处理批量压缩日志测试
"""

import copy
import datetime
import io
import json
import logging
import os
import random
import re
import time
from itertools import chain
from utils.common import gettime, wait_until, wait_not_until, get_flow_timeout, IPRangeSet, setup_logging
from utils.log_handler import DynamicFileHandler
from utils.log_config import build_log_filename
from core.result import result_deal
from device.socket_linux import SocketLinux
from device.dpi import Dpi
from monitor.dpistat import CheckDpiStat
from core.pcap import pcap_send
from utils.ini_handler import INIHandler
from core.excel_reader import parser_excel
from utils.dpi_helper import dpi_init
from utils.marex_helper import get_action_from_marex, get_type_from_marex
from utils.xml_helper import xml2dict
from utils.crypto_helper import decrypt_file_load
from utils.xml_helper import Xml
from core.comparer import compare_exp
from utils.log_parser import monitorlog
from device.dpi_constants import (
    uploadfile, reportfile, house_ipsegsfile, pcip_ipsegsfile,
    comon_inifile, ydcommoninfo_rulefile, commoninfo_rulefile,
    access_log_rulefile, xsa_jsonfile, fz_block_rulefile,
    action2policyfile, provinceId2provID, bzip_ipsegsfile
)

logger = setup_logging(log_file_path="log/bzip.log", logger_name="bzip")

# 日志策略：by_case=按用例拆分，by_sheet=按 sheet 拆分
LOG_STRATEGY = "by_sheet"

# 导入需要添加 DynamicFileHandler 的模块
import device.socket_linux as socket_linux_module
import monitor.dpistat as dpistat_module
import device.dpi as dpi_module
import core.result as result_module


def bzip(p_excel: dict, sheets, path="用例", newpath=None,
         session_id: str = None, log_strategy: str = LOG_STRATEGY):
    """处理 BZIP 批量压缩日志测试。

    Args:
        p_excel: Excel 解析结果
        sheets: sheet 名称列表
        path: Excel 文件路径
        newpath: 新 Excel 文件路径
        session_id: 会话ID，用于日志文件名标识
        log_strategy: 日志策略，"by_case" 按用例生成日志，"by_sheet" 按sheet生成日志
    """
    sheet_name2cases = p_excel["sheet_name2cases"]
    sheet_name2head2col = p_excel["sheet_name2head2col"]
    config = p_excel["config"]
    config_dev = p_excel["config_dev"]

    # 检查 session_id
    if session_id is None:
        session_id = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        logger.warning(f"session_id 为空，自动生成：{session_id}")

    # Socket连接生成
    socket_xsa = (config["ip_xsa"], int(config["port_xsa"]))
    socket_xdr = (config["ip_xdr"], int(config["port_xdr"])) if config["ip_xdr"] and config["ip_xdr"] != config["ip_xsa"] else socket_xsa
    socket_scapy_send = (config["host_scapy_send"], int(config["port_scapy_send"]))
    socket_logserver = (
        config["ip_logserver"] if config["ip_logserver"] else config["ip_xsa"],
        int(config["port_logserver"])
    )

    logserver = SocketLinux(socket_logserver)
    dpi_xsa = Dpi(socket_xsa)
    dpi_xdr = Dpi(socket_xdr)
    stat_dpi_xsa = CheckDpiStat(socket_xsa)

    # ==================== 创建 DynamicFileHandler ====================
    modules = [dpi_xsa, dpi_xdr, stat_dpi_xsa, logserver,
               dpi_module, socket_linux_module, dpistat_module, result_module]

    # 创建 DynamicFileHandler
    dynamic_handler = DynamicFileHandler(log_dir="log", level=logging.DEBUG)

    # 确保日志目录存在
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "log")
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # 添加到所有模块的 logger
    for module in modules:
        if hasattr(module, 'logger'):
            for handler in module.logger.handlers[:]:
                if isinstance(handler, logging.FileHandler):
                    module.logger.removeHandler(handler)
            module.logger.addHandler(dynamic_handler)

    # 为当前模块也添加 handler
    for handler in logger.handlers[:]:
        if isinstance(handler, logging.FileHandler):
            logger.removeHandler(handler)
    logger.addHandler(dynamic_handler)

    try:
        # 执行用例
        counter = 1

        for sheet_name in sheets:
            # 根据策略创建日志文件
            if log_strategy == "by_sheet":
                log_file = build_log_filename(session_id, sheet_name, strategy=log_strategy)
                dynamic_handler.switch_file(log_file)
                logger.info(f"日志文件：{log_file}")

            logger.info(f"---------------------开始执行excel：{path}，sheet：{sheet_name}---------------------")
            if sheet_name != sheets[0]:
                path = newpath

            ignore_fields = config.get(f"{sheet_name}_ignore_fields", None)
            length_fields = config.get(f"{sheet_name}_length_fields", None)
            time_fields = config.get(f"{sheet_name}_time_fields", None)

            cases = sheet_name2cases[sheet_name]
            exp_heads = list()
            act_heads = list()
            for field in p_excel["sheet_name2heads"][sheet_name]:
                if field and field.startswith("act_"):
                    act_heads.append(field)
                elif field and field.startswith("exp_"):
                    exp_heads.append(field)

            # DPI环境初始化
            if sum(list(map(lambda x: 1 if x[0]["执行状态"] and int(x[0]["执行状态"]) == 1 else 0, cases.values()))) > 0:
                devconfig_tmp = dict()
                tmp = config[sheet_name + "_devconfig"].split(",") if config[sheet_name + "_devconfig"] else []
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

                if config["ip_xsa"] == config["ip_xdr"] and config["port_xsa"] == config["port_xdr"]:
                    res_dpi_init = dpi_init(dpi_xsa, **devconfig_tmp)
                    logger.info("停止dpi_monitor和policyserver")
                    dpi_xsa.dpi_monitor(op="stop")
                    dpi_xsa.policyserver(op="stop")
                else:
                    dpi_init(dpi_xsa, **devconfig_tmp)
                    dpi_init(dpi_xdr, **devconfig_tmp)
                    logger.info("停止dpi_monitor和policyserver")
                    dpi_xsa.dpi_monitor(op="stop")
                    dpi_xsa.policyserver(op="stop")
                    dpi_xdr.dpi_monitor(op="stop")
                    dpi_xdr.policyserver(op="stop")
            else:
                continue

            dpimode = dpi_xsa.get_dpimode()
            # 重新获取流超时时间
            timeout_flow = get_flow_timeout(dpi_xsa.json_get(path="/opt/dpi/xsaconf/xsa.json"))
            xsa_json = dpi_xsa.json_get("/opt/dpi/xsaconf/xsa.json")
            bzip_count_time = xsa_json["xdrtxtlog"]["bzip_count_time"]
            bzip_log_write_path = xsa_json["xdrtxtlog"]["bzip_log_write_path"]

            # 等待流超时
            logger.info("等待流超时(%s ms)" % (timeout_flow * 2))
            dpi_xsa.wait_flow_timeout(timeout=timeout_flow / 1000 * 2)
            # 等待写文件完成
            logger.info("等待写文件完成(%s s)" % 100)
            stat_dpi_xsa.wait_fclose(timeout=100)
            time.sleep(2)

            # 更新 pcip_ipsegs.txt
            ipsegs_txt = config.get("pcip_ipsegs", "").strip() if config.get(f"{sheet_name}_ispc", None) else ""
            logger.info("pcip_ipsegs加载：\n%s" % ipsegs_txt)
            ipsegs_lines = list(set(ipsegs_txt.split("\n")))
            with io.BytesIO() as f:
                f.write("\n".join(ipsegs_lines).encode("utf-8"))
                f.seek(0)
                dpi_xsa.putfo(f, pcip_ipsegsfile, overwrite=True)

            # 更新house_ipsegs.txt
            ipsegs_list = config["house_ipsegs"].strip().split("\n")
            logger.info("house_ipsegs加载：\n%s" % ("\n".join(ipsegs_list)))
            houseid, houseid_inner, a, b = ipsegs_list[0].strip().split("|")
            ipsegs_list = list(map(lambda x: x.encode("utf-8"), ipsegs_list))
            dpi_xsa.marex_policy_update(policy=ipsegs_list, path=house_ipsegsfile, md5check=True)

            # 获取业务策略
            policys = list()
            policy_dict = dict()
            commandid2logfiletype = dict()
            darea2flag = {"1": "is", "2": "ds", "3": "ns"}

            for case_name, case in cases.items():
                if "策略" not in case[0] or not case[0]["用例名"] or (case[0]["执行状态"] and int(case[0]["执行状态"])) != 1:
                    continue

                for command in list(map(lambda x: x["策略"], case)):
                    if type(command) == str:
                        commands = command.strip().split("\n")
                    else:
                        continue
                    commands = list(map(lambda x: re.sub(r"hid=\d+,", f"hid={houseid_inner},", x), commands))
                    commands = list(map(lambda x: re.sub(r"^\d+\s", f"{random.randint(1000000, 9999999)} ", x), commands))
                    commands = list(map(lambda x: re.sub(r"(?<=cid=)\d+,|(?<=prex=)\d+,", f"{random.randint(10000000, 99999999)},", x), commands))
                    policys += commands

            for command in policys:
                commandid = re.search(r"(?<=cid=)\d+|(?<=prex=)\d+", command).group()
                action = get_action_from_marex(command)
                if action in policy_dict:
                    policy_dict[action].append(command)
                else:
                    policy_dict[action] = [command]

                command_type = get_type_from_marex(command)
                if action in ("mirr", "pcapdump"):
                    darea = re.search(r"action\.do\s*{.+?darea=(\w+),", command).groups()[0]
                else:
                    darea = None

                if command_type == "monit" and not config.get(f"{sheet_name}_ispc", None):
                    commandid2logfiletype[commandid] = "monitor"
                elif command_type == "monit" and config.get(f"{sheet_name}_ispc", None) and dpimode in ("com_cucc_isbns", "com_ctcc_isbns"):
                    commandid2logfiletype[commandid] = "ismonitor_pc"
                elif command_type == "monit" and config.get(f"{sheet_name}_ispc", None) and dpimode in ("com_cmcc_is",):
                    commandid2logfiletype[commandid] = "monitor_pc"
                elif command_type == "filt" and not config.get(f"{sheet_name}_ispc", None):
                    commandid2logfiletype[commandid] = "filter"
                elif command_type == "filt" and config.get(f"{sheet_name}_ispc", None) and dpimode in ("com_cucc_isbns", "com_ctcc_isbns"):
                    commandid2logfiletype[commandid] = "isfilter_pc"
                elif command_type == "filt" and config.get(f"{sheet_name}_ispc", None) and dpimode in ("com_cmcc_is",):
                    commandid2logfiletype[commandid] = "filter_pc"
                elif action == "mirr" and not config.get(f"{sheet_name}_ispc", None):
                    commandid2logfiletype[commandid] = f"mirrorvlan_{darea2flag[darea]}"
                elif action == "mirr" and config.get(f"{sheet_name}_ispc", None) and dpimode in ("com_cucc_isbns", "com_ctcc_isbns"):
                    commandid2logfiletype[commandid] = f"mirrorlog_pc"
                elif action == "mirr" and config.get(f"{sheet_name}_ispc", None) and dpimode in ("com_cmcc_is",):
                    commandid2logfiletype[commandid] = f"mirrorvlan_{darea2flag[darea]}_pc"
                elif action == "pcapdump" and not config.get(f"{sheet_name}_ispc", None):
                    commandid2logfiletype[commandid] = f"pcapdump_{darea2flag[darea]}"
                elif action == "pcapdump" and config.get(f"{sheet_name}_ispc", None) and dpimode in ("com_cucc_isbns", "com_ctcc_isbns"):
                    commandid2logfiletype[commandid] = f"pcapdumplog_pc"
                elif action == "pcapdump" and config.get(f"{sheet_name}_ispc", None) and dpimode in ("com_cmcc_is",):
                    commandid2logfiletype[commandid] = f"pcapdump_{darea2flag[darea]}_pc"

            for key in policy_dict.keys():
                logger.info(f"{key}策略：\n%s" % ("\n".join(policy_dict[key])))
                policy_dict[key] = list(map(lambda x: x.encode("utf-8"), policy_dict[key]))

            # 更新upload.rule
            logtype2dpath = dict()
            logtype2spath = dict()
            dpath2spath = dict()
            uploadmode = uploadip = uploadport = uploaduser = uploadpwd = uploaddst = uploadsrc = a = uploadex_field = uploadzippwd = None
            dpath_log = spath_log = count_fopen_ok = logfilecount_s = None
            tmppath = []
            if config.get(f"{sheet_name}_uploadrule", None):
                uploadrule_list = config.get(f"{sheet_name}_uploadrule", "").strip().split("\n")
                logger.info("upload策略加载：\n%s" % ("\n".join(uploadrule_list)))
                for uploadrule in uploadrule_list:
                    uploadrule_split = uploadrule.strip().split()
                    if len(uploadrule_split) == 10:
                        uploadmode, uploadip, uploadport, uploaduser, uploadpwd, uploaddst, uploadsrc, a, uploadex_field, uploadzippwd = uploadrule_split
                    elif len(uploadrule_split) == 9:
                        uploadmode, uploadip, uploadport, uploaduser, uploadpwd, uploaddst, uploadsrc, a, uploadex_field = uploadrule_split
                    elif len(uploadrule_split) == 8:
                        uploadmode, uploadip, uploadport, uploaduser, uploadpwd, uploaddst, uploadsrc, a = uploadrule_split
                        uploadex_field = "0|1|1"
                    tmppath.extend([config["sftppath_logserver"].strip().rstrip("/") + "/" + uploaddst.strip().strip("/"), uploadsrc])

                    # 确定上报的源和目的路径
                    # 日志路径
                    if uploadex_field == "0|0|3":
                        # 日志上报路径
                        curdate = datetime.datetime.now().strftime('%Y-%m-%d')
                        dpath_log = config["sftppath_logserver"].strip().rstrip("/") + "/" + uploaddst.strip().strip("/") + f"/{curdate}"
                        # 日志源路径
                        spath_log = uploadsrc
                    elif uploadex_field == "1|21|3":
                        # 日志上报路径
                        curdate = datetime.datetime.now().strftime('%Y-%m-%d')

                        dpath_log4 = config["sftppath_logserver"].strip().rstrip("/") + "/" + uploaddst.strip().strip("/") + f"/{houseid}/4/{curdate}"
                        dpath_log5 = config["sftppath_logserver"].strip().rstrip("/") + "/" + uploaddst.strip().strip("/") + f"/{houseid}/5/{curdate}"
                        dpath_log11 = config["sftppath_logserver"].strip().rstrip("/") + "/" + uploaddst.strip().strip("/") + f"/{houseid}/11/{curdate}"
                        if uploaddst.endswith("_PC"):
                            logtype2dpath.update({"monitor_pc": [dpath_log4], "filter_pc": [dpath_log5], "pcapdump_log_pc": [dpath_log11]})
                        else:
                            logtype2dpath.update({"monitor": [dpath_log4], "filter": [dpath_log5], "pcapdump_log": [dpath_log11]})
                        # 日志源路径
                        spath_log4 = f"{uploadsrc}/{houseid}/4"
                        spath_log5 = f"{uploadsrc}/{houseid}/5"
                        spath_log11 = f"{uploadsrc}/{houseid}/11"
                        if uploaddst.endswith("_PC"):
                            logtype2spath.update({"monitor_pc": [spath_log4], "filter_pc": [spath_log5], "pcapdump_log_pc": [spath_log11]})
                        else:
                            logtype2spath.update({"monitor": [spath_log4], "filter": [spath_log5], "pcapdump_log": [spath_log11]})
                    elif uploadex_field in ("0|1|0", "0|1|1", "0|2"):
                        # 日志上报路径
                        dpath_log = config["sftppath_logserver"].strip().rstrip("/") + "/" + uploaddst.strip().strip("/")
                        # 日志源路径
                        spath_log = f"{uploadsrc}" if uploadsrc else ""
                        if "PCAPDUMP" in (spath_log or ""):
                            if "pcapdump_log" in logtype2dpath:
                                logtype2dpath["pcapdump_log"].append(dpath_log)
                                logtype2spath["pcapdump_log"].append(spath_log)
                            else:
                                logtype2dpath["pcapdump_log"] = [dpath_log]
                                logtype2spath["pcapdump_log"] = [spath_log]
                        elif "MIRRORVLAN" in (spath_log or "") or "MIRRORLOG" in (spath_log or ""):
                            if "mirrorvlan_log" in logtype2dpath:
                                logtype2dpath["mirrorvlan_log"].append(dpath_log)
                                logtype2spath["mirrorvlan_log"].append(spath_log)
                            else:
                                logtype2dpath["mirrorvlan_log"] = [dpath_log]
                                logtype2spath["mirrorvlan_log"] = [spath_log]
                        elif "MONITOR" in (spath_log or ""):
                            if "monitor" in logtype2dpath:
                                logtype2dpath["monitor"].append(dpath_log)
                                logtype2spath["monitor"].append(spath_log)
                            else:
                                logtype2dpath["monitor"] = [dpath_log]
                                logtype2spath["monitor"] = [spath_log]
                        elif "FILTER" in (spath_log or ""):
                            if "filter_pc" in logtype2dpath:
                                logtype2dpath["filter"].append(dpath_log)
                                logtype2spath["filter"].append(spath_log)
                            else:
                                logtype2dpath["filter"] = [dpath_log]
                                logtype2spath["filter"] = [spath_log]

                uploadrule_list = list(map(lambda x: x.encode("utf-8"), uploadrule_list))
                dpi_xdr.marex_policy_update(policy=uploadrule_list, path=uploadfile, md5check=True)

            report_port = None
            reportrule_list = None
            if config.get(f"{sheet_name}_reportrule", None):
                reportrule_list = config.get(f"{sheet_name}_reportrule", "").strip().split("\n")
                logger.info("report策略加载：\n%s" % ("\n".join(reportrule_list)))
                report_port = int(reportrule_list[0].strip().split("|")[8].rsplit(":", 1)[1])
                reportrule_b_list = list(map(lambda x: x.encode("utf-8"), reportrule_list))
                dpi_xdr.marex_policy_update(policy=reportrule_b_list, path=reportfile, md5check=True)
                logtype2spath.update({"monitor": ["/dev/shm/xsa/socket_log", "/dev/shm/xsa/socket_upload"]})

            # 清空目的和源路径
            logger.info(f"上传路径：{logtype2dpath}")
            logger.info(f"源路径：{logtype2spath}")
            for path_tmp in set(chain(chain(*logtype2dpath.values()), chain(*logtype2spath.values()), [bzip_log_write_path])):
                logger.info(f"清空路径：{path_tmp}")
                dpi_xdr.cmd(r"find %s -type f -exec rm -f {} \;" % path_tmp)

            # 更新bzip_ipsegs.txt
            ipsegs_txt = config["bzip_ipsegs"].strip()
            logger.info("bzip_ipsegs加载：\n%s" % ipsegs_txt)
            ipsegs_set = IPRangeSet()
            ipsegs_lines = ipsegs_txt.split("\n")
            for ipsegs_line in ipsegs_lines:
                ip_start, ip_end = ipsegs_line.split("|")
                ipsegs_set.add_range(ip_start, ip_end)
            with io.BytesIO() as f:
                f.write(ipsegs_txt.encode("utf-8"))
                f.seek(0)
                dpi_xsa.putfo(f, bzip_ipsegsfile, overwrite=True)

            # 更新common.ini
            common_ini = config["common_ini"].strip()
            logger.info("common.ini加载")
            dpi_xsa.putfo(fl=io.BytesIO(common_ini.encode("utf-8")), remotepath=comon_inifile, overwrite=False)
            ini_data = INIHandler(common_ini)
            idcId = ini_data.get(section="global_com", option="idcId")
            provinceId = ini_data.get(section="global_com", option="provinceId")
            compressionFormat = ini_data.get(section="global_is", option="compressionFormat")
            hashAlgorithm = ini_data.get(section="global_is", option="hashAlgorithm")
            encryptAlgorithm = ini_data.get(section="global_is", option="encryptAlgorithm")
            authkey = ini_data.get(section="global_is", option="authkey")
            secretkey = ini_data.get(section="global_is", option="secretkey")
            cryptvector = ini_data.get(section="global_is", option="cryptvector")
            crypttype = ini_data.get(section="global_is", option="crypttype")
            houseid = ini_data.get(section="global_com", option="houseid")
            deviceId = ini_data.get(section="global_com", option="deviceId")
            xsa_json2dict = dpi_xsa.json_get(path=xsa_jsonfile)
            dev_ip = xsa_json2dict.get("devinfo", {}).get("dev_ip", "")

            # 更新ydcommoninfo.rule
            ydcommoninfo_rule = config["ydcommoninfo_rule"].strip() if config["ydcommoninfo_rule"] else ""
            logger.info("ydcommoninfo.rule加载")
            dpi_xsa.putfo(fl=io.BytesIO(ydcommoninfo_rule.encode("utf-8")), remotepath=ydcommoninfo_rulefile, overwrite=False)

            # 更新commoninfo.rule
            commoninfo_rule = config["commoninfo_rule"].strip() if config["commoninfo_rule"] else ""
            logger.info("commoninfo.rule加载")
            dpi_xsa.putfo(fl=io.BytesIO(commoninfo_rule.encode("utf-8")), remotepath=commoninfo_rulefile, overwrite=False)

            # 更新access_log.rule
            access_log_rule = config.get("access_log_rule", None)
            if access_log_rule is not None:
                logger.info("access_log.rule加载")
                dpi_xsa.putfo(fl=io.BytesIO(access_log_rule.encode("utf-8")), remotepath=access_log_rulefile, overwrite=False)

            # 启动socket监听
            if report_port:
                logger.info(f"日志服务器上启动端口监听：{report_port}")
                logger.info(logserver.socketserver_start(port=report_port))
                logserver.socketserver_dataclean()

                for reportrule in reportrule_list:
                    reportrule = reportrule.strip()
                    if not reportrule:
                        continue
                    tmp = reportrule.strip().split(r"|")[8].rsplit(":", 1)
                    if len(tmp) == 2:
                        ip, port = tmp
                    else:
                        break
                    ip = ip[1:-1]
                    cmd = r"cat /dev/shm/xsa/datarpt_conn.stat |grep %s|grep %s|awk '{print $3}'" % (ip, port)
                    logger.info(cmd)
                    wait_not_until(dpi_xdr.cmd, '', step=1, timeout=120, args=cmd)
                    wait_not_until(dpi_xdr.cmd, '-1\n', step=1, timeout=120, args=cmd)

            # 清空策略
            logger.info("清空策略")
            if dpi_xsa.isfile(fz_block_rulefile):
                logger.info(f"清空idc_fz策略：{fz_block_rulefile}")
                dpi_xsa.marex_policy_update(policy=[], path=fz_block_rulefile)
            for policyfile in action2policyfile.values():
                dpi_xsa.marex_policy_update(policy=[], path=policyfile)

            logger.info("业务策略加载")
            for action, policys in policy_dict.items():
                wait_until(stat_dpi_xsa.get_policy_total, "0", 2, 60, action)
                dpi_xsa.marex_policy_update(policy=policys, path=action2policyfile[action])
                wait_until(stat_dpi_xsa.get_policy_total, str(len(policys)), 2, 60, action)
            time.sleep(2)

            # 记录开始时间
            time_s = int(dpi_xsa.cmd('date +%s').strip())

            logger.info("执行发包，发包速率控制：200K/s")
            pcaps_tmp = list()
            for case_name, case in cases.items():
                if not case[0].get("用例名", None) or str(case[0].get("执行状态", "")) != "1":
                    continue
                for i in range(len(case)):
                    if case[i].get("pcap", None):
                        path_flag = "/" if config["pcap_path"].startswith("/") else "\\"
                        pcaps = list(map(lambda x: config["pcap_path"].rstrip(path_flag) + path_flag + x.lstrip(path_flag), case[i]["pcap"].split()))
                        if path_flag == "\\":
                            pcaps = list(map(lambda x: x.replace("/", path_flag), pcaps))
                        pcaps_tmp += pcaps

            if pcaps_tmp and config.get(sheet_name + "_sendpktsmode") == "scapy_send":
                pcap_send(
                    client=socket_scapy_send,
                    pcaps=pcaps_tmp,
                    uplink_iface=config.get("eth_scapy_send", ""),
                    downlink_iface=None,
                    uplink_vlan=None,
                    downlink_vlan=None,
                    mbps=0.2,
                    verbose=None,
                    force_ip_src=None,
                    force_ip_dst=None,
                    force_sport=None,
                    force_dport=None,
                    force_build_flow=None,
                    bufsize=1024
                )
            else:
                raise RuntimeError(f"请检查excel中的pcap路径，未找到，pcaps_tmp={pcaps_tmp}，sendpktsmode={config.get(sheet_name + '_sendpktsmode')}")

            # 等待流超时
            logger.info("等待流超时(%s ms)" % (timeout_flow + 2000))
            time.sleep(timeout_flow / 1000 + 2)

            # 等待写文件完成
            logger.info("等待写文件完成(%s s)" % 100)
            stat_dpi_xsa.wait_fclose(timeout=100)
            # 等待写统计日志文件生成时间
            time.sleep(bzip_count_time)

            # 记录结束时间
            time_e = int(dpi_xsa.cmd('date +%s').strip())

            # 初始化解压目录
            logger.info("初始化解压目录：/tmp/txt")
            tmpdir = "/tmp/txt"
            if logserver.isdir(tmpdir):
                logserver.cmd(r"find %s -type f -exec rm -f {} \;" % tmpdir)
            else:
                logserver.mkdir(dir=tmpdir)

            exp_log_list = list()

            # 等待文件上报
            for spath_log in list(set(chain(*list(logtype2spath.values())))):
                logger.info("%s:等待文件上报:超时时间%ss" % (spath_log, timeout_flow * 2))
                cmd = r"find %s -type f|wc -l" % spath_log
                logger.info(cmd)
                wait_until(logserver.cmd, '0\n', step=1, timeout=timeout_flow * 2, args=cmd)

            logger.info("预期值提取开始")
            # 从日志服务器提取预期值
            path_log_tmp = list()
            for logtype, dpath_logs in logtype2dpath.items():
                # 按目录处理
                # 提取commandid对应的序列号
                commandidseq = 0
                for field in p_excel["sheet_name2heads"][logtype]:
                    if field and field.startswith("act_"):
                        if field == config[f"{logtype}_keyvalue"]:
                            break
                        else:
                            commandidseq += 1

                for dpath_log in dpath_logs:
                    if dpath_log in path_log_tmp:
                        continue
                    else:
                        path_log_tmp.append(dpath_log)

                    logger.info(f"处理日志类型：{logtype}，日志路径：{dpath_log}")
                    logserver.cmd(r"find %s -type f -exec rm -f {} \;" % tmpdir)
                    logfilecount_e = logserver.cmd(args=f"ls {dpath_log}|wc -l")
                    logger.info(f"当前上报目录：{dpath_log} 结束时日志文件数量：{int(logfilecount_e)}")
                    if int(logfilecount_e) == 0:
                        logger.info(f"{dpath_log} 没有日志文件，跳过")
                        continue
                    cmd = "ls -rt|tail -n %s|grep %s$" % (int(logfilecount_e),
                                                          config[logtype + "_compression"] if config.get(logtype + "_compression") else config[logtype + "_filetype"])
                    response = logserver.cmd(args=cmd, cwd=dpath_log)
                    logger.info([cmd, dpath_log])
                    logger.info(response)
                    response = response.strip().split()

                    # 解压缩文件
                    if config.get(f"{logtype}_compression", None):
                        logger.info("解压缩文件")
                        for name in response:
                            if config[logtype + "_compression"] == "tar.gz" and name.endswith("tar.gz"):
                                cmd = f"tar -xzvf {name} -C {tmpdir}"
                            elif config[logtype + "_compression"] == "zip" and name.endswith("zip"):
                                cmd = f"unzip {name} -d {tmpdir}"
                            else:
                                raise RuntimeError("不支持压缩方式：%s" % config[logtype + "_compression"])
                            logger.info(cmd)
                            logger.info(logserver.cmd(args=cmd, cwd=dpath_log))
                    elif config.get(f"{logtype}_filetype", None) == "xml":
                        # xml解析成明文
                        for name in response:
                            if name.endswith("xml"):
                                content_encrypt = logserver.getfo(dpath_log.rstrip("/") + "/" + name).read()
                                content_decrypt = decrypt_file_load(xml=content_encrypt, method="fileLoad",
                                                                    inter_key=authkey, inter_skey=secretkey,
                                                                    inter_asepyl=cryptvector)
                                logserver.putfo(io.BytesIO(content_decrypt), f"{tmpdir}/{name}")
                    else:
                        for name in response:
                            logserver.cmd(args=f"cp -f {name} {tmpdir}", cwd=dpath_log)

                    # 提取日志内容
                    logger.info("提取日志内容")
                    sheet_filetype = config.get(logtype + "_filetype", None)
                    cmd = "ls -rt *%s" % sheet_filetype
                    response = logserver.cmd(args=cmd, cwd=tmpdir).strip().split()
                    if (sheet_filetype in ["txt"] or (
                            sheet_filetype == "xml" and config.get(f"{logtype}_splitflag"))) and logtype in (
                    "mirrorvlan_log", "pcapdump_log", "monitor", "filter"):
                        # 文件日志名
                        for name in response:
                            res_tmp = dict()
                            logfiletype = None
                            content = logserver.getfo(remotepath=tmpdir.rstrip("/") + "/" + name).read().decode(
                                "utf-8").strip().split("\n")
                            if config[logtype + "_exist_head"]:
                                content = content[1:]
                            for line in content:
                                # 拆分成行
                                fields = line.split(config[logtype + "_splitflag"])
                                commandid = fields[commandidseq]
                                if not logfiletype:
                                    logfiletype = commandid2logfiletype.get(commandid, None)
                                    if not logfiletype:
                                        raise RuntimeError(f"策略id：{commandid}不存在")
                                if logtype in ("mirrorvlan_log", "pcapdump_log"):
                                    if dpimode == "com_cmcc_is":
                                        sip = fields[5]
                                        dip = fields[6]
                                    elif dpimode in ("com_cucc_isbns", "com_ctcc_isbns"):
                                        sip = fields[3]
                                        dip = fields[4]
                                    else:
                                        raise RuntimeError("不支持的dpi模式：%s" % dpimode)
                                elif logtype in ("monitor", "filter"):
                                    sip = fields[4]
                                    dip = fields[6]
                                else:
                                    raise RuntimeError("不支持的日志类型（sheet页签名称）：%s" % logtype)

                                if ipsegs_set.contains(sip):
                                    ip = sip
                                elif ipsegs_set.contains(dip):
                                    ip = dip
                                else:
                                    continue
                                key = (commandid, ip)
                                if key not in res_tmp:
                                    res_tmp[key] = 1
                                else:
                                    res_tmp[key] += 1

                            for key, value in res_tmp.items():
                                exp_log = dict(zip(exp_heads,
                                                   [deviceId.rjust(6, "0")] + list(key) + [str(value), logfiletype, name,
                                                                                           gettime(4)]))
                                logger.info(exp_log)
                                exp_log_list.append(exp_log)


                    elif sheet_filetype == "xml" and not config.get(logtype + "_splitflag", None) and logtype in (
                    "monitor", "filter"):
                        log_cyclefield = config[f"{logtype}_log_cyclefield"]
                        log_xmlprefix_pattern = config[f"{logtype}_log_xmlprefix"].replace("$provID", provinceId2provID.get(
                            provinceId[:2], "999")).replace("$idcId", idcId)
                        log_xmlsuffix_pattern = config[f"{logtype}_log_xmlsuffix"]
                        logger.info(f"log_xmlprefix_pattern:\n{log_xmlprefix_pattern}")
                        logger.info(f"log_xmlsuffix_pattern:\n{log_xmlsuffix_pattern}")
                        content_list = list()
                        keyvalue_list = config[f"{logtype}_keyvalue"].split(",")
                        log_xmlprefix = None
                        log_xmlsuffix = None

                        for name in response:
                            res_tmp = dict()
                            logfiletype = None
                            content = logserver.getfo(remotepath=tmpdir.rstrip("/") + "/" + name).read().decode(
                                "utf-8").strip()
                            # 先把日志的头和尾缓存下来
                            if log_xmlprefix is None:
                                log_xmlprefix = re.findall(log_xmlprefix_pattern, content)[0]
                            if log_xmlsuffix is None:
                                log_xmlsuffix = re.findall(log_xmlsuffix_pattern, content)[0].strip()

                            content_list = re.findall(r"<%s>(?:.|\n)+?</%s>" % (log_cyclefield, log_cyclefield), content)
                            for content in content_list:
                                content_dict = xml2dict(Xml(content=content).root)
                                commandid = content_dict[config[f"{logtype}_log_cyclefield"]][config[f"{logtype}_keyname"]]
                                if not logfiletype:
                                    logfiletype = commandid2logfiletype.get(commandid, None)
                                    if not logfiletype:
                                        raise RuntimeError(f"策略id：{commandid}不存在")
                                sip = content_dict[config[f"{logtype}_log_cyclefield"]]["srcIp"]
                                dip = content_dict[config[f"{logtype}_log_cyclefield"]]["destIp"]
                                if ipsegs_set.contains(sip):
                                    ip = sip
                                elif ipsegs_set.contains(dip):
                                    ip = dip
                                else:
                                    continue
                                key = (commandid, ip)
                                if key not in res_tmp:
                                    res_tmp[key] = 1
                                else:
                                    res_tmp[key] += 1
                            for key, value in res_tmp.items():
                                exp_log = dict(zip(exp_heads,
                                                   [deviceId.rjust(6, "0")] + list(key) + [str(value), logfiletype, name,
                                                                                           gettime(4)]))
                                logger.info(exp_log)
                                exp_log_list.append(exp_log)

            # 处理socket日志
            if config.get(f"{sheet_name}_reportrule", None):
                log_byts = logserver.socketserver_data()
                res_tmp = dict()
                log_list = monitorlog(log_byts)
                for log in log_list:
                    commandid = log[config[f"monitor_keyvalue"]]
                    sip = log["s_ip"]
                    dip = log["d_ip"]
                    if ipsegs_set.contains(sip):
                        ip = sip
                    elif ipsegs_set.contains(dip):
                        ip = dip
                    else:
                        continue
                    key = (commandid, ip)
                    if key not in res_tmp:
                        res_tmp[key] = 1
                    else:
                        res_tmp[key] += 1
                for key, value in res_tmp.items():
                    logfiletype = commandid2logfiletype.get(key[0], None)
                    if not logfiletype:
                        raise RuntimeError(f"策略id：{key[0]}不存在")

                    exp_log = dict(zip(exp_heads,
                                       [deviceId.rjust(6, "0")] + list(key) + [str(value), logfiletype, "socket",
                                                                               gettime(4)]))
                    logger.info(exp_log)
                    exp_log_list.append(exp_log)

            # 提取实际值 (从 bzip 路径)
            act_log_list = list()
            logger.info("提取bzip日志内容")
            dpath_log = bzip_log_write_path.rstrip("/") + "/" + gettime(7)
            wait_until(dpi_xsa.cmd, expect_value="0\n", step=2, timeout=bzip_count_time * 2,
                       args="sudo expr $(find {} -type f | wc -l) % 2".format(dpath_log))
            logfilecount_e = dpi_xsa.cmd(args="ls|wc -l", cwd=dpath_log)
            logger.info([bzip_count_time, "结束时日志文件数量：", logfilecount_e])

            cmd = "ls *.txt"
            response = dpi_xsa.cmd(args=cmd, cwd=dpath_log)
            logger.info([cmd, dpath_log])
            logger.info(response)
            if config[f"{sheet_name}_filetype"] in ["txt"] or (
                    config[f"{sheet_name}_filetype"] == "xml" and config.get(f"{sheet_name}_splitflag", None)):
                log_lines = []
                # 文件日志名
                for name in response.strip().split():
                    content = dpi_xsa.getfo(remotepath=dpath_log.rstrip("/") + "/" + name).read().decode(
                        "utf-8").strip().split("\n")
                    if config[sheet_name + "_exist_head"]:
                        content = content[1:]
                    log_lines += content

                # 拆分成行
                type_mismatch = config.get(f"{sheet_name}_type_mismatch", "").strip().split(",")
                for line in log_lines:
                    fields = line.split(config[sheet_name + "_splitflag"])
                    # 对部分类型的日志不进行统计
                    if fields[4] in type_mismatch:
                        continue
                    act_log_list.append(dict(zip(act_heads, fields)))

            result_list = list()  # 【行，列，值，背景颜色】
            for case_name, case in cases.items():
                if not case[0]["用例名"] or (case[0]["执行状态"] and int(case[0]["执行状态"])) != 1:
                    continue

                # 按 case 策略时，每个用例切换一次日志文件
                if log_strategy == "by_case":
                    log_file = build_log_filename(session_id, sheet_name, case_name, log_strategy)
                    dynamic_handler.switch_file(log_file)
                    logger.info(f"日志文件：{log_file}")

                logger.info("%s\t核对用例日志：%s\t%s" % (
                    datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), sheet_name, case_name))

                # 状态标记
                mark = list()

                # 实际值
                logger.info("实际值格式化")
                # 针对socket日志进行融合
                key2cnt = dict()
                time_tmp = None
                for i in range(len(act_log_list) - 1, -1, -1):
                    act_log = act_log_list[i]
                    if act_log["act_filename"] == "socket":
                        act_log_list.pop(i)
                        time_act = datetime.datetime.strptime(act_log["act_time_time"], "%Y-%m-%d %H:%M:%S").timestamp()
                        if time_s <= time_act <= time_e:
                            if time_tmp is None:
                                time_tmp = act_log["act_time_time"]
                        else:
                            mark.append(
                                f"socket日志中的实际值时间[{time_act}]不在测试周期范围内，请检查目录文件：{bzip_log_write_path}")
                        key = "\t".join(
                            [act_log["act_devid"], act_log["act_CommandId"], act_log["act_IP"], act_log["act_type"],
                             act_log["act_filename"]])
                        cnt = act_log["act_cnt"]
                        if key in key2cnt:
                            key2cnt[key] += int(cnt)
                        else:
                            key2cnt[key] = int(cnt)

                for key, cnt in key2cnt.items():
                    key_tmp = copy.deepcopy(key.split("\t"))
                    key_tmp.insert(3, str(cnt))
                    key_tmp.insert(6, time_tmp)
                    act_log_list.append(dict(zip(act_heads, key_tmp)))

                if config.get(f"{sheet_name}_sort_flag", None):
                    act_sortheads = list(map(lambda x: "act" + x[3:], config.get(f"{sheet_name}_sort_flag", None).split(",")))
                    act_log_list.sort(key=lambda x: [x[i] for i in act_sortheads])

                # 预期值
                logger.info("预期值格式化")
                if config.get(f"{sheet_name}_sort_flag", None):
                    exp_sortheads = list(map(lambda x: "exp" + x[3:], config.get(f"{sheet_name}_sort_flag", None).split(",")))
                    exp_log_list.sort(key=lambda x: [x[i] for i in exp_sortheads])

                # 预期值写入case
                row_tmp = case[0].get("row", 1)
                case_template = dict(zip(list(case[0].keys()), [None] * len(case[0])))
                case_template["row"] = row_tmp
                for i in range(len(exp_log_list)):
                    if i < len(case):
                        case[i].update(exp_log_list[i])
                        case[i]["row"] = row_tmp + i
                    else:
                        fields_tmp = copy.deepcopy(case_template)
                        fields_tmp.update(exp_log_list[i])
                        fields_tmp["row"] = row_tmp + i
                        case.append(fields_tmp)

                # 预期值写入excel
                for i in range(len(case)):
                    for field, value in case[i].items():
                        if field != "row":
                            result_list.append((case[i]["row"], sheet_name2head2col[sheet_name][field],
                                                json.dumps(value) if type(value) == dict else value, (255, 255, 255)))

                # 结果对比
                logger.info("结果对比")
                datatype = None
                result_compcare = compare_exp(exp_log_list, act_log_list, case, sheet_name2head2col[sheet_name], time_s,
                                              time_e, ignore_fields=ignore_fields, length_fields=length_fields,
                                              time_fields=time_fields, datatype=datatype)
                mark += result_compcare["mark"]
                result_list += result_compcare["result_list"]

                # 写结果到excel
                logger.info(f"异常信息：{mark}")
                mark = list(map(lambda x: str(x), mark))
                if mark:
                    result_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["备注"], "\n".join(mark), None))
                    result_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["结果"], "Failed", (255, 0, 0)))
                else:
                    result_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["备注"], None, None))
                    result_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["结果"], "Pass", (0, 255, 0)))

                counter += 1

            result_deal(
                xls=path, sheet_index=sheet_name, result_list=result_list,
                row=1, head2col=sheet_name2head2col[sheet_name],
                mark=[], only_write=False, newpath=newpath
            )

    finally:
        # 清理所有 FileHandler，防止日志重复输出
        dynamic_handler.close()
        for module in modules:
            if hasattr(module, 'logger'):
                for handler in module.logger.handlers[:]:
                    if isinstance(handler, logging.FileHandler):
                        module.logger.removeHandler(handler)
        for handler in logger.handlers[:]:
            if isinstance(handler, logging.FileHandler):
                logger.removeHandler(handler)

    logserver.client.close()
    dpi_xsa.client.close()
    dpi_xdr.client.close()
    stat_dpi_xsa.client.close()
