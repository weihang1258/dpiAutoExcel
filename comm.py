#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2023/9/21 10:14
# @Author  : weihang
# @File    : comm.py
import ipaddress
import json
import logging
import os
import re
import sys
import time
from io import BytesIO

from common import list_split_by_unit, gettime, setup_logging
from dict_comparer import DictComparer
from dpistat import CheckDpiStat
from excel import Excel
from linux import Linux
from socket_linux import SocketLinux
from ssh import SSHManager
from xml_comparer import XMLComparer

# 添加日志打印
logger = setup_logging(log_file_path="log/comm.log", logger_name="comm")


def result_deal(xls, sheet_index: str, result_list, row: int, head2col: dict, mark: list, only_write=False,  isquit=True,
                newpath=None):
    logger.info([xls, sheet_index, result_list, row, head2col, mark, only_write,  isquit, newpath])
    logger.info("结果准备写入excel")
    if type(xls) == str:
        xls = Excel(xls)

    if not only_write:
        mark = list(map(lambda x: str(x), mark))
        if mark:
            result_list.append((row, head2col["备注"], "\n".join(mark), None))
            result_list.append((row, head2col["结果"], "Failed", (255, 0, 0)))
        else:
            result_list.append((row, head2col["备注"], None, None))
            result_list.append((row, head2col["结果"], "Pass", (0, 255, 0)))

    # 结果去重
    logger.info("结果去重")
    tmp = list()
    tmp1 = list()
    for a, b, c, d in result_list[::-1]:
        if (a, b, c) in tmp:
            pass
        else:
            tmp.append((a, b, c))
            tmp1.insert(0, (a, b, c, d))
    result_list = tmp1

    # 结果按行优化
    logger.info("结果按行优化")
    rowx_colx2value = dict()
    rowx_colx_red2value = dict()
    for rowx, colx, value, bkgcolor in result_list:
        # 提取每行的全部value
        if rowx in rowx_colx2value:
            # logger.info([rowx, colx, value])
            rowx_colx2value[rowx][colx] = value
        else:
            # logger.info([rowx, colx, value])
            rowx_colx2value[rowx] = {colx: value}

        # 提取每行要录入红色的全部value
        if bkgcolor == (255, 0, 0) and rowx in rowx_colx_red2value:
            # logger.info([rowx, colx, value])
            rowx_colx_red2value[rowx][colx] = value
        elif bkgcolor == (255, 0, 0) and rowx not in rowx_colx_red2value:
            # logger.info([rowx, colx, value])
            rowx_colx_red2value[rowx] = {colx: value}
        else:
            pass

    logger.info("非标红数据写入excel")
    rowx_colx2valuelist = list()
    for rowx, tmp in rowx_colx2value.items():
        tmp = sorted(tmp.items(), key=lambda x: x[0])
        # logger.error(f"tmp{rowx}:{tmp}")
        tmp_col = tmp[0][0]
        tmp_value = list()
        for i in range(len(tmp)):
            colx, value = tmp[i]
            if i == 0:
                tmp_value.append(value)
            else:
                if colx - tmp[i - 1][0] == 1:
                    tmp_value.append(value)
                elif colx - tmp[i - 1][0] == 0:
                    tmp_value[-1] = value
                else:
                    rowx_colx2valuelist.append((rowx, tmp_col, tmp_value))
                    tmp_col = colx
                    tmp_value = [value]
        # logger.error([rowx, tmp_col, tmp_value])
        rowx_colx2valuelist.append((rowx, tmp_col, tmp_value))

    # 全量写入，先从sheet复制数据并修改再写入
    if len(list(set(map(lambda x: x[0], rowx_colx2valuelist)))) > 1:
        xls.optimized_write(sheet_index=sheet_index, data=rowx_colx2valuelist, rowx=1, colx=0, bkgcolor=(255, 255, 255))
    else:
        for rowx, colx, row_values in rowx_colx2valuelist:
            # logger.info(rowx, colx, row_values)
            xls.write_row_values(sheet_index=sheet_index, rowx=rowx, colx=colx, value=row_values, bkgcolor=(255, 255, 255))
            # logger.error(["w",rowx,colx,row_values])


        for rowx, tmp in rowx_colx2value.items():
            row_values = list()
            colx_prefix = None
            colx_first = None
            for colx, value in sorted(tmp.items(), key=lambda x: x[0]):
                colx_first = colx_first if colx_first else colx
                if (not colx_prefix) or (colx_prefix and colx_prefix + 1 == colx):
                    row_values.append(value)
                else:
                    # logger.info(rowx, colx_first, row_values)
                    xls.write_row_values(sheet_index=sheet_index, rowx=rowx, colx=colx_first, value=row_values,
                                         bkgcolor=(255, 255, 255))
                    row_values = [value]
                    colx_first = colx
                colx_prefix = colx
            # logger.info(rowx, colx_first, row_values)
            xls.write_row_values(sheet_index=sheet_index, rowx=rowx, colx=colx_first, value=row_values,
                                 bkgcolor=(255, 255, 255))
    logger.info("标红数据写入excel")
    rowx_colx_red2valuelist = list()
    for rowx, tmp in rowx_colx_red2value.items():
        tmp = sorted(tmp.items(), key=lambda x: x[0])
        tmp_col = tmp[0][0]
        tmp_value = list()
        for i in range(len(tmp)):
            colx, value = tmp[i]
            if i == 0:
                tmp_value.append(value)
            else:
                if colx - tmp[i - 1][0] == 1:
                    tmp_value.append(value)
                elif colx - tmp[i - 1][0] == 0:
                    tmp_value[-1] = value
                else:
                    rowx_colx_red2valuelist.append((rowx, tmp_col, tmp_value))
                    tmp_col = colx
                    tmp_value = [value]
        rowx_colx_red2valuelist.append((rowx, tmp_col, tmp_value))

    for rowx, colx, row_values in rowx_colx_red2valuelist:
        # logger.info([rowx, colx, row_values])
        xls.write_row_values(sheet_index=sheet_index, rowx=rowx, colx=colx, value=row_values, bkgcolor=(255, 0, 0))
        # logger.error(["r", rowx, colx, row_values])


    # for rowx, tmp in rowx_colx_red2value.items():
    #     row_values = list()
    #     colx_prefix = None
    #     colx_first = None
    #     for colx, value in sorted(tmp.items(), key=lambda x: x[0]):
    #         colx_first = colx_first if colx_first else colx
    #         if (not colx_prefix) or (colx_prefix and colx_prefix + 1 == colx):
    #             row_values.append(value)
    #         else:
    #             # logger.info(rowx, colx_first, row_values)
    #             xls.write_row_values(sheet_index=sheet_index, rowx=rowx, colx=colx_first, value=row_values,
    #                                  bkgcolor=(255, 0, 0))
    #             row_values = [value]
    #             colx_first = colx
    #         colx_prefix = colx
    #     # logger.info(rowx, colx_first, row_values)
    #     xls.write_row_values(sheet_index=sheet_index, rowx=rowx, colx=colx_first, value=row_values,
    #                          bkgcolor=(255, 0, 0))

    if isquit:
        if newpath:
            path_save = newpath
        elif xls.is_open:
            path_save = xls.path.replace(".xlsx", f"_{gettime(5)}.xlsx")
        else:
            path_save = xls.path
        logger.info(f"xlsx保存路径：{path_save}")
        xls.save(path_save)
        xls.close()


