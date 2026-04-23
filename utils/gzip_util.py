#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2023/10/7 17:35
# @Author  : weihang
# @File    : gzip_util.py
# @Desc    : gzip压缩解压工具

import gzip


def compress_gzip(content):
    """
    gzip压缩数据

    Args:
        content: 要压缩的内容 (bytes)

    Returns:
        bytes: 压缩后的数据
    """
    compressed_data = gzip.compress(content)
    return compressed_data


def decompress_gzip(compressed_data):
    """
    gzip解压数据

    Args:
        compressed_data: 压缩后的数据 (bytes)

    Returns:
        bytes: 解压后的数据
    """
    content = gzip.decompress(compressed_data)
    return content
