#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2023/9/21 10:14
# @Author  : weihang
# @File    : result.py
# @Desc    : 结果写入Excel工具函数

import os
from utils.common import gettime, setup_logging
from io_handler.excel import Excel

logger = setup_logging(log_file_path="log/result.log", logger_name="result")


def result_deal(xls, sheet_index: str, result_list, row: int, head2col: dict, mark: list, only_write=False, isquit=True,
               newpath=None):
    """
    将测试结果写入Excel，支持去重和颜色标记

    Args:
        xls: Excel对象或路径
        sheet_index: sheet名称
        result_list: 结果列表 [(row, col, value, bkgcolor), ...]
        row: 行号
        head2col: 表头到列的映射
        mark: 备注列表
        only_write: 是否只写入
        isquit: 是否关闭保存
        newpath: 新路径
    """
    logger.info([xls, sheet_index, result_list, row, head2col, mark, only_write, isquit, newpath])
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
            rowx_colx2value[rowx][colx] = value
        else:
            rowx_colx2value[rowx] = {colx: value}

        # 提取每行要录入红色的全部value
        if bkgcolor == (255, 0, 0) and rowx in rowx_colx_red2value:
            rowx_colx_red2value[rowx][colx] = value
        elif bkgcolor == (255, 0, 0) and rowx not in rowx_colx_red2value:
            rowx_colx_red2value[rowx] = {colx: value}
        else:
            pass

    logger.info("非标红数据写入excel")
    rowx_colx2valuelist = list()
    for rowx, tmp in rowx_colx2value.items():
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
                    rowx_colx2valuelist.append((rowx, tmp_col, tmp_value))
                    tmp_col = colx
                    tmp_value = [value]
        rowx_colx2valuelist.append((rowx, tmp_col, tmp_value))

    # 全量写入，先从sheet复制数据并修改再写入
    if len(list(set(map(lambda x: x[0], rowx_colx2valuelist)))) > 1:
        xls.optimized_write(sheet_index=sheet_index, data=rowx_colx2valuelist, rowx=1, colx=0, bkgcolor=(255, 255, 255))
    else:
        for rowx, colx, row_values in rowx_colx2valuelist:
            xls.write_row_values(sheet_index=sheet_index, rowx=rowx, colx=colx, value=row_values, bkgcolor=(255, 255, 255))

        for rowx, tmp in rowx_colx2value.items():
            row_values = list()
            colx_prefix = None
            colx_first = None
            for colx, value in sorted(tmp.items(), key=lambda x: x[0]):
                colx_first = colx_first if colx_first else colx
                if (not colx_prefix) or (colx_prefix and colx_prefix + 1 == colx):
                    row_values.append(value)
                else:
                    xls.write_row_values(sheet_index=sheet_index, rowx=rowx, colx=colx_first, value=row_values,
                                         bkgcolor=(255, 255, 255))
                    row_values = [value]
                    colx_first = colx
                colx_prefix = colx
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
        xls.write_row_values(sheet_index=sheet_index, rowx=rowx, colx=colx, value=row_values, bkgcolor=(255, 0, 0))

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
