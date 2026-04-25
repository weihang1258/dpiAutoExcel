#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2023/5/26 16:53
# @Author  : weihang
# @File    : dpiinstall.py
# @Desc    : DPI 安装升级模块，支持全新安装、模式切换、版本升级等功能
"""DPI 安装升级模块。

支持全新安装、模式切换、版本升级等功能。
提供 DPI 设备固件升级、配置管理、日志处理等核心功能。
"""

import os
import re
import time
import json
import datetime
import logging

from core.result import result_deal
from core.excel_reader import parser_excel
from utils.common import gettime, setup_logging, get_base_dir
from device.dpi import Dpi
from io_handler.ftp_client import FTPclient
from utils.log_handler import DynamicFileHandler

# 导入需要添加 DynamicFileHandler 的模块
import utils.common as common
import device.dpi as dpi
import core.result as comm
import io_handler.ftp_client as ftp
import monitor.dpistat as dpistat
import device.socket_linux as socket_linux

# 添加日志打印
logger = setup_logging(log_file_path="log/install.log", logger_name="install")


def get_display_width(text):
    """计算字符串的实际显示宽度。

    中文字符占2个宽度，其他字符占1个宽度。

    Args:
        text: 要计算宽度的字符串

    Returns:
        int: 实际显示宽度
    """
    width = 0
    for char in text:
        # 判断是否为中文字符（Unicode范围）
        if '\u4e00' <= char <= '\u9fff':
            width += 2
        else:
            width += 1
    return width


def sanitize_case_name(case_name):
    """清理用例名称，移除或替换文件系统不支持的字段。

    Args:
        case_name: 原始用例名称

    Returns:
        str: 清理后的用例名称
    """
    # 替换特殊字符为下划线（包括换行符、制表符等）
    sanitized = re.sub(r'[<>:"/\\|?*\r\n\t]', '_', case_name)
    # 限制文件名长度（Windows 限制 255 字符，留出余量给前缀和后缀）
    if len(sanitized) > 200:
        sanitized = sanitized[:200]
    return sanitized


def print_case_separator(case_name, logger, log_file=None):
    """打印用例分隔符。

    Args:
        case_name: 用例名称
        logger: 日志记录器
        log_file: 日志文件路径（可选）
    """
    separator = "─" * 78
    logger.info(separator)
    logger.info(f"用例：{case_name}")
    logger.info(separator)

    # 如果提供了日志文件路径，显示在分隔符之后
    if log_file:
        logger.info(f"日志文件：{log_file}")


def print_stage_separator(stage_name, logger):
    """打印阶段分隔符。

    Args:
        stage_name: 阶段名称
        logger: 日志记录器
    """
    logger.info("")
    logger.info("╔" + "═" * 78 + "╗")

    # 计算阶段名称的显示宽度，确保居中显示
    text_width = get_display_width(stage_name)
    total_width = 78
    padding = (total_width - text_width) // 2

    logger.info("║" + " " * padding + stage_name + " " * (total_width - padding - text_width) + "║")
    logger.info("╚" + "═" * 78 + "╝")


def parse_version(version_str: str) -> tuple:
    """解析版本号字符串为可比较的元组。

    支持格式：
        - "1.0.6.2-4" -> (1, 0, 6, 2, 4, 0, 0)  # 最后一位 0 表示正式版
        - "1.0.6.0-4-patch-1" -> (1, 0, 6, 0, 4, 1, 1)  # 倒数第二位 1 表示 patch

    Args:
        version_str: 版本号字符串

    Returns:
        tuple: 可比较的元组
    """
    # 定义字母标识符权重
    letter_weights = {
        'alpha': -3,
        'beta': -2,
        'rc': -1,
        'patch': 1
    }

    # 分割版本号
    # 1.0.6.2-4 -> [1, 0, 6, 2, 4]
    # 1.0.6.0-4-patch-1 -> [1, 0, 6, 0, 4, 'patch', 1]
    parts = []
    for part in re.split(r'[.\-]', version_str):
        if part.isdigit():
            parts.append(int(part))
        elif part in letter_weights:
            parts.append(letter_weights[part])
        else:
            parts.append(0)  # 未知标识符

    # 补齐长度，确保所有版本号元组长度一致（最多7位）
    while len(parts) < 7:
        parts.append(0)

    return tuple(parts)


def compare_versions(v1: str, v2: str) -> int:
    """比较两个版本号。

    Args:
        v1: 版本号1
        v2: 版本号2

    Returns:
        int: -1 (v1 < v2), 0 (v1 == v2), 1 (v1 > v2)
    """
    parsed_v1 = parse_version(v1)
    parsed_v2 = parse_version(v2)

    if parsed_v1 < parsed_v2:
        return -1
    elif parsed_v1 > parsed_v2:
        return 1
    else:
        return 0


def get_highest_version(versions: list) -> str:
    """
    从版本号列表中提取最高版本

    Args:
        versions: 版本号列表

    Returns:
        最高版本号字符串
    """
    if not versions:
        return ""

    # 使用 sorted 排序，取最后一个（最高版本）
    sorted_versions = sorted(versions, key=lambda v: parse_version(v))
    return sorted_versions[-1]


def get_category_by_mode(mode: str) -> str:
    """
    根据 DPI 模式后缀映射到分类名称

    Args:
        mode: DPI 模式，如 "com_cmcc_is"、"com_cucc_isbns"，None 时抛出异常

    Returns:
        分类名称

    Raises:
        ValueError: 无法识别的模式或模式为 None
    """
    # 检查模式是否为 None
    if mode is None:
        raise ValueError("DPI 模式不能为 None，无法确定分类")

    # 内置映射表
    mode_to_category = {
        "is": "信息安全执行单元",
        "isbns": "信息安全执行单元",
        "bns": "网络安全执行单元",
        "ns": "网络安全执行单元",
        "bnsns": "网络安全执行单元",
        "ds": "数据安全执行单元"
    }

    # 提取模式后缀（最后一个下划线后的部分）
    # 例如：com_cmcc_is -> is
    #      com_cucc_isbns -> isbns
    mode_suffix = mode.split("_")[-1] if "_" in mode else mode

    category = mode_to_category.get(mode_suffix)
    if not category:
        raise ValueError(f"无法识别的模式后缀：{mode_suffix}，完整模式：{mode}")

    return category


def get_mod_switch_args(mode: str, mod_switch_version: str = "idc31") -> tuple:
    """
    根据模式获取 mod_switch 的 args 参数

    Args:
        mode: DPI 模式，如 "com_cmcc_is"、"com_cmcc_ds"
        mod_switch_version: mod_switch 版本，默认 "idc31"

    Returns:
        args 参数元组
    """
    if mode is None:
        return (mod_switch_version,)

    # 提取模式后缀
    mode_suffix = mode.split("_")[-1] if "_" in mode else mode

    # 如果是 ds 模式，返回 (mod_switch_version, "eu")
    if mode_suffix == "ds":
        return (mod_switch_version, "eu")
    else:
        return (mod_switch_version,)


