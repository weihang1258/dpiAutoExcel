#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2023/3/8 0:07
# @Author  : weihang
# @File    : common.py
import datetime
import io
import ipaddress
import os
import random
import socket
import sys
import threading
import time
import hashlib
import ntplib as ntplib
import copy
import shutil
import subprocess
import logging

# 日志格式常量
LOG_FORMAT = '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'


def get_base_dir():
    """获取程序基准目录，兼容 PyInstaller exe 和源码运行两种模式。

    Returns:
        str: 程序运行的基准目录路径。
            - exe 模式：返回 exe 文件所在目录
            - 源码模式：返回当前文件所在目录

    Examples:
        >>> base_dir = get_base_dir()
        >>> print(base_dir)
        'E:\\PycharmProjects\\dpiAutoExcel'
    """
    if getattr(sys, 'frozen', False):
        # exe 模式：exe 文件所在目录（兼容 onefile 和 onedir）
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def keep_console_alive(logger, interval=10):
    """启动后台心跳线程，保持控制台活性。

    Args:
        logger: 日志记录器，用于输出心跳信息
        interval (int, optional): 心跳间隔秒数，默认 10 秒

    Returns:
        threading.Thread: 启动的后台心跳线程对象

    Examples:
        >>> import logging
        >>> logger = logging.getLogger("test")
        >>> thread = keep_console_alive(logger, interval=5)
    """

    def heartbeat():
        while True:
            logger.info(f"Heartbeat - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            time.sleep(interval)

    # 创建并启动后台线程
    heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
    heartbeat_thread.start()
    return heartbeat_thread

def setup_logging(log_file_path, logger_name, encoding="utf-8", keep_alive=False, heartbeat_interval=10):
    """配置日志记录器，支持文件和终端双输出。

    Args:
        log_file_path (str): 日志文件路径
        logger_name (str): 日志记录器名称
        encoding (str, optional): 日志文件编码，默认 utf-8
        keep_alive (bool, optional): 是否启动心跳线程保持控制台，默认 False
        heartbeat_interval (int, optional): 心跳间隔秒数，默认 10

    Returns:
        logging.Logger: 配置好的日志记录器实例

    Raises:
        Exception: 当创建日志目录或配置失败时抛出

    Examples:
        >>> logger = setup_logging("log/app.log", "myapp")
        >>> logger.info("Hello world")
    """
    try:
        # 创建日志目录
        dirname = os.path.dirname(log_file_path)
        if dirname and not os.path.isdir(dirname):
            os.makedirs(dirname)

        # 清空已存在的日志文件
        if os.path.exists(log_file_path):
            with open(log_file_path, 'w', encoding=encoding) as f:
                f.write("")

        # 创建日志记录器
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.DEBUG)

        # 禁用日志传播到 root logger，避免重复输出
        logger.propagate = False

        # 清空之前的处理器，避免重复输出
        if logger.handlers:
            logger.handlers.clear()

        # 文件处理器配置
        file_handler = logging.FileHandler(log_file_path, encoding=encoding)
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
        file_handler.setFormatter(file_format)

        # 控制台处理器配置
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_format = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
        console_handler.setFormatter(console_format)

        # 添加处理器
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

        # 如果需要保持控制台活性，启动心跳线程
        if keep_alive:
            heartbeat_thread = keep_console_alive(logger, heartbeat_interval)
            logger.heartbeat_thread = heartbeat_thread  # 将线程对象保存到logger中，以便后续可能的管理

        return logger

    except Exception as e:
        raise Exception(f"设置日志时发生错误: {str(e)}")




logger = setup_logging(log_file_path=os.path.join(get_base_dir(), "log", "common.log"), logger_name="common")

