#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2024/4/17
# @Author  : weihang
# @File    : crypto_helper.py
# @Desc    : 加密解密工具函数

import base64
import gzip
import hashlib
import io
import random
import string
import zipfile

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import algorithms, Cipher, modes

from utils.xml_helper import xml2dict, Xml
from utils.common import setup_logging

logger = setup_logging(log_file_path="log/crypto.log", logger_name="crypto")


def random_str(length, chars=string.ascii_letters + '0123456789'):
    """生成指定长度的随机字符串。

    Args:
        length (int): 随机字符串长度
        chars (str, optional): 字符集，默认包含字母和数字

    Returns:
        str: 随机生成的字符串

    Examples:
        >>> random_str(8)
        'aB3xY7zQ'
    """
    return ''.join(random.choice(chars) for x in range(length))


def pad(text):
    """使用 PKCS7 填充数据。

    Args:
        text (bytes): 要填充的原始数据

    Returns:
        bytes: PKCS7 填充后的数据

    Examples:
        >>> pad(b"Hello")
        b'Hello\\x0b\\x0b\\x0b\\x0b\\x0b\\x0b\\x0b\\x0b\\x0b\\x0b\\x0b'
    """
    block_size = 16
    padding_size = block_size - len(text) % block_size
    padding = bytes([padding_size] * padding_size)
    return text + padding


def unpad(text):
    """去除 PKCS7 填充。

    Args:
        text (bytes): 填充后的数据

    Returns:
        bytes: 去除填充后的原始数据

    Examples:
        >>> unpad(b'Hello\\x0b\\x0b\\x0b\\x0b\\x0b\\x0b\\x0b\\x0b\\x0b\\x0b\\x0b')
        b'Hello'
    """
    padding_size = text[-1]
    return text[:-padding_size]


def encrypt_cbc(data, key, iv):
    """AES CBC 模式加密。

    Args:
        data (bytes): 要加密的原始数据
        key (bytes): AES 密钥（16/24/32 字节）
        iv (bytes): 初始向量（16 字节）

    Returns:
        bytes: 加密后的数据

    Examples:
        >>> encrypt_cbc(b"Hello", b"1234567890123456", b"0000000000000000")
        b'...'
    """
    data = pad(data)
    backend = default_backend()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=backend)
    encryptor = cipher.encryptor()
    encrypted_data = encryptor.update(data) + encryptor.finalize()
    return encrypted_data


def decrypt_cbc(data, key, iv):
    """AES CBC 模式解密。

    Args:
        data (bytes): 要解密的数据
        key (bytes): AES 密钥（16/24/32 字节）
        iv (bytes): 初始向量（16 字节）

    Returns:
        bytes: 解密后的原始数据

    Examples:
        >>> decrypt_cbc(encrypted, b"1234567890123456", b"0000000000000000")
        b'Hello'
    """
    backend = default_backend()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=backend)
    decryptor = cipher.decryptor()
    decrypted_data = decryptor.update(data) + decryptor.finalize()
    return decrypted_data


def encrypt_idc_command(xml, encryptAlgorithm=1, compressionFormat=1, hashAlgorithm=1, inter_pwd="KWQ239",
                        inter_skey="LJRYRPYF27466944", inter_asepyl="VZAVUFAE58697989", inter_key="666666"):
    """
    IDC命令XML加密

    :param xml: str or bytes - 要加密的XML内容
    :param encryptAlgorithm: 加密算法，0-不加密，1-AES加密
    :param compressionFormat: 压缩格式，0-不压缩，1-Zip压缩，2-gzip压缩
    :param hashAlgorithm: 哈希算法，0-无hash，1-MD5
    :param inter_pwd: 用户口令userKey
    :param inter_skey: 加密密钥encryKey
    :param inter_asepyl: 密钥偏移量asepyl
    :param inter_key: 认证密钥infoInterKey
    :return: dict - 包含加密后的命令信息
    """
    xml_b = xml.encode("utf-8") if type(xml) == str else xml

    inter_pwd = inter_pwd.encode("utf-8")
    inter_skey = inter_skey.encode("utf-8")
    inter_asepyl = inter_asepyl.encode("utf-8")
    inter_key = inter_key.encode("utf-8")

    # 1.产生长度上限为20的随机字符串
    randVal = random_str(random.randint(15, 20)).encode("utf-8")

    # 2.该字符串与控制平台中存储的用户口令进行连接
    if hashAlgorithm == 1:
        pwdHash = base64.b64encode(hashlib.md5((inter_pwd + randVal)).hexdigest().encode())
    elif hashAlgorithm == 0:
        pwdHash = base64.b64encode((inter_pwd + randVal))
    else:
        pwdHash = None

    # 3.zip压缩
    if compressionFormat == 1:
        file = io.BytesIO()
        with zipfile.ZipFile(file, 'w', compression=zipfile.ZIP_DEFLATED) as myzip:
            myzip.writestr("0", xml_b)
        zip_data = file.getvalue()
    elif compressionFormat == 2:
        zip_data = gzip.compress(xml_b)
    else:
        zip_data = xml_b

    # 4.对称加密算法AES加密
    if encryptAlgorithm == 1:
        encryptedbytes = encrypt_cbc(data=zip_data, key=inter_skey, iv=inter_asepyl)
    else:
        encryptedbytes = zip_data
    command = base64.b64encode(encryptedbytes)

    # 5.哈希算法(md5)
    data = zip_data + inter_key
    if hashAlgorithm == 1:
        data = hashlib.md5(data).hexdigest()
    commandHash = base64.b64encode(data.encode())

    return {
        "randVal": randVal.decode("utf-8"),
        "pwdHash": pwdHash.decode("utf-8"),
        "command": command.decode("utf-8"),
        "commandHash": commandHash.decode("utf-8")
    }


