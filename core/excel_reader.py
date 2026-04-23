#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2023/9/21 10:19
# @Author  : weihang
# @File    : read_write_excel.py
import logging
import os

from utils.common import list_rstrip
from io_handler.excel import Excel
# from comm import compare_exp


def parser_excel(path="用例.xlsx"):
    xls = Excel(path)

    # 获取配置信息
    config = xls.get_config_from_book("配置")

    # 获取设备初始化配置
    name_tmp = None
    type_tmp = None
    config_dev = dict()

    # 尝试读取"设备初始化配置"sheet，如果不存在则跳过
    try:
        for name, lines in xls.head2value(sheet_index="设备初始化配置", keys=["配置名称"]).items():
            if name:
                name_tmp = name
            if name_tmp not in config_dev:
                config_dev[name_tmp] = dict()
            for line in lines:
                # print(line["配置类型"])
                if line["配置类型"]:
                    type_tmp = line["配置类型"]
                if type_tmp not in config_dev[name_tmp]:
                    config_dev[name_tmp][type_tmp] = dict()

                key = line["配置项"]
                val = line["配置值"]
                val = int(val) if type(val) in (int, float) and int(val) == val else val
                # print(name_tmp,type_tmp,key,val)
                config_dev[name_tmp][type_tmp][key] = val
    except Exception as e:
        # 如果"设备初始化配置"sheet 不存在，记录日志并继续执行
        logging.warning(f"未找到'设备初始化配置'sheet 或读取失败：{e}")
        config_dev = dict()

    # print(config_dev)

    # 获取用例信息
    sheet_name2cases = dict()
    sheet_name2head2col = dict()
    sheet_name2heads = dict()
    for sheet_name in xls.workbook.sheet_names:
        if sheet_name not in ("配置", "设备初始化配置", "IP规范"):
            try:
                cases = dict()
                case_name = None
                for key, val in xls.head2value(sheet_index=sheet_name, keys=["用例名"]).items():
                    # print([key, val], '\n')
                    if key and key != "None":
                        case_name = key
                    cases[case_name] = val
                sheet_name2cases[sheet_name] = cases
                head_list = xls.list_rstrip(xls.row_values(sheet_index=sheet_name))
                head2col = dict(map(lambda x: list(x)[::-1], list(enumerate(head_list))))
                sheet_name2head2col[sheet_name] = head2col
                sheet_name2heads[sheet_name] = head_list
            except KeyError as e:
                logging.warning(f"Sheet '{sheet_name}' 缺少必要的列: {e}，跳过该 sheet")
                continue
    xls.close()
    del xls
    return {"config": config, "sheet_name2cases": sheet_name2cases, "sheet_name2head2col": sheet_name2head2col, "sheet_name2heads": sheet_name2heads, "config_dev": config_dev}



def casename2exp_log(p_excel: dict, sheet_name):
    cases = p_excel["sheet_name2cases"][sheet_name]
    head2col = (p_excel["sheet_name2head2col"][sheet_name])
    heads = list()
    for field in head2col.keys():
        if field and field.startswith("exp_"):
            heads.append(field)
    res = dict()
    for casename, val in cases.items():
        # print([casename, val])
        lines = list()
        for case in val:
            tmp = dict()
            for i in heads:
                # print(i,case[i])
                tmp[i] = case[i]
            # 如果期望值全为None，不统计
            # print(1111, list(tmp.values()))
            # print(2222, list_rstrip(list(tmp.values()), flags=('', None)))
            # # 兼容xml
            # if len(tmp) == 1 and tmp.get("exp_value", None):
            #     lines.append(tmp["exp_value"])
            if list_rstrip(list(tmp.values()), flags=('', None)):
                lines.append(tmp)
            else:
                pass
        res[casename] = lines
    return res

def act_log(p_excel: dict, sheet_name, act_val_list, sort_flag=None):
    """
    根据Excel中的表头和实际值列表生成字典列表，并可选择进行排序。

    :param p_excel: 包含Excel数据的字典，结构应包含'sheet_name2heads'键。
    :param sheet_name: 需要处理的表格名称。
    :param act_val_list: 包含实际值的列表，每个元素也是一个列表，对应表头的各个字段。
    :param sort_flag: 可选，指定排序的字段，格式为逗号分隔的字符串。
    :return: 包含处理后数据的列表，每个元素是一个字典。
    """
    # print("act_val_list：", act_val_list)

    # 提取表头中以'act_'开头的字段
    heads = list()
    for field in p_excel["sheet_name2heads"][sheet_name]:
        if field and field.startswith("act_"):
            heads.append(field)

    res = list()

    # 处理每一个实际值列表
    # 处理dict
    if act_val_list and type(act_val_list[0]) == dict:
        # print(f"act_val_list:{act_val_list}")
        if sort_flag:
            sort_flag_list = sort_flag.split(",")
            # print(f"sort_flag_list:{sort_flag_list}")
            act_val_list.sort(key=lambda x: [int(x[i]) if i in x and type(x[i]) == str and x[i].isdigit() else x.get(i, "") for i in sort_flag_list])
        res = list(map(lambda act_val: {heads[0]: act_val}, act_val_list))

    else:
        # 处理非dict数据
        for act_val in act_val_list:
            # 检查实际值列表的长度是否与表头一致
            if len(heads) != len(act_val):
                raise RuntimeError("实际日志字段数和预期的字段数不一致，heads：%s，act_val：%s" % (heads, act_val))

            # 将实际结果中空字符串替换为None
            act_val = list(map(lambda x: None if x == "" else x, act_val))

            # 将表头与实际值组合成字典，并添加到结果列表中
            res.append(dict(zip(heads, act_val)))

        # 如果指定了排序字段，对结果进行排序,只对非xml进行排序
        if sort_flag and (p_excel["config"].get(f"{sheet_name}_filetype", "") != "xml" or p_excel["config"].get(f"{sheet_name}_splitflag", None)):
            sort_flag_list = sort_flag.split(",")
            res.sort(key=lambda x: [int(x[i]) if type(x[i]) == str and x[i].isdigit() else x[i] for i in sort_flag_list])

    return res