def gettime(n=4):
    """获取当前时间的多种格式。

    Args:
        n (int, optional): 时间格式类型，默认 4
            - 1: 原始时间数据（浮点数秒）
            - 2: 秒级时间戳
            - 3: 毫秒级时间戳
            - 4: 格式化时间（年-月-日 时:分:秒）
            - 5: 格式化时间（年月日时分秒）
            - 6: 格式化日期（年月日）
            - 7: 格式化日期（年-月-日）
            - 8: 格式化日期（年_月_日）
            - 9: 微秒级时间戳

    Returns:
        Union[float, int, str]: 根据 n 返回对应格式的时间值

    Examples:
        >>> gettime(1)
        1534600402.09
        >>> gettime(4)
        '2018-08-18 21:53:22'
        >>> gettime(6)
        '20180818'
    """
    n = int(n)
    t = time.time()

    # print (t)  # 原始时间数据 例如：1534600402.09
    # print (int(t))  # 秒级时间戳  例如：1534600402
    # print (int(round(t * 1000)))  # 毫秒级时间戳 例如：1534600402086

    nowTime = lambda: int(round(t * 1000))
    # print (nowTime());  # 毫秒级时间戳，基于lambda  例如：2018-08-18 21:53:22

    # print (datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))  # 日期格式化 例如：20180818215322
    if n == 1:
        return t
    elif n == 2:
        return (int(t))
    elif n == 3:
        return (int(round(t * 1000)))
    elif n == 4:
        return (datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    elif n == 5:
        return (datetime.datetime.now().strftime('%Y%m%d%H%M%S'))
    elif n == 6:
        return (datetime.datetime.now().strftime('%Y%m%d'))
    elif n == 7:
        return (datetime.datetime.now().strftime('%Y-%m-%d'))
    elif n == 8:
        return (datetime.datetime.now().strftime('%Y_%m_%d'))
    elif n == 9:
        return (int(round(t * 1000000)))
    else:
        return 0


def list_rstrip(mylist: list, flags=(None,)):
    """从列表末尾移除指定的元素。

    Args:
        mylist (list): 源列表，将被直接修改
        flags (tuple, optional): 要移除的元素集合，默认 (None,)

    Returns:
        list: 处理后的列表

    Examples:
        >>> lst = [1, 2, None, 3, None]
        >>> list_rstrip(lst, flags=(None,))
        [1, 2, None, 3]
    """


def list_split_by_unit(mylist: list, count):
    """将列表按指定数量分段拆分。

    Args:
        mylist (list): 源列表
        count (int): 每段的元素数量

    Returns:
        list: 拆分后的子列表集合

    Examples:
        >>> list_split_by_unit([1, 2, 3, 4, 5, 6, 7], 3)
        [[1, 2, 3], [4, 5, 6], [7]]
    """
    length = len(mylist)
    res_list = list()
    for i in range(0, length, count):
        res_list.append(mylist[i:i + count])
    return res_list


def list_split_by_group(path_list, group_no):
    """将列表均匀分成指定数量的组。

    Args:
        path_list (list): 源列表
        group_no (int): 要分成的组数

    Returns:
        list: 分组后的子列表集合

    Examples:
        >>> list_split_by_group([1, 2, 3, 4, 5, 6, 7], 3)
        [[1, 2, 3], [4, 5], [6, 7]]
    """
    leng = len(path_list)
    if leng % group_no == 0:
        count = leng / group_no
    else:
        count = (leng / group_no) + 1
    tmp_list = list()
    res_list = list()
    for i in range(leng):
        if (i + 1) % count == 0 or (i + 1) == leng:
            tmp_list.append(path_list[i])
            res_list.append(tmp_list)
            tmp_list = []
        else:
            tmp_list.append(path_list[i])
    return res_list


def reverse_dict(mydict: dict):
    """将字典的 key 和 value 对调。

    转换规则：原字典的值是新字典的键，原字典的键（可能是可迭代对象）展开后作为新字典的值。

    Args:
        mydict (dict): 源字典，格式如 {key: [val1, val2, ...]}

    Returns:
        dict: 键值对调后的字典，格式如 {val1: key, val2: key, ...}

    Examples:
        >>> reverse_dict({'a': ['x', 'y'], 'b': ['x', 'z']})
        {'x': 'a', 'y': 'a', 'z': 'b'}
    """
    res = dict()
    for key, val in mydict.items():
        for pci in val:
            res[pci] = key
    return res


def list_pop(mylist: list, index=0, count=1, reverse=False, rm=True):
    """弹出列表中的指定元素。

    Args:
        mylist (list): 源列表，将被直接修改（除非 rm=False）
        index (int, optional): 弹出起始位置，默认 0（最左边）
        count (int, optional): 弹出的元素数量，默认 1
        reverse (bool, optional): 是否从右向左计数，默认 False
        rm (bool, optional): 是否从原列表删除弹出的元素，默认 True

    Returns:
        list: 弹出的元素列表

    Examples:
        >>> lst = [1, 2, 3, 4, 5]
        >>> list_pop(lst, index=2, count=2)
        [3, 4]
        >>> lst
        [1, 2, 5]
    """
    if reverse:
        start = index - count + 1
        end = index + 1
        if start < 0:
            start = 0
    else:
        start = index
        end = index + count
    res = mylist[start: end]
    if rm:
        for i in range(end - 1, start - 1, -1):
            mylist.pop(i)
    return res


# UTC 时间与时间戳互转
utc2stamp = lambda x: int(time.mktime(time.strptime(x, '%Y-%m-%d %H:%M:%S')))
"""将 UTC 时间字符串转换为时间戳。

Args:
    x (str): UTC 时间字符串，格式 '%Y-%m-%d %H:%M:%S'

Returns:
    int: 秒级时间戳

Examples:
    >>> utc2stamp('2018-08-18 21:53:22')
    1534600402
"""

stamp2utc = lambda x: time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(x))
"""将时间戳转换为 UTC 时间字符串。

Args:
    x (int): 秒级时间戳

Returns:
    str: UTC 时间字符串，格式 '%Y-%m-%d %H:%M:%S'

Examples:
    >>> stamp2utc(1534600402)
    '2018-08-18 21:53:22'
"""


