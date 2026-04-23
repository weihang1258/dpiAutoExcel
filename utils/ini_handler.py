#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2023/10/7 17:35
# @Author  : weihang
# @File    : ini_handler.py
# @Desc    : INI配置文件处理器

import configparser
import io


class INIHandler:
    """INI配置文件处理器"""

    def __init__(self, source):
        """
        初始化INIHandler对象。

        参数:
        source (str or bytes or file-like object): INI文件的来源，可以是文件路径、字符串或字节流。
        """
        self.config = configparser.ConfigParser()

        if isinstance(source, str):
            # 检查是否为文件路径或纯字符串
            if '\n' in source or '=' in source:
                self._load_from_string(source)
            else:
                self._load_from_file(source)
        elif isinstance(source, bytes):
            self._load_from_bytes(source)
        elif hasattr(source, 'read'):
            self._load_from_file_object(source)
        else:
            raise ValueError("Unsupported source type. Must be str, bytes, or file-like object.")

    def _load_from_file(self, file_path):
        """从文件路径加载INI文件。"""
        self.config.read(file_path)

    def _load_from_string(self, ini_string):
        """从字符串加载INI文件。"""
        self.config.read_string(ini_string)

    def _load_from_bytes(self, ini_bytes):
        """从字节流加载INI文件。"""
        ini_string = ini_bytes.decode('utf-8')
        self.config.read_string(ini_string)

    def _load_from_file_object(self, file_object):
        """从文件对象加载INI文件。"""
        self.config.read_file(file_object)

    def get(self, section, option, fallback=None):
        """获取指定部分和选项的值。"""
        return self.config.get(section, option, fallback=fallback)

    def set(self, section, option, value):
        """设置指定部分和选项的值。"""
        if not self.config.has_section(section):
            self.config.add_section(section)
        self.config.set(section, option, value)

    def remove_option(self, section, option):
        """移除指定部分的选项。"""
        return self.config.remove_option(section, option)

    def remove_section(self, section):
        """移除指定的部分。"""
        return self.config.remove_section(section)

    def has_section(self, section):
        """检查是否存在指定的部分。"""
        return self.config.has_section(section)

    def has_option(self, section, option):
        """检查指定部分是否有特定选项。"""
        return self.config.has_option(section, option)

    def sections(self):
        """获取所有部分的列表。"""
        return self.config.sections()

    def options(self, section):
        """获取指定部分的所有选项。"""
        return self.config.options(section)

    def save(self, file_path=None):
        """将配置保存到文件。"""
        if file_path is None:
            raise ValueError("file_path must be provided to save the INI content.")
        with open(file_path, 'w') as configfile:
            self.config.write(configfile)

    def to_string(self):
        """将配置转换为字符串。"""
        with io.StringIO() as string_io:
            self.config.write(string_io)
            return string_io.getvalue()

    def to_bytes(self):
        """将配置转换为字节流。"""
        return self.to_string().encode('utf-8')


def extract_field_paths(d, parent_key=''):
    """
    提取字典中的所有字段路径。

    :param d: 当前字典
    :param parent_key: 当前字段的路径前缀
    :return: 字段路径的集合
    """
    paths = set()
    if isinstance(d, dict):
        for key, value in d.items():
            new_key = f"{parent_key}.{key}" if parent_key else key
            paths.update(extract_field_paths(value, new_key))
    elif isinstance(d, list):
        for index, item in enumerate(d):
            new_key = f"{parent_key}[{index}]"
            paths.update(extract_field_paths(item, new_key))
    else:
        paths.add(parent_key)
    return paths