def compare_exp(exp_log_list: list, act_log_list: list, case: list, head2col: dict, time_s: int, time_e: int, ignore_fields=None, length_fields=None, time_fields=None, datatype=None):
    logger.info(f"exp_log_list：{exp_log_list}")
    logger.info(f"act_log_list：{act_log_list}")
    ignore_fields = ignore_fields.split(",") if ignore_fields else None
    time_fields = dict(map(lambda x: (x, (time_s, time_e)), time_fields.split(","))) if time_fields else None
    length_fields = length_fields.split(",") if length_fields else None

    mark = list()
    result_list = list()
    # 判断日志条数是否一致
    if len(exp_log_list) != len(act_log_list):
        mark.append(f"期望值条数：{len(exp_log_list)}，实际值条数：{len(act_log_list)}！")
        # logger.info(case)
        # logger.info((case[0]["row"], head2col["实际条数"], len(act_log_list), (255, 0, 0)))
        mark.append(json.dumps(act_log_list))
        # logger.error(f"mmark1:{[(case[0]["row"], head2col["实际条数"], len(act_log_list), (255, 0, 0))]}")
        result_list.append((case[0]["row"], head2col["实际条数"], len(act_log_list), (255, 0, 0)))
        for i in range(min(len(exp_log_list), len(act_log_list))):
            for k, v in act_log_list[i].items():
                # logger.error(k)
                # logger.error(f"mmark2:{[(case[i]["row"], head2col[k], json.dumps(v) if type(v) == dict else v, (255, 255, 255))]}")
                result_list.append((case[i]["row"], head2col[k], json.dumps(v) if type(v) == dict else v, (255, 255, 255)))
    else:
        result_list.append((case[0]["row"], head2col["实际条数"], len(act_log_list), (255, 255, 255)))
        for i in range(len(act_log_list)):
            for k, v in act_log_list[i].items():
                # 将预期值颜色重置
                tmp_exp_value = exp_log_list[i][k.replace("act_", "exp_")]
                result_list.append((case[i]["row"], head2col[k.replace("act_", "exp_")], json.dumps(tmp_exp_value) if type(tmp_exp_value) == dict else tmp_exp_value, (255, 255, 255)))

                name = k[4:]
                # 针对xml文件对比
                if datatype in ("xml", "dict"):
                    exp_val = exp_log_list[i]["exp_" + name]
                    if datatype == "xml":
                        logger.info("开始xml字符串对比")
                        comparer = XMLComparer(exp_val, v, ignore_fields=ignore_fields, time_fields=time_fields, length_fields=length_fields)
                    elif datatype == "dict":
                        logger.info("开始dict对比")
                        comparer = DictComparer(exp_val, v, ignore_fields=ignore_fields, time_fields=time_fields, length_fields=length_fields)
                    else:
                        raise RuntimeError(f"请检查datatype：{datatype}")
                    res_comp = comparer.compare()
                    diff = comparer.differences
                    result_list.append((case[i]["row"], head2col[k], json.dumps(v) if type(v) == dict else v, (255, 255, 255)))

                    if diff:
                        mark += diff
                        # result_list.append((case[i]["row"], head2col[k], v, (255, 0, 0)))
                        # result_list.append((case[i]["row"], head2col[k.replace("act_", "exp_")],
                        #                     exp_log_list[i][k.replace("act_", "exp_")], (255, 0, 0)))


                elif name.startswith("None_"):
                    result_list.append((case[i]["row"], head2col[k], v, (255, 255, 255)))
                elif name.startswith("time_"):
                    if type(v) == str and v.startswith("17"):
                        v = int(v)
                    if type(v) in (int, float) and v < 2000000000:
                        time_act = int(v)
                    elif type(v) in (int, float) and v >= 9999999999:
                        time_act = int(str(int(v))[:10])
                    elif type(v) == str and re.match(r"\d\d\d\d-\d\d-\d\d \d\d:\d\d:\d\d\.\d+", v):
                        time_act = int(time.mktime(time.strptime(v, '%Y-%m-%d %H:%M:%S.%f')))
                    elif type(v) == str and re.match(r"\d\d\d\d-\d\d-\d\d \d\d:\d\d:\d\d", v):
                        time_act = int(time.mktime(time.strptime(v, '%Y-%m-%d %H:%M:%S')))
                    else:
                        raise RuntimeError(f"name:{name},value:{v},请检查脚本！")
                    if time_act <= time_s and time_act > time_e:
                        mark.append(f"{k}：{v}，时间不准确！")
                        result_list.append((case[i]["row"], head2col[k], v, (255, 0, 0)))
                        result_list.append((case[i]["row"], head2col[k.replace("act_", "exp_")],
                                            exp_log_list[i][k.replace("act_", "exp_")], (255, 0, 0)))
                    else:
                        result_list.append((case[i]["row"], head2col[k], v, (255, 255, 255)))

                    # 同步对比字符串长度
                    exp_val = exp_log_list[i]["exp_" + name]
                    if len(str(v)) != len(str(exp_val)):
                        mark.append(f"{k}：实际值{v}，期望值{exp_val}")
                        result_list.append((case[i]["row"], head2col[k], v, (255, 0, 0)))
                        result_list.append((case[i]["row"], head2col[k.replace("act_", "exp_")],
                                            exp_log_list[i][k.replace("act_", "exp_")], (255, 0, 0)))
                    else:
                        result_list.append((case[i]["row"], head2col[k], v, (255, 255, 255)))

                elif name.startswith("len_"):
                    exp_val = exp_log_list[i]["exp_" + name]
                    if len(str(v)) != len(str(exp_val)):
                        mark.append(f"{k}：实际值{v}，期望值{exp_val}")
                        result_list.append((case[i]["row"], head2col[k], v, (255, 0, 0)))
                        result_list.append((case[i]["row"], head2col[k.replace("act_", "exp_")],
                                            exp_log_list[i][k.replace("act_", "exp_")], (255, 0, 0)))
                    else:
                        result_list.append((case[i]["row"], head2col[k], v, (255, 255, 255)))
                else:
                    exp_val = exp_log_list[i]["exp_" + name]
                    if exp_val != v:
                        mark.append(f"{k}：实际值{v}，期望值{exp_val}")
                        result_list.append((case[i]["row"], head2col[k], v, (255, 0, 0)))
                        result_list.append((case[i]["row"], head2col[k.replace("act_", "exp_")],
                                            exp_log_list[i][k.replace("act_", "exp_")], (255, 0, 0)))
                    else:
                        result_list.append((case[i]["row"], head2col[k], v, (255, 255, 255)))

    tmp = list()
    tmp1 = list()
    for a, b, c, d in result_list[::-1]:
        if (a, b, c) in tmp:
            pass
        else:
            tmp.append((a, b, c))
            tmp1.insert(0, (a, b, c, d))
    result_list = tmp1

    return {"mark": mark, "result_list": result_list}


