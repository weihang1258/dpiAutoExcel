#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2023/10/7 17:35
# @Author  : weihang
# @File    : ini_handler.py
# @Desc    : INI配置文件处理器

import configparser
import io


class INIHandler:
    """INI 配置文件处理器。

    支持从多种来源加载 INI 配置：文件路径、字符串、字节流、文件对象。

    Attributes:
        config (configparser.ConfigParser): 内部使用的配置解析器

    Examples:
        >>> handler = INIHandler("config.ini")
        >>> value = handler.get("section", "option")
        >>> handler.set("section", "option", "new_value")
        >>> handler.save("config.ini")
    """

    def __init__(self, source):
        """初始化 INIHandler。

        Args:
            source (str or bytes or file-like): INI 配置来源，可以是：
                - 文件路径字符串
                - INI 内容字符串
                - 字节流
                - 文件对象
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
        """从文件路径加载 INI 配置。

        Args:
            file_path (str): INI 文件路径
        """
        self.config.read(file_path)

    def _load_from_string(self, ini_string):
        """从字符串加载 INI 配置。

        Args:
            ini_string (str): INI 格式的字符串内容
        """
        self.config.read_string(ini_string)

    def _load_from_bytes(self, ini_bytes):
        """从字节流加载 INI 配置。

        Args:
            ini_bytes (bytes): INI 格式的字节数据
        """
        ini_string = ini_bytes.decode('utf-8')
        self.config.read_string(ini_string)

    def _load_from_file_object(self, file_object):
        """从文件对象加载 INI 配置。

        Args:
            file_object: 文件对象，需支持 read 方法
        """
        self.config.read_file(file_object)

    def get(self, section, option, fallback=None):
        """获取配置项的值。

        Args:
            section (str): 配置段名称
            option (str): 配置项名称
            fallback: 当配置项不存在时返回的默认值

        Returns:
            str: 配置项的值
        """
        return self.config.get(section, option, fallback=fallback)

    def set(self, section, option, value):
        """设置配置项的值。

        Args:
            section (str): 配置段名称
            option (str): 配置项名称
            value: 配置项的值
        """
        if not self.config.has_section(section):
            self.config.add_section(section)
        self.config.set(section, option, value)

    def remove_option(self, section, option):
        """移除指定的配置项。

        Args:
            section (str): 配置段名称
            option (str): 配置项名称

        Returns:
            bool: 成功移除返回 True
        """
        return self.config.remove_option(section, option)

    def remove_section(self, section):
        """移除指定的配置段。

        Args:
            section (str): 配置段名称

        Returns:
            bool: 成功移除返回 True
        """
        return self.config.remove_section(section)

    def has_section(self, section):
        """检查配置段是否存在。

        Args:
            section (str): 配置段名称

        Returns:
            bool: 存在返回 True
        """
        return self.config.has_section(section)

    def has_option(self, section, option):
        """检查配置项是否存在。

        Args:
            section (str): 配置段名称
            option (str): 配置项名称

        Returns:
            bool: 存在返回 True
        """
        return self.config.has_option(section, option)

    def sections(self):
        """获取所有配置段名称。

        Returns:
            list: 配置段名称列表
        """
        return self.config.sections()

    def options(self, section):
        """获取指定配置段的所有选项名称。

        Args:
            section (str): 配置段名称

        Returns:
            list: 选项名称列表
        """
        return self.config.options(section)

    def save(self, file_path=None):
        """保存配置到文件。

        Args:
            file_path (str): 目标文件路径

        Raises:
            ValueError: 未提供 file_path 时抛出
        """
        if file_path is None:
            raise ValueError("file_path must be provided to save the INI content.")
        with open(file_path, 'w') as configfile:
            self.config.write(configfile)

    def to_string(self):
        """将配置转换为字符串。

        Returns:
            str: INI 格式的字符串内容
        """
        with io.StringIO() as string_io:
            self.config.write(string_io)
            return string_io.getvalue()

    def to_bytes(self):
        """将配置转换为字节流。

        Returns:
            bytes: UTF-8 编码的字节数据
        """
        return self.to_string().encode('utf-8')


def extract_field_paths(d, parent_key=''):
    """递归提取字典中的所有字段路径。

    Args:
        d: 当前遍历的字典或列表
        parent_key (str, optional): 当前字段的路径前缀，默认空字符串

    Returns:
        set: 所有字段路径的集合

    Examples:
        >>> d = {"a": {"b": 1}, "c": [1, 2]}
        >>> extract_field_paths(d)
        {'a.b', 'c[0]', 'c[1]'}
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