def get_target_version(sheet_name: str, category: str, config: dict, mode: str, rdm_refreshed: dict) -> str:
    """
    获取目标版本号

    Args:
        sheet_name: 当前 sheet 名称
        category: 分类名称
        config: 配置字典
        mode: DPI 模式
        rdm_refreshed: 临时记忆字典，格式：{"信息安全执行单元": True, ...}

    Returns:
        版本号字符串
    """
    # 1. 构建配置参数名称
    config_key = f"{sheet_name}_target_version_{category}"

    # 2. 从配置中读取
    target_version = config.get(config_key, "")

    # 3. 如果配置为空，自动获取最高版本
    if not target_version:
        # 3.1 检查该分类是否已刷新过 RDM
        if rdm_refreshed.get(category, False):
            # 已刷新过，直接从 versions.json 读取
            logger.info(f"→ 分类 {category} 已刷新过 RDM，直接从 versions.json 读取最高版本")
        else:
            # 未刷新过，从 RDM 刷新 versions.json
            logger.info(f"→ 分类 {category} 首次遇到，从 RDM 刷新 versions.json")

            # 获取项目列表
            config_key_projects = f"{sheet_name}_projects_{category}"
            projects_str = config.get(config_key_projects, "")
            project_list = [p.strip() for p in projects_str.split("\n") if p.strip()]

            if not project_list:
                logger.error(f"✗ 未配置项目列表：{config_key_projects}")
                raise ValueError(f"未配置项目列表：{config_key_projects}")

            # 获取 RDM 配置
            rdm_base_url = config.get(f"{sheet_name}_base_url", "https://10.128.4.196:2000")
            rdm_username = config.get(f"{sheet_name}_rdm_username", "weihang")
            rdm_password = config.get(f"{sheet_name}_rdm_password", "12345678")

            # 执行刷新
            from utils.rdm_extractor import get_multiple_projects_release_paths, save_versions_to_json

            logger.info(f"→ 开始从 RDM 平台提取版本信息...")
            results = get_multiple_projects_release_paths(
                projects=project_list,
                base_url=rdm_base_url,
                username=rdm_username,
                password=rdm_password,
                headless=True,
                debug=False,
                verbose=True
            )

            logger.info(f"✓ 提取完成，共 {len(results)} 个项目")

            # 保存到 versions.json
            json_file = os.path.join(get_base_dir(), "versions.json")
            save_result = save_versions_to_json(
                version_data=results,
                category=category,
                json_file=json_file
            )

            logger.info(f"✓ versions.json 更新完成")

            # 标记为已刷新
            rdm_refreshed[category] = True

        # 3.2 从 versions.json 读取该分类下所有版本
        json_file = os.path.join(get_base_dir(), "versions.json")
        if not os.path.exists(json_file):
            logger.error(f"✗ versions.json 文件不存在")
            raise FileNotFoundError(f"versions.json 文件不存在")

        with open(json_file, "r", encoding="utf-8") as f:
            versions_data = json.load(f)

        # 3.3 提取该分类下所有版本号
        if category not in versions_data:
            logger.error(f"✗ versions.json 中未找到分类：{category}")
            raise ValueError(f"versions.json 中未找到分类：{category}")

        category_data = versions_data[category]

        # 收集所有版本号
        all_versions = []
        for project_name, project_versions in category_data.items():
            all_versions.extend(project_versions.keys())

        # 去重
        all_versions = list(set(all_versions))

        if not all_versions:
            logger.error(f"✗ 分类 {category} 下没有任何版本")
            raise ValueError(f"分类 {category} 下没有任何版本")

        # 3.4 提取最高版本号
        target_version = get_highest_version(all_versions)
        logger.info(f"✓ 自动获取最高版本：{target_version}")

    return target_version


def resolve_version_target(version: str, mode: str, sheet_name: str, config: dict, rdm_refreshed: dict) -> str:
    """
    解析版本号，如果是 target_version 则替换为实际版本号

    Args:
        version: 版本号（可能是 "target_version" 或具体版本号）
        mode: DPI 模式
        sheet_name: 当前 sheet 名称
        config: 配置字典
        rdm_refreshed: 临时记忆字典，记录每个分类是否已刷新过 RDM

    Returns:
        实际版本号
    """
    # 如果不是 target_version，直接返回
    if version != "target_version":
        return version

    # 根据 mode 判断分类
    category = get_category_by_mode(mode)

    # 获取目标版本（传入 rdm_refreshed）
    return get_target_version(sheet_name, category, config, mode, rdm_refreshed)


def get_ftp_path_from_json(
    json_file: str,
    category: str,
    version: str,
    project_list: list = None
) -> str:
    """
    从 JSON 文件中提取指定版本的 FTP 路径（仅匹配程序包）

    Args:
        json_file: JSON 文件路径
        category: 分类名称（如"信息安全执行单元"）
        version: 版本号（如"1.0.5.2-2"）
        project_list: 项目列表，用于限定搜索范围（可选）

    Returns:
        FTP 路径字符串（仅返回程序包路径），未找到则返回空字符串

    Raises:
        FileNotFoundError: JSON 文件不存在
        KeyError: 找不到对应分类
        ValueError: 找不到对应版本或程序包
    """
    # 1. 检查文件是否存在
    if not os.path.exists(json_file):
        raise FileNotFoundError(f"JSON 文件不存在：{json_file}")

    # 2. 读取 JSON 文件
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 3. 检查分类是否存在
    if category not in data:
        raise KeyError(f"JSON 中未找到分类：{category}")

    category_data = data[category]

    # 4. 确定搜索范围
    if project_list:
        # 如果指定了项目列表，只在这些项目中搜索
        search_projects = {p: category_data[p] for p in project_list if p in category_data}
    else:
        # 否则搜索该分类下的所有项目
        search_projects = category_data

    # 5. 遍历项目查找版本
    for project_name, versions in search_projects.items():
        if version in versions:
            paths = versions[version]
            if not paths or len(paths) == 0:
                continue

            # 6. 仅匹配程序包（ACT-DPI-ISE-、ACT-DPI-NSE-、ACT-DPI-DSE-、ACT-DPI-EU- 前缀）
            # 程序包格式：ACT-DPI-ISE-1.0.4.8-3_20250320164434.tar.gz
            #           ACT-DPI-EU-1.0.6.2-4_20260331134807.tar.gz

            # 定义程序包前缀（仅这2种）
            program_package_prefixes = [
                "ACT-DPI-ISE-",
                "ACT-DPI-NSE-",
                "ACT-DPI-DSE-",
                "ACT-DPI-EU-"
            ]

            # 匹配程序包
            for path in paths:
                # 提取文件名
                filename = os.path.basename(path)

                # 检查是否匹配程序包前缀 + 版本号
                for prefix in program_package_prefixes:
                    # 构建匹配模式：前缀 + 版本号
                    # 例如：ACT-DPI-ISE-1.0.4.8-3
                    pattern = f"{prefix}{version}"
                    if filename.startswith(pattern):
                        logger.info(f"  → 匹配到程序包：{filename}")
                        return path

            # 7. 未找到程序包，返回空字符串
            logger.warning(f"  ⚠ 版本 {version} 未找到程序包（仅支持 ACT-DPI-ISE-、ACT-DPI-NSE-、ACT-DPI-DSE-和 ACT-DPI-EU- 前缀）")
            return ""

    # 8. 未找到版本
    raise ValueError(f"在分类 {category} 中未找到版本 {version}")