if __name__ == '__main__':
    p_excel = parser_excel(r"E:\DPI_SVN\8AutomatedTest\信安EU自动化3.1\report\用例_电信_pc_20250507140250.xlsx")
    # print(p_excel["sheet_name2head2col"].keys())
    # print(p_excel["sheet_name2cases"])
    sheet_name2statistics = dict()
    statistics_list = list()
    actdomain_send_flag = False
    for sheet_name, cases in p_excel.get("sheet_name2cases", dict()).items():
        if sheet_name == "actdomain发包":
            result_exeflag = list(map(lambda x: x[0].get("执行状态", 0), cases.values()))
            count_exe = len([x for x in result_exeflag if x not in (0, "", None)])
            if count_exe:
                actdomain_send_flag = True
            continue

        count_exe = count_unexe = count_pass = count_fail = count_noresult = 0

        # 非活跃的处理
        for casename, case_list in cases.items():
            if case_list[0].get("执行状态", 0) not in (0, "", None):
                if sheet_name == "monitor":
                    print(case_list[0].get("用例名", 0))
                count_exe += 1
                cases_result = case_list[0].get("结果", None)
                if cases_result == "Pass":
                    count_pass += 1
                elif cases_result == "Failed":
                    count_fail += 1
                else:
                    count_noresult += 1
            else:
                count_unexe += 1
        # 单独处理活跃
        if sheet_name in ("actdomain入向", "actdomain出向", "acturl入向", "acturl出向") and actdomain_send_flag:
            count_exe = 1


        success_rate = count_pass / count_exe if count_exe else 0.0
        sheet_name2statistics[sheet_name] = {"count_exe": count_exe, "count_unexe": count_unexe,
                                        "count_pass": count_pass, "count_fail": count_fail,
                                        "count_noresult": count_noresult, "success_rate": success_rate}
        statistics_list.append([sheet_name, count_exe, count_pass, count_fail, count_noresult, f"{success_rate:.2%}"])
        print(
            f"sheet:{sheet_name}\tcount_exe:{count_exe}\tcount_pass:{count_pass}\tcount_fail:{count_fail}\tcount_noresult:{count_noresult}\tsuccess_rate:{success_rate:.2%}")

# print(casename2exp_log(p,"monitor"))
    # a = casename2exp_log(p_excel, "audit")["出向IPV4__应用层协议__1226目的IP+目的端口+传输层协议（ICMP）"]
    # print(a)
    # xls =Excel("用例_移动.xlsx")
    # a = xls.row_values(sheet_index="eu_policy")
    # print(a)
    #
    # b = '''4925|117|11701|FF|FF|F|M-WH|9514841fe70b0220|103|1697005584450084|1697005584450746|FFFFFFFF|FFFFFFFF|FFFF|F|1|68|3|F|7|0|11.1.241.187|FFFFFFFFFFFFFFFF|11027|0|21.7.201.168|FFFFFFFFFFFFFFFF|80|5258|3372|7|4|662|634|0|0|0|0|28|24|0|0|0|28|8192|0|1|0|1|1|1|0|0|0|0|0|0|0|0|0|0|0|0|0|0|FF|9514841fe70b0220|1|F|F|0|3|6|200|28|662|662|22|www.host0000000001.com|4125|http://www.host0000000001.com/98ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1xyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz1098ABCxyz10.html|FF||144|Mozilla/5.0 (Linux; U; Android 2.2.2; zh-cn; HW-HUAWEI_C8500S/C8500SV100R001C92B627SP01; 240*320; CTC/2.0) AppleWebKit/533.1 Mobile Safari/533.1|text/html|85|http://clientwap.tyread.com/androidSeven/faxian.action?ca=ad&_timestamp=1517901438154|136|recent="[{"ContentId":10000058997037,"Position":3000,"ChapterId":13}]"; userMessage="{"userGuestId":"1342776068884004","viewType":1}END"|2976|FF|1|0|28|0|0|FF||1|FFFFFFFFFFFFFFFF|68|3'''
    # log = act_log(p, "http", [b.split("|")])
    # print(log)

    # print(p["sheet_name2cases"]["accesslog"]['IP-TCP-10.1.1.152-20.1.1.152-65015-80-6-6-435-6556'])
    # compare_exp(exp_log_list, act_log_list,case=p["sheet_name2cases"]["accesslog"]['IP-TCP-10.1.1.152-20.1.1.152-65015-80-6-6-435-6556'],head2col=p["sheet_name2head2col"]["accesslog"],time_e=1,time_s=0)