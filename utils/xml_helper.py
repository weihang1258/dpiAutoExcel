#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2024/4/17
# @Author  : weihang
# @File    : xml_helper.py
# @Desc    : XML工具函数

import xml.etree.ElementTree as ET
from xml.etree.ElementTree import Element


def xml2dict(node):
    """
    将XML Element转换为字典

    :param node: xml.etree.ElementTree.Element对象
    :return: dict - 转换后的字典
    """
    if not isinstance(node, ET.Element):
        raise Exception("upper_node format error.")

    if len(node) == 0:
        return {node.tag: node.text}

    data = {}
    temp = None
    for child in node:
        key, val = list(xml2dict(child).items())[0]
        if key in data:
            if type(data[key]) == list:
                data[key].append(val)
            else:
                temp = data[key]
                data[key] = [temp, val]
        else:
            data[key] = val
    return {node.tag: data}


def dict2node(content, upper_node=None, key_tmp=None):
    """
    将字典转换为XML Element

    :param content: 要转换的字典
    :param upper_node: 父节点（Element对象）
    :param key_tmp: 临时键名
    :return: Element对象
    """
    if upper_node is None:
        key, val = list(content.items())[0]
        return dict2node(val, upper_node=Element(key))

    if type(content) == dict:
        for key, val in content.items():
            if type(val) in (str, int, float):
                elem = Element(key)
                elem.text = str(val)
                upper_node.append(elem)
            elif type(val) in (list, set, tuple):
                dict2node(val, upper_node, key)
            elif type(val) == dict:
                elem = Element(key)
                upper_node.append(dict2node(val, elem))
            else:
                raise RuntimeError("不支持的类型")
    elif type(content) in (list, set, tuple):
        for val in content:
            if type(val) in (str, int, float):
                elem = Element(key_tmp)
                elem.text = str(val)
                upper_node.append(elem)
            else:
                elem = Element(key_tmp)
                upper_node.append(elem)
                dict2node(val, elem, key_tmp)
    else:
        raise RuntimeError("不支持的类型")
    return upper_node


def assembly_xml_encrypt(xml: str, idcId: str, commandType: int, commandVersion="3.0", encryptAlgorithm=1,
                         compressionFormat=1, hashAlgorithm=1, inter_pwd="KWQ239", inter_skey="LJRYRPYF27466944",
                         inter_asepyl="VZAVUFAE58697989", inter_key="666666"):
    """
    XML加密组装

    :param xml: XML字符串
    :param idcId: IDC ID
    :param commandType: 指令类型
        0：基础数据管理指令
        1：访问日志存储管理指令
        2：信息安全管理指令（违法网站列表管理指令、免过滤网站列表管理指令、违法信息监测和处置指令管理指令）
        3：信息安全管理指令查询指令
        4：代码表发布指令
        5：活跃资源上报周期指令
        6：信息安全查询指令（活跃资源统计信息查询指令、违法违规网站监测记录查询指令、违法信息监测和处置记录查询指令）
        7：流量采集管理指令
        8：数据安全监测巡查指令
        9：恶意报文监测指令
        10：恶意文件监测指令
        11：深度合成信息监测处置指令
        12：深度合成监测模型同步指令
        30：基础信息下发指令
        31：恶意流量监测设备状态查询指令
        32：异常流量场景监测规则指令
    :param commandVersion: 接口方法版本，默认3.0
    :param encryptAlgorithm: 对称加密算法，0-不加密，1-AES加密
    :param compressionFormat: 压缩格式，0-不压缩，1-Zip压缩
    :param hashAlgorithm: 哈希算法，0-无hash，1-MD5
    :param inter_pwd: 用户口令userKey
    :param inter_skey: 加密密钥encryKey
    :param inter_asepyl: 密钥偏移量asepyl
    :param inter_key: 认证密钥infoInterKey
    :return: dict - 包含加密后的命令信息
    """
    res = encrypt_idc_command(
        xml=xml,
        encryptAlgorithm=encryptAlgorithm,
        compressionFormat=compressionFormat,
        hashAlgorithm=hashAlgorithm,
        inter_pwd=inter_pwd,
        inter_skey=inter_skey,
        inter_asepyl=inter_asepyl,
        inter_key=inter_key
    )
    res["idcId"] = idcId
    res["commandType"] = commandType
    res["commandVersion"] = commandVersion
    res["compressionFormat"] = compressionFormat
    res["hashAlgorithm"] = hashAlgorithm
    res["encryptAlgorithm"] = encryptAlgorithm
    return res


class Xml:
    """
    XML处理类
    """

    def __init__(self, content=None, encoding="utf-8", file_path=None):
        """
        初始化XML对象

        :param content: XML内容（字符串）
        :param encoding: 编码格式
        :param file_path: XML文件路径
        """
        self._encoding = encoding
        if file_path:
            self.tree = ET.parse(file_path)
            self.root = self.tree.getroot()
        elif content:
            self.root = ET.fromstring(content)
        else:
            raise ValueError("必须提供content或file_path参数")

    def tostring(self, indent=False):
        """
        将XML转换为字符串

        :param indent: 是否格式化输出
        :return: XML字符串
        """
        if indent:
            self._indent(self.root)
        return ET.tostring(self.root, encoding=self._encoding).decode()

    def _indent(self, elem, level=0):
        """
        格式化XML（添加缩进）

        :param elem: Element对象
        :param level: 缩进级别
        """
        i = "\n" + level * "  "
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = i + "  "
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
            for child in elem:
                self._indent(child, level + 1)
            if not child.tail or not child.tail.strip():
                child.tail = i
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = i


if __name__ == '__main__':
    # 测试代码
    test_xml = '<?xml version="1.0" encoding="utf-8"?><root><item>value</item></root>'
    xml_obj = Xml(content=test_xml)
    result = xml2dict(xml_obj.root)
    print("XML to Dict:", result)

    # 测试加密组装
    encrypted = assembly_xml_encrypt(test_xml, "test_id", 1)
    print("Encrypted:", encrypted)