def wait_until(func, expect_value, step=2, timeout=60, *args, **kwargs):
    """循环调用函数直到返回值匹配预期或超时。

    Args:
        func (callable): 要调用的函数
        expect_value: 期望的返回值
        step (int, optional): 重试间隔秒数，默认 2
        timeout (int, optional): 超时时间秒数，默认 60
        *args: 传递给 func 的位置参数
        **kwargs: 传递给 func 的关键字参数

    Returns:
        bool: True 表示成功匹配到期望值

    Raises:
        RuntimeError: 超时后抛出

    Examples:
        >>> def check_service():
        ...     return ping('localhost')
        >>> wait_until(check_service, True, step=1, timeout=30)
    """
    cur_time = time.time()
    flag = False
    while time.time() - cur_time <= timeout:
        # logger.info(args, kwargs)
        try:
            act_value = func(*args, **kwargs)
            # logger.info("cur_value:", [act_value], "expect_value:", [expect_value], "waittime:", time.time() - cur_time)
        except Exception as e:
            logger.info(f"wait_until 异常：{e}")
            continue
        if act_value == expect_value:
            flag = True
            return flag
        else:
            pass
        time.sleep(step)
    raise RuntimeError(f"wait_until 超时，{args} {kwargs},总共等待时间：{time.time() - cur_time}")


def wait_not_until(func, expect_value, step=2, timeout=60, *args, **kwargs):
    """循环调用函数直到返回值不再匹配预期或超时。

    Args:
        func (callable): 要调用的函数
        expect_value: 不期望的返回值（匹配此值会继续等待）
        step (int, optional): 重试间隔秒数，默认 2
        timeout (int, optional): 超时时间秒数，默认 60
        *args: 传递给 func 的位置参数
        **kwargs: 传递给 func 的关键字参数

    Returns:
        bool: True 表示成功匹配到非期望值

    Raises:
        RuntimeError: 超时后抛出

    Examples:
        >>> def check_stopped():
        ...     return get_status()
        >>> wait_not_until(check_stopped, 'running', timeout=60)
    """
    cur_time = time.time()
    flag = False
    while time.time() - cur_time <= timeout:
        try:
            act_value = func(*args, **kwargs)
            # logger.info("cur_value:", [act_value], "expect_value(not):", [expect_value], "waittime:", time.time() - cur_time)
        except Exception as e:
            logger.info(e)
            continue
        if act_value != expect_value:
            flag = True
            return flag
        else:
            pass
        time.sleep(step)
    raise RuntimeError(f"wait_not_until 超时，{args} {kwargs},总共等待时间：{time.time() - cur_time}")


