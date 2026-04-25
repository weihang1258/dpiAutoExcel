import copy
import re
from collections.abc import MutableMapping, MutableSequence
from datetime import datetime
from collections import OrderedDict
from utils.ini_handler import extract_field_paths


class DictComparer:
    """嵌套字典比较器，支持复杂的字典结构比对。

    支持忽略字段、时间区间判断、长度对比等高级功能。

    Attributes:
        dict1: 第一个字典
        dict2: 第二个字典
        differences: 所有差异列表
        ignore_fields: 忽略对比的字段列表
        time_fields: 时间区间字段字典
        length_fields: 长度对比字段列表
    """

    def __init__(self, dict1, dict2, ignore_fields=None, time_fields=None, length_fields=None):
        """初始化字典比较器。

        Args:
            dict1: 第一个字典
            dict2: 第二个字典
            ignore_fields (list, optional): 要忽略对比的字段列表
            time_fields (dict, optional): 时间区间字段字典，
                格式为 {字段路径: (开始时间, 结束时间)}
            length_fields (list, optional): 需要对比值长度的字段列表
        """
        self.dict1 = dict1
        self.dict2 = dict2
        self.dict2_keys_str = "\n".join(extract_field_paths(self.dict2))
        self.differences = []  # 存储所有的差异
        self.ignore_fields = ignore_fields if ignore_fields else []  # 设置忽略对比的字段列表
        self.time_fields = self.parse_time_fields(time_fields) if time_fields else {}  # 解析时间字段
        self.length_fields = length_fields if length_fields else []  # 设置长度对比字段列表
        # print([self.dict1, self.dict2, ignore_fields, time_fields, length_fields])

        # 对参数字段没有中，如果使用monitorResult.log.gatherTime字段的更新为log[0]、log[1]
        tmp = list()
        for field_str in self.ignore_fields:
            fields = field_str.split(".")
            pattern = ""
            if len(fields) == 1:
                pattern = fields[0]
            else:
                for field in fields[:-1]:
                    if field.endswith("]"):
                        escaped_field = field.replace("[", r"\[").replace("]", r"\]")
                        pattern += f"{escaped_field}."
                    else:
                        pattern += field + r"(?:\[\d+?\])*\."
                pattern += fields[-1]
            newkeys = re.findall(pattern, self.dict2_keys_str)
            if newkeys:
                tmp += newkeys
        self.ignore_fields = copy.deepcopy(tmp)
        tmp = list()
        for field_str in self.length_fields:
            fields = field_str.split(".")
            pattern = ""
            if len(fields) == 1:
                pattern = fields[0]
            else:
                for field in fields[:-1]:
                    if field.endswith("]"):
                        escaped_field = field.replace("[", r"\[").replace("]", r"\]")
                        pattern += f"{escaped_field}."
                    else:
                        pattern += field + r"(?:\[\d+?\])*\."
                pattern += fields[-1]
            newkeys = re.findall(pattern, self.dict2_keys_str)
            if newkeys:
                tmp += newkeys

        self.length_fields = copy.deepcopy(tmp)
        tmp = dict()
        for field_str, time_value in self.time_fields.items():
            fields = field_str.split(".")
            pattern = ""
            if len(fields) == 1:
                pattern = fields[0]
            else:
                for field in fields[:-1]:
                    if field.endswith("]"):
                        escaped_field = field.replace("[", r"\[").replace("]", r"\]")
                        pattern += f"{escaped_field}."
                    else:
                        pattern += field + r"(?:\[\d+?\])*\."
                pattern += fields[-1]
            newkeys = re.findall(pattern, self.dict2_keys_str)
            if newkeys:
                for new_field in newkeys:
                    tmp[new_field] = time_value
        self.time_fields = copy.deepcopy(tmp)

        # 根据 ignore_fields 更新 length_fields 和 time_fields
        self.length_fields = [field for field in self.length_fields if field not in self.ignore_fields]
        self.time_fields = {field: (start, end, start_formatted, end_formatted)
                            for field, (start, end, start_formatted, end_formatted) in self.time_fields.items()
                            if field not in self.ignore_fields}

        # 将 time_fields 加入到 ignore_fields
        self.length_fields += [field for field in self.time_fields.keys() if field not in self.length_fields]

        # print(f"self.ignore_fields: {self.ignore_fields}")
        # print(f"self.length_fields: {self.length_fields}")
        # print(f"self.time_fields: {self.time_fields}")


    def parse_time_fields(self, time_fields):
        """将时间字段中的时间范围字符串转换为时间戳。

        Args:
            time_fields (dict): 时间字段字典，格式为 {字段路径: (开始时间, 结束时间)}

        Returns:
            dict: 转换后的时间戳字典，
                格式为 {字段路径: (开始时间戳, 结束时间戳, 格式化开始时间, 格式化结束时间)}

        Raises:
            ValueError: 时间字符串格式错误时抛出
        """
        result = {}
        for field, (start_time, end_time) in time_fields.items():
            start_timestamp, start_time_formatted = self.parse_time(start_time)
            end_timestamp, end_time_formatted = self.parse_time(end_time)
            result[field] = (start_timestamp, end_timestamp, start_time_formatted, end_time_formatted)
        return result

    def parse_time(self, time_str):
        """将时间字符串解析为时间戳和格式化时间字符串。

        Args:
            time_str (str or int): 时间字符串或时间戳

        Returns:
            tuple: (时间戳, 格式化时间字符串)

        Raises:
            ValueError: 时间字符串格式错误时抛出
        """
        try:
            if type(time_str) == int or str(time_str).isdigit():
                timestamp = int(time_str)
                formatted_time = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
            else:
                timestamp = int(datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S').timestamp())
                formatted_time = time_str
        except ValueError:
            raise ValueError(f"无法解析时间字符串: {time_str}")
        return timestamp, formatted_time

    def compare(self):
        """比较两个字典并输出所有差异。

        Returns:
            bool: 如果两个字典相同返回 True，否则返回 False
        """
        self.compare_dicts(self.dict1, self.dict2)
        if self.differences:
            for diff in self.differences:
                print(diff)
            return False
        return True

    def compare_values(self, val1, val2, path=''):
        """比较两个值，支持字典、列表和基本类型。

        Args:
            val1: 第一个值
            val2: 第二个值
            path (str, optional): 当前字段路径
        """
        if path in self.ignore_fields:
            return

        if path in self.length_fields:
            if len(str(val1)) != len(str(val2)):
                self.differences.append(f"不一致在 {path}: 长度不同 {len(str(val1))} != {len(str(val2))}")
            if path in self.time_fields:
                pass
            else:
                return

        if path in self.time_fields:
            start, end, start_formatted, end_formatted = self.time_fields[path]

            if isinstance(val1, str) and isinstance(val2, str) and len(val1) != len(val2):
                self.differences.append(f"不一致在 {path}: 长度不同 {len(val1)} != {len(val2)}")
                return

            try:
                time_val1 = int(val1)
                time_val2 = int(val2)
            except ValueError:
                try:
                    time_val1 = int(datetime.strptime(val1, '%Y-%m-%d %H:%M:%S').timestamp())
                except ValueError:
                    self.differences.append(f"时间字段格式错误在 {path}: {val1}")
                    return

                try:
                    time_val2 = int(datetime.strptime(val2, '%Y-%m-%d %H:%M:%S').timestamp())
                except ValueError:
                    self.differences.append(f"时间字段格式错误在 {path}: {val2}")
                    return

            if not (start <= time_val2 <= end):
                self.differences.append(
                    f"不一致在 {path}: {val2} 不在时间区间 {start_formatted} 到 {end_formatted} 之间")
            return

        if isinstance(val1, MutableMapping) and isinstance(val2, MutableMapping):
            self.compare_dicts(val1, val2, path)
        elif isinstance(val1, MutableSequence) and isinstance(val2, MutableSequence):
            self.compare_lists(val1, val2, path)
        else:
            if val1 != val2:
                self.differences.append(f"不一致在 {path}: {val1} != {val2}")

    def compare_lists(self, list1, list2, path=''):
        """比较两个列表。

        Args:
            list1: 第一个列表
            list2: 第二个列表
            path (str, optional): 当前字段路径
        """
        if len(list1) != len(list2):
            self.differences.append(f"不一致在 {path}: 列表长度不同 {len(list1)} != {len(list2)}")
        else:
            for i, (item1, item2) in enumerate(zip(list1, list2)):
                self.compare_values(item1, item2, f"{path}[{i}]")

    def compare_dicts(self, dict1, dict2, path=''):
        """比较两个字典。

        Args:
            dict1: 第一个字典
            dict2: 第二个字典
            path (str, optional): 当前字段路径
        """
        for key in set(dict1.keys()).union(set(dict2.keys())):
            new_path = f"{path}.{key}" if path else key
            if key not in dict1:
                self.differences.append(f"缺少字段在 {new_path}: {dict2[key]}")
            elif key not in dict2:
                self.differences.append(f"缺少字段在 {new_path}: {dict1[key]}")
            else:
                self.compare_values(dict1[key], dict2[key], new_path)


if __name__ == '__main__':
    dict1 = {
        "name": "Alice",
        "age": 25,
        "registered": "1724125558",
        "address": {"city": "New York", "zip": "10001", "registered": "1724125558"},
        "hobbies": ["reading", "traveling", {"registered": "1724125558"}, {"registered": "1724125558"}]
    }

    dict2 = {
        "name": "Alice",
        "age": "25",
        "registered": "1724125558",
        "address": {"city": "New York", "zip": "10001", "registered": "1724125558"},
        "hobbies": ["reading", "traveling", {"registered": "1724125558"}, {"registered": "1724125551"}]
    }

    ignore_fields = ["name"]
    length_fields = ["age","hobbies.registered"]
    time_fields = {"hobbies[2].registered": ("2023-08-01 10:29:00", "2024-08-20 10:31:00")}

    dict1 = {'Ver': '1', 'Proto-Signature': 'X1D', 'ManufactureID': 13, 'DeviceSerialNo': '000', 'Packet Type': 1, 'Packet Subtype': 224, 'Resv': '\x00\x00', 'Packet Length': 71, 'CommandID': '10001168', 'House_ID_Length': 4, 'House_ID': '1000', 'SourceIP_Length': 4, 's_ip': '20.13.1.6', 'DestinationIP_Length': 4, 'd_ip': '30.13.1.6', 's_port': 58164, 'd_port': 14567, 'DomainName_Length': 0, 'ProxyType_Flag': 0, 'Title_Length': 0, 'Content_Length': 0, 'Url_Length': 0, 'Attachmentfile_Num': 0, 'GatherTime': 1724116069, 'TrafficType': 2, 'ProtocolType': 1, 'ApplicationProtocol': 41, 'BusinessProtocol': 28}
    dict2 = {'Ver': '1', 'Proto-Signature': 'X1D', 'ManufactureID': 13, 'DeviceSerialNo': '000', 'Packet Type': 1, 'Packet Subtype': 224, 'Resv': '\x00\x00', 'Packet Length': 71, 'CommandID': '10001168', 'House_ID_Length': 4, 'House_ID': '1000', 'SourceIP_Length': 4, 's_ip': '20.13.1.6', 'DestinationIP_Length': 4, 'd_ip': '30.13.1.6', 's_port': 58164, 'd_port': 14567, 'DomainName_Length': 0, 'ProxyType_Flag': 0, 'Title_Length': 0, 'Content_Length': 0, 'Url_Length': 0, 'Attachmentfile_Num': 0, 'GatherTime': 1724235583, 'TrafficType': 2, 'ProtocolType': 1, 'ApplicationProtocol': 41, 'BusinessProtocol': 28}

    comparer = DictComparer(dict1, dict2, ignore_fields=ignore_fields, time_fields=time_fields,
                            length_fields=length_fields)
    result = comparer.compare()

    if result:
        print("两个字典相同")
    else:
        print("两个字典不同")

    print(comparer.differences)
