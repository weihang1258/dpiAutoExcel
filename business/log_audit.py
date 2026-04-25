#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2024/10/7
# @Author  : weihang
# @File    : log_audit.py

"""
审计日志处理模块
处理 audit 等审计日志的测试
"""

import copy
import datetime
import io
import json
import random
import re
import time
from utils.common import gettime, wait_until, wait_not_until, setup_logging
from core.excel_reader import parser_excel, casename2exp_log, act_log
from core.comparer import compare_exp
from core.result import result_deal
from device.socket_linux import SocketLinux
from device.dpi import Dpi
from monitor.dpistat import CheckDpiStat
from core.pcap import pcap_send
from utils.ini_handler import INIHandler
from utils.dpi_helper import dpi_init
from utils.marex_helper import get_action_from_marex
from utils.xml_helper import xml2dict, Xml
from utils.crypto_helper import decrypt_file_load
from device.dpi_constants import (
    uploadfile, reportfile, house_ipsegsfile, comon_inifile, ydcommoninfo_rulefile,
    commoninfo_rulefile, access_log_rulefile, pcip_ipsegsfile, xsa_jsonfile, fz_block_rulefile,
    action2policyfile, src2logtype, provinceId2provID
)

logger = setup_logging(log_file_path="log/log_audit.log", logger_name="log_audit")