def decrypt_idc_command(xml, method="idc_command", inter_pwd="KWQ239", inter_skey="LJRYRPYF27466944",
                        inter_asepyl="VZAVUFAE58697989", inter_key="666666"):
    """
    IDC命令XML解密

    :param xml: str or bytes - 要解密的XML内容
    :param method: 方法名
    :param inter_pwd: 用户口令userKey
    :param inter_skey: 加密密钥encryKey
    :param inter_asepyl: 密钥偏移量asepyl
    :param inter_key: 认证密钥infoInterKey
    :return: 解密后的XML内容（bytes）
    """
    inter_pwd = inter_pwd.encode("utf-8")
    inter_skey = inter_skey.encode("utf-8")
    inter_asepyl = inter_asepyl.encode("utf-8")
    inter_key = inter_key.encode("utf-8")

    xml_dict = xml2dict(__import__('xml.etree.ElementTree', fromlist=['ElementTree']).ElementTree(
        __import__('xml.etree.ElementTree', fromlist=['ElementTree']).fromstring(xml)).getroot())

    randVal = xml_dict[method]["randVal"].encode("utf-8")
    pwdHash = xml_dict[method]["pwdHash"]
    command = xml_dict[method]["command"]
    commandHash = xml_dict[method]["commandHash"]
    compressionFormat = xml_dict[method]["compressionFormat"]
    hashAlgorithm = xml_dict[method]["hashAlgorithm"]
    encryptAlgorithm = xml_dict[method]["encryptAlgorithm"]

    # 1.该字符串与控制平台中存储的用户口令进行连接，pwdHash校验
    if hashAlgorithm == "1":
        pwdHash_new = base64.b64encode(hashlib.md5((inter_pwd + randVal)).hexdigest().encode())
    elif hashAlgorithm == "0":
        pwdHash_new = base64.b64encode((inter_pwd + randVal))
    else:
        pwdHash_new = None
    if pwdHash.encode("utf-8") != pwdHash_new:
        raise RuntimeError(f"请检查用户口令userKey，当前值inter_pwd:{inter_pwd}")

    # 2.对称加密算法AES解密
    encryptedbytes = base64.b64decode(command)
    if encryptAlgorithm == "1":
        data = decrypt_cbc(data=encryptedbytes, key=inter_skey, iv=inter_asepyl)
        zip_data = data[:-data[-1]]
    else:
        zip_data = encryptedbytes

    # 3.哈希算法校验(md5)
    data_hash = zip_data + inter_key
    if hashAlgorithm == "1":
        data_hash = hashlib.md5(data_hash).hexdigest()
    commandHash_new = base64.b64encode(data_hash.encode("utf-8"))
    if commandHash.encode("utf-8") != commandHash_new:
        raise RuntimeError(f"请检查认证密钥infoInterKey，当前值inter_key:{inter_key}")

    # 4.zip解压
    if compressionFormat == "1":
        file = io.BytesIO()
        file.write(zip_data)
        file.seek(0)
        with zipfile.ZipFile(file, 'r', compression=zipfile.ZIP_DEFLATED) as myzip:
            xml_b = myzip.read(myzip.namelist()[0])
    elif compressionFormat == "2":
        xml_b = gzip.decompress(zip_data)
    else:
        xml_b = zip_data

    return xml_b