def tcpreplay(ssh: SSHManager, pcaps, eth, M=None, x=None, p=None, splitflag=None):
    linux = Linux(ssh)
    dir_remote = "/tmp/pcap_auto"
    if not linux.exist_path(dir_remote):
        linux.mkdir(dir_remote)
    # eth修改mtu为2000
    linux.mtu(eth, value=2000)
    pcaps_remote = list()
    for pcap in pcaps.split(sep=splitflag):
        # 传包到服务器
        if ":" in pcap or not pcap.startswith("/"):
            name = pcap.rsplit("\\", 1)[1]
            pcap_remote = dir_remote + "/" + name
            logger.info("传包到服务器")
            logger.info("%s --> %s" % (pcap, pcap_remote))
            if not os.path.isfile(pcap):
                raise RuntimeError("缺少包：%s,请检查！" % pcap)
            ssh.check_remote_file(pcap, pcap_remote)
        else:
            pcap_remote = pcap
        pcaps_remote.append(pcap_remote)

    # tcpreplay发包
    cmd = "tcpreplay -i %s" % eth
    if M:
        cmd = f"{cmd} -M {M}"
    if x:
        cmd = f"{cmd} -x {x}"
    if p:
        cmd = f"{cmd} -p {p}"
    for i in range(len(pcaps_remote)):
        pcap_remote = pcaps_remote[i]
        cmd = f"{cmd} {pcap_remote}"
        logger.info(f"发包{i + 1}/{len(pcaps_remote)}：{cmd}")
        logger.info(ssh.ssh_exec_cmd(cmd, path="/tmp").decode("utf-8"))



def pcap_send(client:tuple, pcaps, uplink_iface, downlink_iface=None, mbps=50, uplink_vlan=None, downlink_vlan=None,verbose=None, force_ip_src=None, force_ip_dst=None, force_sport=None, force_dport=None, force_build_flow=None, enable_pcap_cache=False, pcap_cache_dir="cached_pcaps", bufsize=1024):
    sl = SocketLinux(client) if type(client) == tuple else client
    dir_remote = "/tmp/pcap_auto"
    if not sl.isdir(dir_remote):
        sl.mkdir(dir_remote)
    # eth修改mtu为2000
    if uplink_iface == downlink_iface:
        sl.mtu(uplink_iface, value=2000)
    elif downlink_iface:
        sl.mtu(downlink_iface, value=2000)
    else:
        sl.mtu(uplink_iface, value=2000)

    pcaps_remote = list()
    for pcap in pcaps:
        # 传包到服务器
        if ":" in pcap or not pcap.startswith("/"):
            name = pcap.rsplit("\\", 1)[1]
            pcap_remote = dir_remote + "/" + name
            logger.info("传包到服务器")
            logger.info("%s --> %s" % (pcap, pcap_remote))
            if not os.path.isfile(pcap):
                raise RuntimeError("缺少包：%s,请检查！" % pcap)
            sl.put(pcap, pcap_remote)
        else:
            pcap_remote = pcap
        pcaps_remote.append(pcap_remote)

    for i in range(len(pcaps_remote)):
        pcap_remote = pcaps_remote[i]
        logger.info(f"发包 {i + 1}/{len(pcaps_remote)}：{pcap_remote}")
    # logger.info(sl.scapy_send(eth=eth, pcaps=pcaps_remote, mbps=mbps, show_progress=show_progress, bufsize=bufsize))
    logger.info((sl.scapy_send(pcaps=pcaps_remote, uplink_iface=uplink_iface, downlink_iface=downlink_iface, uplink_vlan=uplink_vlan, downlink_vlan=downlink_vlan, mbps=mbps, verbose=verbose, force_ip_src=force_ip_src, force_ip_dst=force_ip_dst, force_sport=force_sport, force_dport=force_dport, force_build_flow=force_build_flow, enable_pcap_cache=enable_pcap_cache, pcap_cache_dir=pcap_cache_dir, bufsize=bufsize)))
    sl.client.close()



