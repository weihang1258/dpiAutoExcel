#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2023/3/7 15:31
# @Author  : weihang
# @File    : excel.py
import json
import os
import sys
import time
import xlwings

from common import convert_unit_string


class Excel:
    def __init__(self, path):
        self.path = path
        self.is_open = self._is_open()
        self.app = xlwings.App(visible=False, add_book=False)
        self.app.display_alerts = False
        self.app.screen_updating = False
        if os.path.exists(path):
            self.workbook = self.app.books.open(path)
        else:
            self.workbook = self.app.books.add()

    # def __del__(self):
    #     self.quit_without_save()

    def int2col_str(self, n):
        '''excel中数字转换成列名'''
        assert (isinstance(n, int) and n > 0)
        num = [chr(i) for i in range(65, 91)]
        ret = []
        while n > 0:
            n, m = divmod(n - 1, len(num))
            ret.append(num[m])
        return ''.join(ret[::-1])

    def col_str2int(self, s):
        '''excel中列名转换成数字'''
        assert (isinstance(s, str))
        for i in s:
            if not 64 < ord(i) < 91:
                raise ValueError('Excel Column ValueError')
        return sum([(ord(n) - 64) * 26 ** i for i, n in enumerate(list(s)[::-1])])

    def row(self, sheet_index):
        return int(self.workbook.sheets[sheet_index].used_range.last_cell.row)

    def col(self, sheet_index):
        return int(self.workbook.sheets[sheet_index].used_range.last_cell.column)

    def range_values(self, sheet_index, row1, col1, row2=None, col2=None):
        if not row2:
            row2 = self.row(sheet_index=sheet_index)
        if not col2:
            col2 = self.col(sheet_index=sheet_index)
        return self.workbook.sheets[sheet_index].range(f"{self.int2col_str(col1 + 1)}{row1 + 1}",
                                                       f"{self.int2col_str(col2 + 1)}{row2 + 1}").value

    def row_values(self, sheet_index, rowx=0, col_start=0, col_end=None) -> list:
        col_end = col_end if col_end else self.col(sheet_index=sheet_index)
        location = f"{self.int2col_str(col_start + 1)}{rowx + 1}:{self.int2col_str(col_end + 1)}{rowx + 1}"
        return self.workbook.sheets[sheet_index].range(location).value

    def col_values(self, sheet_index, colx=0, row_start=0, row_end=None) -> list:
        row_end = row_end if row_end else self.row(sheet_index=sheet_index)
        location = f"{self.int2col_str(colx + 1)}{row_start + 1}:{self.int2col_str(colx + 1)}{row_end + 1}"
        return self.workbook.sheets[sheet_index].range(location).value

    def head2value(self, sheet_index, keys: list, head_row=0) -> dict:
        res = dict()
        if sheet_index not in self.workbook.sheet_names:
            return res
        head = self.row_values(sheet_index=sheet_index, rowx=head_row)
        for i in range(len(head) - 1, -1, -1):
            if not (head[i]):
                head.pop(-1)

        if self.row(sheet_index=sheet_index) == head_row + 1:
            return res
        value = self.range_values(sheet_index=sheet_index, row1=head_row + 1, col1=0,
                                  row2=self.row(sheet_index=sheet_index),
                                  col2=len(head) - 1)
        str_key = None
        for i in range(len(value)):
            row_value = value[i]
            # 全空行不处理
            if not self.list_rstrip(row_value, flags=(None, "")):
                continue
            row_value += [None] * (len(head) - len(row_value))
            # print(111,head,len(head))
            # print(222,row_value,len(row_value))

            tmp = dict(zip(head, row_value))
            tmp["row"] = head_row + 1 + i
            # print(["-".join(list(map(lambda x: str(int(tmp[x])) if type(tmp[x]) == float else str(tmp[x]), keys))), head_row + 1 + i])

            str_key_tmp = "-".join(list(map(lambda x: str(int(tmp[x])) if type(tmp[x]) == float else str(tmp[x]), keys)))
            str_key = str_key_tmp if str_key_tmp != "None" else str_key

            if str_key in res:
                res[str_key].append(tmp)
            else:
                res[str_key] = [tmp]
        return res

    def write_row_values(self, sheet_index, value, rowx=0, colx=0, bkgcolor=None, linestyle=1):
        # print(time.time(),rowx,colx,bkgcolor)
        if type(value) != list:
            location = f"{self.int2col_str(colx + 1)}{rowx + 1}"
        else:
            location = f"{self.int2col_str(colx + 1)}{rowx + 1}:{self.int2col_str(colx + len(value))}{rowx + 1}"
        data_range = self.workbook.sheets[sheet_index].range(location)
        data_range.value = value
        data_range.color = bkgcolor
        for i in range(7, 13):
            data_range.api.Borders(i).LineStyle = linestyle

    def write_col_values(self, sheet_index, value, colx=0, rowx=0, bkgcolor=None, linestyle=1):
        # print([sheet_index, value, colx, rowx])
        if type(value) != list:
            location = f"{self.int2col_str(colx + 1)}{rowx + 1}"
        else:
            location = f"{self.int2col_str(colx + 1)}{rowx + 1}:{self.int2col_str(colx + 1)}{rowx + len(value)}"
        data_range = self.workbook.sheets[sheet_index].range(location)
        data_range.options(transpose=True).value = value
        data_range.color = bkgcolor
        for i in range(7, 13):
            data_range.api.Borders(i).LineStyle = linestyle

    def write_range_values(self, sheet_index, value, row1, col1, row2=None, col2=None, bkgcolor=None, linestyle=1):
        if row2:
            location = f"{self.int2col_str(col1 + 1)}{row1 + 1}:{self.int2col_str(col2 + 1)}{row2 + 1}"
        else:
            if type(value) != list:
                location = f"{self.int2col_str(col1 + 1)}{row1 + 1}"
            else:
                if type(value[0]) != list:
                    location = f"{self.int2col_str(col1 + 1)}{row1 + 1}:{self.int2col_str(col1 + len(value))}{row1 + 1}"
                else:
                    location = f"{self.int2col_str(col1 + 1)}{row1 + 1}:{self.int2col_str(row1 + len(value[0]))}{col1 + len(value)}"
        data_range = self.workbook.sheets[sheet_index].range(location)
        data_range.value = value
        # Borders(9) 底部边框，LineStyle = 1 直线
        # Borders(7) 左边框，LineStyle = 2 虚线
        # Borders(8) 顶部框，LineStyle = 5 双点划线。
        # Borders(10) 右边框，LineStyle = 4 点划线。
        # Borders(5) 单元格内从左上角 到 右下角。
        # Borders(6) 单元格内从左下角 到 右上角。
        # Borders(11) 内部垂直边线。
        # Borders(12) 内部水平边线。
        # 设置背景色
        # 白色：rgb(255, 255, 255)
        # 黑色：rgb(0, 0, 0)
        # 红色：rgb(255, 0, 0)
        # 绿色：rgb(0, 255, 0)
        # 蓝色：rgb(0, 0, 255)
        # 青色：rgb(0, 255, 255)
        # 紫色：rgb(255, 0, 255)
        data_range.color = bkgcolor
        # 设置字体颜色
        # self.workbook.sheets[sheet_index].range(location).api.Font.Color = _fontcolor
        for i in range(7, 13):
            data_range.api.Borders(i).LineStyle = linestyle
            # self.workbook.sheets[sheet_index].range(location).api.Borders(12).Weight  = 3 # 设置边框粗细。

    def optimized_write(self, sheet_index, data, rowx=1, colx=0, bkgcolor=None, linestyle=1):
        """
        优化的Excel批量写入方法，支持高效写入大量数据。

        此方法通过一次性读取整个sheet到内存、批量修改后再一次性写回，以提高性能。
        特别优化了多次写入同一行的情况，确保数据一致性。

        参数:
            sheet_index: 工作表索引或名称
            data: 写入数据列表，每项格式为(行索引, 列索引, 数据列表)
            rowx: 起始行索引
            colx: 起始列索引
            bkgcolor: 背景色
            linestyle: 边框样式
        """
        from collections import defaultdict
        import time

        # 1. 按行分组数据
        row_data_map = defaultdict(list)
        for row, col, row_values in data:
            row_data_map[row].append((col, row_values))
        
        # 记录多次写入的行(用于debug)
        multiple_writes = {row: len(cols) for row, cols in row_data_map.items() if len(cols) > 1}
        
        # 2. 读取整个sheet到内存
        existing_data = self.workbook.sheets[sheet_index].used_range.value
        
        # 处理空sheet的情况
        if existing_data is None:
            existing_data = [[]]
            
        # 确保existing_data是二维列表
        if isinstance(existing_data, str):
            existing_data = [[existing_data]]
        elif isinstance(existing_data, list) and (not existing_data or not isinstance(existing_data[0], list)):
            if not existing_data:
                existing_data = [[]]
            else:
                existing_data = [existing_data]
        
        # 3. 计算需要的最大行列数
        max_rows = max(
            len(existing_data),
            max(row_data_map.keys()) + 1 if row_data_map else 0
        )
        
        # 计算每行所需的最大列数
        max_cols = max(
            max(len(row) for row in existing_data) if existing_data and existing_data[0] else 0,
            max(
                max(col + len(values) for col, values in row_items) 
                for row_items in row_data_map.values()
            ) if row_data_map else 0
        )
        
        # 4. 扩展现有数据到需要的大小
        # 扩展行
        while len(existing_data) < max_rows:
            existing_data.append([])
        
        # 扩展列
        for i, row in enumerate(existing_data):
            if len(row) < max_cols:
                row.extend([None] * (max_cols - len(row)))
        
        # 5. 在内存中修改数据 - 关键优化部分
        for row, row_items in row_data_map.items():
            # 按列排序，从左到右处理，避免覆盖
            row_items.sort(key=lambda x: x[0])
            
            # 创建基于现有数据的合并行
            merged_row = existing_data[row].copy()
            
            # 按顺序应用每个写入操作
            for col, values in row_items:
                # 确保不会越界
                end_col = min(col + len(values), len(merged_row))
                # 更新现有范围内的值
                merged_row[col:end_col] = values[:end_col-col]
                # 如果需要添加更多列
                if col + len(values) > len(merged_row):
                    merged_row.extend(values[end_col-col:])
            
            # 更新回原数据
            existing_data[row] = merged_row
        
        # 6. 一次性写回Excel
        start_cell = f"{self.int2col_str(colx + 1)}{rowx + 1}"
        end_cell = f"{self.int2col_str(max_cols)}{max_rows}"
        location = f"{start_cell}:{end_cell}"
        
        data_range = self.workbook.sheets[sheet_index].range(location)
        data_range.value = existing_data[rowx:]
        data_range.color = bkgcolor
        for i in range(7, 13):
            data_range.api.Borders(i).LineStyle = linestyle

    def list_rstrip(self, mylist: list, flags=(None,)):
        for i in range(len(mylist) - 1, -1, -1):
            if mylist[i] in flags:
                mylist.pop(-1)
            else:
                return mylist
        return mylist

    def key2col(self, sheet_index, key: str, rowx=0):
        row_value = self.row_values(sheet_index=sheet_index, rowx=rowx)
        for i in range(len(row_value)):
            if key == row_value[i]:
                return i
        return None

    def close(self):
        try:
            if hasattr(self, 'workbook'):
                self.workbook.close()
            if hasattr(self, 'app'):
                self.app.quit()
        except:
            pass

    def save(self, path=None):
        if not path:
            path = self.path
        self.workbook.save(path)

    def get_config_from_book(self, sheet_index, row_start=1):
        res = dict()
        if sheet_index not in self.workbook.sheet_names:
            return res
        for i in range(row_start, self.row(sheet_index)):
            key, val, mytype = self.row_values(sheet_index, rowx=i, col_start=0, col_end=2)
            if mytype == "str":
                val = str(val) if val else ""
            elif mytype == "int":
                val = int(val)
            elif mytype == "int2str":
                val = str(int(val))
            elif mytype == "dict":
                val = json.loads(val.strip())
            elif not key:
                continue
            else:
                pass
            res[key] = val
        return res

    def dict_form_xlsx(self, sheet_name, key, headrow=0):
        res = dict()
        head_list = self.list_rstrip(self.row_values(sheet_index=sheet_name, rowx=headrow))
        flag_key = None
        # print(self.range_values(sheet_index=sheet, row1=headrow+1, col1=0))
        row = headrow + 1
        for line in self.range_values(sheet_index=sheet_name, row1=headrow + 1, col1=0):
            if not self.list_rstrip(line):
                continue
            flag_dict = dict(zip(head_list, line[:len(head_list)]))
            flag_key = flag_dict[key] if flag_dict[key] else flag_key
            if flag_key and flag_key not in res:
                res[flag_key] = list()

            # print(flag_key,flag_dict)
            tmp_dict = dict()
            for field, value in flag_dict.items():
                if field != key:
                    tmp_dict[field] = value
                    tmp_dict["row"] = row
            res[flag_key].append(tmp_dict)
            row += 1
        return res

    def _is_open(self):
        path_split = self.path.rsplit(os.path.sep, 1)
        if len(path_split) == 2:
            dir, basename = path_split
            basename_new = "~$" + basename
            # print(os.path.join(dir, basename_new))
            return os.path.isfile(os.path.join(dir, basename_new))
        else:
            path_new = "~$" + self.path
            return os.path.isfile(path_new)