def decrypt_file_load(xml, method="file_load", inter_pwd="KWQ239", inter_skey="LJRYRPYF27466944",
                      inter_asepyl="VZAVUFAE58697989", inter_key="666666"):
    """
    xml解密
    :param xml: str or bytes
    :param encryptAlgorithm: 1  # 对称加密算法0：不进行加密，明文传输；1：AES加密算法
    :param crypttype: "cbc"  # 加密CBC类型
    :param compressionFormat: 1  # 压缩格式0：无压缩1：Zip压缩格式
    :param hashAlgorithm: 1  # 哈希算法0：无hash 1：MD5 2：SHA-1
    :param inter_pwd: "KWQ239"  # 用户口令userKey
    :param inter_skey: "LJRYRPYF27466944"  # 加密密钥encryKey
    :param inter_asepyl: "VZAVUFAE58697989"  # 密钥偏移量asepyl
    :param inter_key: "666666"  # 认证密钥infoInterKey
    :return:
    """
    # crypttype = "cbc"
    # crypttype2mode = {"cbc": AES.MODE_CBC}
    inter_pwd = inter_pwd.encode("utf-8")
    inter_skey = inter_skey.encode("utf-8")
    inter_asepyl = inter_asepyl.encode("utf-8")
    inter_key = inter_key.encode("utf-8")

    xml_dict = xml2dict(Xml(content=xml, encoding="utf-8").root)
    logger.info(xml_dict)
    # randVal = xml_dict[method]["randVal"].encode("utf-8")
    # pwdHash = xml_dict[method]["pwdHash"]
    command = xml_dict[method]["dataUpload"]
    commandHash = xml_dict[method]["dataHash"]
    # idcId = xml_dict[method]["idcId"]
    # commandType = xml_dict[method]["commandType"]
    # commandVersion = xml_dict[method]["commandVersion"]
    compressionFormat = xml_dict[method]["compressionFormat"]
    hashAlgorithm = xml_dict[method]["hashAlgorithm"]
    encryptAlgorithm = xml_dict[method]["encryptAlgorithm"]

    # # 1.该字符串与控制平台中存储的用户口令进行连接，pwdHash校验
    # if hashAlgorithm == "1":
    #     pwdHash_new = base64.b64encode(hashlib.md5((inter_pwd + randVal)).hexdigest().encode())
    # elif hashAlgorithm == "0":
    #     pwdHash_new = base64.b64encode((inter_pwd + randVal))
    # else:
    #     pwdHash_new = None
    # if pwdHash.encode("utf-8") != pwdHash_new:
    #     raise RuntimeError(f"请检查用户口令userKey，当前值inter_pwd:{inter_pwd}")

    # 2.对称加密算法AES解密
    encryptedbytes = base64.b64decode(command)
    if encryptAlgorithm == "1":
        # cipher = AES.new(inter_skey, crypttype2mode[crypttype], inter_asepyl)
        # data = cipher.decrypt(encryptedbytes)
        data = decrypt_cbc(data=encryptedbytes, key=inter_skey, iv=inter_asepyl)
        zip_data = data[:-data[-1]]
    else:
        zip_data = encryptedbytes

    # 3.哈希算法校验(md5)
    data_hash = zip_data + inter_key
    if hashAlgorithm == "1":
        data_hash = hashlib.md5(data_hash).hexdigest()
    commandHash_new = base64.b64encode(data_hash.encode("utf-8"))
    if commandHash.encode("utf-8") != commandHash_new:
        raise RuntimeError(f"请检查认证密钥infoInterKey，当前值inter_key:{inter_key}")

    # 4.zip压缩
    if compressionFormat == "1":
        file = io.BytesIO()
        file.write(zip_data)
        file.seek(0)
        with zipfile.ZipFile(file, 'r', compression=zipfile.ZIP_DEFLATED) as myzip:
            xml_b = myzip.read(myzip.namelist()[0])
    elif compressionFormat == "2":
        xml_b = gzip.decompress(zip_data)
        # logger.info(xml_b.decode("utf-8"))
    else:
        xml_b = zip_data

    return xml_b