def tcpdump_start(ssh: SSHManager, path, eth, extended=""):
    cmd = "kill -9 `ps -ef|grep tcpdump|grep -v grep|awk '{print $2}'`"
    ssh.ssh_exec_cmd(cmd)
    cmd = "tcpdump -i %s -w %s %s &" % (eth, path, extended)
    ssh.ssh_exec_cmd(cmd)


def tcpdump_stop(ssh: SSHManager):
    cmd = "kill -9 `ps -ef|grep tcpdump|grep -v grep|awk '{print $2}'`"
    ssh.ssh_exec_cmd(cmd)


# def mytrex1(ssh: SSHManager, pcaps, cmd: str, base_dir, config, multiple=1, cpuNo=1, time=1, extended="",splitflag=None):
#     # cmd = "./t-rex-64 --cfg /etc/trex_cfg.yaml -f  test/http_48G.yaml  -m 22.5 -c 5 -d 120 -e"
#     cmd_list = cmd.strip().split()
#     cmd_dict = dict()
#     if len(cmd_list) == 0:
#         return
#     elif len(cmd_list) == 1:
#         cmd_dict["-f"] = cmd_list[0]
#     else:
#         key = ""
#         val = []
#         for i in cmd_list[1:] + ["-end"]:
#             if i.startswith("-"):
#                 if key:
#                     cmd_dict[key] = " ".join(val)
#                     val = []
#                 key = i
#             else:
#                 val.append(i)
#     logger.info(cmd_dict)
#
#     if "--cfg" in cmd_dict:
#         config = cmd_dict["--cfg"]
#         cmd_dict.pop("--cfg")
#     if "-f" in cmd_dict:
#         yamlfile = cmd_dict["-f"]
#         cmd_dict.pop("-f")
#     else:
#         raise RuntimeError("没指定yaml文件：%s" % cmd)
#     if "-m" in cmd_dict:
#         multiple = cmd_dict["-m"]
#         cmd_dict.pop("-m")
#     if "-c" in cmd_dict:
#         cpuNo = cmd_dict["-c"]
#         cmd_dict.pop("-c")
#     if "-d" in cmd_dict:
#         time = cmd_dict["-d"]
#         cmd_dict.pop("-d")
#     for key, val in cmd_dict.items():
#         extended = (extended + " " + key + val).strip()
# logger.info(config,yamlfile,multiple,cpuNo,time,extended)


def compare_tuple(tuple_exp: tuple, tuple_act: tuple, time_s: int, time_e: int, time_fields=None, length_fields=None, ignore_fields=None, flag=None):
    # 对比字段长度
    if len(tuple_exp) != len(tuple_act):
        raise RuntimeError(f"key值：{flag}，预期值长度： {len(tuple_exp)}，实际值长度： {len(tuple_act)}")
    else:
        # 对比val类型
        for i in range(len(tuple_exp)):
            flag = i
            val_exp = tuple_exp[i]
            val_act = tuple_act[i]
            if isinstance(val_act, type(val_exp)):
                raise RuntimeError(f"元组index{i}格式不对，预期值： {tuple_exp}，实际值： {tuple_act}")
        # 对比val值
        for i in range(len(tuple_exp)):
            val_exp = tuple_exp[i]
            val_act = tuple_act[i]
            # val值为列表
            if isinstance(val_exp, list):
                compare_tuple(tuple(sorted(val_exp)), tuple(sorted(val_act)), time_s, time_e, time_fields, length_fields, ignore_fields, flag)
            if isinstance(val_exp, tuple):
                compare_tuple(val_exp, val_act, time_s, time_e, time_fields, length_fields, ignore_fields, flag)
            if isinstance(val_exp, set):
                compare_tuple(tuple(val_exp), tuple(val_act), time_s, time_e, time_fields, length_fields, ignore_fields, flag)
            elif isinstance(val_exp, dict):
                compare_dict(val_exp, val_act, time_s, time_e, time_fields, length_fields, ignore_fields, flag)
            else:
                # 其他字段对比
                if val_exp != val_act:
                    raise RuntimeError(f"元组index{i}值不对，预期值： {tuple_exp}，实际值： {tuple_act}")

def compare_dict(dict_exp: dict, dict_act: dict, time_s: int, time_e: int, time_fields=None, length_fields=None, ignore_fields=None, flag=None):
    # 对比字段长度
    if len(dict_exp) != len(dict_act):
        raise RuntimeError(f"key值：{flag}，预期值长度： {len(dict_exp)}，实际值长度： {len(dict_act)}")
    # 对比key是否一样
    elif sorted(dict_exp.keys()) != sorted(dict_act.keys()):
        raise RuntimeError(f"预期值keys： {sorted(dict_exp.keys())}，实际值keys： {sorted(dict_act.keys())}")
    else:
        # 对比val类型
        for key, val in dict_exp.items():
            if isinstance(dict_act[key], type(val)):
                raise RuntimeError(f"key值：{key}，预期值类型： {type(val)}，实际值类型： {type(dict_act[key])}")
        # 对比val值
        for key, val in dict_exp.items():
            flag = key
            # val值为列表
            if isinstance(val, list):
                compare_tuple(tuple(sorted(val)), tuple(sorted(dict_act[key])), time_s, time_e, time_fields, length_fields, ignore_fields, flag)
            if isinstance(val, tuple):
                compare_tuple(val, dict_act[key], time_s, time_e, time_fields, length_fields, ignore_fields, flag)
            if isinstance(val, set):
                compare_tuple(tuple(val), tuple(dict_act[key]), time_s, time_e, time_fields, length_fields, ignore_fields, flag)
            elif isinstance(val, dict):
                compare_dict(val, dict_act[key], time_s, time_e, time_fields, length_fields, ignore_fields, flag)
            else:
                # 忽略字段
                if ignore_fields and key in ignore_fields:
                    continue
                # 时间字段对比
                if time_fields and key in time_fields:
                    if isinstance(val, int) or isinstance(val, float) or str(val).replace(".", "").isdigit():
                        time_act = int(time_fields)
                    elif isinstance(val, str) and re.match(r"\d\d\d\d-\d\d-\d\d \d\d:\d\d:\d\d", val):
                        time_act = int(time.mktime(time.strptime(val, '%Y-%m-%d %H:%M:%S')))
                    else:
                        raise RuntimeError(f"key:{key},value:{val},请检查脚本！")

                    if time_act <= time_s and time_act > time_e:
                        raise RuntimeError(f"key值：{key}，预期值时间： {time_s}-{time_e}，实际值时间： {time_act}")
                # 长度字段对比
                if (time_fields and key in time_fields) or (length_fields and key in length_fields):
                    if len(str(val)) != len(str(dict_act[key])):
                        raise RuntimeError(f"key值：{key}，预期值长度： {len(str(val))}，实际值长度： {len(str(dict_act[key]))}")
                # 其他字段对比
                if (not time_fields or key not in time_fields) and (not length_fields or key not in length_fields):
                    if val != dict_act[key]:
                        raise RuntimeError(f"key值：{key}，预期值： {val}，实际值： {dict_act[key]}")





