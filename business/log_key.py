#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2024/10/7
# @Author  : weihang
# @File    : log_key.py

"""
关键字日志处理模块
处理 accesslog、s_accesslog、monitor、filter、mirrorvlan_log、pcapdump_log、
vpn_block、vpn_block_kk、vpn_block_inner、dns_parse、fz_filter 等日志测试
"""

import copy
import datetime
import io
import json
import logging
import os
import re
import tempfile
import time
from utils.common import gettime, get_flow_timeout, wait_until, wait_not_until, setup_logging
from utils.log_parser import monitorlog
from core.excel_reader import parser_excel, casename2exp_log, act_log
from core.comparer import compare_exp
from core.result import result_deal
from device.socket_linux import SocketLinux
from device.dpi import Dpi
from monitor.dpistat import CheckDpiStat
from core.pcap import pcap_send
from utils.ini_handler import INIHandler
from utils.dpi_helper import dpi_init
from utils.marex_helper import get_action_from_marex, get_type_from_marex
from utils.crypto_helper import decrypt_file_load
from utils.log_handler import DynamicFileHandler
from utils.log_config import build_log_filename
from utils.xml_helper import xml2dict, Xml
from utils.kafka_avro_parser import parse_kafka_avro_file
from device.dpi_constants import (
    uploadfile, reportfile, house_ipsegsfile, pcip_ipsegsfile,
    comon_inifile, ydcommoninfo_rulefile, commoninfo_rulefile,
    access_log_rulefile, xsa_jsonfile, fz_block_rulefile,
    overseaip_ipsegsfile, xdr_filter_rulefile,
    fz_action_txtfile, ip_segment_txtfile,
    action2policyfile, src2logtype
)

logger = setup_logging(log_file_path="log/log_key.log", logger_name="log_key")

# 日志策略：by_case=按用例拆分，by_sheet=按 sheet 拆分
LOG_STRATEGY = "by_sheet"

# provinceId2provID,省ID到省份ID映射
provinceId2provID = {"11": "100", "44": "200", "31": "210", "12": "220", "50": "230", "21": "240", "32": "250",
                     "42": "270", "43": "731", "51": "280", "61": "290", "13": "311", "14": "351", "41": "371",
                     "22": "431", "23": "451", "15": "471", "37": "531", "34": "551", "33": "571", "35": "591",
                     "46": "731", "45": "771", "36": "791", "52": "851", "53": "871", "54": "891", "62": "931",
                     "64": "951", "63": "971", "65": "991"}

# 导入需要添加 DynamicFileHandler 的模块
import device.socket_linux as socket_linux_module
import monitor.dpistat as dpistat_module
import device.dpi as dpi_module
import core.result as result_module