if __name__ == '__main__':

    excel_path = r"D:\Users\Downloads\2025-05-29\四川联通-2025-05-28.xlsx"
    xlsx = Excel(excel_path)

    s = xlsx.head2value(sheet_index="详情数据", keys=["computer_room", "eu_name"], head_row=0)
    print(f"computer_room\teu_name\teu_type\tget_eu_dpi_config\tget_eu_dpi_soft_version\t问题")
    for k, v in s.items():
        mark = list()
        computer_room = v[0].get("computer_room")
        eu_name = v[0].get("eu_name")
        eu_type = v[0].get("eu_type")
        get_eu_dpi_config = v[0].get("get_eu_dpi_config")
        get_eu_dpi_soft_version = v[0].get("get_eu_dpi_soft_version")
        if get_eu_dpi_config and "ds" in get_eu_dpi_config:
            continue
        # 重启判断
        get_eu_xsa_restart_num = v[0].get("get_eu_xsa_restart_num")
        if get_eu_xsa_restart_num not in ("0", None):
            mark.append(f"重启次数：{get_eu_xsa_restart_num}")
        # 段错误判断
        get_eu_segfault_status = v[0].get("get_eu_segfault_status")
        if get_eu_segfault_status not in ("1", None):
            mark.append(f"段错误：{get_eu_segfault_status}")
        # 收包情况
        get_09_eu_receiver_package_flow_info = v[0].get("get_09_eu_receiver_package_flow_info")
        get_16_eu_receiver_package_flow_info = v[0].get("get_16_eu_receiver_package_flow_info")
        get_23_eu_receiver_package_flow_info = v[0].get("get_23_eu_receiver_package_flow_info")
        try:
            get_09_eu_receiver_package_flow_info_dict = json.loads(get_09_eu_receiver_package_flow_info)
        except Exception as e:
            get_09_eu_receiver_package_flow_info_dict = {}
        try:
            get_16_eu_receiver_package_flow_info_dict = json.loads(get_16_eu_receiver_package_flow_info)
        except Exception as e:
            get_16_eu_receiver_package_flow_info_dict = {}
        try:
            get_23_eu_receiver_package_flow_info_dict = json.loads(get_23_eu_receiver_package_flow_info)
        except Exception as e:
            get_23_eu_receiver_package_flow_info_dict = {}
        rx_miss_09 = get_09_eu_receiver_package_flow_info_dict.get("miss", "0")
        rx_miss_16 = get_16_eu_receiver_package_flow_info_dict.get("miss", "0")
        rx_miss_23 = get_23_eu_receiver_package_flow_info_dict.get("miss", "0")
        if rx_miss_09 != rx_miss_16 or rx_miss_16 != rx_miss_23:
            mark.append(f"持续丢包：{rx_miss_23}")

        httpcps_09 = get_09_eu_receiver_package_flow_info_dict.get("httpcps", "0")
        httpcps_16 = get_16_eu_receiver_package_flow_info_dict.get("httpcps", "0")
        httpcps_23 = get_23_eu_receiver_package_flow_info_dict.get("httpcps", "0")
        rxsp_09 = get_09_eu_receiver_package_flow_info_dict.get("rxsp", "0")
        rxsp_16 = get_16_eu_receiver_package_flow_info_dict.get("rxsp", "0")
        rxsp_23 = get_23_eu_receiver_package_flow_info_dict.get("rxsp", "0")
        rxsp = convert_unit_string(rxsp_16, "G")
        if rxsp_23 == "0":
            continue
        err_09 = get_09_eu_receiver_package_flow_info_dict.get("err", "0")
        err_16 = get_16_eu_receiver_package_flow_info_dict.get("err", "0")
        err_23 = get_23_eu_receiver_package_flow_info_dict.get("err", "0")
        if err_09 != err_16 or err_16 != err_23:
            mark.append(f"持续收包error：{err_23}")

        enf_09 = get_09_eu_receiver_package_flow_info_dict.get("enf", "0")
        enf_16 = get_16_eu_receiver_package_flow_info_dict.get("enf", "0")
        enf_23 = get_23_eu_receiver_package_flow_info_dict.get("enf", "0")
        if enf_09 != enf_16 or enf_16 != enf_23:
            mark.append(f"持续收包队列失败：{enf_23}")

        cps_09 = get_09_eu_receiver_package_flow_info_dict.get("cps", "0")
        cps_16 = get_16_eu_receiver_package_flow_info_dict.get("cps", "0")
        cps_23 = get_23_eu_receiver_package_flow_info_dict.get("cps", "0")
        cps = convert_unit_string(cps_16, "w")

        currcnt_09 = get_09_eu_receiver_package_flow_info_dict.get("currcnt", "0")
        currcnt_16 = get_16_eu_receiver_package_flow_info_dict.get("currcnt", "0")
        currcnt_23 = get_23_eu_receiver_package_flow_info_dict.get("currcnt", "0")
        currcnt = convert_unit_string(currcnt_16, "w")

        flow_fail_cnt_09 = get_09_eu_receiver_package_flow_info_dict.get("flow_fail_cnt", "0")
        flow_fail_cnt_16 = get_16_eu_receiver_package_flow_info_dict.get("flow_fail_cnt", "0")
        flow_fail_cnt_23 = get_23_eu_receiver_package_flow_info_dict.get("flow_fail_cnt", "0")
        if flow_fail_cnt_09 != flow_fail_cnt_16 or flow_fail_cnt_16 != flow_fail_cnt_23:
            mark.append(f"持续建流失败：{flow_fail_cnt_23}")
        elif flow_fail_cnt_23 not in ("0", None):
            mark.append(f"历史建流失败：{flow_fail_cnt_23}")

        flow_pub_fail_cnt_09 = get_09_eu_receiver_package_flow_info_dict.get("flow_pub_fail_cnt", "0")
        flow_pub_fail_cnt_16 = get_16_eu_receiver_package_flow_info_dict.get("flow_pub_fail_cnt", "0")
        flow_pub_fail_cnt_23 = get_23_eu_receiver_package_flow_info_dict.get("flow_pub_fail_cnt", "0")
        if flow_pub_fail_cnt_09 != flow_pub_fail_cnt_16 or flow_pub_fail_cnt_16 != flow_pub_fail_cnt_23:
            mark.append(f"持续流释放失败：{flow_pub_fail_cnt_23}")
        elif flow_pub_fail_cnt_23 not in ("0", None):
            mark.append(f"历史流释放失败：{flow_pub_fail_cnt_23}")

        http_split_fail_cnt_09 = get_09_eu_receiver_package_flow_info_dict.get("http_split_fail_cnt", "0")
        http_split_fail_cnt_16 = get_16_eu_receiver_package_flow_info_dict.get("http_split_fail_cnt", "0")
        http_split_fail_cnt_23 = get_23_eu_receiver_package_flow_info_dict.get("http_split_fail_cnt", "0")
        if http_split_fail_cnt_09 != http_split_fail_cnt_16 or http_split_fail_cnt_16 != http_split_fail_cnt_23:
            mark.append(f"持续http流拆分失败：{http_split_fail_cnt_23}")
        elif http_split_fail_cnt_23 not in ("0", None):
            mark.append(f"历史http流拆分失：{http_split_fail_cnt_23}")

        # 重组情况
        get_09_eu_reorganzie_failed_status = v[0].get("get_09_eu_reorganzie_failed_status")
        get_16_eu_reorganzie_failed_status = v[0].get("get_16_eu_reorganzie_failed_status")
        get_23_eu_reorganzie_failed_status = v[0].get("get_23_eu_reorganzie_failed_status")
        try:
            get_09_eu_reorganzie_failed_status_dict = json.loads(get_09_eu_reorganzie_failed_status)
        except Exception as e:
            get_09_eu_reorganzie_failed_status_dict = {}
        try:
            get_16_eu_reorganzie_failed_status_dict = json.loads(get_16_eu_reorganzie_failed_status)
        except Exception as e:
            get_16_eu_reorganzie_failed_status_dict = {}
        try:
            get_23_eu_reorganzie_failed_status_dict = json.loads(get_23_eu_reorganzie_failed_status)
        except Exception as e:
            get_23_eu_reorganzie_failed_status_dict = {}
        cache_flow_loss_09 = get_09_eu_reorganzie_failed_status_dict.get("cache_flow_loss", "0")
        cache_flow_loss_16 = get_16_eu_reorganzie_failed_status_dict.get("cache_flow_loss", "0")
        cache_flow_loss_23 = get_23_eu_reorganzie_failed_status_dict.get("cache_flow_loss", "0")
        if cache_flow_loss_09 != cache_flow_loss_16 or cache_flow_loss_16 != cache_flow_loss_23:
            mark.append(f"持续重组缓存失败：{cache_flow_loss_23}")
        elif cache_flow_loss_23 not in ("0", None):
            mark.append(f"历史重组缓存失败：{cache_flow_loss_23}")

        # 内存使用情况
        get_09_eu_commem_failed_num = v[0].get("get_09_eu_commem_failed_num")
        get_16_eu_commem_failed_num = v[0].get("get_16_eu_commem_failed_num")
        get_23_eu_commem_failed_num = v[0].get("get_23_eu_commem_failed_num")
        try:
            get_09_eu_commem_failed_num_list = json.loads(get_09_eu_commem_failed_num)
        except Exception as e:
            get_09_eu_commem_failed_num_list = []
        try:
            get_16_eu_commem_failed_num_list = json.loads(get_16_eu_commem_failed_num)
        except Exception as e:
            get_16_eu_commem_failed_num_list = []
        try:
            get_23_eu_commem_failed_num_list = json.loads(get_23_eu_commem_failed_num)
        except Exception as e:
            get_23_eu_commem_failed_num_list = []
        if get_09_eu_commem_failed_num_list:
            get_09_eu_commem_failed_num_dict = {}
            for content_dict in get_09_eu_commem_failed_num_list:
                key = "blks_" + str(content_dict.get("blks"))
                get_09_eu_commem_failed_num_dict[key] = content_dict.get("errcnt")
            get_16_eu_commem_failed_num_dict = {}
            for content_dict in get_16_eu_commem_failed_num_list:
                key = "blks_" + str(content_dict.get("blks"))
                get_16_eu_commem_failed_num_dict[key] = content_dict.get("errcnt")
            get_23_eu_commem_failed_num_dict = {}
            for content_dict in get_23_eu_commem_failed_num_list:
                key = "blks_" + str(content_dict.get("blks"))
                get_23_eu_commem_failed_num_dict[key] = content_dict.get("errcnt")

            for key, var09 in get_09_eu_commem_failed_num_dict.items():
                var16 = get_16_eu_commem_failed_num_dict.get(key)
                var23 = get_23_eu_commem_failed_num_dict.get(key)
                if key == "blks_4096":
                    pass
                elif var09 != var16 or var16 != var23:
                    mark.append(f"持续内存池{key}失败：{var23}")
                elif var23 not in (0, "0", None):
                    mark.append(f"历史内存池{key}失败：{var23}")




        # print(f"{computer_room}\t{eu_name}\t{eu_type}\t{get_eu_dpi_config}\t{get_eu_dpi_soft_version}\t{cps}\t{currcnt}\t{rxsp}")
        if mark:
            print(f"{computer_room}\t{eu_name}\t{eu_type}\t{get_eu_dpi_config}\t{get_eu_dpi_soft_version}\t{mark}")


    # s = xlsx.workbook.sheets["accesslog"].range("A1").expand().value
    # print(len(s), s[-1])
    # xlsx.optimized_write("accesslog", [(0,0,s)])
    # xlsx.save(excel_path1)
    # xlsx.close()
    # sys.exit()
    # delete_flag = False
    # tmp_sheets = ["accesslog", "monitor", "filter", "mirrorvlan_log", "pcapdump_log", "block", "mirrorvlan", "pcapdump",
    #               "actdomain发包", "actdomain入向", "actdomain出向", "acturl入向", "acturl出向", "audit"]
    # for name in [sheet.name for sheet in xlsx.workbook.sheets]:
    #     if name not in tmp_sheets:
    #
    #         xlsx.workbook.sheets[name].delete()
    #         delete_flag = True
    # if delete_flag:
    #     xlsx.save(path=excel_path)
    #     xlsx.close()
    # else:
    #     xlsx.close()

    # aa = Excel(r"E:\PycharmProjects\pythonProject_socket\mycode\script\auto_test\idc31\用例_联通.xlsx")

    # c = aa.head2value("mirrorvlan_log", keys=["用例名"], head_row=0)
    # print(c)
    # print(aa.is_open)
    # print(aa.list_rstrip(['lv1', 'lv2', 'lv3', None, None, None, None, None, None, None, None]))
    # print(aa.write_col_values('sheet1', ['指令下发结果', 'succeed', 'succeed', 'succeed', None, None, None, 'succeed', None, None, 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', None, None, 'succeed', None, None, None, None, 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', None, None, 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', None, None, 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', None, None, 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', None, None, 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', None, None, 'succeed', None, None, None, None, 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', None, None, None, 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', None, None, 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', None, None, 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', None, None, 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', None, None, 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed', 'succeed'], 26, 0))
    # aa.save()
    # aa.quit_without_save()