def url_special_char_escape(str1):
    """对 URL 中的特殊字符进行转义处理。

    Args:
        str1 (str): 待转义的字符串

    Returns:
        str: 转义后的字符串

    Examples:
        >>> url_special_char_escape("test?query=1")
        'test?query=1'
    """
    # chars = {".": "\.", "?": "\?", "{": "\{", "}": "\}", "[": "\[", "]": "\]", "$": "\$", "^": "\^", "*": "\*",
    #          "(": "\(", ")": "\)", "+": "\+"}
    chars = {".": ".", "?": "?", "{": "{", "}": "}", "[": "[", "]": "]", "$": "$", "^": "^", "*": "*",
             "(": "(", ")": ")", "+": "+"}

    res = ""
    for i in str1:
        if i in chars:
            res += chars[i]
        else:
            res += i
    return res


def get_flow_timeout(xsa_json, key="idle_timeout_ms", default=30000):
    """
    安全获取 xsa.json 中的流超时时间

    :param xsa_json: xsa.json 解析后的字典
    :param key: 超时字段名，默认 idle_timeout_ms，可选 tcp_fin_timeout_ms
    :param default: 默认值，默认 30000ms
    :return: 超时时间（毫秒）
    """
    if isinstance(xsa_json, dict) and "flow" in xsa_json and isinstance(xsa_json["flow"], dict):
        result = xsa_json["flow"].get(key, default)
        logger.debug(f"get_flow_timeout: found flow.{key} = {result}")
        return result
    logger.warning(f"xsa.json 中未找到 flow.{key}，使用默认值 {default}")
    logger.debug(f"get_flow_timeout xsa_json keys: {list(xsa_json.keys()) if isinstance(xsa_json, dict) else type(xsa_json)}")
    return default


def net_is_used(port, ip='127.0.0.1'):
    """检测指定 IP 和端口是否已被占用。

    Args:
        port (int): 要检测的端口号
        ip (str, optional): 要检测的 IP 地址，默认 '127.0.0.1'

    Returns:
        bool: True 表示端口已被占用，False 表示端口可用

    Examples:
        >>> net_is_used(8080)
        False
        >>> net_is_used(80, ip='192.168.1.1')
        True
    """


def get_port_unused(portrange=range(10000, 65535)):
    """从指定范围内随机获取一个未使用的端口。

    Args:
        portrange (range, optional): 端口范围，默认 range(10000, 65535)

    Returns:
        int: 可用的端口号

    Raises:
        RuntimeError: 当范围内没有可用端口时抛出

    Examples:
        >>> port = get_port_unused()
        >>> print(port)
        54321
    """


# logger.info(get_port_unused())

# def test(*param):
#     tmp = random.choice(param)
#     logger.info(tmp)
#     return tmp
# wait_until("test",1111, 2, 60, 1111,2222,3333,4444)

def ntpget():
    """从 NTP 服务器获取当前时间。

    尝试多个 NTP 服务器，返回第一个成功响应的时间。

    Returns:
        list: [时间戳, "年-月-日 时:分:秒"] 格式的时间列表

    Raises:
        Exception: 所有 NTP 服务器都请求失败时抛出

    Examples:
        >>> result = ntpget()
        >>> print(result)
        [1534600402.0, '2018-08-18 21:53:22']
    """
    t = ntplib.NTPClient()
    for host in hosts:
        try:
            res = t.request(host, port='ntp', version=4, timeout=5)
            if res:
                ts = res.tx_time
                # 方法一
                _date = time.strftime('%Y-%m-%d', time.localtime(ts))
                _time = time.strftime('%X', time.localtime(ts))
                # logger.info([_date,_time])
                return [ts, _date + " " + _time]
        except Exception as e:
            logger.info(e)
            pass