if __name__ == '__main__':
    # a = {'pcaps': ['/home/pcap_auto/bc/pcapdump_14.pcap'], 'iface': 'ens256'}
    # a = {'pcaps':['/home/pcap_auto/fiter/IPv6-TCP-2e02__1208-2e03__1208-10650-80-4-3-378-481.pcap'], 'iface': 'ens193', 'inter': 2e-05, 'return_packets': False}
    # a["eth"] = a["iface"]
    # a["eth"] = "ens256"
    # a.pop("iface")
    # a["mbps"] = 30
    #
    # print(pcap_send(client=("172.31.140.87", 9000), **a))
    # exp_log_list = [{'exp_devid': '001002', 'exp_CommandId': '58804335', 'exp_IP': '20.9.1.2', 'exp_cnt': 1, 'exp_type': 'filter', 'exp_filename': '42111310_001002_17397737791428992200.xml', 'exp_time_time': '2025-02-17 14:32:37'}, {'exp_devid': '001002', 'exp_CommandId': '80276166', 'exp_IP': '2e03::1208', 'exp_cnt': 1, 'exp_type': 'filter', 'exp_filename': '42111310_001002_17397737791428992200.xml', 'exp_time_time': '2025-02-17 14:32:37'}, {'exp_devid': '001002', 'exp_CommandId': '64985242', 'exp_IP': '20.6.1.1', 'exp_cnt': 1, 'exp_type': 'mirrorvlan_ns', 'exp_filename': '42111310_001002_17397737791549288200.txt', 'exp_time_time': '2025-02-17 14:32:37'}, {'exp_devid': '001002', 'exp_CommandId': '75929494', 'exp_IP': '2e03::c0c', 'exp_cnt': 1, 'exp_type': 'mirrorvlan_ns', 'exp_filename': '42111310_001002_17397737791549288200.txt', 'exp_time_time': '2025-02-17 14:32:37'}, {'exp_devid': '001002', 'exp_CommandId': '56408814', 'exp_IP': '20.1.1.1', 'exp_cnt': 1, 'exp_type': 'monitor', 'exp_filename': '42111310_001002_17397737791303542200.xml', 'exp_time_time': '2025-02-17 14:32:37'}, {'exp_devid': '001002', 'exp_CommandId': '53339862', 'exp_IP': '2e03::201', 'exp_cnt': 1, 'exp_type': 'monitor', 'exp_filename': '42111310_001002_17397737791303542200.xml', 'exp_time_time': '2025-02-17 14:32:37'}, {'exp_devid': '001002', 'exp_CommandId': '85986442', 'exp_IP': '20.3.1.1', 'exp_cnt': 1, 'exp_type': 'pcapdump_ns', 'exp_filename': '42111310_001002_17397737791669972200.txt', 'exp_time_time': '2025-02-17 14:32:37'}, {'exp_devid': '001002', 'exp_CommandId': '43824775', 'exp_IP': '2e03::60c', 'exp_cnt': 1, 'exp_type': 'pcapdump_ns', 'exp_filename': '42111310_001002_17397737791669972200.txt', 'exp_time_time': '2025-02-17 14:32:37'}, {'exp_devid': '001002', 'exp_CommandId': '85201171', 'exp_IP': '30.5.1.11', 'exp_cnt': 1, 'exp_type': 'pcapdump_ns', 'exp_filename': '42111310_001002_17397737791669972200.txt', 'exp_time_time': '2025-02-17 14:32:37'}]
    # act_log_list = [{'act_devid': '001002', 'act_CommandId': '58804335', 'act_IP': '20.9.1.2', 'act_cnt': '1', 'act_type': 'filter', 'act_filename': '42111310_001002_17397737791428992200.xml', 'act_time_time': '2025-02-17 14:29:48'}, {'act_devid': '001002', 'act_CommandId': '80276166', 'act_IP': '2e03::1208', 'act_cnt': '1', 'act_type': 'filter', 'act_filename': '42111310_001002_17397737791428992200.xml', 'act_time_time': '2025-02-17 14:29:48'}, {'act_devid': '001002', 'act_CommandId': '64985242', 'act_IP': '20.6.1.1', 'act_cnt': '1', 'act_type': 'mirrorvlan_ns', 'act_filename': '42111310_001002_17397737791549288200.xml', 'act_time_time': '2025-02-17 14:30:38'}, {'act_devid': '001002', 'act_CommandId': '75929494', 'act_IP': '2e03::c0c', 'act_cnt': '1', 'act_type': 'mirrorvlan_ns', 'act_filename': '42111310_001002_17397737791549288200.xml', 'act_time_time': '2025-02-17 14:30:38'}, {'act_devid': '001002', 'act_CommandId': '56408814', 'act_IP': '20.1.1.1', 'act_cnt': '1', 'act_type': 'monitor', 'act_filename': '42111310_001002_17397737791303542200.xml', 'act_time_time': '2025-02-17 14:29:48'}, {'act_devid': '001002', 'act_CommandId': '53339862', 'act_IP': '2e03::201', 'act_cnt': '1', 'act_type': 'monitor', 'act_filename': '42111310_001002_17397737791303542200.xml', 'act_time_time': '2025-02-17 14:29:48'}, {'act_devid': '001002', 'act_CommandId': '85986442', 'act_IP': '20.3.1.1', 'act_cnt': '1', 'act_type': 'pcapdump_ns', 'act_filename': '42111310_001002_17397737791669972200.xml', 'act_time_time': '2025-02-17 14:30:38'}, {'act_devid': '001002', 'act_CommandId': '43824775', 'act_IP': '2e03::60c', 'act_cnt': '1', 'act_type': 'pcapdump_ns', 'act_filename': '42111310_001002_17397737791669972200.xml', 'act_time_time': '2025-02-17 14:30:38'}, {'act_devid': '001002', 'act_CommandId': '85201171', 'act_IP': '30.5.1.11', 'act_cnt': '1', 'act_type': 'pcapdump_ns', 'act_filename': '42111310_001002_17397737791669972200.xml', 'act_time_time': '2025-02-17 14:30:38'}]
    exp_log_list = [{'exp_xml': '<filterResult>\n <version>3.1</version>\n <provID>270</provID>\n <idcId>A2.B1.B2-20100001</idcId>\n<log>\n  <logId>173077516550000379</logId>\n  <commandId>10010302</commandId>\n  <houseId>100000000012345</houseId>\n  <srcIp>20.10.1.7</srcIp>\n  <destIp>30.10.1.7</destIp>\n  <srcPort>54706</srcPort>\n  <destPort>80</destPort>\n  <domainName>www.act4016836.com</domainName>\n  <trafficType>2</trafficType>\n  <protocol>1</protocol>\n  <applicationProtocol>5</applicationProtocol>\n  <businessProtocol>28</businessProtocol>\n  <url>aHR0cDovL3d3dy5hY3Q0MDE2ODM2LmNvbS91dGY2Lmh0bWw=</url>\n  <gatherTime>2024-11-05 10:52:45</gatherTime>\n  <virusOs>0</virusOs>\n </log>\n<log>\n  <logId>173077516550000380</logId>\n  <commandId>10010302</commandId>\n  <houseId>100000000012345</houseId>\n  <srcIp>20.10.1.8</srcIp>\n  <destIp>30.10.1.7</destIp>\n  <srcPort>54706</srcPort>\n  <destPort>80</destPort>\n  <domainName>www.act4016836.com</domainName>\n  <trafficType>2</trafficType>\n  <protocol>1</protocol>\n  <applicationProtocol>5</applicationProtocol>\n  <businessProtocol>28</businessProtocol>\n  <url>aHR0cDovL3d3dy5hY3Q0MDE2ODM2LmNvbS91dGY2Lmh0bWw=</url>\n  <gatherTime>2024-11-05 10:52:45</gatherTime>\n  <virusOs>0</virusOs>\n </log>\n<log>\n  <logId>173077516566000394</logId>\n  <commandId>10010302</commandId>\n  <houseId>100000000012345</houseId>\n  <srcIp>20.10.1.9</srcIp>\n  <destIp>30.10.1.7</destIp>\n  <srcPort>54706</srcPort>\n  <destPort>80</destPort>\n  <domainName>www.act4016836.com</domainName>\n  <trafficType>2</trafficType>\n  <protocol>1</protocol>\n  <applicationProtocol>5</applicationProtocol>\n  <businessProtocol>28</businessProtocol>\n  <url>aHR0cDovL3d3dy5hY3Q0MDE2ODM2LmNvbS91dGY2Lmh0bWw=</url>\n  <gatherTime>2024-11-05 10:52:45</gatherTime>\n  <virusOs>0</virusOs>\n </log>\n<timeStamp>2024-11-05 10:52:13</timeStamp>\n</filterResult>'}]
    act_log_list = [{'act_xml': '<filterResult>\n\t<version>3.1</version>\n\t<provID>270</provID>\n\t<idcId>A2.B1.B2-20100001</idcId>\n<log>\n\t\t<logId>175696918180009200</logId>\n\t\t<commandId>10010302</commandId>\n\t\t<houseId>100000000012345</houseId>\n\t\t<srcIp>20.10.1.7</srcIp>\n\t\t<destIp>30.10.1.7</destIp>\n\t\t<srcPort>54706</srcPort>\n\t\t<destPort>80</destPort>\n\t\t<domainName>www.act4016836.com</domainName>\n\t\t<trafficType>2</trafficType>\n\t\t<protocol>1</protocol>\n\t\t<applicationProtocol>5</applicationProtocol>\n\t\t<businessProtocol>28</businessProtocol>\n\t\t<url>aHR0cDovL3d3dy5hY3Q0MDE2ODM2LmNvbS91dGY2Lmh0bWw=</url>\n\t\t<gatherTime>2025-09-04 14:59:41</gatherTime>\n\t\t<virusOs>0</virusOs>\n\t</log>\n<log>\n\t\t<logId>175696918180002280</logId>\n\t\t<commandId>10010302</commandId>\n\t\t<houseId>100000000012345</houseId>\n\t\t<srcIp>20.10.1.8</srcIp>\n\t\t<destIp>30.10.1.7</destIp>\n\t\t<srcPort>54706</srcPort>\n\t\t<destPort>80</destPort>\n\t\t<domainName>www.act4016836.com</domainName>\n\t\t<trafficType>2</trafficType>\n\t\t<protocol>1</protocol>\n\t\t<applicationProtocol>5</applicationProtocol>\n\t\t<businessProtocol>28</businessProtocol>\n\t\t<url>aHR0cDovL3d3dy5hY3Q0MDE2ODM2LmNvbS91dGY2Lmh0bWw=</url>\n\t\t<gatherTime>2025-09-04 14:59:41</gatherTime>\n\t\t<virusOs>0</virusOs>\n\t</log>\n<log>\n\t\t<logId>175696918180008224</logId>\n\t\t<commandId>10010302</commandId>\n\t\t<houseId>100000000012345</houseId>\n\t\t<srcIp>20.10.1.9</srcIp>\n\t\t<destIp>30.10.1.7</destIp>\n\t\t<srcPort>54706</srcPort>\n\t\t<destPort>80</destPort>\n\t\t<domainName>www.act4016836.com</domainName>\n\t\t<trafficType>2</trafficType>\n\t\t<protocol>1</protocol>\n\t\t<applicationProtocol>5</applicationProtocol>\n\t\t<businessProtocol>28</businessProtocol>\n\t\t<url>aHR0cDovL3d3dy5hY3Q0MDE2ODM2LmNvbS91dGY2Lmh0bWw=</url>\n\t\t<gatherTime>2025-09-04 14:59:41</gatherTime>\n\t\t<virusOs>0</virusOs>\n\t</log>\n<timeStamp>2025-09-04 14:59:41</timeStamp>\n</filterResult>'}]
    a = compare_exp([{'exp_xml': '<filterResult>\n <version>3.1</version>\n <provID>270</provID>\n <idcId>A2.B1.B2-20100001</idcId>\n<log>\n  <logId>173077516550000379</logId>\n  <commandId>10010302</commandId>\n  <houseId>100000000012345</houseId>\n  <srcIp>20.10.1.7</srcIp>\n  <destIp>30.10.1.7</destIp>\n  <srcPort>54706</srcPort>\n  <destPort>80</destPort>\n  <domainName>www.act4016836.com</domainName>\n  <trafficType>2</trafficType>\n  <protocol>1</protocol>\n  <applicationProtocol>5</applicationProtocol>\n  <businessProtocol>28</businessProtocol>\n  <url>aHR0cDovL3d3dy5hY3Q0MDE2ODM2LmNvbS91dGY2Lmh0bWw=</url>\n  <gatherTime>2024-11-05 10:52:45</gatherTime>\n  <virusOs>0</virusOs>\n </log>\n<log>\n  <logId>173077516550000380</logId>\n  <commandId>10010302</commandId>\n  <houseId>100000000012345</houseId>\n  <srcIp>20.10.1.8</srcIp>\n  <destIp>30.10.1.7</destIp>\n  <srcPort>54706</srcPort>\n  <destPort>80</destPort>\n  <domainName>www.act4016836.com</domainName>\n  <trafficType>2</trafficType>\n  <protocol>1</protocol>\n  <applicationProtocol>5</applicationProtocol>\n  <businessProtocol>28</businessProtocol>\n  <url>aHR0cDovL3d3dy5hY3Q0MDE2ODM2LmNvbS91dGY2Lmh0bWw=</url>\n  <gatherTime>2024-11-05 10:52:45</gatherTime>\n  <virusOs>0</virusOs>\n </log>\n<log>\n  <logId>173077516566000394</logId>\n  <commandId>10010302</commandId>\n  <houseId>100000000012345</houseId>\n  <srcIp>20.10.1.9</srcIp>\n  <destIp>30.10.1.7</destIp>\n  <srcPort>54706</srcPort>\n  <destPort>80</destPort>\n  <domainName>www.act4016836.com</domainName>\n  <trafficType>2</trafficType>\n  <protocol>1</protocol>\n  <applicationProtocol>5</applicationProtocol>\n  <businessProtocol>28</businessProtocol>\n  <url>aHR0cDovL3d3dy5hY3Q0MDE2ODM2LmNvbS91dGY2Lmh0bWw=</url>\n  <gatherTime>2024-11-05 10:52:45</gatherTime>\n  <virusOs>0</virusOs>\n </log>\n<timeStamp>2024-11-05 10:52:13</timeStamp>\n</filterResult>'}], [{'act_xml': '<filterResult>\n\t<version>3.1</version>\n\t<provID>270</provID>\n\t<idcId>A2.B1.B2-20100001</idcId>\n<log>\n\t\t<logId>175697017681009201</logId>\n\t\t<commandId>10010302</commandId>\n\t\t<houseId>100000000012345</houseId>\n\t\t<srcIp>20.10.1.7</srcIp>\n\t\t<destIp>30.10.1.7</destIp>\n\t\t<srcPort>54706</srcPort>\n\t\t<destPort>80</destPort>\n\t\t<domainName>www.act4016836.com</domainName>\n\t\t<trafficType>2</trafficType>\n\t\t<protocol>1</protocol>\n\t\t<applicationProtocol>5</applicationProtocol>\n\t\t<businessProtocol>28</businessProtocol>\n\t\t<url>aHR0cDovL3d3dy5hY3Q0MDE2ODM2LmNvbS91dGY2Lmh0bWw=</url>\n\t\t<gatherTime>2025-09-04 15:16:16</gatherTime>\n\t\t<virusOs>0</virusOs>\n\t</log>\n<log>\n\t\t<logId>175697017681002281</logId>\n\t\t<commandId>10010302</commandId>\n\t\t<houseId>100000000012345</houseId>\n\t\t<srcIp>20.10.1.8</srcIp>\n\t\t<destIp>30.10.1.7</destIp>\n\t\t<srcPort>54706</srcPort>\n\t\t<destPort>80</destPort>\n\t\t<domainName>www.act4016836.com</domainName>\n\t\t<trafficType>2</trafficType>\n\t\t<protocol>1</protocol>\n\t\t<applicationProtocol>5</applicationProtocol>\n\t\t<businessProtocol>28</businessProtocol>\n\t\t<url>aHR0cDovL3d3dy5hY3Q0MDE2ODM2LmNvbS91dGY2Lmh0bWw=</url>\n\t\t<gatherTime>2025-09-04 15:16:16</gatherTime>\n\t\t<virusOs>0</virusOs>\n\t</log>\n<log>\n\t\t<logId>175697017681008225</logId>\n\t\t<commandId>10010302</commandId>\n\t\t<houseId>100000000012345</houseId>\n\t\t<srcIp>20.10.1.9</srcIp>\n\t\t<destIp>30.10.1.7</destIp>\n\t\t<srcPort>54706</srcPort>\n\t\t<destPort>80</destPort>\n\t\t<domainName>www.act4016836.com</domainName>\n\t\t<trafficType>2</trafficType>\n\t\t<protocol>1</protocol>\n\t\t<applicationProtocol>5</applicationProtocol>\n\t\t<businessProtocol>28</businessProtocol>\n\t\t<url>aHR0cDovL3d3dy5hY3Q0MDE2ODM2LmNvbS91dGY2Lmh0bWw=</url>\n\t\t<gatherTime>2025-09-04 15:16:16</gatherTime>\n\t\t<virusOs>0</virusOs>\n\t</log>\n<timeStamp>2025-09-04 15:16:16</timeStamp>\n</filterResult>'}], [{'执行状态': '1', '用例名': 'FILTER-出向IPV4__单类型__0313多个源IP对应目的IP', 'commandId': '10010302', '策略': '8520767  ip.dst==30.10.1.7 with action.do{eu_plc,type=filt,hid=95217,blk=enable,log=enable,lvl=1025,cid=1000000000300,way=2,time=2024-10-17 09:03:42|2054-10-19 21:04:16,report=enable}', 'pcap': 'fiter/IP-TCP-20.10.1.7-30.10.1.7-54706-80-5-2-371-569.pcap\nfiter/IP-TCP-20.10.1.8-30.10.1.7-54706-80-5-2-371-569.pcap\nfiter/IP-TCP-20.10.1.9-30.10.1.7-54706-80-5-2-371-569.pcap', '结果': None, '备注': None, '实际条数': None, 'exp_xml': '<filterResult>\n <version>3.1</version>\n <provID>270</provID>\n <idcId>A2.B1.B2-20100001</idcId>\n<log>\n  <logId>173077516550000379</logId>\n  <commandId>10010302</commandId>\n  <houseId>100000000012345</houseId>\n  <srcIp>20.10.1.7</srcIp>\n  <destIp>30.10.1.7</destIp>\n  <srcPort>54706</srcPort>\n  <destPort>80</destPort>\n  <domainName>www.act4016836.com</domainName>\n  <trafficType>2</trafficType>\n  <protocol>1</protocol>\n  <applicationProtocol>5</applicationProtocol>\n  <businessProtocol>28</businessProtocol>\n  <url>aHR0cDovL3d3dy5hY3Q0MDE2ODM2LmNvbS91dGY2Lmh0bWw=</url>\n  <gatherTime>2024-11-05 10:52:45</gatherTime>\n  <virusOs>0</virusOs>\n </log>\n<log>\n  <logId>173077516550000380</logId>\n  <commandId>10010302</commandId>\n  <houseId>100000000012345</houseId>\n  <srcIp>20.10.1.8</srcIp>\n  <destIp>30.10.1.7</destIp>\n  <srcPort>54706</srcPort>\n  <destPort>80</destPort>\n  <domainName>www.act4016836.com</domainName>\n  <trafficType>2</trafficType>\n  <protocol>1</protocol>\n  <applicationProtocol>5</applicationProtocol>\n  <businessProtocol>28</businessProtocol>\n  <url>aHR0cDovL3d3dy5hY3Q0MDE2ODM2LmNvbS91dGY2Lmh0bWw=</url>\n  <gatherTime>2024-11-05 10:52:45</gatherTime>\n  <virusOs>0</virusOs>\n </log>\n<log>\n  <logId>173077516566000394</logId>\n  <commandId>10010302</commandId>\n  <houseId>100000000012345</houseId>\n  <srcIp>20.10.1.9</srcIp>\n  <destIp>30.10.1.7</destIp>\n  <srcPort>54706</srcPort>\n  <destPort>80</destPort>\n  <domainName>www.act4016836.com</domainName>\n  <trafficType>2</trafficType>\n  <protocol>1</protocol>\n  <applicationProtocol>5</applicationProtocol>\n  <businessProtocol>28</businessProtocol>\n  <url>aHR0cDovL3d3dy5hY3Q0MDE2ODM2LmNvbS91dGY2Lmh0bWw=</url>\n  <gatherTime>2024-11-05 10:52:45</gatherTime>\n  <virusOs>0</virusOs>\n </log>\n<timeStamp>2024-11-05 10:52:13</timeStamp>\n</filterResult>', 'act_xml': None, '🚀 执行Sheet': None, '🚀 执行Book': None, 'row': 302}], {'执行状态': 0, '用例名': 1, 'commandId': 2, '策略': 3, 'pcap': 4, '结果': 5, '备注': 6, '实际条数': 7, 'exp_xml': 8, 'act_xml': 9, '🚀 执行Sheet': 10, '🚀 执行Book': 11}, 1756970170,1756970241, ignore_fields="", length_fields="filterResult.log.logId", time_fields="filterResult.log.gatherTime,filterResult.timeStamp", datatype="xml")
    logger.info([a])
    sys.exit()
    # from mycode.script.auto_test.idc31.read_write_excel import parser_excel
    # path = r"E:\PycharmProjects\pythonProject_socket\mycode\script\auto_test\idc31\用例_移动.xlsx"
    # p_excel = parser_excel(path=path)
    # sheet_name2head2col = p_excel["sheet_name2head2col"]
    # sheet_name = "mirrorvlan"
    # result_list = [(1, 7, '=HYPERLINK("out/001-目的IP+目的端口（入向）-数安-pcap_exp1724407440.pcap", "out/001-目的IP+目的端口（入向）-数安-pcap_exp1724407440.pcap")', (255, 255, 255)), (1, 8, '=HYPERLINK("out/001-目的IP+目的端口（入向）-数安-pcap_act1724407423.pcap", "out/001-目的IP+目的端口（入向）-数安-pcap_act1724407423.pcap")', (255, 255, 255)), (1, 4, 3000, (255, 255, 255))]
    # path_save = f"{path.split('.')[0]}_{gettime(5)}.xlsx"
    # a = result_deal(path, sheet_name, result_list, 1, sheet_name2head2col[sheet_name], [], newpath=path_save)
    #
    result_list = []

    path = r"E:\DPI_SVN\8AutomatedTest\信安EU自动化3.1\用例_电信.xlsx"
    p_excel = parser_excel(path=path)
    sheet_name2head2col = p_excel["sheet_name2head2col"]
    sheet_name = "bzip"
    path_save = f"{path.split('.')[0]}_{gettime(5)}.xlsx"
    a = result_deal(path, sheet_name, result_list, 1, sheet_name2head2col[sheet_name], [], newpath=path_save)