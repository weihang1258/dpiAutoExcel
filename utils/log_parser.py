#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2024/4/17
# @Author  : weihang
# @File    : log_parser.py
# @Desc    : 日志解析工具函数

import ipaddress
import os
import struct

# 格式化字符串到数据类型的映射
fmt_str2datatype = {
    "B": "%s字节-无符号整型",
    "H": "%s字节-无符号短整型",
    "I": "%s字节-无符号整型",
    "s": "%s字节-字符",
    "T": "%s字节-整形"
}

# 包头格式定义
head2format = {
    "Ver": "s",
    "Proto-Signature": "3s",
    "ManufactureID": "B",
    "DeviceSerialNo": "3s",
    "Packet Type": "B",
    "Packet Subtype": "B",
    "Resv": "2s",
    "Packet Length": "I"
}

# 字段去重映射
field2rstrip = {
    b"\x31": ("CommandID"),
    b"\x10": ("CommandID"),
    b"\x01": ()
}

# IP字段映射
field2ip = {
    b"\x31": ("s_ip", "d_ip"),
    b"\x10": ("s_ip", "d_ip"),
    b"\x01": ("s_ip", "d_ip")
}

# 内容格式定义
content2formats = {
    b"\x31": {
        "CommandID": "13s",
        "House_ID_Length": "B",
        "House_ID": None,
        "SourceIP_Length": "B",
        "s_ip": None,
        "DestinationIP_Length": "B",
        "d_ip": None,
        "s_port": "H",
        "d_port": "H",
        "DomainName_Length": "H",
        "DomainName": None,
        "ProxyType_Flag": ["H", {
            "ProxyType": "H",
            "ProxyIp_Length": "B",
            "Proxy_ip": None,
            "Proxy_port": "H"
        }],
        "Title_Length": "H",
        "Title": None,
        "Content_Length": "I",
        "Content": None,
        "Url_Length": "H",
        "Url": None,
        "Attachmentfile_Num": ["B", {
            "AttachmentfileName_Length": "H",
            "AttachmentfileName": None
        }],
        "GatherTime": "I",
        "TrafficType": "B",
        "ProtocolType": "B",
        "ApplicationProtocol": "H",
        "BusinessProtocol": "H"
    },
    b"\x10": {
        "CommandID": "10s",
        "House_ID_Length": "B",
        "House_ID": None,
        "SourceIP_Length": "B",
        "s_ip": None,
        "DestinationIP_Length": "B",
        "d_ip": None,
        "s_port": "H",
        "d_port": "H",
        "DomainName_Length": "H",
        "DomainName": None,
        "ProxyType_Flag": ["H", {
            "ProxyType": "H",
            "ProxyIp_Length": "B",
            "Proxy_ip": None,
            "Proxy_port": "H"
        }],
        "Title_Length": "H",
        "Title": None,
        "Content_Length": "I",
        "Content": None,
        "Url_Length": "H",
        "Url": None,
        "Attachmentfile_Num": ["B", {
            "AttachmentfileName_Length": "H",
            "AttachmentfileName": None
        }],
        "GatherTime": "I"
    },
    b"\x01": {
        "CommandID": "10T",
        "House_ID_Length": "B",
        "House_ID": None,
        "SourceIP_Length": "B",
        "s_ip": None,
        "DestinationIP_Length": "B",
        "d_ip": None,
        "s_port": "H",
        "d_port": "H",
        "DomainName_Length": "H",
        "DomainName": None,
        "ProxyType_Flag": ["H", {
            "ProxyType": "H",
            "ProxyIp_Length": "B",
            "Proxy_ip": None,
            "Proxy_port": "H"
        }],
        "Title_Length": "H",
        "Title": None,
        "Content_Length": "I",
        "Content": None,
        "Url_Length": "H",
        "Url": None,
        "Attachmentfile_Num": ["B", {
            "AttachmentfileName_Length": "H",
            "AttachmentfileName": None
        }],
        "GatherTime": "I"
    }
}


def fmt_str2datatype_str(fmt_str: str):
    """
    将格式字符串转换为数据类型描述

    :param fmt_str: 格式字符串，如 "13s", "B", "H"
    :return: 数据类型描述字符串
    """
    if fmt_str[-1] in ("s", "T"):
        count = fmt_str[:-1]
        return fmt_str2datatype[fmt_str[-1]] % count
    else:
        return fmt_str2datatype[fmt_str]


def head_parser(data, format_str, byte_order=">"):
    """
    解析包头

    :param data: 二进制数据
    :param format_str: 格式字符串字典
    :param byte_order: 字节序，">" 为大端序，"<" 为小端序
    :return: (解析结果字典, 剩余数据)
    """
    format_str = byte_order + "".join(format_str.values())
    head_length = struct.calcsize(format_str)
    head_value = dict(zip(head2format.keys(), struct.unpack(format_str, data[:head_length])))
    return head_value, data[head_length:]