def md5(data):
    """计算数据的 MD5 哈希值。

    支持多种输入类型：文件路径、bytes 对象、io.BytesIO 对象。

    Args:
        data: 输入数据，支持以下类型:
            - str: 文件路径，将计算文件的 MD5
            - bytes: 直接计算字节串的 MD5
            - io.BytesIO: 计算 BytesIO 内容的 MD5

    Returns:
        str: 32 位十六进制 MD5 字符串

    Raises:
        TypeError: 当输入类型不支持时抛出

    Examples:
        >>> md5("test.txt")  # 文件
        '098f6bcd4621d373cade4e832627b4f6'
        >>> md5(b"hello")
        '5d41402abc4b2a76b9719d911017c592'
    """
    md5 = hashlib.md5()

    # 如果是文件路径
    if isinstance(data, str) and os.path.isfile(data):
        with open(data, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                md5.update(chunk)

    # 如果是 bytes 对象
    elif isinstance(data, bytes):
        md5.update(data)

    # 如果是 io.BytesIO 对象
    elif isinstance(data, io.BytesIO):
        data.seek(0)
        for chunk in iter(lambda: data.read(4096), b''):
            md5.update(chunk)

    # 如果类型不支持
    else:
        raise TypeError("不支持的数据类型")

    return md5.hexdigest()

class IPRangeSet:
    """IP 地址范围集合，支持 IPv4 和 IPv6。

    用于存储和查询 IP 地址是否在指定范围内。

    Attributes:
        ipv4_ranges (list): IPv4 地址范围列表
        ipv6_ranges (list): IPv6 地址范围列表
    """

    def __init__(self):
        """初始化空的 IP 范围集合。"""
        self.ipv4_ranges = []
        self.ipv6_ranges = []

    def add_range(self, start_ip, end_ip):
        """添加一个 IP 地址范围。

        Args:
            start_ip (str): 起始 IP 地址
            end_ip (str): 结束 IP 地址

        Examples:
            >>> ip_set = IPRangeSet()
            >>> ip_set.add_range("192.168.1.0", "192.168.1.255")
        """
        ip_obj = ipaddress.ip_address(start_ip)
        if isinstance(ip_obj, ipaddress.IPv4Address):
            self.ipv4_ranges.append((ipaddress.IPv4Address(start_ip), ipaddress.IPv4Address(end_ip)))
        else:
            self.ipv6_ranges.append((ipaddress.IPv6Address(start_ip), ipaddress.IPv6Address(end_ip)))

    def contains(self, ip):
        """检查 IP 地址是否在范围内。

        Args:
            ip (str): 要检查的 IP 地址

        Returns:
            bool: True 表示在范围内，False 表示不在范围内

        Examples:
            >>> ip_set = IPRangeSet()
            >>> ip_set.add_range("192.168.1.0", "192.168.1.255")
            >>> ip_set.contains("192.168.1.100")
            True
            >>> ip_set.contains("10.0.0.1")
            False
        """
        ip_obj = ipaddress.ip_address(ip)
        ranges = self.ipv4_ranges if isinstance(ip_obj, ipaddress.IPv4Address) else self.ipv6_ranges
        return any(start <= ip_obj <= end for start, end in ranges)

def dict_update(mydict: dict, **kargs):
    """深度更新嵌套字典的值。

    支持使用点号分隔的路径更新嵌套字典，如 "key1.key2.key3"。

    Args:
        mydict (dict): 源字典，将被直接修改
        **kargs: 键值对，键为点号分隔的路径，值为要设置的值

    Returns:
        bool or None: 成功更新返回 True，无变化返回 None

    Examples:
        >>> d = {"a": {"b": 1}}
        >>> dict_update(d, **{"a.b": 2})
        True
        >>> d
        {'a': {'b': 2}}
    """
    for key, val in kargs.items():
        logger.info(f"修改{key}为{val}")
        tmp = mydict
        key_list = key.strip().split(".")
        key_list = list(map(lambda x: int(x) if x.isdigit() else x, key_list))
        if len(key_list) == 1:
            tmp[key_list[0]] = val
        else:
            for i in key_list[:-1]:
                tmp = tmp[i]
            tmp[key_list[-1]] = val
    if mydict == flag:
        return None
    else:
        return True

def convert_unit_string(s, target_unit=None):
    """
    将类似 '10G387' 或 '667' 的字符串转换为指定单位的数值。

    - '10G387' 按单位换算；
    - '667' 被视为基础单位数值；
    - target_unit 指定时转换成对应单位；
    - 保留两位小数（如果非整数）；
    """
    import re

    # 空值、0 值处理
    if not s or s.strip() in ["0", ""]:
        return 0

    s = s.strip()

    # 匹配标准格式：整数 + 单位 + 小数部分
    match = re.fullmatch(r"(\d+)([GgMmKkWw])(\d+)", s)

    # 单位换算表
    unit_multipliers = {
        'G': 1024 ** 3,
        'M': 1024 ** 2,
        'K': 1024,
        'k': 1000,
        'W': 10000,  # 大写 W 表示 10000
    }

    if match:
        int_part, unit, decimal_part = match.groups()
        num = float(f"{int_part}.{decimal_part}")
        # 单位转标准格式（k 除外）
        unit = unit if unit == 'k' else unit.upper()
        if unit not in unit_multipliers:
            raise ValueError(f"Unsupported unit: {unit}")
        base_value = num * unit_multipliers[unit]
    elif s.isdigit():
        # 如果是纯数字，直接当作基础单位使用
        base_value = float(s)
    else:
        raise ValueError(f"Invalid format: {s}")

    # 如果不指定目标单位，返回整数
    if target_unit is None:
        return int(round(base_value))

    # 目标单位格式化
    target_unit = target_unit if target_unit == 'k' else target_unit.upper()
    if target_unit not in unit_multipliers:
        raise ValueError(f"Unsupported target unit: {target_unit}")

    # 转换目标单位
    target_value = base_value / unit_multipliers[target_unit]

    # 按需保留小数
    return int(target_value) if target_value.is_integer() else round(target_value, 2)

def ensure_command(cmd: str, install_cmd: str = None):
    """
    确保系统中存在指定命令，如果不存在且提供了安装命令，则尝试自动安装。

    参数:
        cmd (str): 要检测的系统命令名称，例如 "ifconfig"、"curl" 等。
        install_cmd (str): 可选，当 cmd 不存在时要执行的安装命令（如 yum/apt 安装指令）。

    返回:
        True  - 命令存在，或已执行安装指令（不保证安装成功）
        False - 命令不存在，且未提供安装命令
    """

    # 使用 shutil.which 判断命令是否存在于系统 PATH 中
    if shutil.which(cmd):
        print(f"✅ {cmd} 存在")
        return True
    else:
        print(f"❌ {cmd} 不存在")

        # 如果提供了安装命令，尝试自动安装
        if install_cmd:
            print(f"尝试安装：{install_cmd}")
            # 使用 subprocess 运行安装命令，shell=True 允许执行 shell 语法
            subprocess.run(install_cmd, shell=True)

        # 返回 False 表示命令不存在（即使已尝试安装，也不确定是否成功）
        return False


if __name__ == '__main__':

    # dpi = SocketLinux(("172.31.140.81", 9000))
    # cmd = "ls *AVL *CHK|wc -l"
    # path = "/dev/shm/sess/ACCESSTempt/EU_ACCESS_LOG"
    # wait_until(dpi.cmd, "0\n", step=1, timeout=65, args=cmd, cwd=path)
    path = r"D:\Users\Downloads\1.pcap"
    f = open(path, 'rb')
    f1 = io.BytesIO(f.read())
    logger.info(md5(path))
    f.seek(0)
    logger.info(md5(f.read()))
    logger.info(md5(f1))
    f.close()
    sys.exit()

    cmd = "cat /dev/shm/xsa/pcapdump.stat|tail -n 1|awk '{print $6}'"

    servers = [
        ("172.31.140.81", 9000),
        ("172.31.140.82", 9000),
        ("172.31.140.56", 9000),
        # ("172.31.140.61", 9000),
        # ("172.31.140.62", 9000),
        # ("172.31.140.63", 9000),
        # ("172.31.140.67", 9000),
        # ("172.31.140.68", 9000),
        # ("172.31.140.69", 9000),
        # ("172.31.140.70", 9000),
        # ("172.31.140.71", 9000),
        ("172.31.140.87", 9000),
        ("172.31.140.105", 9000),
        ("172.31.139.158", 9000)]
    sls = list()
    tmp = list()
    for server in servers:
        sl = SocketLinux(server)
        sls.append(sl)
        tmp.append((server[0], sl.get_systemversion()))

    mytime = ntpget()[1]
    logger.info(mytime)
    for sl in sls:
        sl.update_systime(settime=mytime)

    for m, n in tmp:
        logger.info([m, n])