def log_audit(p_excel: dict, sheets, path="用例", newpath=None):
    """处理审计日志测试。

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
    timeout_flow = dpi_xsa.json_get(path="/opt/dpi/xsaconf/xsa.json")["flow"]["idle_timeout_ms"]

    # 执行用例
    counter = 1

    for sheet_name in sheets:
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
                response = dpi_init(dpi_xsa, **devconfig_tmp)
                if not response:
                    dpi_xsa.restart()
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

        # 清空dpi的log
        dpi_xsa.cmd("truncate -s0 /var/log/dpi.log")

        # 重新获取流超时时间
        timeout_flow = dpi_xsa.json_get(path="/opt/dpi/xsaconf/xsa.json")["flow"]["idle_timeout_ms"]

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
        uploadmode = uploadip = uploadport = uploaduser = uploadpwd = uploaddst = uploadsrc = a = uploadex_field = uploadzippwd = None
        path_log = spath_log = count_fopen_ok = logfilecount_s = None
        uploadrule_list = list()
        if config.get(f"{sheet_name}_uploadrule", None):
            uploadrule_list = config.get(f"{sheet_name}_uploadrule", "").strip().split("\n")
            logger.info("upload策略加载：\n%s" % ("\n".join(uploadrule_list)))
            uploadrule = ""
            for i in uploadrule_list:
                if "AUDIT" in i:
                    uploadrule = i
                    break
            uploadrule_split = uploadrule.strip().split()
            if len(uploadrule_split) == 10:
                uploadmode, uploadip, uploadport, uploaduser, uploadpwd, uploaddst, uploadsrc, a, uploadex_field, uploadzippwd = uploadrule_split
            elif len(uploadrule_split) == 9:
                uploadmode, uploadip, uploadport, uploaduser, uploadpwd, uploaddst, uploadsrc, a, uploadex_field = uploadrule_split
            elif len(uploadrule_split) == 8:
                uploadmode, uploadip, uploadport, uploaduser, uploadpwd, uploaddst, uploadsrc, a = uploadrule_split
                uploadex_field = "0|1|1"

            # 确定上报的源和目的路径
            logtype = None
            if config.get(f"{sheet_name}_uploadrule", None):
                if uploadex_field == "0|0|3":
                    curdate = datetime.datetime.now().strftime('%Y-%m-%d')
                    path_log = config["sftppath_logserver"].strip().rstrip("/") + "/" + uploaddst.strip().strip("/") + f"/{curdate}"
                    spath_log = uploadsrc
                elif uploadex_field == "1|21|3":
                    curdate = datetime.datetime.now().strftime('%Y-%m-%d')
                    logtype = src2logtype[uploadsrc] if not logtype else logtype
                    path_log = config["sftppath_logserver"].strip().rstrip("/") + "/" + uploaddst.strip().strip("/") + f"/{houseid}/{logtype}/{curdate}"
                    spath_log = f"{uploadsrc}/{houseid}/{logtype}"
                elif uploadex_field in ("0|1|0", "0|1|1", "0|2"):
                    path_log = config["sftppath_logserver"].strip().rstrip("/") + "/" + uploaddst.strip().strip("/")
                    spath_log = f"{uploadsrc}"

                logger.info(f"上传路径：{path_log}")
                logger.info(f"源路径：{spath_log}")
                # 清空源路径
                logger.info(f"清空源路径：{spath_log}")
                dpi_xdr.cmd(f"rm -rf {spath_log}/*")
                logserver.cmd(f"rm -rf {path_log}")

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
                wait_not_until(dpi_xdr.cmd, '', step=1, timeout=300, args=cmd)
                wait_not_until(dpi_xdr.cmd, '-1\n', step=1, timeout=300, args=cmd)

        # 获取业务策略
        policys = list()
        policy_dict = dict()
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
                action = get_action_from_marex(command)
                if action in policy_dict:
                    policy_dict[action].append(command)
                else:
                    policy_dict[action] = [command]
            for key in policy_dict.keys():
                policy_dict[key] = list(map(lambda x: x.encode("utf-8"), policy_dict[key]))

        # 清空策略
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

        # 提取关联的关键字
        keynames = config.get(sheet_name + "_keyname", None).split(",") if config.get(sheet_name + "_keyname", None) else []
        if keynames:
            keyname2keyvalue = dict(zip(keynames, config[sheet_name + "_keyvalue"].split(",")))
            if config.get(f"{sheet_name}_filetype", None):
                keyname2keyvalue_headNo = dict(zip(keynames, list(map(lambda x: act_heads.index(x), [keyname2keyvalue[i] for i in keynames]))))
                keyvalue_headNos = list(map(lambda x: keyname2keyvalue_headNo[x], keynames))
            else:
                keyvalue_headNos = None

        # 统计日志文件数量
        logfilecount_s = '0'
        txtfilecount_s = '0'
        logger.info(f"{path_log}\t开始时日志文件数量：{logfilecount_s}")

        # 统计xdr上的fopen_ok数量
        cmd = "cat /dev/shm/xsa/xdrtxtlog.stat |grep all|awk '{print $2}'"
        count_fopen_ok = dpi_xdr.cmd(cmd)

        dpimode = dpi_xsa.get_dpimode()
        # 记录开始时间
        time_s = int(dpi_xsa.cmd('date +%s').strip())

        logger.info("执行发包")
        pcaps_tmp = list()
        for case_name, case in cases.items():
            if not case[0].get("用例名", None) or str(case[0].get("执行状态", "")) != "1":
                continue

            for i in range(len(case)):
                if case[i]["pcap"]:
                    path_flag = "/" if config["pcap_path"].startswith("/") else "\\"
                    pcaps = list(map(lambda x: config["pcap_path"].rstrip(path_flag) + path_flag + x.lstrip(path_flag), case[i]["pcap"].split()))
                    if path_flag == "\\":
                        pcaps = list(map(lambda x: x.replace("/", path_flag), pcaps))
                    pcaps_tmp += pcaps

        if pcaps_tmp and config[sheet_name + "_sendpktsmode"] == "scapy_send":
            pcap_send(
                client=socket_scapy_send,
                pcaps=pcaps_tmp,
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
        else:
            raise RuntimeError("请检查excel中的pcap路径，未找到")

        # 等待流超时
        logger.info("等待流超时(%s ms)" % (timeout_flow + 2000))
        time.sleep(timeout_flow / 1000 + 2)

        exp_log_list = list()
        if config.get(f"{sheet_name}_uploadrule", None):
            # 等待日志文件开始生成
            logger.info("等待日志文件开始生成:超时时间%ss" % int(timeout_flow / 1000 + 2))
            cmd = "cat /dev/shm/xsa/xdrtxtlog.stat |grep all|awk '{print $2}'"
            logger.info(cmd)
            wait_not_until(dpi_xdr.cmd, count_fopen_ok, step=1, timeout=int(timeout_flow / 1000 + 2), args=cmd)

            # 等待日志文件生成
            logger.info("等待日志文件生成:超时时间85s")
            cmd = "cat /dev/shm/xsa/xdrtxtlog.stat|grep all|awk '{print $2 - $4}'"
            logger.info(cmd)
            if not wait_until(dpi_xdr.cmd, expect_value="0\n", step=2, timeout=85, args=cmd):
                raise RuntimeError("流超时后等待65s后，xdrtxtlog.stat显示文件还没有关闭！")

            # 等待文件上报
            logger.info("等待时间%ss" % (10 * 60))
            time.sleep(10 * 60)
            logger.info("等待文件上报:超时时间%ss" % (10 * 60))

            cmd = f"cat {spath_log.replace('IS', '*').replace('BNS', '*')}/*|wc -l"
            logger.info(cmd)
            try:
                logger.info(dpi_xsa.cmd("date +'%Y-%m-%d %H:%M:%S'"))
                wait_until(logserver.cmd, '0\n', step=1, timeout=10 * 60, args=cmd)
                logger.info(dpi_xsa.cmd("date +'%Y-%m-%d %H:%M:%S'"))
            except Exception as e:
                logger.error(e)

            # 清空上报策略
            dpi_xdr.marex_policy_update(policy=[], path=uploadfile, md5check=True)

            # 记录结束时间
            time_e = int(dpi_xsa.cmd('date +%s').strip())
            # 预期值提取
            logger.info("预期值提取")
            exp_fileNames = list()
            for line in dpi_xsa.cmd("cat /var/log/dpi.log|grep uploadFileToSftpServe|grep -v AUDIT|awk -F 'uploadFileToSftpServer:' '{print $2}'").strip().split("\n"):
                logger.info(line)
                line_split = line.strip().split("/")
                fileName = line_split[-1]
                if dpimode == "com_cmcc_is":
                    if fileName[-3:] in ("AVL", "CHK"):
                        fileType = "3"
                    elif fileName[-3:] in ("zip",):
                        fileType = line.split("/")[-4]
                    else:
                        fileType = line_split[-2]
                    if not fileType.isdigit():
                        continue
                    filedir = fileType
                    fileName = f"/{filedir}/{fileName}"
                    exp_log_list.append(dict(zip(exp_heads, ["3.1", idcId, houseid, "17258709496298640003", "1", "10",
                                                             deviceId.rjust(6, "0"), "", "", dev_ip, "", fileName,
                                                             fileType, "1", "2024-09-09 16:35:38", "2024-09-09 16:35:38"])))
                    exp_log_list.append(dict(zip(exp_heads, ["3.1", idcId, houseid, "17258709496298640003", "1", "10",
                                                             deviceId.rjust(6, "0"), "", "", dev_ip, "", fileName,
                                                             fileType, "3", "2024-09-09 16:35:38", "2024-09-09 16:35:38"])))
                    exp_log_list.append(dict(zip(exp_heads, ["3.1", idcId, houseid, "17258709496298640003", "1", "10",
                                                             deviceId.rjust(6, "0"), "", "", dev_ip, "", fileName,
                                                             fileType, "2", "2024-09-09 16:35:38", "2024-09-09 16:35:38"])))

                elif dpimode in ("com_cucc_isbns", "com_ctcc_isbns"):
                    logger.info([fileName, fileName[-2:]])
                    if fileName[-2:] in ("ok", "OK") or not fileName.startswith("0x"):
                        continue
                    name_split = fileName.split("+")
                    filedir = name_split[1]
                    fileType = None
                    if name_split[1] in ("0x04a1", "0x04a3", "0x04a5"):
                        if name_split[3] == "1":
                            fileType = "12"
                        elif name_split[3] == "2":
                            fileType = "13"
                        elif name_split[3] == "3":
                            fileType = "14"
                    elif name_split[1] in ("0x03a0",):
                        fileType = "3"
                    elif name_split[1] in ("0x04a0", "0x04a2", "0x04a4"):
                        fileType = "11"
                    elif name_split[1] in ("0x0100",):
                        fileType = "4"
                    elif name_split[1] in ("0x0101",):
                        fileType = "5"

                    if fileType in ("11", "12", "13", "14"):
                        DeviceType = "8"
                    else:
                        DeviceType = "1"

                    fileName = f"/{filedir}/{fileName}"
                    if dpimode == "com_cucc_isbns":
                        exp_log_list.append(dict(zip(exp_heads, ["17262161740020720024", houseid, DeviceType,
                                                                 deviceId.rjust(6, "0"), dev_ip, fileName, fileType,
                                                                 "1", "1753360226", "1"])))
                        exp_log_list.append(dict(zip(exp_heads, ["17262161740020720024", houseid, DeviceType,
                                                                 deviceId.rjust(6, "0"), dev_ip, fileName, fileType,
                                                                 "3", "1753360226", "1"])))
                        exp_log_list.append(dict(zip(exp_heads, ["17262161740020720024", houseid, DeviceType,
                                                                 deviceId.rjust(6, "0"), dev_ip, fileName, fileType,
                                                                 "2", "1753360226", "1"])))
                    else:
                        DeviceType = "1"
                        exp_log_list.append(dict(zip(exp_heads, ["17262161740020720024", houseid, DeviceType,
                                                                 deviceId.rjust(6, "0"), dev_ip, fileName, fileType,
                                                                 "1", "1753360226"])))
                        exp_log_list.append(dict(zip(exp_heads, ["17262161740020720024", houseid, DeviceType,
                                                                 deviceId.rjust(6, "0"), dev_ip, fileName, fileType,
                                                                 "3", "1753360226"])))
                        exp_log_list.append(dict(zip(exp_heads, ["17262161740020720024", houseid, DeviceType,
                                                                 deviceId.rjust(6, "0"), dev_ip, fileName, fileType,
                                                                 "2", "1753360226"])))

        act_log_list = list()
        if config.get(f"{sheet_name}_uploadrule", None):
            # 初始化解压目录
            logger.info("初始化解压目录：/tmp/txt")
            tmpdir = "/tmp/txt"
            if logserver.isdir(tmpdir):
                logserver.cmd("rm -rf %s" % tmpdir)
            logserver.mkdir(dir=tmpdir)

            logfilecount_e = logserver.cmd(args="ls|wc -l", cwd=path_log)
            logger.info(f"{path_log}结束时日志文件数量：{logfilecount_e}")
            logger.info([logfilecount_s, logfilecount_e])
            cmd = "ls -rt|tail -n %s|grep %s$" % (
                int(logfilecount_e) - int(logfilecount_s),
                config[sheet_name + "_compression"] if config[sheet_name + "_compression"] else config[sheet_name + "_filetype"]
            )
            response = logserver.cmd(args=cmd, cwd=path_log)
            logger.info(cmd)
            response = response.strip().split()

            # 解压缩文件
            if config[sheet_name + "_compression"]:
                logger.info("解压缩文件")
                for name in response:
                    if config[sheet_name + "_compression"] == "tar.gz" and name.endswith("tar.gz"):
                        cmd = f"tar -xzvf {name} -C {tmpdir}"
                    elif config[sheet_name + "_compression"] == "zip" and name.endswith("zip"):
                        cmd = f"unzip {name} -d {tmpdir}"
                    else:
                        raise RuntimeError("不支持压缩方式：%s" % config[sheet_name + "_compression"])
                    logger.info(cmd)
                    logger.info(logserver.cmd(args=cmd, cwd=path_log))
            elif config[sheet_name + "_filetype"] == "xml":
                for name in response:
                    if name.endswith("xml"):
                        content_encrypt = logserver.getfo(path_log.rstrip("/") + "/" + name).read()
                        content_decrypt = decrypt_file_load(
                            xml=content_encrypt,
                            method="fileLoad",
                            inter_key=authkey,
                            inter_skey=secretkey,
                            inter_asepyl=cryptvector
                        )
                        logserver.putfo(io.BytesIO(content_decrypt), f"{tmpdir}/{name}")
            else:
                for name in response:
                    if name.endswith(config[sheet_name + "_filetype"]):
                        logserver.cmd(args=f"cp -f {name} {tmpdir}", cwd=path_log)

            # 提取日志内容
            logger.info("提取日志内容")
            cmd = "ls -rt *%s" % config[f"{sheet_name}_filetype"]
            response = logserver.cmd(args=cmd, cwd=tmpdir).strip().split()
            if config[f"{sheet_name}_filetype"] in ["AVL", "txt"] or (
                    config[f"{sheet_name}_filetype"] == "xml" and f"{sheet_name}_splitflag" in config and config[f"{sheet_name}_splitflag"]):
                log_lines = []
                for name in response:
                    content = logserver.getfo(remotepath=tmpdir.rstrip("/") + "/" + name).read().decode("utf-8").strip().split("\n")
                    if config[sheet_name + "_exist_head"]:
                        content = content[1:]
                    log_lines += content

                for line in log_lines:
                    fields = line.split(config[sheet_name + "_splitflag"])
                    act_log_list.append(dict(zip(act_heads, fields)))
            elif config[f"{sheet_name}_filetype"] == "xml" and (
                    f"{sheet_name}_splitflag" not in config or not config[sheet_name + "_splitflag"]):
                log_cyclefield = config[f"{sheet_name}_log_cyclefield"]
                log_xmlprefix_pattern = config[f"{sheet_name}_log_xmlprefix"].replace("$provID", provinceId2provID.get(provinceId[:2], "999")).replace("$idcId", idcId)
                log_xmlsuffix_pattern = config[f"{sheet_name}_log_xmlsuffix"]
                logger.info(f"log_xmlprefix_pattern:\n{log_xmlprefix_pattern}")
                logger.info(f"log_xmlsuffix_pattern:\n{log_xmlsuffix_pattern}")
                content_list = list()
                keyvalue_list = config[f"{sheet_name}_keyvalue"].split(",")
                log_xmlprefix = None
                log_xmlsuffix = None

                for name in response:
                    content = logserver.getfo(remotepath=tmpdir.rstrip("/") + "/" + name).read().decode("utf-8").strip()
                    if log_xmlprefix is None:
                        log_xmlprefix = re.findall(log_xmlprefix_pattern, content)[0]
                    if log_xmlsuffix is None:
                        log_xmlsuffix = re.findall(log_xmlsuffix_pattern, content)[0].strip()
                    logger.info(f"log_xmlprefix:{log_xmlprefix}")
                    logger.info(f"log_xmlsuffix:{log_xmlsuffix}")
                    content_list += re.findall(r"<%s>(?:.|\n)+?</%s>" % (log_cyclefield, log_cyclefield), content)

                for content in content_list:
                    content_dict = xml2dict(Xml(content=log_xmlprefix + content + log_xmlsuffix).root)
                    tmpkeys = list()
                    for keyvalue in keyvalue_list:
                        tmp = content_dict
                        for tmp_key in keyvalue.split("."):
                            tmp = tmp.get(tmp_key)
                        tmpkeys.append(tmp)
                    key = "_".join(tmpkeys)

        result_list = list()
        for case_name, case in cases.items():
            if not case[0]["用例名"] or (case[0]["执行状态"] and int(case[0]["执行状态"])) != 1:
                continue

            logger.info("%s\t核对用例日志：%s\t%s\t%s" % (
                datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), sheet_name, counter, case_name))

            mark = list()
            key = "_".join(list(map(lambda x: case[0][x], keynames)))

            # 实际值格式化
            logger.info("实际值格式化")
            act_sortheads = list(map(lambda x: "act" + x[3:], config.get(f"{sheet_name}_sort_flag", None).split(",")))
            act_log_list.sort(key=lambda x: [x[i] for i in act_sortheads])

            # 联通电信socket上报的日志统计
            sockettype2log = dict()
            if dpimode in ("com_cucc_isbns", "com_ctcc_isbns") and not config.get(f"{sheet_name}_ispc", None):
                for fields in act_log_list:
                    if fields["act_FileType"] in ("4", "5"):
                        if fields["act_FileType"] in sockettype2log:
                            sockettype2log[fields["act_FileType"]].append(fields["act_FileName"])
                        else:
                            sockettype2log[fields["act_FileType"]] = [fields["act_FileName"]]
            sockettype2log = dict(map(lambda x: (x[0], list(set(x[1]))), sockettype2log.items()))

            # 预期值格式化
            logger.info("预期值格式化")
            if dpimode in ("com_cucc_isbns", "com_ctcc_isbns"):
                monitor_monitorlog_succ_cnt = int(dpi_xsa.cmd(
                    "cat /dev/shm/xsa/eu_output.stat|grep all: -A 50|grep monitor_monitorlog_succ_cnt|awk -F ':' '{print $2}'").strip())
                monitor_filterlog_succ_cnt = int(dpi_xsa.cmd(
                    "cat /dev/shm/xsa/eu_output.stat|grep all: -A 50|grep monitor_filterlog_succ_cnt|awk -F ':' '{print $2}'").strip())
                if monitor_monitorlog_succ_cnt and len(sockettype2log.get("4", [])) != 1:
                    mark.append(f"monitor_monitorlog_succ_cnt数量：{monitor_monitorlog_succ_cnt}，实际日志条数：{len(sockettype2log.get('4', []))}")
                if monitor_filterlog_succ_cnt and len(sockettype2log.get("5", [])) != 1:
                    mark.append(f"monitor_filterlog_succ_cnt：{monitor_filterlog_succ_cnt}，实际日志条数：{len(sockettype2log.get('5', []))}")
                for act_FileType, act_FileNames in sockettype2log.items():
                    if dpimode == "com_cucc_isbns":
                        for act_FileName in act_FileNames:
                            exp_log_list.append(dict(zip(exp_heads,
                                                         ["17262161740020720021", houseid, "1", deviceId.rjust(6, "0"),
                                                          dev_ip, act_FileName, act_FileType, "1", "1753360226", "1"])))
                            exp_log_list.append(dict(zip(exp_heads,
                                                         ["17262161740020720021", houseid, "1", deviceId.rjust(6, "0"),
                                                          dev_ip, act_FileName, act_FileType, "3", "1753360226", "1"])))
                            exp_log_list.append(dict(zip(exp_heads,
                                                         ["17262161740020720021", houseid, "1", deviceId.rjust(6, "0"),
                                                          dev_ip, act_FileName, act_FileType, "2", "1753360226", "1"])))
                    else:
                        for act_FileName in act_FileNames:
                            exp_log_list.append(dict(zip(exp_heads,
                                                         ["17262161740020720021", houseid, "1", deviceId.rjust(6, "0"),
                                                          dev_ip, act_FileName, act_FileType, "1", "1753360226"])))
                            exp_log_list.append(dict(zip(exp_heads,
                                                         ["17262161740020720021", houseid, "1", deviceId.rjust(6, "0"),
                                                          dev_ip, act_FileName, act_FileType, "3", "1753360226"])))
                            exp_log_list.append(dict(zip(exp_heads,
                                                         ["17262161740020720021", houseid, "1", deviceId.rjust(6, "0"),
                                                          dev_ip, act_FileName, act_FileType, "2", "1753360226"])))

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
            mark=[], only_write=True, newpath=newpath
        )

    logserver.client.close()
    dpi_xsa.client.close()
    dpi_xdr.client.close()
    stat_dpi_xsa.client.close()