def singel_parser(hex_str, format_str, byte_order=">", fieldmark=None, loglevel=0, fields_rstrip=(), fields_ip=()):
    """
    解析单个字段

    :param hex_str: 二进制数据
    :param format_str: 格式字符串
    :param byte_order: 字节序
    :param fieldmark: 字段名称
    :param loglevel: 日志级别，0-详细，1-简洁，3-静默
    :param fields_rstrip: 需要去空的字段
    :param fields_ip: 需要转换为IP的字段
    :return: (解析值, 剩余数据)
    """
    try:
        T_flag = False
        if format_str[-1] == "T":
            T_flag = True
            format_str = f"{format_str[:-1]}s"
        format_str = format_str if format_str[0] in ("<", ">") else byte_order + format_str
        length = struct.calcsize(format_str)
        value = struct.unpack(format_str, hex_str[:length])[0]
        if T_flag:
            value = int.from_bytes(value, byteorder="big" if byte_order == ">" else "little", signed=False)
        if fieldmark in fields_ip:
            value = ipaddress.ip_address(value).compressed
        if fieldmark in fields_rstrip:
            value = value.rstrip(b"\x00")
        if type(value) == bytes:
            try:
                value = value.decode("utf-8")
            except Exception:
                value = value.hex()
        if loglevel == 0:
            print(
                f"\t字段：{str(fieldmark).ljust(25, ' ')}字节数：{str(fmt_str2datatype_str(format_str[1:])).ljust(13, ' ')}格式：{str(format_str.ljust(5, ' '))}value：{str(value).ljust(20, ' ')}\t16进制：{hex_str[:length].hex()}")
        elif loglevel == 1:
            print(f"\t字段：{fieldmark.ljust(25, ' ')}\t{value}")
        return value, hex_str[length:]
    except Exception as e:
        length = struct.calcsize(format_str)
        err_length = f"期望长度{length}，实际长度{len(hex_str)}" if len(hex_str) < length else ""
        print(
            f"\t字段：{str(fieldmark).ljust(25, ' ')}字节数：{str(fmt_str2datatype_str(format_str[1:])).ljust(13, ' ')}格式：{str(format_str.ljust(5, ' '))}value：{str(value).ljust(20, ' ')}\t16进制：{hex_str[:length].hex()}")
        raise RuntimeError(
            f"filed:{fieldmark},format:{format_str},value:{hex_str[:length].hex()},error:{e}\t{err_length}")


def content_parser(data, content2format: dict, length=0, loglevel=0, byte_order=">", fields_rstrip=("CommandID"), fields_ip=("s_ip", "d_ip")):
    """
    解析内容部分

    :param data: 二进制数据
    :param content2format: 格式定义字典
    :param length: 长度
    :param loglevel: 日志级别
    :param byte_order: 字节序
    :param fields_rstrip: 需要去空的字段
    :param fields_ip: 需要转换为IP的字段
    :return: (解析结果字典, 剩余数据)
    """
    res = {}
    for filed, fmt_tmp in content2format.items():
        if isinstance(fmt_tmp, str):
            value, data = singel_parser(hex_str=data, format_str=fmt_tmp, byte_order=byte_order, fieldmark=filed,
                                        loglevel=loglevel, fields_rstrip=fields_rstrip, fields_ip=fields_ip)
            res[filed] = value
            if isinstance(value, int):
                length = value
        elif fmt_tmp is None:
            if length == 0:
                continue
            fmt = f"{length}s"
            value, data = singel_parser(hex_str=data, format_str=fmt, byte_order=byte_order, fieldmark=filed,
                                        loglevel=loglevel, fields_rstrip=fields_rstrip, fields_ip=fields_ip)
            res[filed] = value
        elif isinstance(fmt_tmp, list):
            fmt, content2format_tmp = fmt_tmp
            loop_time, data = singel_parser(hex_str=data, format_str=fmt, byte_order=byte_order, fieldmark=filed,
                                            loglevel=loglevel, fields_rstrip=fields_rstrip, fields_ip=fields_ip)
            res_tmp = {}
            for i in range(loop_time):
                res1, data = content_parser(data=data, content2format=content2format_tmp, loglevel=loglevel,
                                            byte_order=byte_order, fields_rstrip=fields_rstrip, fields_ip=fields_ip)
                res_tmp.update(res1)
            if res_tmp:
                if res.get(filed, None) is None:
                    res[filed] = [res_tmp]
                else:
                    res[filed].append(res_tmp)
            else:
                res[filed] = loop_time
        else:
            raise RuntimeError(f"不支持类型：{fmt_tmp}")
    return res, data


def content_parser_with_message_type(data, message_type=b"\x10", loglevel=0, byte_order=">"):
    """
    根据消息类型解析内容

    :param data: 二进制数据
    :param message_type: 消息类型
    :param loglevel: 日志级别
    :param byte_order: 字节序
    :return: (解析结果字典, 剩余数据)
    """
    content2format = content2formats.get(message_type, None)
    if not content2format:
        return {}, data

    return content_parser(
        data,
        content2format,
        loglevel=loglevel,
        byte_order=byte_order,
        fields_rstrip=field2rstrip.get(message_type, ()),
        fields_ip=field2ip.get(message_type, ())
    )


def bytes_to_str(data, encode="utf-8"):
    """
    递归转换bytes到字符串

    :param data: 要转换的数据
    :param encode: 编码格式
    :return: 转换后的数据
    """
    if isinstance(data, dict):
        return {key: bytes_to_str(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [bytes_to_str(item) for item in data]
    elif isinstance(data, tuple):
        return tuple(bytes_to_str(item) for item in data)
    elif isinstance(data, bytes):
        return data.decode(encode)
    else:
        return data


def monitorlog(bin, byte_order='>'):
    """
    监控日志解析

    :param bin: 二进制数据或文件路径
    :param byte_order: 字节序
    :return: 解析结果列表
    """
    res = list()
    if os.path.exists(bin):
        with open(bin, 'rb') as f:
            data = f.read()
    else:
        data = bin

    while data:
        log = dict()
        head_value, data = head_parser(data=data, format_str=head2format, byte_order=byte_order)
        message_type = head_value["Ver"]
        log.update(bytes_to_str(head_value))
        content_value, data = content_parser_with_message_type(data=data, message_type=message_type, loglevel=3)
        log.update(content_value)
        res.append(log)
    return res


if __name__ == '__main__':
    # 测试代码
    print("日志解析工具模块")