def auto_update_json_and_get_path(
    json_file: str,
    category: str,
    version: str,
    base_url: str,
    username: str,
    password: str,
    project_list: list = None
) -> str:
    """
    自动更新 JSON 文件并获取 FTP 路径

    当 JSON 中找不到版本时，自动执行多项目提取并更新 JSON

    Args:
        json_file: JSON 文件路径
        category: 分类名称
        version: 版本号
        base_url: RDM 平台地址
        username: 用户名
        password: 密码
        project_list: 项目列表（可选，为 None 时自动从 JSON 中读取该分类下所有项目）

    Returns:
        FTP 路径字符串

    Raises:
        RuntimeError: 更新后仍未找到版本
    """
    logger.info("")
    logger.info("┌" + "─" * 78 + "┐")
    text = "自动更新 JSON 版本数据"
    text_width = get_display_width(text)
    right_spaces = 78 - 25 - text_width
    logger.info("│" + " " * 25 + text + " " * right_spaces + "│")
    logger.info("└" + "─" * 78 + "┘")
    logger.info(f"→ 版本 {version} 未在 JSON 中找到，开始自动更新...")

    # 如果未指定项目列表，从 JSON 中读取该分类下所有项目
    if project_list is None:
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if category in data:
                project_list = list(data[category].keys())
                logger.info(f"→ 自动获取分类 {category} 下的所有项目：{project_list}")
            else:
                raise RuntimeError(f"JSON 中未找到分类：{category}")
        except FileNotFoundError:
            raise RuntimeError(f"JSON 文件不存在：{json_file}")
    else:
        logger.info(f"→ 目标项目列表：{project_list}")

    # 1. 执行多项目提取
    from utils.rdm_extractor import get_multiple_projects_release_paths, save_versions_to_json

    logger.info("→ 开始执行多项目提取...")
    results = get_multiple_projects_release_paths(
        projects=project_list,
        base_url=base_url,
        username=username,
        password=password,
        headless=True,
        debug=False,
        verbose=True
    )

    logger.info(f"✓ 多项目提取完成，共 {len(results)} 个项目")

    # 2. 保存到 JSON 文件
    logger.info("→ 保存数据到 JSON 文件...")
    save_result = save_versions_to_json(
        version_data=results,
        category=category,
        json_file=json_file
    )

    logger.info(f"✓ JSON 更新完成：{save_result['status']}")
    logger.info(f"  → 新增版本：{save_result['summary']['new_count']}")
    logger.info(f"  → 更新版本：{save_result['summary']['updated_count']}")
    logger.info(f"  → 总版本数：{save_result['summary']['total_versions']}")

    # 3. 再次尝试获取路径（搜索该分类下所有项目）
    try:
        ftp_path = get_ftp_path_from_json(
            json_file=json_file,
            category=category,
            version=version
        )
        logger.info(f"✓ 成功获取版本 {version} 的 FTP 路径")
        return ftp_path
    except ValueError:
        # 更新后仍未找到
        logger.error(f"✗ 自动更新 JSON 后仍未找到版本 {version}")
        raise RuntimeError(
            f"自动更新 JSON 后仍未找到版本 {version}\n"
            f"分类：{category}\n"
            f"请检查 RDM 平台是否存在该版本"
        )


