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
# from mycode.lib.socket_linux import SocketLinux
import logging

# 日志格式常量
LOG_FORMAT = '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

def keep_console_alive(logger, interval=10):
    """
    保持控制台活性的后台线程函数
    :param logger: 日志记录器
    :param interval: 心跳间隔（秒）
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




logger = setup_logging(log_file_path="log/common.log", logger_name="common")

def gettime(n=4):
    '''
    获取当前时间
    时间格式：
    n = 1 原始时间数据 例如：1534600402.09
    n = 2 秒级时间戳  例如：1534600402
    n = 3 毫秒级时间戳 例如：1534600402086
    n = 4 时间格式化 例如：2018-08-18 21:53:22(年-月-日 时:分:秒)
    n = 5 时间格式化 例如：20180818215322(年月日时分秒)
    n = 6 日期格式化 例如：20180818(年月日)
    n = 7 日期格式化 例如：2018-08-18(年-月-日)
    n = 8 日期格式化 例如：2018_08_18(年月日)
    n = 9 微秒级时间戳 例如：1534600402086123
    :param n:
    :return:
    '''
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
    for i in range(len(mylist) - 1, -1, -1):
        if mylist[i] in flags:
            mylist.pop(-1)
        else:
            return mylist
    return mylist


def list_split_by_unit(mylist: list, count):
    '''
    将mylist按照每count个拆分。
    :param mylist: 源列表
    :param count: 按照指定数量拆分
    :return: 拆分后的列表集合
    '''
    length = len(mylist)
    res_list = list()
    for i in range(0, length, count):
        res_list.append(mylist[i:i + count])
    return res_list


def list_split_by_group(path_list, group_no):
    '''
    将列表分成n组，返回列表
    :param path_list:
    :param group_no:
    :return:
    '''
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
    """dict的key和value对调"""
    res = dict()
    for key, val in mydict.items():
        for pci in val:
            res[pci] = key
    return res


def list_pop(mylist: list, index=0, count=1, reverse=False, rm=True):
    """对list操作，弹出指定数量，弹出开启位置，默认从左边第一个开始，可以反向，默认删除原列表弹出内容"""
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


utc2stamp = lambda x: int(time.mktime(time.strptime(x, '%Y-%m-%d %H:%M:%S')))

stamp2utc = lambda x: time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(x))


def wait_until(func, expect_value, step=2, timeout=60, *args, **kwargs):
    '''通过循环查询，直到查询成功或者超时！'''
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
    '''通过循环查询，直到查询成功或者超时！'''
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
    """特殊字符转义"""
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


def net_is_used(port, ip='127.0.0.1'):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect((ip, port))
        s.shutdown(2)
        logger.info('%s:%d is used' % (ip, port))
        return True
    except:
        logger.info('%s:%d is unused' % (ip, port))
        return False
    finally:
        try:
            s.close()
        except:
            pass


def get_port_unused(portrange=range(10000, 65535)):
    counter = 10
    while counter:
        port = random.choice(portrange)
        if not net_is_used(port):
            return port
        counter -= 1
    raise RuntimeError("No unused port!")


# logger.info(get_port_unused())

# def test(*param):
#     tmp = random.choice(param)
#     logger.info(tmp)
#     return tmp
# wait_until("test",1111, 2, 60, 1111,2222,3333,4444)

def ntpget():
    hosts = ['2.cn.pool.ntp.org', '3.cn.pool.ntp.org', '0.cn.pool.ntp.org', '1.cn.pool.ntp.org']
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
    """ 计算数据的 MD5 值 """
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
    def __init__(self):
        self.ipv4_ranges = []
        self.ipv6_ranges = []

    def add_range(self, start_ip, end_ip):
        ip_obj = ipaddress.ip_address(start_ip)
        if isinstance(ip_obj, ipaddress.IPv4Address):
            self.ipv4_ranges.append((ipaddress.IPv4Address(start_ip), ipaddress.IPv4Address(end_ip)))
        else:
            self.ipv6_ranges.append((ipaddress.IPv6Address(start_ip), ipaddress.IPv6Address(end_ip)))

    def contains(self, ip):
        ip_obj = ipaddress.ip_address(ip)
        ranges = self.ipv4_ranges if isinstance(ip_obj, ipaddress.IPv4Address) else self.ipv6_ranges
        return any(start <= ip_obj <= end for start, end in ranges)

def dict_update(mydict: dict, **kargs):
    flag = copy.deepcopy(mydict)
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
