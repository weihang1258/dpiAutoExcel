#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2023/9/21 10:14
# @Author  : weihang
# @File    : comparer.py
# @Desc    : 数据比较工具函数

import json
import re
import time
from utils.common import setup_logging
from data.xml_comparer import XMLComparer
from data.dict_comparer import DictComparer

logger = setup_logging(log_file_path="log/comparer.log", logger_name="comparer")


def compare_exp(exp_log_list: list, act_log_list: list, case: list, head2col: dict, time_s: int, time_e: int,
               ignore_fields=None, length_fields=None, time_fields=None, datatype=None):
    """
    对比期望值和实际值

    Args:
        exp_log_list: 期望值列表
        act_log_list: 实际值列表
        case: 用例信息
        head2col: 表头到列的映射
        time_s: 时间起始
        time_e: 时间结束
        ignore_fields: 忽略字段
        length_fields: 长度字段
        time_fields: 时间字段
        datatype: 数据类型 (xml/dict)

    Returns:
        dict: {"mark": [], "result_list": []}
    """
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
        mark.append(json.dumps(act_log_list))
        result_list.append((case[0]["row"], head2col["实际条数"], len(act_log_list), (255, 0, 0)))
        for i in range(min(len(exp_log_list), len(act_log_list))):
            for k, v in act_log_list[i].items():
                result_list.append((case[i]["row"], head2col[k], json.dumps(v) if type(v) == dict else v, (255, 255, 255)))
    else:
        result_list.append((case[0]["row"], head2col["实际条数"], len(act_log_list), (255, 255, 255)))
        for i in range(len(act_log_list)):
            for k, v in act_log_list[i].items():
                # 将预期值颜色重置
                tmp_exp_value = exp_log_list[i][k.replace("act_", "exp_")]
                result_list.append((case[i]["row"], head2col[k.replace("act_", "exp_")],
                                   json.dumps(tmp_exp_value) if type(tmp_exp_value) == dict else tmp_exp_value,
                                   (255, 255, 255)))

                name = k[4:]
                # 针对xml文件对比
                if datatype in ("xml", "dict"):
                    exp_val = exp_log_list[i]["exp_" + name]
                    if datatype == "xml":
                        logger.info("开始xml字符串对比")
                        comparer = XMLComparer(exp_val, v, ignore_fields=ignore_fields,
                                              time_fields=time_fields, length_fields=length_fields)
                    elif datatype == "dict":
                        logger.info("开始dict对比")
                        comparer = DictComparer(exp_val, v, ignore_fields=ignore_fields,
                                                 time_fields=time_fields, length_fields=length_fields)
                    else:
                        raise RuntimeError(f"请检查datatype：{datatype}")
                    res_comp = comparer.compare()
                    diff = comparer.differences
                    result_list.append((case[i]["row"], head2col[k],
                                        json.dumps(v) if type(v) == dict else v, (255, 255, 255)))

                    if diff:
                        mark += diff

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


def compare_tuple(tuple_exp: tuple, tuple_act: tuple, time_s: int, time_e: int,
                 time_fields=None, length_fields=None, ignore_fields=None, flag=None):
    """递归对比元组"""
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
                compare_tuple(tuple(sorted(val_exp)), tuple(sorted(val_act)), time_s, time_e, \
                    time_fields, length_fields, ignore_fields, flag)
            if isinstance(val_exp, tuple):
                compare_tuple(val_exp, val_act, time_s, time_e, time_fields, length_fields, ignore_fields, flag)
            if isinstance(val_exp, set):
                compare_tuple(tuple(val_exp), tuple(val_act), time_s, time_e,
                              time_fields, length_fields, ignore_fields, flag)
            elif isinstance(val_exp, dict):
                compare_dict(val_exp, val_act, time_s, time_e, time_fields, length_fields, ignore_fields, flag)
            else:
                # 其他字段对比
                if val_exp != val_act:
                    raise RuntimeError(f"元组index{i}值不对，预期值： {tuple_exp}，实际值： {tuple_act}")


def compare_dict(dict_exp: dict, dict_act: dict, time_s: int, time_e: int,
                time_fields=None, length_fields=None, ignore_fields=None, flag=None):
    """递归对比字典"""
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
                compare_tuple(tuple(sorted(val)), tuple(sorted(dict_act[key])), time_s, time_e,
                              time_fields, length_fields, ignore_fields, flag)
            if isinstance(val, tuple):
                compare_tuple(val, dict_act[key], time_s, time_e, time_fields, length_fields, ignore_fields, flag)
            if isinstance(val, set):
                compare_tuple(tuple(val), tuple(dict_act[key]), time_s, time_e,
                              time_fields, length_fields, ignore_fields, flag)
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