def dpi_install(
    dpiserver: Dpi,
    ftphost: str,
    ftppath: str,
    dpiversion: str = None,
    scanpktpath: bool = None,
    mode: str = None,
    pcicfg: dict = None,
    modified_param: dict = None,
    mod_switch_version: str = "idc31",
    timeout: int = 600,
    user: str = "weihang",
    password: str = "12345678",
    upms: bool = False,
    dpipath_bak: str = None,
    xsa_modify_dict: dict = None,
    use_upgrade_system: bool = False,
    upgrade_start_timeout: int = 300,
    upgrade_complete_timeout: int = 1200
) -> dict:
    """
    DPI 安装/升级主函数

    根据参数执行 DPI 程序的全新安装或升级操作，支持以下功能：
    1. 全新安装：从 FTP 下载安装包，解压并安装 DPI 程序
    2. 版本升级：在现有 DPI 基础上执行升级脚本

    安装包结构说明：
    - 旧版本（ACT-DPI-ISE-）三层压缩：
      第一层：ACT-DPI-ISE-1.0.5.2-2_20250427161928.tar.gz（带时间戳的外层压缩包）
      第二层：ACT-DPI-ISE-1.0.5.2-2.tar.gz（版本号命名的内层压缩包，使用 unzip 解压）
      第三层：ACT-DPI-ISE-1.0.5.2-2/（最终安装目录，包含 install.sh）

    - 新版本（ACT-DPI-EU-）两层压缩：
      第一层：ACT-DPI-EU-1.0.6.2-4_20260331134807.tar.gz（带时间戳的外层压缩包）
      第二层：ALL-BOOT-ALL-ALL-1.0.6.2-4_20260331134807.tar.gz（使用 tar 解压）
      脚本位置：ALL-BOOT-ALL-ALL-1.0.6.2-4_20260331134807/（包含 install.sh 和 upms_install.sh）

    参数说明:
        :param dpiserver: DPI 服务器对象，Dpi 类实例，用于执行远程操作
        :param ftphost: FTP 服务器地址，格式：IP 或 IP:端口，如 "172.31.128.180"
        :param ftppath: FTP 服务器上的安装包完整路径，
                        如："/02测试/PD240200354_信息安全执行单元V1.0.5.0（信安EU）/V1.0.5.2/ACT-DPI-ISE-1.0.5.2-2_20250427161928.tar.gz"
        :param dpiversion: DPI 版本号，如 "V1.0.5.2-2"，升级时用于校验版本
        :param scanpktpath: 是否扫描并复用已存在的安装包，True 表示优先使用已有安装包
        :param mode: DPI 运行模式，如：
                     - "com_cmcc_is"：中国移动信安模式
                     - "com_cucc_isbns"：中国联通信安模式
                     - "com_ctcc_isbns"：中国电信信安模式
        :param pcicfg: PCI 配置信息，用于配置网卡，格式如：
                       {"raw_port": "0", "src_mac": "00:00:00:00:00:00",
                        "dst_mac": "00:00:00:00:00:00", "pci_list": ["0000:03:00.0"]}
        :param modified_param: mod_switch.sh 开关参数，如：
                               {"wlan_switch": "1", "oversea_switch": "1"}
        :param mod_switch_version: mod_switch 版本，如 "idc31"、"ircs20"
        :param timeout: 等待 DPI 启动的超时时间，单位秒，默认 600s
        :param user: FTP 登录用户名
        :param password: FTP 登录密码
        :param upms: 是否执行升级操作，False=全新安装，True=升级
        :param dpipath_bak: DPI 备份目录路径，如 "/home/dpibak"
        :param xsa_modify_dict: xsa.json 预修改配置项，如：
                                {"dpi.vlan_multiplexing": 2, "flow.ipv4_hash_ksize": 302}

    返回值:
        :return: 安装/升级结果字典
                 - 全新安装：返回 mod_switch 结果 {"result": bool, "mark": list}
                 - 升级：返回 upms_install 结果 {"result": bool, "mark": list}

    异常:
        :raises RuntimeError: 当 FTP 上找不到安装包时抛出
    """
    # ==================== 版本解压配置 ====================
    VERSION_EXTRACT_CONFIG = {
        "ACT-DPI-EU-": {
            "version": "v2",
            "layers": 2,
            "layer2_method": "tar",
            "layer2_pattern": "ALL-BOOT-ALL-ALL-*.tar.gz",  # 第二层文件匹配模式
            "script_location": {
                "install": 2,    # 安装脚本在第2层
                "upgrade": 2     # 升级脚本在第2层
            }
        },
        "ACT-DPI-ISE-": {
            "version": "v1",
            "layers": 3,
            "layer2_method": "unzip",
            "layer2_pattern": "*.tar.gz",  # 第二层文件匹配模式
            "layer3_method": "tar",
            "script_location": {
                "install": 3,    # 安装脚本在第3层
                "upgrade": 2     # 升级脚本在第2层
            }
        },
        "ACT-DPI-NSE-": {
            "version": "v1",
            "layers": 3,
            "layer2_method": "unzip",
            "layer2_pattern": "*.tar.gz",  # 第二层文件匹配模式
            "layer3_method": "tar",
            "script_location": {
                "install": 3,    # 安装脚本在第3层
                "upgrade": 2     # 升级脚本在第2层
            }
        },
        "ACT-DPI-DSE-": {
            "version": "v1",
            "layers": 3,
            "layer2_method": "unzip",
            "layer2_pattern": "*.tar.gz",  # 第二层文件匹配模式
            "layer3_method": "tar",
            "script_location": {
                "install": 3,    # 安装脚本在第3层
                "upgrade": 2     # 升级脚本在第2层
            }
        }
    }

    # ==================== 第一阶段：验证安装包 ====================
    print_stage_separator("第一阶段：验证 FTP 安装包", logger)

    # 连接 FTP 服务器并验证安装包是否存在
    logger.info(f"→ 连接 FTP 服务器：{ftphost}")
    ftp = FTPclient(host=ftphost, user=user, passwd=password)

    logger.info(f"→ 验证安装包路径：{ftppath}")
    if not ftp.file_exists(ftppath):
        logger.error(f"✗ 未找到安装包：{ftppath}")
        raise RuntimeError(f"未找到安装包：{ftppath}")
    logger.info(f"✓ 安装包验证通过")

    # ==================== 第二阶段：下载安装包 ====================
    print_stage_separator("第二阶段：下载安装包", logger)

    # 提取安装包文件名和下载路径
    pktname = os.path.basename(ftppath)  # 如：ACT-DPI-ISE-1.0.5.2-2_20250427161928.tar.gz
    pktremotepath = "ftp://" + ftphost + ftppath
    pktlocalpath = "/home/" + pktname  # 目标服务器上的存放路径

    logger.info(f"→ 安装包名称：{pktname}")
    logger.info(f"→ 远程路径：{pktremotepath}")
    logger.info(f"→ 本地存放路径：{pktlocalpath}")

    # 判断是否需要下载安装包
    downloadflag = True
    if scanpktpath:
        # 扫描目标服务器上是否已存在同名安装包
        cmd = f"find / -type f -name {pktname} -print -quit"
        logger.info(f"→ 扫描目标服务器是否存在可用安装包...")
        response = dpiserver.cmd(cmd).strip()

        if response:
            # 找到已存在的安装包，直接使用
            pktlocalpath = response
            logger.info(f"✓ 发现可用安装包，跳过下载：{pktlocalpath}")
            downloadflag = False
        else:
            logger.info("→ 未发现可用安装包，需要从 FTP 下载")

    # 执行下载操作
    if downloadflag:
        logger.info(f"→ 开始下载安装包...")
        dpiserver.wget_ftp(
            remotepath=pktremotepath,
            localpath=pktlocalpath,
            user=user,
            password=password,
            overwrite=True
        )
        logger.info("✓ 安装包下载完成")

    # ==================== 第三阶段：解压安装包 ====================
    # 获取版本配置
    version_config = None
    for prefix, config in VERSION_EXTRACT_CONFIG.items():
        if pktname.startswith(prefix):
            version_config = config
            break

    if version_config is None:
        raise RuntimeError(f"未知的安装包前缀：{pktname}")

    print_stage_separator(f"第三阶段：解压安装包（{version_config['layers']}层压缩）", logger)
    logger.info(f"→ 检测到版本：{version_config['version']}，解压方式：{version_config['layer2_method']}")

    # ---------- 解压第一层：外层压缩包（带时间戳） ----------
    logger.info(f"→ [1/{version_config['layers']}] 解压第一层压缩包")
    outdir1 = os.path.dirname(pktlocalpath) + "/" + pktname.rstrip('.tar.gz')

    if scanpktpath and dpiserver.isdir(outdir1):
        logger.info(f"  ✓ 第一层已解压，跳过：{outdir1}")
    else:
        logger.info(f"  → 解压到：{outdir1}")
        dpiserver.unzip(
            file=pktlocalpath,
            outdir=outdir1,
            passwd="GeUpms@1995",
            overwrite=True,
            bufsize=1024
        )
        logger.info(f"  ✓ 第一层解压完成")

    # ---------- 解压第二层：内层压缩包 ----------
    # 根据配置的匹配模式查找第二层压缩包
    pattern = version_config['layer2_pattern']
    tmpname = dpiserver.listdir(path=outdir1, args=f'-name "{pattern}"')[0]
    lf = outdir1 + "/" + tmpname
    logger.info(f"→ [2/{version_config['layers']}] 解压第二层压缩包：{tmpname}")

    outdir2 = outdir1 + "/" + tmpname.rstrip(".tar.gz")

    if scanpktpath and dpiserver.isdir(outdir2):
        logger.info(f"  ✓ 第二层已解压，跳过：{outdir2}")
    else:
        # 根据版本配置选择解压方式
        if version_config['layer2_method'] == 'tar':
            # 新版本：使用 tar 解压
            logger.info(f"  → 使用 tar 解压到：{outdir1}")
            cmd = f"tar -xzf {lf} -C {outdir1}"
            logger.info(f"  → 执行命令：{cmd}")
            dpiserver.cmd(cmd)
            logger.info(f"  ✓ 第二层解压完成")
        else:
            # 旧版本：使用 unzip 解压
            logger.info(f"  → 使用 unzip 解压到：{outdir2}")
            dpiserver.unzip(
                file=lf,
                outdir=outdir1,
                passwd="GeUpms@1995",
                overwrite=True,
                bufsize=1024
            )
            logger.info(f"  ✓ 第二层解压完成")

    # 定位升级脚本路径（根据配置）
    upgrade_script_layer = version_config['script_location']['upgrade']
    if upgrade_script_layer == 2:
        upms_install_file = f"{outdir2}/upms_install.sh"
    else:
        upms_install_file = f"{outdir3}/upms_install.sh"
    logger.info(f"→ 升级脚本路径：{upms_install_file}")

    # ==================== 第四阶段：执行安装/升级 ====================
    action = '升级' if upms else '全新安装'
    print_stage_separator(f"第四阶段：执行{action}", logger)

    if not upms:
        # ==================== 全新安装流程 ====================
        logger.info("→ 执行全新安装流程...")

        # 根据配置判断是否需要解压第三层
        install_script_layer = version_config['script_location']['install']

        if install_script_layer == 3:
            # 旧版本：需要解压第三层
            tmpname = dpiserver.listdir(path=outdir2, args='-name "*.tar.gz"')[0]
            logger.info(f"→ [3/{version_config['layers']}] 解压第三层压缩包：{tmpname}")

            outdir3 = outdir2 + "/" + tmpname.rstrip(".tar.gz")

            if scanpktpath and dpiserver.isdir(outdir3):
                logger.info(f"  ✓ 第三层已解压，跳过：{outdir3}")
            else:
                # 使用 tar 命令解压（非 zip 格式）
                cmd = f"tar -xzf {tmpname}"
                logger.info(f"  → 执行命令：{cmd}")
                logger.info(f"  → 工作目录：{outdir2}")
                dpiserver.cmd(cmd, cwd=outdir2)
                logger.info(f"  ✓ 第三层解压完成")

            # 定位安装脚本
            install_file = f"{outdir3}/install.sh"
            logger.info(f"→ 安装脚本路径：{install_file}")
        else:
            # 新版本：脚本在第2层，无需解压第三层
            install_file = f"{outdir2}/install.sh"
            logger.info(f"→ 安装脚本路径：{install_file}")

        # ---------- 执行安装 ----------
        logger.info("→ 开始执行 install.sh 安装脚本...")
        dpiserver.install(dpipath=install_file, dpipath_bak=dpipath_bak)
        logger.info("✓ install.sh 执行完成")

        # ---------- 执行模式切换 ----------
        logger.info(f"→ 开始执行模式切换")
        logger.info(f"  → 目标模式：{mode}")
        logger.info(f"  → PCI 配置：{pcicfg}")
        logger.info(f"  → 开关参数：{modified_param}")
        logger.info(f"  → 超时时间：{timeout}s")

        # 根据模式获取 args 参数
        mod_switch_args = get_mod_switch_args(mode, mod_switch_version)
        logger.info(f"  → 切换参数：{mod_switch_args}")

        result = dpiserver.mod_switch(
            mode=mode,
            args=mod_switch_args,
            modified_param=modified_param,
            force=False,
            pcicfg=pcicfg,
            timeout=timeout
        )
        logger.info(f"✓ 模式切换完成，结果：{result}")

    else:
        # ==================== 升级流程 ====================
        logger.info("→ 执行升级流程...")
        logger.info(f"  → 目标版本：{dpiversion}")
        logger.info(f"  → xsa.json 修改项：{xsa_modify_dict}")
        logger.info(f"  → 备份目录：{dpipath_bak}")

        result = dpiserver.upms_install(
            dpiversion=dpiversion,
            path=upms_install_file,
            dpipath_bak=dpipath_bak,
            rmvarbak=False,
            xsa_modify_dict=xsa_modify_dict,
            timeout=timeout,
            use_upgrade_system=use_upgrade_system,
            upgrade_start_timeout=upgrade_start_timeout,
            upgrade_complete_timeout=upgrade_complete_timeout
        )
        logger.info(f"✓ 升级完成，结果：{result}")

    # ==================== 第五阶段：输出最终状态 ====================
    print_stage_separator("第五阶段：输出最终状态", logger)

    logger.info(f"→ PCI 信息：{dpiserver.get_pcicfg()}")
    logger.info(f"→ DPI 模式：{dpiserver.get_dpimode()}")
    logger.info(f"→ DPI 版本：{dpiserver.get_dpiversion()}")
    logger.info("")

    return result


