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

from utils.xml_helper import xml2dict
from utils.common import setup_logging

logger = setup_logging(log_file_path="log/crypto.log", logger_name="crypto")


def random_str(length, chars=string.ascii_letters + '0123456789'):
    """
    生成随机字符串

    :param length: 字符串长度
    :param chars: 字符集
    :return: 随机字符串
    """
    return ''.join(random.choice(chars) for x in range(length))


def pad(text):
    """
    PKCS7填充

    :param text: 要填充的数据（bytes）
    :return: 填充后的数据
    """
    block_size = 16
    padding_size = block_size - len(text) % block_size
    padding = bytes([padding_size] * padding_size)
    return text + padding


def unpad(text):
    """
    去除PKCS7填充

    :param text: 填充后的数据（bytes）
    :return: 去除填充后的数据
    """
    padding_size = text[-1]
    return text[:-padding_size]


def encrypt_cbc(data, key, iv):
    """
    AES CBC加密

    :param data: 要加密的数据（bytes）
    :param key: 密钥（bytes）
    :param iv: 初始向量（bytes）
    :return: 加密后的数据
    """
    data = pad(data)
    backend = default_backend()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=backend)
    encryptor = cipher.encryptor()
    encrypted_data = encryptor.update(data) + encryptor.finalize()
    return encrypted_data


def decrypt_cbc(data, key, iv):
    """
    AES CBC解密

    :param data: 要解密的数据（bytes）
    :param key: 密钥（bytes）
    :param iv: 初始向量（bytes）
    :return: 解密后的数据
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
    文件加载XML解密

    :param xml: str or bytes - 要解密的XML内容
    :param method: 方法名
    :param inter_pwd: 用户口令userKey
    :param inter_skey: 加密密钥encryKey
    :param inter_asepyl: 密钥偏移量asepyl
    :param inter_key: 认证密钥infoInterKey
    :return: 解密后的文件内容（bytes）
    """
    inter_pwd = inter_pwd.encode("utf-8")
    inter_skey = inter_skey.encode("utf-8")
    inter_asepyl = inter_asepyl.encode("utf-8")
    inter_key = inter_key.encode("utf-8")

    xml_dict = xml2dict(__import__('xml.etree.ElementTree', fromlist=['ElementTree']).ElementTree(
        __import__('xml.etree.ElementTree', fromlist=['ElementTree']).fromstring(xml)).getroot())
    logger.info(xml_dict)

    command = xml_dict[method]["dataUpload"]
    commandHash = xml_dict[method]["dataHash"]
    compressionFormat = xml_dict[method]["compressionFormat"]
    hashAlgorithm = xml_dict[method]["hashAlgorithm"]
    encryptAlgorithm = xml_dict[method]["encryptAlgorithm"]

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


if __name__ == '__main__':
    # 测试代码
    test_xml = '<?xml version="1.0" encoding="utf-8"?><test>Hello World</test>'
    encrypted = encrypt_idc_command(test_xml)
    print("Encrypted:", encrypted)