def log_key(p_excel: dict, sheets, path="用例", newpath=None,
            session_id: str = None, log_strategy: str = LOG_STRATEGY):
    """处理关键字日志测试。

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

    # 检查 session_id，如果为空则自动生成
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

    # 获取流超时时间
    xsa_json = dpi_xsa.json_get(path="/opt/dpi/xsaconf/xsa.json")
    timeout_flow = get_flow_timeout(xsa_json)

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
            # 移除原有的 FileHandler（保留 ConsoleHandler）
            for handler in module.logger.handlers[:]:
                if isinstance(handler, logging.FileHandler):
                    module.logger.removeHandler(handler)
            # 添加 DynamicFileHandler
            module.logger.addHandler(dynamic_handler)

    # 为当前模块也添加 handler
    # 先移除原有的 FileHandler
    handlers_to_remove = []
    for handler in logger.handlers[:]:
        if isinstance(handler, logging.FileHandler):
            handlers_to_remove.append(handler)
    for handler in handlers_to_remove:
        logger.removeHandler(handler)
    logger.addHandler(dynamic_handler)

    try:
        for sheet_name in sheets:
            # 根据策略创建日志文件
            if log_strategy == "by_sheet":
                log_file = build_log_filename(session_id, sheet_name, strategy=log_strategy)
                dynamic_handler.switch_file(log_file)
                logger.info(f"日志文件：{log_file}")

            logger.info(f"---------------------开始执行excel：{path}，sheet：{sheet_name}---------------------")
            if sheet_name != sheets[0]:
                path = newpath
                time.sleep(20)

            ignore_fields = config.get(f"{sheet_name}_ignore_fields", None)
            length_fields = config.get(f"{sheet_name}_length_fields", None)
            time_fields = config.get(f"{sheet_name}_time_fields", None)

            cases = sheet_name2cases[sheet_name]

            heads = list()
            for field in p_excel["sheet_name2heads"][sheet_name]:
                if field and field.startswith("act_"):
                    heads.append(field)

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

                if config["ip_xsa"] == config["ip_xdr"] and config["port_xsa"] == config["port_xdr"]:
                    if sheet_name in ("vpn_block", "vpn_block_inner", "dns_parse"):
                        dpi_xsa.mod_switch(modified_param={"oversea_switch": "1"})
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

            # 重新获取流超时时间
            xsa_json_reload = dpi_xsa.json_get(path="/opt/dpi/xsaconf/xsa.json")
            timeout_flow = get_flow_timeout(xsa_json_reload)
        xsa_json2dict = dpi_xsa.json_get(path=xsa_jsonfile)
        xsa_modcfg2dict = dpi_xsa.modcfg2dict()

        # 跨境更新overseaip_ipsegs.txt
        if sheet_name in ("vpn_block", "vpn_block_kk", "vpn_block_inner", "dns_parse"):
            overseaip_ipsegs_list = config.get(f"{sheet_name}_overseaip_ipsegs", "").strip().split("\n")
            if overseaip_ipsegs_list != [""]:
                logger.info("overseaip_ipsegs加载：\n%s" % ("\n".join(overseaip_ipsegs_list)))
                overseaip_ipsegs_list = list(map(lambda x: x.encode("utf-8"), overseaip_ipsegs_list))
                dpi_xsa.marex_policy_update(policy=overseaip_ipsegs_list, path=overseaip_ipsegsfile, md5check=True)

        # 跨境更新xdr_filter.rule
        if sheet_name in ("dns_parse",):
            xdr_filterrule_list = config.get(f"{sheet_name}_xdr_filter", "").strip().split("\n")
            if xdr_filterrule_list != [""]:
                logger.info("xdr_filterrule加载：\n%s" % ("\n".join(xdr_filterrule_list)))
                xdr_filterrule_list = list(map(lambda x: x.encode("utf-8"), xdr_filterrule_list))
                dpi_xsa.marex_policy_update(policy=xdr_filterrule_list, path=xdr_filter_rulefile, md5check=True)

        # 更新eu_active_resource.rule
        if sheet_name in ("vpn_block_kk",):
            eu_active_resource_rule = config.get("eu_active_resource_rule", "").strip()
            eu_active_resource_rule_tmp = eu_active_resource_rule.split("|")
            eu_active_resource_rule_tmp[-1] = "1"
            eu_active_resource_rule = "|".join(eu_active_resource_rule_tmp)
            logger.info(f"eu_active_resource.rule加载：{eu_active_resource_rule}")
            dpi_xsa.putfo(fl=io.BytesIO(eu_active_resource_rule.encode("utf-8")), remotepath=eu_active_resource_rulefile, overwrite=False)

        # 更新idc反诈规则
        logger.info("更新idc反诈规则")
        adms_mode = xsa_modcfg2dict.get("adms", "0")
        idc_flag = xsa_json2dict.get("adms", {}).get("idc_flag", None)
        logger.info(f"adms_mode开关：{[adms_mode]}\tidc_flag开关：{[idc_flag]}")
        if dpi_xsa.isfile(fz_block_rulefile) and adms_mode in ("1", "2") and idc_flag == 1:
            logger.info(f"清空策略：{fz_block_rulefile}")
            dpi_xsa.marex_policy_update(policy=[], path=fz_block_rulefile)
            wait_until(stat_dpi_xsa.adms_idc_debug2dict, "0", 2, 60, "adms_allrule_num")

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

        # 更新upload.rule
        uploadrule_list = list()
        uploadrule_pc_list = list()
        uploadmode = uploadip = uploadport = uploaduser = uploadpwd = uploaddst = uploadsrc = a = uploadex_field = uploadzippwd = None
        if config.get(f"{sheet_name}_uploadrule", None):
            uploadrule_list = config.get(f"{sheet_name}_uploadrule", "").strip().split("\n")
            logger.info("upload常态策略加载：\n%s" % ("\n".join(uploadrule_list)))
            uploadrule_split = uploadrule_list[0].strip().split()
            if len(uploadrule_split) == 10:
                uploadmode, uploadip, uploadport, uploaduser, uploadpwd, uploaddst, uploadsrc, a, uploadex_field, uploadzippwd = uploadrule_split
            elif len(uploadrule_split) == 9:
                uploadmode, uploadip, uploadport, uploaduser, uploadpwd, uploaddst, uploadsrc, a, uploadex_field = uploadrule_split
            elif len(uploadrule_split) == 8:
                uploadmode, uploadip, uploadport, uploaduser, uploadpwd, uploaddst, uploadsrc, a = uploadrule_split
                uploadex_field = "0|1|1"
            else:
                uploadex_field = None
            uploadrule_list = list(map(lambda x: x.encode("utf-8"), uploadrule_list))

        uploadmode_pc = uploadip_pc = uploadport_pc = uploaduser_pc = uploadpwd_pc = uploaddst_pc = uploadsrc_pc = a_pc = uploadex_field_pc = uploadzippwd_pc = None
        if config.get(f"{sheet_name}_uploadrule_pc", None):
            uploadrule_pc_list = config.get(f"{sheet_name}_uploadrule_pc", "").strip().split("\n")
            logger.info("upload评测策略加载：\n%s" % ("\n".join(uploadrule_pc_list)))
            uploadrule_pc_split = uploadrule_pc_list[0].strip().split()
            if len(uploadrule_pc_split) == 10:
                uploadmode_pc, uploadip_pc, uploadport_pc, uploaduser_pc, uploadpwd_pc, uploaddst_pc, uploadsrc_pc, a_pc, uploadex_field_pc, uploadzippwd_pc = uploadrule_pc_split
            elif len(uploadrule_pc_split) == 9:
                uploadmode_pc, uploadip_pc, uploadport_pc, uploaduser_pc, uploadpwd_pc, uploaddst_pc, uploadsrc_pc, a_pc, uploadex_field_pc = uploadrule_pc_split
            elif len(uploadrule_pc_split) == 8:
                uploadmode_pc, uploadip_pc, uploadport_pc, uploaduser_pc, uploadpwd_pc, uploaddst_pc, uploadsrc_pc, a_pc = uploadrule_pc_split
                uploadex_field_pc = "0|1|1"
            uploadrule_pc_list = list(map(lambda x: x.encode("utf-8"), uploadrule_pc_list))

        if uploadrule_list or uploadrule_pc_list:
            dpi_xdr.marex_policy_update(policy=uploadrule_list + uploadrule_pc_list, path=uploadfile, md5check=True)

        report_port = None
        reportrule_list = None
        if config.get(f"{sheet_name}_reportrule", None):
            reportrule_list = config.get(f"{sheet_name}_reportrule", "").strip().split("\n")
            logger.info("report策略加载：\n%s" % ("\n".join(reportrule_list)))
            report_port = int(reportrule_list[0].strip().split("|")[8].rsplit(":", 1)[1])
            reportrule_b_list = list(map(lambda x: x.encode("utf-8"), reportrule_list))
            dpi_xdr.marex_policy_update(policy=reportrule_b_list, path=reportfile, md5check=True)

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
            logger.info(f"清理socket缓存：{logserver.socketserver_dataclean()}")
            logger.info(f"缓存数据：{logserver.socketserver_data()}")

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

        # 获取业务策略
        policys = list()
        for case_name, case in cases.items():
            if "策略" not in case[0] or not case[0]["用例名"] or (case[0]["执行状态"] and int(case[0]["执行状态"])) != 1:
                continue
            if case[0].get("策略", None):
                policy = list(map(lambda x: re.sub(r"hid=\d+,", f"hid={houseid_inner},", x), case[0]["策略"].strip().split("\n")))
                policy = list(map(lambda x: re.sub(r"^\d+\s", f"{'1' + case[0]['commandId'][-6:]} ", x), policy))
                policy = list(map(lambda x: re.sub(r"(?<=cid=)\d+,|(?<=prex=)\d+|(?<=vpnId=)\d+,", f"{case[0]['commandId']},", x).encode("utf-8"), policy))
                policys += policy
        logger.info(b"\n".join(policys).decode("utf-8") if policys else "No policies")

        logtype = None

        # 清空策略
        for policyfile in action2policyfile.values():
            dpi_xsa.marex_policy_update(policy=[], path=policyfile)

        if policys:
            logger.info("业务策略加载")
            action = get_action_from_marex(policys[0].decode("utf-8"))
            command_type = get_type_from_marex(policys[0].decode("utf-8"))
            if command_type == "monit":
                logtype = "4"
            elif command_type == "filt":
                logtype = "5"
            elif action in ("mirr", "pcapdump"):
                logtype = "11"

            # 跨境内置规则统计
            if action == "vpn_block":
                cmd = "cat vpn_block_inner.rule|grep vpn_block -c"
                policys_length_oversea = int(dpi_xsa.cmd(cmd, cwd=os.path.dirname(action2policyfile[action])).strip())
            else:
                policys_length_oversea = 0

            wait_until(stat_dpi_xsa.get_policy_total, str(0 + policys_length_oversea), 2, 60, action)
            dpi_xsa.marex_policy_update(policy=policys, path=action2policyfile[action])
            wait_until(stat_dpi_xsa.get_policy_total, str(len(policys) + policys_length_oversea), 2, 60, action)
        time.sleep(2)

        if config.get(f"{sheet_name}_casetype", None) == "idcfz_log" and adms_mode in ("1", "2") and idc_flag == 1:
            # 获取fz_block.rule策略
            logger.info("获取策略：")
            policys_idcfz = list()
            for case_name, case in cases.items():
                if "策略" not in case[0] or not case[0]["用例名"] or (case[0]["执行状态"] and int(case[0]["执行状态"])) != 1:
                    continue
                if case[0].get("fz_block.rule"):
                    policy = list(map(lambda x: re.sub(r"^\d+", case[0]['commandId'], x).encode("utf-8"),
                                      case[0]["fz_block.rule"].strip().split("\n")))
                    policys_idcfz += policy
            logger.info(b"\n".join(policys_idcfz).decode("utf-8") if policys_idcfz else "No fz_block policies")

            logger.info("加载策略")
            dpi_xsa.marex_policy_update(policy=policys_idcfz, path=fz_block_rulefile, md5check=True)
            wait_until(stat_dpi_xsa.adms_idc_debug2dict, str(len(policys_idcfz)), 2, 60, "adms_allrule_num")

        if config.get(f"{sheet_name}_casetype", None) == "idcfz_log":
            logtype = "5"

        # gwfz_log 用例类型处理：加载 fz_block.rule、fz_action.txt、ip_segment.txt
        if config.get(f"{sheet_name}_casetype", None) == "gwfz_log":
            logger.info("gwfz_log 用例类型，加载反诈策略")
            policys_gwfz = list()
            for case_name, case in cases.items():
                if not case[0].get("用例名") or str(case[0].get("执行状态")) != "1":
                    continue
                # fz_block.rule
                if case[0].get("fz_block.rule"):
                    policy = list(map(lambda x: re.sub(r"^\d+", case[0]['commandId'], x).encode("utf-8"),
                                      case[0]["fz_block.rule"].strip().split("\n")))
                    policys_gwfz += policy
                # fz_action.txt
                if case[0].get("fz_action.txt"):
                    action_rules = case[0]["fz_action.txt"].strip().split("\n")
                    action_rules = list(map(lambda x: x.encode("utf-8"), action_rules))
                    logger.info(f"fz_action.txt加载：{case[0]['fz_action.txt'].strip()}")
                    dpi_xsa.marex_policy_update(policy=action_rules, path=fz_action_txtfile, md5check=True)
                # ip_segment.txt
                if case[0].get("ip_segment.txt"):
                    ipseg_rules = case[0]["ip_segment.txt"].strip().split("\n")
                    ipseg_rules = list(map(lambda x: x.encode("utf-8"), ipseg_rules))
                    logger.info(f"ip_segment.txt加载：{case[0]['ip_segment.txt'].strip()}")
                    dpi_xsa.marex_policy_update(policy=ipseg_rules, path=ip_segment_txtfile, md5check=True)

            if policys_gwfz:
                logger.info("gwfz fz_block.rule加载")
                logger.info(b"\n".join(policys_gwfz).decode("utf-8") if policys_gwfz else "No fz_block policies")
                dpi_xsa.marex_policy_update(policy=policys_gwfz, path=fz_block_rulefile, md5check=True)
                # wait_until(stat_dpi_xsa.adms_idc_debug2dict, str(len(policys_gwfz)), 2, 60, "adms_allrule_num")
                time.sleep(3)
            logtype = "5"

        # 提取关联的关键字
        keynames = config[sheet_name + "_keyname"].split(",")
        keyname2keyvalue = dict(zip(keynames, config[sheet_name + "_keyvalue"].split(",")))
        if config.get(f"{sheet_name}_splitflag", None) or config.get(f"{sheet_name}_fileparsertype") == "kafka_list":
            keyname2keyvalue_headNo = dict(zip(keynames, list(map(lambda x: heads.index(x), [keyname2keyvalue[i] for i in keynames]))))
            keyvalue_headNos = list(map(lambda x: keyname2keyvalue_headNo[x], keynames))
        else:
            keyvalue_headNos = None

        # 日志路径设置
        path_log = spath_log = count_fopen_ok = logfilecount_s = empty_path = curpath_log = curspath_log = None
        curdate = datetime.datetime.now().strftime('%Y-%m-%d')
        if config.get(f"{sheet_name}_uploadrule", None):
            if uploadex_field in ("0|0|3", "1|1|3"):
                path_log = config["sftppath_logserver"].strip().rstrip("/") + "/" + uploaddst.strip().strip("/") + f"/{curdate}"
                spath_log = uploadsrc
            elif uploadex_field == "1|21|3":
                logtype = src2logtype[uploadsrc] if not logtype else logtype
                path_log = config["sftppath_logserver"].strip().rstrip("/") + "/" + uploaddst.strip().strip("/") + f"/{houseid}/{logtype}/{curdate}"
                spath_log = f"{uploadsrc}/{houseid}/{logtype}"
            elif uploadex_field == "0|1|1":
                path_log = config["sftppath_logserver"].strip().rstrip("/") + "/" + uploaddst.strip().strip("/")
                spath_log = f"{uploadsrc}"
            else:
                path_log = config["sftppath_logserver"].strip().rstrip("/") + "/" + uploaddst.strip().strip("/")
                spath_log = f"{uploadsrc}"

            logger.info(f"常态上传路径：{path_log}")
            logger.info(f"常态源路径：{spath_log}")
            logger.info(f"清空源路径：{spath_log}")
            dpi_xdr.cmd(r"find %s -type f -exec rm -f {} \;" % spath_log)

        path_log_pc = spath_log_pc = None
        if config.get(f"{sheet_name}_uploadrule_pc", None):
            if uploadex_field_pc in ("0|0|3", "1|1|3"):
                path_log_pc = config["sftppath_logserver"].strip().rstrip("/") + "/" + uploaddst_pc.strip().strip("/") + f"/{curdate}"
                spath_log_pc = uploadsrc_pc
            elif uploadex_field_pc == "1|21|3":
                logtype = src2logtype[uploadsrc_pc] if not logtype else logtype
                path_log_pc = config["sftppath_logserver"].strip().rstrip("/") + "/" + uploaddst_pc.strip().strip("/") + f"/{houseid}/{logtype}/{curdate}"
                spath_log_pc = f"{uploadsrc_pc}/{houseid}/{logtype}"
            elif uploadex_field_pc == "0|1|1":
                path_log_pc = config["sftppath_logserver"].strip().rstrip("/") + "/" + uploaddst_pc.strip().strip("/")
                spath_log_pc = f"{uploadsrc_pc}"
            else:
                path_log_pc = config["sftppath_logserver"].strip().rstrip("/") + "/" + uploaddst_pc.strip().strip("/")
                spath_log_pc = f"{uploadsrc_pc}"

            logger.info(f"评测上传路径：{path_log_pc}")
            logger.info(f"评测源路径：{spath_log_pc}")
            logger.info(f"清空评测源路径：{spath_log_pc}")
            dpi_xdr.cmd(r"find %s -type f -exec rm -f {} \;" % spath_log_pc)

        if config.get(f"{sheet_name}_ispc", None):
            curpath_log = path_log_pc
            curspath_log = spath_log_pc
            empty_path = path_log
        else:
            curpath_log = path_log
            curspath_log = spath_log
            empty_path = path_log_pc

        logger.info(f"清空置空的上报路径：{empty_path}")
        if empty_path and logserver.isdir(empty_path):
            logserver.cmd(f"find {empty_path} -exec rm -rf {{}} \\;")

        # 统计日志文件数量-开始量
        logfilecount_s = logserver.cmd(f"find {curpath_log} -type f|wc -l")
        logger.info(f"{curpath_log} 开始时日志文件数量：{logfilecount_s.strip()}")

        # 统计xdr上的fopen_ok数量
        cmd = "cat /dev/shm/xsa/xdrtxtlog.stat |grep all|awk '{print $2}'"
        count_fopen_ok = dpi_xdr.cmd(cmd)

        # 记录开始时间
        time_s = int(dpi_xsa.cmd('date +%s').strip())
        logger.info(f"开始时间：{gettime(4)}")

        logger.info("执行发包")
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
                mbps=50,
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

        # 等待跨境（科开）上报，等待2分钟，不走xdr文件生成等待，走活跃生成等待
        if sheet_name in ("vpn_block_kk",):
            logger.info("等待跨境（科开）上报，等待2分钟")
            time.sleep(120)

        elif not config.get(f"{sheet_name}_reportrule", None) and (
                config.get(f"{sheet_name}_uploadrule", None) or config.get(f"{sheet_name}_uploadrule_pc", None)) or (
                config.get(f"{sheet_name}_uploadrule_pc", None) and (config.get(f"{sheet_name}_ispc", None))):
            # 等待日志文件开始生成
            logger.info("等待日志文件开始生成:超时时间%ss" % int(timeout_flow / 1000 + 2))
            cmd = "cat /dev/shm/xsa/xdrtxtlog.stat |grep all|awk '{print $2}'"
            logger.info(cmd)
            try:
                wait_not_until(dpi_xdr.cmd, count_fopen_ok, step=1, timeout=int(timeout_flow / 1000 + 2), args=cmd)
            except Exception as e:
                logger.warning(f"日志文件未生成：{e}")

            # 等待日志文件生成
            logger.info("等待日志文件生成:超时时间85s")
            cmd = "cat /dev/shm/xsa/xdrtxtlog.stat|grep all|awk '{print $2 - $4}'"
            logger.info(cmd)
            if not wait_until(dpi_xdr.cmd, expect_value="0\n", step=2, timeout=85, args=cmd):
                raise RuntimeError("流超时后等待65s后，xdrtxtlog.stat显示文件还没有关闭！")

        # 记录结束时间
        time_e = int(dpi_xsa.cmd('date +%s').strip())
        logger.info(f"结束时间：{gettime(4)}")

        # 提取日志内容
        act_log_dict = dict()
        if not config.get(f"{sheet_name}_reportrule", None) and (
                config.get(f"{sheet_name}_uploadrule", None) or config.get(f"{sheet_name}_uploadrule_pc", None)) or (
                config.get(f"{sheet_name}_uploadrule_pc", None) and (config.get(f"{sheet_name}_ispc", None))):
            # 等待文件上报
            logger.info("等待文件上报:超时时间%sms" % timeout_flow * 2)
            cmd = f"find {curspath_log} -type f|wc -l"
            logger.info(cmd)
            wait_until(logserver.cmd, '0\n', step=1, timeout=timeout_flow * 2/1000, args=cmd)

            # 初始化解压目录
            logger.info("初始化解压目录：/tmp/txt")
            tmpdir = "/tmp/txt"
            if logserver.isdir(tmpdir):
                logserver.cmd(r"find %s -type f -exec rm -f {} \;" % tmpdir)
            else:
                logserver.mkdir(dir=tmpdir)

            logfilecount_e = logserver.cmd(f"find {curpath_log} -type f|wc -l")
            logger.info(f"{curpath_log} 结束时日志文件数量：{logfilecount_e}")
            logger.info([logfilecount_s, logfilecount_e])
            if int(logfilecount_e.strip()) - int(logfilecount_s.strip()) > 0:
                cmd = "ls -rt|tail -n %s|grep %s$" % (
                    int(logfilecount_e) - int(logfilecount_s),
                    config.get(sheet_name + "_compression") if config.get(sheet_name + "_compression") else config.get(sheet_name + "_filetype")
                )
                response = logserver.cmd(args=cmd, cwd=curpath_log)
                logger.info(cmd)
                logger.info(response)
                response = response.strip().split()

            # 解压缩文件
            if config.get(sheet_name + "_compression", None):
                logger.info("解压缩文件")
                for name in response:
                    if config[sheet_name + "_compression"] == "tar.gz" and name.endswith("tar.gz"):
                        cmd = f"tar -xzvf {name} -C {tmpdir}"
                    elif config[sheet_name + "_compression"] == "zip" and name.endswith("zip"):
                        cmd = f"unzip {name} -d {tmpdir}"
                    else:
                        raise RuntimeError("不支持压缩方式：%s" % config.get(sheet_name + "_compression"))
                    logger.info(logserver.cmd(args=cmd, cwd=curpath_log))
            else:
                for name in response:
                    if name.endswith(config.get(sheet_name + "_filetype", "txt")):
                        # XML文件需要解密处理
                        if config.get(sheet_name + "_filetype") == "xml":
                            logger.info("xml解析成明文")
                            content_encrypt = logserver.getfo(remotepath=curpath_log.rstrip("/") + "/" + name).read()
                            content_decrypt = decrypt_file_load(
                                xml=content_encrypt,
                                method="fileLoad",
                                inter_key=authkey,
                                inter_skey=secretkey,
                                inter_asepyl=cryptvector
                            )
                            logserver.putfo(io.BytesIO(content_decrypt), f"{tmpdir}/{name}")
                        else:
                            logserver.cmd(args=f"cp -f {name} {tmpdir}", cwd=curpath_log)

            # 提取日志内容
            logger.info("提取日志内容")
            cmd = "ls -rt *%s" % config.get(sheet_name + "_filetype", "txt")
            response = logserver.cmd(args=cmd, cwd=tmpdir).strip().split()

            # 区分XML和普通文本的处理方式
            if config.get(sheet_name + "_filetype") == "xml" and not config.get(sheet_name + "_splitflag"):
                # XML格式处理：提取<log>节点
                log_cyclefield = config[f"{sheet_name}_log_cyclefield"]
                log_xmlprefix_pattern = config[f"{sheet_name}_log_xmlprefix"].replace("$provID", provinceId2provID.get(provinceId[:2], "999")).replace("$idcId", idcId)
                log_xmlsuffix_pattern = config[f"{sheet_name}_log_xmlsuffix"]
                logger.info(f"log_xmlprefix_pattern:\n{log_xmlprefix_pattern}")
                logger.info(f"log_xmlsuffix_pattern:\n{log_xmlsuffix_pattern}")

                content_list = list()
                log_xmlprefix = None
                log_xmlsuffix = None

                for name in response:
                    if name.endswith("xml"):
                        content = logserver.getfo(remotepath=tmpdir.rstrip("/") + "/" + name).read().decode("utf-8").strip()
                        # 先把日志的头和尾缓存下来
                        if log_xmlprefix is None:
                            log_xmlprefix_match = re.search(log_xmlprefix_pattern, content)
                            if log_xmlprefix_match:
                                log_xmlprefix = log_xmlprefix_match.group()
                        if log_xmlsuffix is None:
                            log_xmlsuffix_match = re.search(log_xmlsuffix_pattern, content)
                            if log_xmlsuffix_match:
                                log_xmlsuffix = log_xmlsuffix_match.group().strip()
                        logger.info(f"log_xmlprefix:{log_xmlprefix}")
                        logger.info(f"log_xmlsuffix:{log_xmlsuffix}")
                        # 提取log节点
                        content_list += re.findall(r"<%s>(?:.|\n)+?</%s>" % (log_cyclefield, log_cyclefield), content)

                # 从每个 log 节点中提取 key 并按 key 分组（按照原始代码 line 4336-4361 逻辑）
                keyvalue_list = config.get(sheet_name + "_keyvalue", "").split(",")
                keyvalue_list = [] if keyvalue_list == [""] else keyvalue_list

                for content in content_list:
                    # 从 XML 中提取 key
                    content_dict = xml2dict(Xml(content=log_xmlprefix + content + log_xmlsuffix).root)
                    tmpkeys = list()
                    for keyvalue in keyvalue_list:
                        tmp = content_dict
                        for tmp_key in keyvalue.split("."):
                            tmp = tmp.get(tmp_key)
                        tmpkeys.append(str(tmp) if tmp is not None else "")
                    key = "_".join(tmpkeys).lower()

                    if key in act_log_dict:
                        act_log_dict[key].append(content)
                    else:
                        act_log_dict[key] = [content]

                # 调整格式：act_log_dict[key] = [{filed:log_xml}]
                # 按照原始代码 line 4357-4359 的排序逻辑
                sort_flag = config.get(sheet_name + "_sort_flag", "")
                for key in act_log_dict.keys():
                    if sort_flag:
                        act_log_dict[key].sort(
                            key=lambda x: [re.search(f".*{i}.*", x).group() if re.search(f".*{i}.*", x) else "" for i in
                                           sort_flag.split(",")])
                    else:
                        act_log_dict[key].sort()
                    log_xml = "\n".join([log_xmlprefix] + act_log_dict[key] + [log_xmlsuffix])
                    act_log_dict[key] = [[log_xml]]
            elif config.get(f"{sheet_name}_fileparsertype") == "kafka_list":
                # Kafka Avro 二进制格式处理
                logger.info("kafka_list 格式解析")

                # 从远程设备下载 .avsc Schema 文件到本地临时文件
                schema_remote_path = config[f"{sheet_name}_kafkaschema"]
                logger.info(f"下载 Avro Schema: {schema_remote_path}")
                schema_content = dpi_xsa.getfo(remotepath=schema_remote_path).read()
                schema_local = os.path.join(tempfile.gettempdir(), "kafka_schema.avsc")
                with open(schema_local, "wb") as f:
                    f.write(schema_content)

                # 调试用：在 /tmp/txt/kafka/ 目录保存解析后的明文
                kafka_debug_dir = tmpdir.rstrip("/") + "/kafka"
                if not logserver.isdir(kafka_debug_dir):
                    logserver.mkdir(dir=kafka_debug_dir)

                # 遍历每个已下载到 /tmp/txt 的日志文件
                for name in response:
                    # 下载二进制文件内容到本地临时文件
                    file_content = logserver.getfo(remotepath=tmpdir.rstrip("/") + "/" + name).read()
                    file_local = os.path.join(tempfile.gettempdir(), f"kafka_{name}")
                    with open(file_local, "wb") as f:
                        f.write(file_content)

                    # 用 kafka_avro_parser 解析，得到 List[dict]
                    records = parse_kafka_avro_file(file_local, schema_local, output_format="dict")
                    logger.info(f"Kafka 解析完成: {name}，共 {len(records)} 条记录")

                    # 调试用：将解析后的明文保存到 /tmp/txt/kafka/ 目录
                    debug_remote = f"{kafka_debug_dir}/{name}"
                    debug_lines = "\n".join(
                        ["\t".join([str(record.get(h[4:], "")) for h in heads]) for record in records]
                    )
                    logserver.putfo(io.BytesIO(debug_lines.encode("utf-8")), debug_remote)
                    logger.info(f"Kafka 解析明文已保存: {debug_remote}")

                    # 将每条 Avro 记录转换为值列表，按 act_* 列顺序排列
                    for record in records:
                        fields = [str(record.get(h[4:], "")) for h in heads]
                        key = "_".join([str(fields[i]) for i in keyvalue_headNos]).lower() if keyvalue_headNos else "log"
                        if key in act_log_dict:
                            act_log_dict[key].append(fields)
                        else:
                            act_log_dict[key] = [fields]

                    os.remove(file_local)
                os.remove(schema_local)
            else:
                # 普通文本格式处理
                log_lines = []
                for name in response:
                    content = logserver.getfo(remotepath=tmpdir.rstrip("/") + "/" + name).read().decode("utf-8").strip().split("\n")
                    if config.get(sheet_name + "_exist_head", None):
                        content = content[1:]
                    log_lines += content

                for line in log_lines:
                    fields = line.split(config.get(sheet_name + "_splitflag", "\t"))
                    key = "_".join(list(map(lambda x: str(fields[x]), keyvalue_headNos))).lower() if keyvalue_headNos else "log"
                    if key in act_log_dict:
                        act_log_dict[key].append(fields)
                    else:
                        act_log_dict[key] = [fields]

        # report rule socket 处理
        if config.get(f"{sheet_name}_reportrule", None):
            keyvalue_list = config.get(f"{sheet_name}_keyvalue", "").split(",")
            keyvalue_list = [] if keyvalue_list == [""] else keyvalue_list

            logger.info("等待socket日志上报：20秒")
            time.sleep(20)

            logger.info("等待socket日志文件上报完成")
            stat_dpi_xsa.wait_socket_fclose(timeout=60)
            log_byts = logserver.socketserver_data()
            logserver.socketserver_writefile("/tmp/socketserver.bin")
            log_list = monitorlog(log_byts)
            for log in log_list:
                key = "_".join(list(map(lambda x: str(log[x]), keyvalue_list))).lower()
                if key in act_log_dict:
                    act_log_dict[key].append(log)
                else:
                    act_log_dict[key] = [log]

        mark_tmp = list()
        row_tmp = 1
        if empty_path and logserver.cmd(f"find {empty_path} -type f|wc -l").strip() != "0":
            mark_tmp = [f"评测相关检查，上报目录存在文件：{empty_path}"]
        elif config.get(f"{sheet_name}_reportrule", None):
            cmd = "cat /dev/shm/xsa/eu_output.stat | grep all: -A 50 | grep -E 'monitor_monitorlog_succ_cnt|monitor_filterlog_succ_cnt' | awk -F':' '{sum += $2} END {print sum}'"
            reportlogcount = logserver.cmd(cmd).strip()
            logger.info(f"report上报日志数量：{reportlogcount}")
            if empty_path and reportlogcount != "0":
                mark_tmp = [f"评测相关检查，上报目录存在文件：{empty_path}"]

        result_list = list()
        counter = 1

        # 提前提取所有用例的预期值
        logger.info("预期值格式化（提前提取）")
        all_exp_logs = casename2exp_log(p_excel, sheet_name)

        for case_name, case in cases.items():
            if not case[0].get("用例名", None) or str(case[0].get("执行状态", "")) != "1":
                continue

            # 按 case 策略时，每个用例切换一次日志文件
            if log_strategy == "by_case":
                log_file = build_log_filename(session_id, sheet_name, case_name, log_strategy)
                dynamic_handler.switch_file(log_file)
                logger.info(f"日志文件：{log_file}")

            logger.info("%s\t核对用例日志：%s\t%s\t%s" % (
                datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), sheet_name, counter, case_name))

            mark = list()
            key = "_".join(list(map(lambda x: str(case[0][x]), keynames))).lower() if keynames else "log"

            # 预期值
            logger.info("预期值格式化")
            exp_log_list = all_exp_logs.get(case_name, [])
            # 针对json数据解析成dict
            if config.get(f"{sheet_name}_reportrule", None) and not config.get(f"{sheet_name}_ispc", None):
                exp_log_list = list(map(lambda x: {list(x.keys())[0]: json.loads(list(x.values())[0])}, exp_log_list))

            # 实际值
            logger.info("实际值格式化")
            if key in act_log_dict:
                act_log_list = act_log(
                    p_excel=p_excel,
                    sheet_name=sheet_name,
                    act_val_list=act_log_dict.pop(key),
                    sort_flag=config.get(sheet_name + "_sort_flag", None)
                )
            else:
                result_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["实际条数"], 0, None))
                if len(exp_log_list) != 0:
                    logger.info(f"预期条数{len(exp_log_list)}，实际条数0")
                    mark.append(f"预期条数{len(exp_log_list)}，实际条数0")

                mark = list(map(lambda x: str(x), mark))
                if mark:
                    result_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["备注"], "\n".join(mark), None))
                    result_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["结果"], "Failed", (255, 0, 0)))
                else:
                    result_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["备注"], None, None))
                    result_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["结果"], "Pass", (0, 255, 0)))

                counter += 1
                continue

            # 确定日志格式
            datatype = None
            if config.get(sheet_name + "_reportrule", None) and not config.get(sheet_name + "_ispc", None):
                datatype = "dict"
            elif config.get(sheet_name + "_filetype", None) == "xml" and not config.get(sheet_name + "_splitflag", None):
                datatype = "xml"

            # 结果对比
            logger.info("结果对比")
            result_compcare = compare_exp(
                exp_log_list, act_log_list, case,
                sheet_name2head2col[sheet_name], time_s, time_e,
                ignore_fields=ignore_fields,
                length_fields=length_fields,
                time_fields=time_fields,
                datatype=datatype
            )
            mark += result_compcare["mark"]
            result_list += result_compcare["result_list"]

            # 写结果到excel
            logger.error(f"异常信息：{mark}")
            mark = list(map(lambda x: str(x), mark))

            if counter == 1:
                row_tmp = case[0]["row"]
            if mark:
                if counter == 1:
                    mark_tmp.extend(mark)
                else:
                    result_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["备注"], "\n".join(mark), None))
                result_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["结果"], "Failed", (255, 0, 0)))
            else:
                result_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["备注"], None, None))
                result_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["结果"], "Pass", (0, 255, 0)))

            counter += 1

        if act_log_dict:
            logger.warning(f"多出日志统计{len(act_log_dict)}条：{act_log_dict}")
            mark_tmp.append(f"多出日志统计{len(act_log_dict)}条：{act_log_dict}")

        result_deal(
            xls=path, sheet_index=sheet_name, result_list=result_list,
            row=row_tmp, head2col=sheet_name2head2col[sheet_name],
            mark=mark_tmp, only_write=False, newpath=newpath
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