def install(p_excel: dict, sheets: tuple = ("install",), path: str = "用例", newpath: str = None, versions_json: str = None, mod_switch_version: str = "idc31", session_id: str = None, log_strategy: str = "by_case") -> None:
    """
    基于 Excel 用例执行批量安装/升级测试

    该函数从 Excel 文件中读取测试用例，按用例配置执行以下操作：
    1. 全新安装：直接安装指定版本的 DPI
    2. 模式切换：先安装源版本，再切换到目标模式
    3. 升级测试：先安装源版本，再升级到目标版本

    Excel 用例格式说明:
        - 执行状态：1 表示执行，其他值表示跳过
        - 安装类型：全新安装、模式切换、升级
        - dpiversion_s：源版本号（模式切换/升级时使用）
        - dpiversion_d：目标版本号
        - dpimode_s：源模式
        - dpimode_d：目标模式
        - 优先使用备份dpi_s：是否优先使用备份的源版本 DPI
        - 优先使用存在安装包_s/d：是否优先使用已存在的安装包

    参数说明:
        :param p_excel: Excel 解析后的数据字典，包含以下键：
                        - sheet_name2cases：每个 sheet 的用例数据
                        - sheet_name2head2col：每个 sheet 的列头映射
                        - config：配置信息
        :param sheets: 要执行的 sheet 名称列表，默认 ("install",)
        :param path: Excel 文件路径
        :param newpath: 结果保存路径，None 则自动生成
        :param versions_json: JSON 版本文件路径，默认 "versions.json"
        :param session_id: 会话ID，格式 YYYYMMDDHHMMSS
        :param log_strategy: 日志拆分策略，"by_case" 或 "by_sheet"

    返回值:
        :return: None，结果直接写入 Excel 文件

    配置项说明（Excel config sheet）:
        - ip_xsa：DPI 服务器 IP
        - port_xsa：DPI 服务器端口
        - {sheet}_base_url：RDM 平台地址
        - {sheet}_install_rdm_username：RDM 平台用户名
        - {sheet}_install_rdm_password：RDM 平台密码
        - {sheet}_install_ftp_username：FTP 登录用户名（不填默认使用 RDM 用户名）
        - {sheet}_install_ftp_password：FTP 登录密码（不填默认使用 RDM 密码）
        - {sheet}_paths_scan_dpi：DPI 备份扫描路径，多个路径用逗号分隔
        - {sheet}_path_dpibak：DPI 备份存放目录
        - {sheet}_pcis：PCI 列表，多个用逗号分隔
        - {sheet}_projects_{category}：各分类对应的项目列表，多个项目用换行符分隔
    """
    # ==================== 初始化 ====================
    # 检查 session_id，如果为空则自动生成
    if session_id is None:
        session_id = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        logger.warning(f"session_id 为空，自动生成：{session_id}")

    # 如果 versions_json 为 None，使用 exe 目录下的 versions.json
    if versions_json is None:
        versions_json = os.path.join(get_base_dir(), "versions.json")

    # 解析 Excel 数据
    sheet_name2cases = p_excel["sheet_name2cases"]
    sheet_name2head2col = p_excel["sheet_name2head2col"]
    config = p_excel["config"]

    # 新增：临时记忆字典，记录每个分类是否已刷新过 RDM
    rdm_refreshed = {}  # 格式：{"信息安全执行单元": True, "网络安全执行单元": False, ...}

    # 建立 DPI 服务器连接
    socket_xsa = (config["ip_xsa"], config["port_xsa"])
    logger.info(f"连接 DPI 服务器：{socket_xsa}")
    xsa = Dpi(socket_xsa)

    # ==================== 遍历执行用例 ====================
    counter = 0

    for sheet_name in sheets:
        # ==================== 创建 DynamicFileHandler ====================
        modules = [
            common, dpi, comm, ftp,
            dpistat, socket_linux
        ]

        # 创建 DynamicFileHandler
        dynamic_handler = DynamicFileHandler(log_dir="log", level=logging.DEBUG)

        # 添加到所有模块的 logger (包括当前模块 dpiinstall)
        # 先移除原有的 FileHandler，避免重复输出到文件
        for module in modules:
            if hasattr(module, 'logger'):
                # 移除原有的 FileHandler（保留 ConsoleHandler）
                for handler in module.logger.handlers[:]:
                    if isinstance(handler, logging.FileHandler):
                        module.logger.removeHandler(handler)
                # 添加 DynamicFileHandler
                module.logger.addHandler(dynamic_handler)

        # 为当前模块也添加 handler（同样先移除原有的 FileHandler）
        for handler in logger.handlers[:]:
            if isinstance(handler, logging.FileHandler):
                logger.removeHandler(handler)
        logger.addHandler(dynamic_handler)

        try:
            # 根据策略创建初始日志文件
            if log_strategy == "by_sheet":
                log_file = f"{session_id}_{sheet_name}.log"
                dynamic_handler.switch_file(log_file)
                logger.info(f"日志文件：{log_file}")

            # ==================== Sheet 开始标识 ====================
            # 计算字符串的实际显示宽度（中文字符占2个宽度）
            text = f"执行 Sheet：{sheet_name}"
            text_width = get_display_width(text)
            left_spaces = 30
            right_spaces = 78 - left_spaces - text_width

            logger.info("")
            logger.info("╔" + "═" * 78 + "╗")
            logger.info("║" + " " * left_spaces + text + " " * right_spaces + "║")
            logger.info("╚" + "═" * 78 + "╝")

            # 读取 FTP 相关配置
            rdm_base_url = config.get(f"{sheet_name}_base_url", "https://10.128.4.196:2000")
            rdm_username = config.get(f"{sheet_name}_rdm_username", "weihang")
            rdm_password = config.get(f"{sheet_name}_rdm_password", "12345678")
            ftp_username = config.get(f"{sheet_name}_ftp_username", rdm_username)
            ftp_password = config.get(f"{sheet_name}_ftp_password", rdm_password)
            if not ftp_username:
                ftp_username = rdm_username
                ftp_password = rdm_password

            logger.info(f"→ RDM 配置：")
            logger.info(f"  → 平台地址：{rdm_base_url}")
            logger.info(f"  → 用户名：{rdm_username}")
            logger.info(f"→ FTP 配置：")
            logger.info(f"  → 用户名：{ftp_username}")

            # 读取配置项
            path_list_scan_dpi = list(
                map(lambda x: x.strip(), config.get(f"{sheet_name}_paths_scan_dpi", "").strip().split(","))
            )
            path_dpibak = config.get(f"{sheet_name}_path_dpibak", "/home/dpibak")
            pcicfg = {
                "pci_list": list(
                    map(lambda x: x.strip(), config.get(f"{sheet_name}_pcis", "").strip().split(","))
                )
            }

            # 读取升级系统配置
            use_upgrade_system = config.get(f"{sheet_name}_use_upgrade_system", "False").strip().lower() == "true"
            upgrade_start_timeout = int(config.get(f"{sheet_name}_upgrade_start_timeout", "300"))
            upgrade_complete_timeout = int(config.get(f"{sheet_name}_upgrade_complete_timeout", "1200"))

            logger.info(f"→ 配置信息：")
            logger.info(f"  → DPI 备份扫描路径：{path_list_scan_dpi}")
            logger.info(f"  → DPI 备份存放目录：{path_dpibak}")
            logger.info(f"  → PCI 配置：{pcicfg}")

            # 定义统一的路径获取函数
            def get_ftp_path_with_auto_update(version: str, mode: str) -> str:
                """
                获取 FTP 路径，支持自动更新

                Args:
                    version: 版本号
                    mode: DPI 模式

                Returns:
                    FTP 路径
                """
                # 1. 根据模式获取分类
                try:
                    category = get_category_by_mode(mode)
                    logger.info(f"→ 版本 {version} 模式 {mode} 映射到分类：{category}")
                except ValueError as e:
                    raise RuntimeError(f"无法确定分类：{e}")

                # 2. 直接从 JSON 获取路径（搜索该分类下所有项目）
                try:
                    ftp_path = get_ftp_path_from_json(
                        json_file=versions_json,
                        category=category,
                        version=version
                    )
                    logger.info(f"✓ 从 JSON 获取到版本 {version} 的路径")
                    return ftp_path

                except (FileNotFoundError, KeyError, ValueError) as e:
                    # 3. 未找到，执行自动更新
                    logger.warning(f"⚠ JSON 中未找到版本 {version}：{e}")

                    try:
                        ftp_path = auto_update_json_and_get_path(
                            json_file=versions_json,
                            category=category,
                            version=version,
                            base_url=rdm_base_url,
                            username=rdm_username,
                            password=rdm_password
                        )
                        return ftp_path

                    except RuntimeError as e:
                        # 5. 更新后仍未找到，记录错误并跳过当前 sheet
                        logger.error(f"✗ 无法获取版本 {version} 的 FTP 路径：{e}")
                        raise  # 向上抛出，由外层捕获并跳过 sheet

            # 获取当前 sheet 的所有用例
            cases = sheet_name2cases[sheet_name]

            # 遍历每个用例组
            for case_name, case_list in cases.items():
                # 跳过空用例名或未标记执行的用例
                if not case_name or str(case_list[0]["执行状态"]) not in ("1", "1.0"):
                    continue

                # 遍历用例组中的每个用例
                for i in range(len(case_list)):
                    case = case_list[i]
                    counter += 1

                    # 处理路径（第一次使用原路径，后续使用新路径）
                    if counter != 1:
                        path = newpath

                    # ==================== 日志文件切换 ====================
                    # 如果策略是按用例拆分，切换到新的日志文件
                    log_file = None
                    if log_strategy == "by_case":
                        safe_case_name = sanitize_case_name(case_name)
                        log_file = f"{session_id}_{sheet_name}_{safe_case_name}.log"
                        dynamic_handler.switch_file(log_file)

                    # 打印用例分隔符
                    print_case_separator(case_name, logger, log_file)

                    # ==================== 解析用例参数 ====================
                    result = "Pass"
                    mark = list()
                    tmp_list = list()  # 存储写入 Excel 的结果数据

                    # 安装类型：全新安装、模式切换、升级
                    installtype = case.get("安装类型", "")

                    # 是否优先使用备份
                    prefer_backup_dpi_s = case.get("优先使用备份dpi_s", "") == "是"
                    prefer_backup_pkt_s = case.get("优先使用存在安装包_s", "") == "是"
                    prefer_backup_pkt_d = case.get("优先使用存在安装包_d", "") == "是"

                    # 版本和模式配置
                    dpiversion_s = case.get("dpiversion_s", "")
                    dpiversion_d = case.get("dpiversion_d", "")
                    dpimode_s = case.get("dpimode_s", "")
                    dpimode_d = case.get("dpimode_d", "")

                    # 处理 target_version 替换
                    # 处理 dpiversion_s
                    if dpiversion_s == "target_version":
                        # 优先使用 dpimode_s，如果为空则使用 dpimode_d
                        mode_for_version_s = dpimode_s if dpimode_s else dpimode_d
                        if mode_for_version_s:
                            try:
                                dpiversion_s = resolve_version_target(
                                    dpiversion_s, mode_for_version_s, sheet_name, config, rdm_refreshed
                                )
                                logger.info(f"→ dpiversion_s 替换为：{dpiversion_s}")
                            except Exception as e:
                                logger.error(f"✗ 无法获取目标版本：{e}")
                                mark.append(f"无法获取目标版本：{str(e)}")
                                result_deal(
                                    xls=path,
                                    sheet_index=sheet_name,
                                    result_list=tmp_list,
                                    row=case["row"] + i,
                                    head2col=sheet_name2head2col[sheet_name],
                                    mark=mark,
                                    only_write=False,
                                    newpath=newpath
                                )
                                continue
                        else:
                            logger.error("✗ 无法确定版本分类：dpimode_s 和 dpimode_d 都为空")
                            mark.append("无法确定版本分类：dpimode_s 和 dpimode_d 都为空")
                            result_deal(
                                xls=path,
                                sheet_index=sheet_name,
                                result_list=tmp_list,
                                row=case["row"] + i,
                                head2col=sheet_name2head2col[sheet_name],
                                mark=mark,
                                only_write=False,
                                newpath=newpath
                            )
                            continue

                    # 处理 dpiversion_d
                    if dpiversion_d == "target_version":
                        # 优先使用 dpimode_d，如果为空则使用 dpimode_s
                        mode_for_version_d = dpimode_d if dpimode_d else dpimode_s
                        if mode_for_version_d:
                            try:
                                dpiversion_d = resolve_version_target(
                                    dpiversion_d, mode_for_version_d, sheet_name, config, rdm_refreshed
                                )
                                logger.info(f"→ dpiversion_d 替换为：{dpiversion_d}")
                            except Exception as e:
                                logger.error(f"✗ 无法获取目标版本：{e}")
                                mark.append(f"无法获取目标版本：{str(e)}")
                                result_deal(
                                    xls=path,
                                    sheet_index=sheet_name,
                                    result_list=tmp_list,
                                    row=case["row"] + i,
                                    head2col=sheet_name2head2col[sheet_name],
                                    mark=mark,
                                    only_write=False,
                                    newpath=newpath
                                )
                                continue
                        else:
                            logger.error("✗ 无法确定版本分类：dpimode_d 和 dpimode_s 都为空")
                            mark.append("无法确定版本分类：dpimode_d 和 dpimode_s 都为空")
                            result_deal(
                                xls=path,
                                sheet_index=sheet_name,
                                result_list=tmp_list,
                                row=case["row"] + i,
                                head2col=sheet_name2head2col[sheet_name],
                                mark=mark,
                                only_write=False,
                                newpath=newpath
                            )
                            continue

                    # 解析 xsa.json 预修改配置
                    # 格式示例："dpi.vlan_multiplexing": 2, "flow.ipv4_hash_ksize": 302
                    tmp = case.get("xsa.json预修改", "") or ""
                    xsa_modify_dict = dict(
                        map(
                            lambda x: (eval(x[0]), eval(x[1])),
                            re.findall(r'(".*?")\s*:\s*("(?:.*?)"|[^",\s]+)', tmp)
                        )
                    )

                    # 解析源版本开关参数
                    tmp = case.get("switch_param_s", "") or ""
                    switch_param_s_dict = dict(
                        map(
                            lambda x: (eval(x[0]), eval(x[1])),
                            re.findall(r'(".*?")\s*:\s*("(?:.*?)"|[^",\s]+)', tmp)
                        )
                    )

                    # 解析目标版本开关参数
                    tmp = case.get("switch_param_d", "") or ""
                    switch_param_d_dict = dict(
                        map(
                            lambda x: (eval(x[0]), eval(x[1])),
                            re.findall(r'(".*?")\s*:\s*("(?:.*?)"|[^",\s]+)', tmp)
                        )
                    )

                    logger.info(f"→ 用例参数：")
                    logger.info(f"  → 安装类型：{installtype}")
                    logger.info(f"  → 源版本：{dpiversion_s}，目标版本：{dpiversion_d}")
                    logger.info(f"  → 源模式：{dpimode_s}，目标模式：{dpimode_d}")
                    logger.info(f"  → 优先使用备份 DPI：{prefer_backup_dpi_s}")
                    logger.info(f"  → 优先使用已有安装包（源）：{prefer_backup_pkt_s}")
                    logger.info(f"  → 优先使用已有安装包（目标）：{prefer_backup_pkt_d}")
                    if xsa_modify_dict:
                        logger.info(f"  → xsa.json 修改项：{xsa_modify_dict}")
                    if switch_param_s_dict:
                        logger.info(f"  → 源版本开关参数：{switch_param_s_dict}")
                    if switch_param_d_dict:
                        logger.info(f"  → 目标版本开关参数：{switch_param_d_dict}")

                    # ==================== 执行全新安装 ====================
                    if installtype == "全新安装":
                        logger.info("")
                        logger.info("▶ 执行全新安装")

                        # 获取目标版本的 FTP 路径
                        try:
                            ftp_path_d = get_ftp_path_with_auto_update(
                                version=dpiversion_d,
                                mode=dpimode_d
                            )
                        except RuntimeError as e:
                            logger.error(f"✗ 获取目标版本 FTP 路径失败：{e}")
                            logger.error(f"✗ 跳过当前 Sheet：{sheet_name}")
                            break  # 跳出当前 sheet 的用例循环

                        # 解析 FTP 地址
                        ftphost, ftppath = re.findall(r'ftp://(.+?\..+?\..+?\..+?)(/.+?)\s*$', ftp_path_d)[0]

                        # 执行安装
                        response = dpi_install(
                            dpiserver=xsa,
                            ftphost=ftphost,
                            ftppath=ftppath,
                            scanpktpath=prefer_backup_pkt_d,
                            mode=dpimode_d,
                            pcicfg=pcicfg,
                            modified_param=switch_param_d_dict,
                            timeout=900,
                            user=ftp_username,
                            password=ftp_password,
                            upms=False,
                            dpipath_bak=path_dpibak,
                            mod_switch_version=mod_switch_version
                        )

                        if not response:
                            mark.append("安装失败")

                        # 写入结果到 Excel
                        result_deal(
                            xls=path,
                            sheet_index=sheet_name,
                            result_list=tmp_list,
                            row=case["row"] + i,
                            head2col=sheet_name2head2col[sheet_name],
                            mark=mark,
                            only_write=False,
                            newpath=newpath
                        )
                        logger.info("✓ 全新安装完成")

                    # ==================== 执行模式切换或升级 ====================
                    elif installtype in ("模式切换", "升级"):
                        logger.info("")
                        logger.info("▶ 执行源 DPI 安装")

                        # 测试前统一关闭 agent（开关关闭时）
                        if not use_upgrade_system:
                            logger.info("→ 测试前关闭 agent...")
                            xsa.stop_agent()

                        # 备份当前 DPI
                        logger.info("→ 备份当前 DPI 程序...")
                        xsa.dpibak(bakpath=path_dpibak)

                        # 确定后续操作模式
                        # 0: 不需要安装（当前版本已满足）
                        # 1: 需要切换模式（从备份恢复）
                        # 2: 需要全新安装
                        follow_up_mode = 2

                        if prefer_backup_dpi_s:
                            # 检查当前 DPI 版本是否满足要求
                            logger.info("→ 检查当前 DPI 版本...")
                            if xsa.isdir("/opt/dpi") and xsa.get_dpiversion() == dpiversion_s:
                                logger.info(f"✓ 当前 DPI 版本已是 {dpiversion_s}，无需重新安装")
                                follow_up_mode = 1
                            else:
                                # 当前版本不满足，尝试从备份目录恢复
                                logger.info("→ 当前 DPI 版本不满足要求，扫描备份目录...")

                                # 清理当前 DPI
                                if xsa.isdir("/opt/dpi"):
                                    logger.info("→ 清理当前 DPI 程序...")
                                    xsa.stop()
                                    xsa.rm("/opt/dpi")

                                # 扫描备份目录查找匹配版本和模式
                                logger.info(f"→ 扫描备份目录：{path_list_scan_dpi}")
                                break_flag = False

                                for path_tmp in path_list_scan_dpi:
                                    if not xsa.isdir(path_tmp):
                                        logger.info(f"  → 备份目录不存在：{path_tmp}")
                                        continue

                                    # 查找版本文件
                                    for path_ver in xsa.listdir(path=path_tmp, args="-type f -name ver.txt", maxdepth=2):
                                        dpipath_tmp = path_tmp.rstrip("/") + "/" + os.path.dirname(path_ver)
                                        logger.info(f"  → 检查备份版本：{dpipath_tmp}")

                                        # 检查版本号是否匹配
                                        backup_version = xsa.get_dpiversion(dpipath_tmp)
                                        if backup_version != dpiversion_s:
                                            logger.info(f"    → 版本不匹配（期望: {dpiversion_s}, 实际: {backup_version}），跳过")
                                            continue

                                        # 从备份目录中获取模式
                                        backup_mode = xsa.get_dpimode(dpipath_tmp)
                                        if not backup_mode:
                                            logger.info(f"    → 备份中无模式信息，跳过")
                                            continue

                                        logger.info(f"    → 备份模式：{backup_mode}")

                                        # 检查模式是否匹配
                                        if backup_mode == dpimode_s:
                                            # 找到精确匹配（版本+模式）
                                            follow_up_mode = 1
                                            logger.info(f"  ✓ 找到精确匹配（版本+模式）：{dpipath_tmp}")

                                            # 执行恢复
                                            cmd = f"cp -r {dpipath_tmp} /opt/dpi"
                                            logger.info(f"  → 执行命令：{cmd}")
                                            xsa.cmd(cmd)
                                            xsa.cmd("ldconfig")
                                            time.sleep(3)

                                            break_flag = True
                                            break
                                        else:
                                            logger.info(f"    → 模式不匹配（期望: {dpimode_s}, 实际: {backup_mode}），跳过")

                                    if break_flag:
                                        break

                                if not break_flag:
                                    logger.info(f"→ 未找到版本 {dpiversion_s} 模式 {dpimode_s} 的可用备份，需要全新安装")
                                    follow_up_mode = 2

                        # 根据模式执行相应操作
                        if follow_up_mode == 0:
                            # 无需操作
                            pass

                        elif follow_up_mode == 1:
                            # 执行模式切换
                            logger.info(f"→ 执行版本 {dpiversion_s} 模式切换到 {dpimode_s}...")

                            # 根据模式获取 args 参数
                            mod_switch_args = get_mod_switch_args(dpimode_s, mod_switch_version)

                            result_mod_switch = xsa.mod_switch(
                                mode=dpimode_s,
                                args=mod_switch_args,
                                modified_param=switch_param_s_dict,
                                pcicfg=pcicfg,
                                timeout=900
                            )

                            if not result_mod_switch["result"]:
                                mark += result_mod_switch["mark"]
                                logger.error(f"✗ 版本 {dpiversion_s} 模式切换失败")

                                result_deal(
                                    xls=path,
                                    sheet_index=sheet_name,
                                    result_list=tmp_list,
                                    row=case["row"] + i,
                                    head2col=sheet_name2head2col[sheet_name],
                                    mark=mark,
                                    only_write=False,
                                    newpath=newpath
                                )
                                continue

                        else:
                            # 执行全新安装
                            logger.info(f"→ 执行版本 {dpiversion_s} 全新安装，模式 {dpimode_s}...")

                            # 优化：先尝试从已有安装包安装，失败后再获取 FTP 路径
                            ftp_path_s = None
                            try:
                                ftp_path_s = get_ftp_path_with_auto_update(
                                    version=dpiversion_s,
                                    mode=dpimode_s
                                )
                            except RuntimeError as e:
                                logger.warning(f"⚠ 获取源版本 FTP 路径失败：{e}")

                                # 如果配置了"优先使用存在安装包_s"，尝试扫描已有安装包
                                if prefer_backup_pkt_s:
                                    logger.info("→ 尝试扫描目标服务器已有安装包...")
                                    # 这里需要根据版本号构造安装包名称模式
                                    # 由于无法直接获取安装包路径，继续尝试其他方式
                                    logger.warning("⚠ 无法通过已有安装包解决，跳过当前用例")
                                    mark.append(f"获取 FTP 路径失败：{str(e)}")
                                    result_deal(
                                        xls=path,
                                        sheet_index=sheet_name,
                                        result_list=tmp_list,
                                        row=case["row"] + i,
                                        head2col=sheet_name2head2col[sheet_name],
                                        mark=mark,
                                        only_write=False,
                                        newpath=newpath
                                    )
                                    continue
                                else:
                                    logger.error(f"✗ 跳过当前 Sheet：{sheet_name}")
                                    break

                            if not ftp_path_s:
                                logger.error(f"✗ 无法获取版本 {dpiversion_s} 的安装路径")
                                mark.append(f"无法获取安装路径")
                                result_deal(
                                    xls=path,
                                    sheet_index=sheet_name,
                                    result_list=tmp_list,
                                    row=case["row"] + i,
                                    head2col=sheet_name2head2col[sheet_name],
                                    mark=mark,
                                    only_write=False,
                                    newpath=newpath
                                )
                                continue

                            ftphost, ftppath = re.findall(r'ftp://(.+?\..+?\..+?\..+?)(/.+?)\s*$', ftp_path_s)[0]

                            response = dpi_install(
                                dpiserver=xsa,
                                ftphost=ftphost,
                                ftppath=ftppath,
                                scanpktpath=prefer_backup_pkt_s,
                                mode=dpimode_s,
                                pcicfg=pcicfg,
                                modified_param=switch_param_s_dict,
                                timeout=600,
                                user=ftp_username,
                                password=ftp_password,
                                upms=False,
                                dpipath_bak=path_dpibak,
                                mod_switch_version=mod_switch_version
                            )

                            if not response:
                                mark.append("安装失败")
                                result_deal(
                                    xls=path,
                                    sheet_index=sheet_name,
                                    result_list=tmp_list,
                                    row=case["row"] + i,
                                    head2col=sheet_name2head2col[sheet_name],
                                    mark=mark,
                                    only_write=False,
                                    newpath=newpath
                                )
                                continue

                        logger.info("✓ 源 DPI 安装完成")

                        # ==================== 执行目标操作 ====================
                        if installtype == "模式切换":
                            # 执行模式切换
                            logger.info("")
                            logger.info("▶ 执行目标 DPI 模式切换")
                            logger.info(f"  → 切换参数：版本 {dpiversion_s}，模式 {dpimode_d}")
                            logger.info(f"  → 开关参数：{switch_param_d_dict}")
                            logger.info(f"  → PCI 配置：{pcicfg}")

                            # 根据模式获取 args 参数
                            mod_switch_args = get_mod_switch_args(dpimode_d, mod_switch_version)

                            result_mod_switch = xsa.mod_switch(
                                mode=dpimode_d,
                                args=mod_switch_args,
                                modified_param=switch_param_d_dict,
                                pcicfg=pcicfg,
                                timeout=900
                            )

                            if not result_mod_switch["result"]:
                                mark += result_mod_switch["mark"]
                                logger.error(f"✗ 版本 {dpiversion_d} 模式切换失败")

                                result_deal(
                                    xls=path,
                                    sheet_index=sheet_name,
                                    result_list=tmp_list,
                                    row=case["row"] + i,
                                    head2col=sheet_name2head2col[sheet_name],
                                    mark=mark,
                                    only_write=False,
                                    newpath=newpath
                                )
                                continue

                            logger.info("✓ 目标 DPI 模式切换完成")

                        elif installtype == "升级":
                            # 执行版本升级
                            logger.info("")
                            logger.info("▶ 执行目标 DPI 版本升级")

                            # 预修改 xsa.json 配置
                            if xsa_modify_dict:
                                logger.info(f"→ 预修改 xsa.json 配置：{xsa_modify_dict}")
                                xsa.modify_xsajson(**xsa_modify_dict)

                            # 执行升级
                            logger.info(f"→ 执行版本升级：{dpiversion_s} -> {dpiversion_d}")

                            # ==================== 升级系统接管 ====================
                            if use_upgrade_system:
                                # 升级系统接管，不需要准备升级脚本
                                logger.info("→ 升级系统接管升级流程，无需准备升级脚本")

                                response = xsa.wait_upgrade_system_complete(
                                    dpiversion=dpiversion_d,
                                    upgrade_start_timeout=upgrade_start_timeout,
                                    upgrade_complete_timeout=upgrade_complete_timeout
                                )

                            # ==================== 本地升级流程 ====================
                            else:
                                # 升级场景：使用源版本模式确定分类（升级不改变模式）
                                try:
                                    ftp_path_d = get_ftp_path_with_auto_update(
                                        version=dpiversion_d,
                                        mode=dpimode_s  # 使用源版本模式
                                    )
                                except RuntimeError as e:
                                    logger.error(f"✗ 获取目标版本 FTP 路径失败：{e}")
                                    logger.error(f"✗ 跳过当前 Sheet：{sheet_name}")
                                    break

                                ftphost, ftppath = re.findall(r'ftp://(.+?\..+?\..+?\..+?)(/.+?)\s*$', ftp_path_d)[0]

                                response = dpi_install(
                                    dpiserver=xsa,
                                    ftphost=ftphost,
                                    ftppath=ftppath,
                                    dpiversion=dpiversion_d,
                                    scanpktpath=prefer_backup_pkt_d,
                                    mode=None,
                                    pcicfg=None,
                                    modified_param=None,
                                    timeout=upgrade_complete_timeout,
                                    user=ftp_username,
                                    password=ftp_password,
                                    upms=True,
                                    dpipath_bak=path_dpibak,
                                    xsa_modify_dict=xsa_modify_dict,
                                    mod_switch_version=mod_switch_version
                                )

                            if not response["result"]:
                                mark += response["mark"]
                                logger.error(f"✗ 版本 {dpiversion_d} 升级失败")

                                result_deal(
                                    xls=path,
                                    sheet_index=sheet_name,
                                    result_list=tmp_list,
                                    row=case["row"] + i,
                                    head2col=sheet_name2head2col[sheet_name],
                                    mark=mark,
                                    only_write=False,
                                    newpath=newpath
                                )
                                continue

                            logger.info("✓ 目标 DPI 版本升级完成")

                    # ==================== 写入最终结果 ====================
                    logger.info(f"✓ 用例执行完成：{case_name}")
                    result_deal(
                        xls=path,
                        sheet_index=sheet_name,
                        result_list=tmp_list,
                        row=case["row"] + i,
                        head2col=sheet_name2head2col[sheet_name],
                        mark=mark,
                        only_write=False,
                        newpath=newpath
                    )

        finally:
            # ==================== 清理 DynamicFileHandler ====================
            logger.info(f"关闭 Sheet {sheet_name} 的日志处理器")
            dynamic_handler.close()

            # 从所有模块的 logger 中移除 handler
            for module in modules:
                if hasattr(module, 'logger'):
                    module.logger.removeHandler(dynamic_handler)
            logger.removeHandler(dynamic_handler)

    # 关闭连接
    xsa.client.close()
    logger.info("")
    logger.info("╔" + "═" * 78 + "╗")
    text = "所有用例执行完成"
    text_width = get_display_width(text)
    right_spaces = 78 - 30 - text_width
    logger.info("║" + " " * 30 + text + " " * right_spaces + "║")
    logger.info("╚" + "═" * 78 + "╝")
    logger.info("")


if __name__ == '__main__':
    """
    主程序入口

    使用示例：
        1. 准备 Excel 用例文件，包含 install sheet
        2. 配置 FTP 路径、服务器地址等信息
        3. 运行脚本执行自动化安装/升级测试
    """
    # Excel 用例文件路径
    excel_path = r"E:\DPI_SVN\8AutomatedTest\信安EU自动化3.1\用例_电信_1060.xlsx"

    # 解析 Excel 文件（需要 parser_excel 函数）
    p_excel = parser_excel(path=excel_path)

    # 生成结果保存路径
    path_save = f"{excel_path.split('.')[0]}_{gettime(5)}.xlsx"

    # 执行安装测试
    install(p_excel=p_excel, sheets=["install"], path=excel_path, newpath=path_save)