if __name__ == '__main__':
    # 测试代码
    xml = """<dataCollect>
        <version>3.0</version>
        <commandId>1518601</commandId>
        <collectType>1</collectType>
        <dataArea>1</dataArea>
        <operationType>0</operationType>
        <cycleType>1</cycleType>
        <rule>
            <url>aHR0cDovL3d3dy5hY3QxMDE2ODMxOC5jb20vdXRmMTguaHRtbA==</url>
            <urlPositive>1</urlPositive>
            <domain>www.act10168318.com</domain>
            <domainPositive>1</domainPositive>
            <startTime>2023-04-12 14:12:52</startTime>
            <endTime>2023-04-15 02:12:52</endTime>
            <srcIp>
                <startIp>2E02::976</startIp>
                <endIp>2E02::976</endIp>
            </srcIp>
            <srcIpPositive>1</srcIpPositive>
            <srcPort>8856</srcPort>
            <srcPortPositive>1</srcPortPositive>
            <protocolType>1</protocolType>
            <protocolTypePositive>1</protocolTypePositive>
        </rule>
        <range>
            <idcId>鄂A1234567890</idcId>
            <houseId>1000</houseId>
        </range>
        <proportion>1.000000</proportion>
        <collectWay>3</collectWay>
        <storageAmount>1024</storageAmount>
        <saveTime>1</saveTime>
        <timeStamp>2023-04-12 14:13:18</timeStamp>
    </dataCollect>"""
    # # 加密后的dict
    # aa = assembly_xml_encrypt(xml=xml, idcId="鄂A1234567890", commandType=7)
    # print(aa)
    #
    # # 生成加密后的xml
    # bb = Xml()
    # bb.root = dict2node(aa,  Element("idc_command"))
    # cc = bb.tostring(True)
    # print(cc)
    # # 解密xml
    cc = """<fileLoad>
        <idcId>A2.B1.B2-20100001</idcId>
        <provinceId>420000</provinceId>
        <dataUpload>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</dataUpload>
        <encryptAlgorithm>1</encryptAlgorithm>
        <compressionFormat>1</compressionFormat>
        <hashAlgorithm>1</hashAlgorithm>
        <dataHash>ZTFlY2NiZGI1NjY3NGE5OGJhZDNjMmY5MTJjMDU5Mzk=</dataHash>
        <commandVersion>3.1</commandVersion>
    </fileLoad>"""
    # with open(r"D:\Users\Documents\WXWork\1688852665886560\Cache\File\2024-08\42111310_001001_17243093554486270000.xml", "r") as f:
    #     cc = f.read()
    # dd = decrypt_file_load(xml=cc, method="fileLoad",inter_key="1234567890ABCDEF",inter_skey="1234567890ABCDEF",inter_asepyl="1234567890ABCDEF",inter_pwd="1234567890ABCDEF")
    # print(dd.decode("utf-8"))

    # cc = b'<?xml version="1.1" encoding="UTF-8"?>\n<fileLoad>\n    <idcId>A2.B1.B2-20100001</idcId>\n    <provinceId>640000</provinceId>\n    <dataUpload>scdVJ8AagJnv+FHwc/Ab1P1q1qDeqJwVpOSmkOePjK2Fs+2/AAGZOnZgFzt59rjiTMS1cXOfLP6d65XFJ1adDnJzZV9tYVNtKV8WfXYn3+09ly9Akl4TTltw+Z54K3msjn2ImJSNqSQznFsO0/2hgLHcUJnUR12+HHMGRPI2WLs9kgo7jF4gQR0WfLCIz3gXPIGl2TYMai2GDh75ZqM7v474glCJm6Gx2nJBpdQ3CulUhSLFkx3y0rhWuqDESFg8MuVVDMk3QTJpXAvKtMAABV22Qqj+F+KwEjZuXkXsXjpVrfRu+lp6L7aq6Gp2yMAIcn3mVRsLd/68B2EyrI4dERdBlr6/q5nax/quvD3tcZZg0XKlG6JFgm3iBNV2kv9NPvZ+1Hh77KAyd4bzpxlT+js2JouJtAEZCfhn7vIBJvBcTbhWMEDDlgMTWS3Ef2a9mO2KyyailPngDfA+gXzZmIgcBPy7VIT8fdnNBvlvMMXX7IgrNfewllA8oHDq4u+ur94R4qt/2PCn3p7w5GU53Ytk5D4uheBHONdLBrHzyIGaVeRyxMoJyMa0GGcMsGybmnV/76i/UnV9RXm4iv08nFv/Qi1sjd9uPvrAsK1bhKxLsApsdB7oUXscxuqgUCdskR9umspGWEC11cZheWQNdYMw52MRHpOy90osAkqsdeYDfoyqhnqF0r+oObszyML8ddX2syXo77db31qOkV9SblARMlMQrfL255r/oNArxtKNTgUI10DgX23MYwjI/cXU4q6vvNBHqKi2qyf0oFP+GZ6k/Q2rubXRONS6tfm5zNfPy+dOejO+v0/nPF2E+YSa+QiMUkFS/Y2AAwVheTGu3UiVCnN7L+Guattuh69hPfVXI0CbBCeQAuLfYPGKnyk0micSqPtjGmlq0UdZHRxOww==</dataUpload>\n    <encryptAlgorithm>1</encryptAlgorithm>\n    <compressionFormat>1</compressionFormat>\n    <hashAlgorithm>1</hashAlgorithm>\n    <dataHash>YWMxODk3YzcxYTNjYzJjY2EwYzM5ZGVmOWRhODdjY2Y=</dataHash>\n    <commandVersion>3.1</commandVersion>\n</fileLoad>\n'
    dd = decrypt_file_load(xml=cc, method="fileLoad")
    print(dd.decode("utf-8"))
