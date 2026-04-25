#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2024/10/7
# @Author  : weihang
# @File    : log_active.py

"""
活跃日志处理模块
处理 actdomain、acturl 等活跃日志的测试
"""

import copy
import datetime
import io
import re
import time
from utils.common import logger, gettime
from core.excel_reader import parser_excel, casename2exp_log, act_log
from core.comparer import compare_exp
from core.result import result_deal
from device.socket_linux import SocketLinux
from device.dpi import Dpi
from monitor.dpistat import CheckDpiStat
from core.pcap import pcap_send
from utils.ini_handler import INIHandler
from utils.dpi_helper import dpi_init
from utils.crypto_helper import decrypt_file_load
from device.dpi_constants import (
    uploadfile, reportfile, house_ipsegsfile, comon_inifile, ydcommoninfo_rulefile,
    commoninfo_rulefile, eu_active_resource_rulefile, pcip_ipsegsfile, fz_block_rulefile,
    action2policyfile, provinceId2provID
)


def log_active(p_excel: dict, sheets_sendpkt, sheets_actdomain_list, path="用例", newpath=None):
    """处理活跃日志测试。

    Args:
        p_excel: Excel 解析结果
        sheets_sendpkt: 发包 sheet 名称
        sheets_actdomain_list: 活跃域 sheet 列表
        path: Excel 文件路径
        newpath: 新 Excel 文件路径
    """
    logger.info(f"---------------------开始执行excel：{path}，sheet：{sheets_sendpkt}---------------------")

    sheet_name2cases = p_excel["sheet_name2cases"]
    sheet_name2head2col = p_excel["sheet_name2head2col"]
    config = p_excel["config"]
    config_dev = p_excel["config_dev"]

    sheet2logtype = {
        "actdomain入向": 25, "actdomain出向": 28, "acturl入向": 29, "acturl出向": 30, "actdomain": 8
    }

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
    # 等待流超时
    logger.info("等待流超时(%s ms)" % (timeout_flow * 2))
    dpi_xsa.wait_flow_timeout(timeout=timeout_flow / 1000 * 2)
    # 等待写文件完成
    logger.info("等待写文件完成(%s s)" % 100)
    stat_dpi_xsa.wait_fclose(timeout=100)
    time.sleep(2)

    # 执行用例
    counter = 1
    cases = sheet_name2cases[sheets_sendpkt]

    # DPI环境初始化
    if sum(list(map(lambda x: 1 if x[0]["执行状态"] and int(x[0]["执行状态"]) == 1 else 0, cases.values()))) > 0:
        devconfig_tmp = dict()
        tmp = config.get(f"{sheets_sendpkt}_devconfig", "").split(",") if config.get(f"{sheets_sendpkt}_devconfig", None) else []
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
            dpi_init(dpi_xsa, **devconfig_tmp)
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
        return

    # 重新获取流超时时间
    timeout_flow = dpi_xsa.json_get(path="/opt/dpi/xsaconf/xsa.json")["flow"]["idle_timeout_ms"]

    # 更新 pcip_ipsegs.txt
    ipsegs_txt = config.get("pcip_ipsegs", "").strip() if config.get(f"{sheets_sendpkt}_ispc", None) else ""
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
    uploadrule_list = config.get(f"{sheets_sendpkt}_uploadrule", "").strip().split("\n")
    if uploadrule_list:
        logger.info("upload常态策略加载：\n%s" % ("\n".join(uploadrule_list)))
        uploadmode, uploadip, uploadport, uploaduser, uploadpwd, uploaddst, uploadsrc, a, uploadex_field, uploadzippwd = uploadrule_list[0].strip().split()
        uploadrule_list = list(map(lambda x: x.encode("utf-8"), uploadrule_list))
    else:
        uploadmode = uploadip = uploadport = uploaduser = uploadpwd = uploaddst = uploadsrc = a = uploadex_field = uploadzippwd = None

    # 评测规则
    uploadrule_pc_list = config.get(f"{sheets_sendpkt}_uploadrule_pc", "").strip().split("\n")
    if uploadrule_pc_list and uploadrule_pc_list != [""]:
        logger.info("upload评测策略加载：\n%s" % ("\n".join(uploadrule_pc_list)))
        uploadmode_pc, uploadip_pc, uploadport_pc, uploaduser_pc, uploadpwd_pc, uploaddst_pc, uploadsrc_pc, a_pc, uploadex_field_pc, uploadzippwd_pc = uploadrule_pc_list[0].strip().split()
        uploadrule_pc_list = list(map(lambda x: x.encode("utf-8"), uploadrule_pc_list))
    else:
        uploadmode_pc = uploadip_pc = uploadport_pc = uploaduser_pc = uploadpwd_pc = uploaddst_pc = uploadsrc_pc = a_pc = uploadex_field_pc = uploadzippwd_pc = None
        uploadrule_pc_list = []

    dpi_xdr.marex_policy_update(policy=uploadrule_list + uploadrule_pc_list, path=uploadfile, md5check=True)

    if config.get(f"{sheets_sendpkt}_ispc", None):
        curuploadmode = uploadmode_pc
        curuploadip = uploadip_pc
        curuploadport = uploadport_pc
        curuploaduser = uploaduser_pc
        curuploadpwd = uploadpwd_pc
        curuploaddst = uploaddst_pc
        curuploadsrc = uploadsrc_pc
        curuploadex_field = uploadex_field_pc
        curuploadzippwd = uploadzippwd_pc
        otheruploaddst = uploaddst
        otheruploadsrc = uploadsrc
        otheruploadex_field = uploadex_field
    else:
        curuploadmode = uploadmode
        curuploadip = uploadip
        curuploadport = uploadport
        curuploaduser = uploaduser
        curuploadpwd = uploadpwd
        curuploaddst = uploaddst
        curuploadsrc = uploadsrc
        curuploadex_field = uploadex_field
        curuploadzippwd = uploadzippwd
        otheruploaddst = uploaddst_pc
        otheruploadsrc = uploadsrc_pc
        otheruploadex_field = uploadex_field_pc

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
    activecycletime = int(ini_data.get(section="global_is", option="activecycletime"))
    houseid = ini_data.get(section="global_com", option="houseid")

    # 更新ydcommoninfo.rule
    ydcommoninfo_rule = config["ydcommoninfo_rule"].strip() if config["ydcommoninfo_rule"] else ""
    logger.info("ydcommoninfo.rule加载")
    dpi_xsa.putfo(fl=io.BytesIO(ydcommoninfo_rule.encode("utf-8")), remotepath=ydcommoninfo_rulefile, overwrite=False)

    # 更新commoninfo.rule
    commoninfo_rule = config["commoninfo_rule"].strip() if config["commoninfo_rule"] else ""
    logger.info("commoninfo.rule加载")
    dpi_xsa.putfo(fl=io.BytesIO(commoninfo_rule.encode("utf-8")), remotepath=commoninfo_rulefile, overwrite=False)

    # 更新eu_active_resource.rule
    eu_active_resource_rule = config.get("eu_active_resource_rule", "").strip()
    logger.info("eu_active_resource.rule加载")
    dpi_xsa.putfo(fl=io.BytesIO(eu_active_resource_rule.encode("utf-8")), remotepath=eu_active_resource_rulefile, overwrite=False)

    # 清空策略
    logger.info("清空策略")
    if dpi_xsa.isfile(fz_block_rulefile):
        logger.info(f"清空idc_fz策略：{fz_block_rulefile}")
        dpi_xsa.marex_policy_update(policy=[], path=fz_block_rulefile)
    for policyfile in action2policyfile.values():
        dpi_xsa.marex_policy_update(policy=[], path=policyfile)

    # 等待2个上报周期
    logger.info(f"等待2个上报周期:{activecycletime * 2}")
    time.sleep(activecycletime * 2)

    # 清空上报目录
    curdate = datetime.datetime.now().strftime('%Y-%m-%d')
    if uploadrule_list:
        logger.info("清空常态测试上报路径")
        for logtype_tmp in sheet2logtype.values():
            path_log = config["sftppath_logserver"].strip().rstrip("/") + "/" + uploaddst.strip().strip("/") + f"/{houseid}/{logtype_tmp}/{curdate}"
            logger.info(f"清空上报路径：{path_log}")
            if logserver.isdir(path_log):
                logserver.cmd("rm -rf *", cwd=path_log)

    if uploadrule_pc_list:
        logger.info("清空评测测试上报路径")
        for logtype_tmp in sheet2logtype.values():
            path_log = config["sftppath_logserver"].strip().rstrip("/") + "/" + uploaddst_pc.strip().strip("/") + f"/{houseid}/{logtype_tmp}/{curdate}"
            logger.info(f"清空上报路径：{path_log}")
            if logserver.isdir(path_log):
                logserver.cmd("rm -rf *", cwd=path_log)

    # 记录开始时间
    time_s = gettime(2)
    logger.info(f"开始时间：{gettime(4)}")

    logger.info("执行发包")
    pcaps_tmp = list()
    for case_name, case in cases.items():
        if not case[0]["用例名"] or (case[0]["执行状态"] and int(case[0]["执行状态"])) != 1:
            continue

        # 发包
        if case[0]["pcap"]:
            path_flag = "/" if config["pcap_path"].startswith("/") else "\\"
            pcaps = "\n".join(list(
                map(lambda x: config["pcap_path"].rstrip(path_flag) + path_flag + x.lstrip(path_flag),
                    case[0]["pcap"].split())))
            if path_flag == "\\":
                pcaps = pcaps.replace("/", path_flag)
            pcaps_tmp.append(pcaps)

    if pcaps_tmp and config.get(f"{sheets_sendpkt}_sendpktsmode") == "scapy_send":
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

    # 记录结束时间
    time_e = gettime(2)
    logger.info(f"结束时间：{gettime(4)}")

    # 等待2个上报周期
    logger.info(f"等待2个上报周期:{activecycletime * 2}")
    time.sleep(activecycletime * 2)

    first_flag = True
    for sheet_name in sheets_actdomain_list:
        logger.info(f"执行sheet页签：{sheet_name}")
        if sheet_name not in p_excel.get("sheet_name2cases", {}).keys():
            continue
        if first_flag == False:
            path = newpath
        else:
            first_flag = False
        logtype = sheet2logtype[sheet_name]

        ignore_fields = config.get(f"{sheet_name}_ignore_fields", None)
        length_fields = config.get(f"{sheet_name}_length_fields", None)
        time_fields = config.get(f"{sheet_name}_time_fields", None)

        cases = sheet_name2cases[sheet_name]
        heads = list()
        for field in p_excel["sheet_name2heads"][sheet_name]:
            if field and field.startswith("act_"):
                heads.append(field)

        # 日志路径
        curpath_log = curspath_log = otherpath_log = otherspath_log = None
        # 当前测试路径
        if curuploadex_field == "0|0|3":
            curpath_log = config["sftppath_logserver"].strip().rstrip("/") + "/" + curuploaddst.strip().strip("/") + f"/{curdate}"
            curspath_log = curuploadsrc
        elif curuploadex_field == "1|21|3":
            curpath_log = config["sftppath_logserver"].strip().rstrip("/") + "/" + curuploaddst.strip().strip("/") + f"/{houseid}/{logtype}/{curdate}"
            curspath_log = f"{curuploadsrc}/{houseid}/{logtype}"

        logger.info(f"当前上传路径：{curpath_log}")
        logger.info(f"当前源路径：{curspath_log}")

        # other测试路径
        if otheruploadex_field == "0|0|3":
            otherpath_log = config["sftppath_logserver"].strip().rstrip("/") + "/" + otheruploaddst.strip().strip("/") + f"/{curdate}"
            otherspath_log = otheruploadsrc
        elif otheruploadex_field == "1|21|3":
            otherpath_log = config["sftppath_logserver"].strip().rstrip("/") + "/" + otheruploaddst.strip().strip("/") + f"/{houseid}/{logtype}/{curdate}"
            otherspath_log = f"{otheruploadsrc}/{houseid}/{logtype}"

        logger.info(f"other上传路径：{otherpath_log}")
        logger.info(f"other源路径：{otherspath_log}")

        # 提取关联的关键字
        keynames = config.get(f"{sheet_name}_keyname").split(",") if config.get(f"{sheet_name}_keyname", None) else []
        keyname2keyvalue = dict(zip(keynames, config.get(f"{sheet_name}_keyvalue", "").split(",")))
        if config.get(f"{sheet_name}_keyname", None) and "." not in config.get(f"{sheet_name}_keyvalue", ""):
            keyname2keyvalue_headNo = dict(zip(keynames, list(map(lambda x: heads.index(x), [keyname2keyvalue[i] for i in keynames]))))
        keyvalue_headNos = None
        if config.get(f"{sheet_name}_keyvalue", None):
            keyvalue_headNos = list(map(lambda x: keyname2keyvalue_headNo[x], keynames))

        # 初始化解压目录
        logger.info("初始化解压目录：/tmp/txt")
        tmpdir = "/tmp/txt"
        if logserver.isdir(tmpdir):
            logserver.cmd("rm -rf %s" % tmpdir)
        logserver.mkdir(dir=tmpdir)

        logfilecount_e = logserver.cmd(args="ls|wc -l", cwd=curpath_log)
        logger.info(f"{curpath_log}\t结束时日志文件数量：\t{logfilecount_e}")
        cmd = "ls -rt|grep %s$" % (config.get(f"{sheet_name}_compression", None) if config.get(f"{sheet_name}_compression", None) else config.get(f"{sheet_name}_filetype"))
        response = logserver.cmd(args=cmd, cwd=curpath_log)
        logger.info(cmd)
        logger.info(response)
        response = response.strip().split()

        # 解压缩文件
        if config.get(f"{sheet_name}_compression", None):
            logger.info("解压缩文件")
            for name in response:
                if config.get(f"{sheet_name}_compression") == "tar.gz" and name.endswith("tar.gz"):
                    cmd = f"tar -xzvf {name} -C {tmpdir}"
                elif config.get(f"{sheet_name}_compression") == "zip" and name.endswith("zip"):
                    cmd = f"unzip {name} -d {tmpdir}"
                else:
                    raise RuntimeError("不支持压缩方式：%s" % config.get(f"{sheet_name}_compression"))
                logger.info(cmd)
                logger.info(logserver.cmd(args=cmd, cwd=curpath_log))
        elif config.get(f"{sheet_name}_filetype", "") == "xml":
            logger.info("xml解析成明文")
            for name in response:
                if name.endswith("xml"):
                    content_encrypt = logserver.getfo(curpath_log.rstrip("/") + "/" + name).read()
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
                if name.endswith(config.get(f"{sheet_name}_filetype")):
                    logserver.cmd(args=f"cp -f {name} {tmpdir}", cwd=curpath_log)

        # 提取日志内容
        logger.info("提取日志内容")
        act_log_dict = dict()
        cmd = "ls -rt *%s" % config[f"{sheet_name}_filetype"]
        response = logserver.cmd(args=cmd, cwd=tmpdir).strip().split()

        if config.get(f"{sheet_name}_filetype") in ["AVL", "txt"] or (config.get(f"{sheet_name}_filetype") == "xml" and config.get(f"{sheet_name}_splitflag", False)):
            log_lines = []
            for name in response:
                content = logserver.getfo(remotepath=tmpdir.rstrip("/") + "/" + name).read().decode("utf-8").strip().split("\n")
                if config.get(f"{sheet_name}_exist_head", None):
                    content = content[1:]
                log_lines += content

            for line in log_lines:
                fields = line.split(config.get(f"{sheet_name}_splitflag"))
                key = "_".join(list(map(lambda x: str(fields[x]), keyvalue_headNos))) if keyvalue_headNos else "log"
                if key in act_log_dict:
                    act_log_dict[key].append(fields)
                else:
                    act_log_dict[key] = [fields]

        elif config.get(f"{sheet_name}_filetype") == "xml" and not config.get(f"{sheet_name}_splitflag", None):
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

            log_xml = log_xmlprefix + "\n".join(sorted(content_list)) + log_xmlsuffix
            act_log_dict["log"] = [[log_xml]]

        if otherpath_log and logserver.cmd(f"find {otherpath_log} -type f|wc -l").strip() != "0":
            mark_tmp = [f"评测相关检查，上报目录存在文件：{otherpath_log}"]
        else:
            mark_tmp = list()

        result_list = list()
        for case_name, case in cases.items():
            try:
                logger.info("%s\t核对用例日志：%s\t%s\t%s" % (
                    datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), sheet_name, counter, case_name))

                mark = list()
                key = "_".join(list(map(lambda x: case[0][x], keynames))) if keynames else "log"

                # 预期值
                logger.info("预期值格式化")
                exp_log_list = casename2exp_log(p_excel, sheet_name)[case_name]

                # 实际值
                logger.info("实际值格式化")
                if key in act_log_dict:
                    act_log_list = act_log(
                        p_excel=p_excel,
                        sheet_name=sheet_name,
                        act_val_list=act_log_dict.pop(key),
                        sort_flag=config.get(f"{sheet_name}_sort_flag", None)
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
                    continue

                # 确定日志格式
                if config.get(f"{sheet_name}_reportrule", None):
                    datatype = "list"
                elif config.get(f"{sheet_name}_filetype", None) == "xml" and not config.get(f"{sheet_name}_splitflag", None):
                    datatype = "xml"
                else:
                    datatype = None

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
                if mark:
                    mark_tmp.extend(mark)
                    result_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["备注"], "\n".join(mark), None))
                    result_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["结果"], "Failed", (255, 0, 0)))
                else:
                    result_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["备注"], None, None))
                    result_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["结果"], "Pass", (0, 255, 0)))

            except Exception as e:
                logger.error(f"Exception log_active:{e}")
                result_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["备注"], str(e), None))
                result_list.append((case[0]["row"], sheet_name2head2col[sheet_name]["结果"], "Failed", (255, 0, 0)))

            counter += 1

        if act_log_dict:
            logger.error(f"多出日志统计{len(act_log_dict)}条：{act_log_dict}")
            mark_tmp.append(f"多出日志统计{len(act_log_dict)}条：{act_log_dict}")

        result_deal(
            xls=path, sheet_index=sheet_name, result_list=result_list,
            row=1, head2col=sheet_name2head2col[sheet_name],
            mark=mark_tmp, only_write=False, newpath=newpath
        )

    logserver.client.close()
    dpi_xsa.client.close()
    dpi_xdr.client.close()
