#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2023/5/26 16:53
# @Author  : weihang
# @File    : dpiinstall.py
# @Desc    : DPI 安装升级模块，支持全新安装、模式切换、版本升级等功能

import os
import re
import time
from read_write_excel import parser_excel
from common import gettime, setup_logging
from dpi import Dpi
from ftp import FTPclient

# 添加日志打印
logger = setup_logging(log_file_path="log/install.log", logger_name="install")


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
    password: str = "Qq111222",
    upms: bool = False,
    dpipath_bak: str = None,
    xsa_modify_dict: dict = None
) -> dict:
    """
    DPI 安装/升级主函数

    根据参数执行 DPI 程序的全新安装或升级操作，支持以下功能：
    1. 全新安装：从 FTP 下载安装包，解压并安装 DPI 程序
    2. 版本升级：在现有 DPI 基础上执行升级脚本

    安装包结构说明（三层压缩）：
    - 第一层：ACT-DPI-ISE-1.0.5.2-2_20250427161928.tar.gz（带时间戳的外层压缩包）
    - 第二层：ACT-DPI-ISE-1.0.5.2-2.tar.gz（版本号命名的内层压缩包）
    - 第三层：ACT-DPI-ISE-1.0.5.2-2/（最终安装目录，包含 install.sh）

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
    # ==================== 第一阶段：验证安装包 ====================
    logger.info("=" * 60)
    logger.info("第一阶段：验证 FTP 安装包")
    logger.info("=" * 60)

    # 连接 FTP 服务器并验证安装包是否存在
    ftp = FTPclient(host=ftphost, user="weihang", passwd="Qq111222")
    if not ftp.file_exists(ftppath):
        raise RuntimeError(f"未找到安装包：{ftppath}")
    logger.info(f"安装包验证通过：{ftppath}")

    # ==================== 第二阶段：下载安装包 ====================
    logger.info("=" * 60)
    logger.info("第二阶段：下载安装包")
    logger.info("=" * 60)

    # 提取安装包文件名和下载路径
    pktname = os.path.basename(ftppath)  # 如：ACT-DPI-ISE-1.0.5.2-2_20250427161928.tar.gz
    pktremotepath = "ftp://" + ftphost + ftppath
    pktlocalpath = "/home/" + pktname  # 目标服务器上的存放路径

    logger.info(f"安装包名称：{pktname}")
    logger.info(f"远程路径：{pktremotepath}")
    logger.info(f"本地存放路径：{pktlocalpath}")

    # 判断是否需要下载安装包
    downloadflag = True
    if scanpktpath:
        # 扫描目标服务器上是否已存在同名安装包
        cmd = f"find / -type f -name {pktname} -print -quit"
        logger.info(f"扫描目标服务器是否存在可用安装包：{cmd}")
        response = dpiserver.cmd(cmd).strip()

        if response:
            # 找到已存在的安装包，直接使用
            pktlocalpath = response
            logger.info(f"发现可用安装包，跳过下载：{pktlocalpath}")
            downloadflag = False
        else:
            logger.info("未发现可用安装包，需要从 FTP 下载")

    # 执行下载操作
    if downloadflag:
        logger.info(f"开始下载安装包：{pktremotepath} -> {pktlocalpath}")
        dpiserver.wget_ftp(
            remotepath=pktremotepath,
            localpath=pktlocalpath,
            user=user,
            password=password,
            overwrite=True
        )
        logger.info("安装包下载完成")

    # ==================== 第三阶段：解压安装包 ====================
    logger.info("=" * 60)
    logger.info("第三阶段：解压安装包（三层压缩结构）")
    logger.info("=" * 60)

    # ---------- 解压第一层：外层压缩包（带时间戳） ----------
    logger.info(f"[1/3] 解压第一层压缩包：{pktlocalpath}")
    outdir1 = os.path.dirname(pktlocalpath) + "/" + pktname.rstrip('.tar.gz')

    if scanpktpath and dpiserver.isdir(outdir1):
        logger.info(f"第一层已解压，跳过：{outdir1}")
    else:
        logger.info(f"解压到：{outdir1}")
        dpiserver.unzip(
            file=pktlocalpath,
            outdir=outdir1,
            passwd="GeUpms@1995",
            overwrite=True,
            bufsize=1024
        )
        logger.info("第一层解压完成")

    # ---------- 解压第二层：内层压缩包（版本号命名） ----------
    # 查找第一层解压后的 tar.gz 文件
    tmpname = dpiserver.listdir(path=outdir1, args='-name "*.tar.gz"')[0]
    lf = outdir1 + "/" + tmpname
    logger.info(f"[2/3] 解压第二层压缩包：{lf}")

    outdir2 = outdir1 + "/" + tmpname.rstrip(".tar.gz")

    if scanpktpath and dpiserver.isdir(outdir2):
        logger.info(f"第二层已解压，跳过：{outdir2}")
    else:
        logger.info(f"解压到：{outdir2}")
        dpiserver.unzip(
            file=lf,
            outdir=outdir1,
            passwd="GeUpms@1995",
            overwrite=True,
            bufsize=1024
        )
        logger.info("第二层解压完成")

    # 定位升级脚本路径
    upms_install_file = f"{outdir2}/upms_install.sh"
    logger.info(f"升级脚本路径：{upms_install_file}")

    # ==================== 第四阶段：执行安装/升级 ====================
    logger.info("=" * 60)
    logger.info(f"第四阶段：执行{'升级' if upms else '全新安装'}")
    logger.info("=" * 60)

    if not upms:
        # ==================== 全新安装流程 ====================
        logger.info("执行全新安装流程...")

        # ---------- 解压第三层：最内层安装包 ----------
        tmpname = dpiserver.listdir(path=outdir2, args='-name "*.tar.gz"')[0]
        logger.info(f"[3/3] 解压第三层压缩包：{tmpname}")

        outdir3 = outdir2 + "/" + tmpname.rstrip(".tar.gz")

        if scanpktpath and dpiserver.isdir(outdir3):
            logger.info(f"第三层已解压，跳过：{outdir3}")
        else:
            # 使用 tar 命令解压（非 zip 格式）
            cmd = f"tar -xzf {tmpname}"
            logger.info(f"执行命令：{cmd}，工作目录：{outdir2}")
            dpiserver.cmd(cmd, cwd=outdir2)
            logger.info("第三层解压完成")

        # 定位安装脚本
        install_file = f"{outdir3}/install.sh"
        logger.info(f"安装脚本路径：{install_file}")

        # ---------- 执行安装 ----------
        logger.info("开始执行 install.sh 安装脚本...")
        dpiserver.install(dpipath=install_file, dpipath_bak=dpipath_bak)
        logger.info("install.sh 执行完成")

        # ---------- 执行模式切换 ----------
        logger.info(f"开始执行模式切换：{mode}")
        logger.info(f"  - PCI 配置：{pcicfg}")
        logger.info(f"  - 开关参数：{modified_param}")
        logger.info(f"  - 超时时间：{timeout}s")

        result = dpiserver.mod_switch(
            mode=mode,
            modified_param=modified_param,
            force=False,
            pcicfg=pcicfg,
            timeout=timeout
        )
        logger.info(f"模式切换完成，结果：{result}")

    else:
        # ==================== 升级流程 ====================
        logger.info("执行升级流程...")
        logger.info(f"  - 目标版本：{dpiversion}")
        logger.info(f"  - xsa.json 修改项：{xsa_modify_dict}")
        logger.info(f"  - 备份目录：{dpipath_bak}")

        result = dpiserver.upms_install(
            dpiversion=dpiversion,
            path=upms_install_file,
            dpipath_bak=dpipath_bak,
            rmvarbak=False,
            xsa_modify_dict=xsa_modify_dict,
            timeout=timeout
        )
        logger.info(f"升级完成，结果：{result}")

    # ==================== 第五阶段：输出最终状态 ====================
    logger.info("=" * 60)
    logger.info("第五阶段：输出最终状态")
    logger.info("=" * 60)

    logger.info(f"PCI 信息：{dpiserver.get_pcicfg()}")
    logger.info(f"DPI 模式：{dpiserver.get_dpimode()}")
    logger.info(f"DPI 版本：{dpiserver.get_dpiversion()}")

    return result


def install(p_excel: dict, sheets: tuple = ("install",), path: str = "用例", newpath: str = None) -> None:
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

    返回值:
        :return: None，结果直接写入 Excel 文件

    配置项说明（Excel config sheet）:
        - ip_xsa：DPI 服务器 IP
        - port_xsa：DPI 服务器端口
        - {sheet}_paths_scan_dpi：DPI 备份扫描路径，多个路径用逗号分隔
        - {sheet}_path_dpibak：DPI 备份存放目录
        - {sheet}_pcis：PCI 列表，多个用逗号分隔
        - {sheet}_ftp_path_{version}：各版本对应的 FTP 路径
    """
    # ==================== 初始化 ====================
    # 解析 Excel 数据
    sheet_name2cases = p_excel["sheet_name2cases"]
    sheet_name2head2col = p_excel["sheet_name2head2col"]
    config = p_excel["config"]

    # 建立 DPI 服务器连接
    socket_xsa = (config["ip_xsa"], config["port_xsa"])
    logger.info(f"连接 DPI 服务器：{socket_xsa}")
    xsa = Dpi(socket_xsa)

    # ==================== 遍历执行用例 ====================
    counter = 0

    for sheet_name in sheets:
        logger.info("=" * 80)
        logger.info(f"开始执行 Sheet：{sheet_name}")
        logger.info("=" * 80)

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

        logger.info(f"配置信息：")
        logger.info(f"  - DPI 备份扫描路径：{path_list_scan_dpi}")
        logger.info(f"  - DPI 备份存放目录：{path_dpibak}")
        logger.info(f"  - PCI 配置：{pcicfg}")

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

                logger.info("-" * 80)
                logger.info(f"用例 Sheet：{sheet_name}")
                logger.info(f"用例名称：{case_name}")
                logger.info(f"执行序号：第 {i + 1} 项")
                logger.info("-" * 80)

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

                logger.info(f"用例参数：")
                logger.info(f"  - 安装类型：{installtype}")
                logger.info(f"  - 源版本：{dpiversion_s}，目标版本：{dpiversion_d}")
                logger.info(f"  - 源模式：{dpimode_s}，目标模式：{dpimode_d}")
                logger.info(f"  - 优先使用备份 DPI：{prefer_backup_dpi_s}")
                logger.info(f"  - 优先使用已有安装包（源）：{prefer_backup_pkt_s}")
                logger.info(f"  - 优先使用已有安装包（目标）：{prefer_backup_pkt_d}")
                logger.info(f"  - xsa.json 修改项：{xsa_modify_dict}")
                logger.info(f"  - 源版本开关参数：{switch_param_s_dict}")
                logger.info(f"  - 目标版本开关参数：{switch_param_d_dict}")

                # ==================== 执行全新安装 ====================
                if installtype == "全新安装":
                    logger.info(">>>>>>>>>> 执行全新安装 <<<<<<<<<<")

                    # 获取目标版本的 FTP 路径
                    ftp_path_d = config.get(f"{sheet_name}_ftp_path_{dpiversion_d}", None)
                    if not ftp_path_d:
                        raise RuntimeError(f"请在配置页签中配置 ftp 参数：ftp_path_{dpiversion_d}")

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
                        user="weihang",
                        password="Qq111222",
                        upms=False,
                        dpipath_bak=path_dpibak
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
                    logger.info(">>>>>>>>>> 全新安装完成 <<<<<<<<<<")

                # ==================== 执行模式切换或升级 ====================
                elif installtype in ("模式切换", "升级"):
                    logger.info(">>>>>>>>>> 执行源 DPI 安装 <<<<<<<<<<")

                    # 备份当前 DPI
                    logger.info("备份当前 DPI 程序...")
                    xsa.dpibak(bakpath=path_dpibak)

                    # 确定后续操作模式
                    # 0: 不需要安装（当前版本已满足）
                    # 1: 需要切换模式（从备份恢复）
                    # 2: 需要全新安装
                    follow_up_mode = 2

                    if prefer_backup_dpi_s:
                        # 检查当前 DPI 版本是否满足要求
                        logger.info("检查当前 DPI 版本...")
                        if xsa.isdir("/opt/dpi") and xsa.get_dpiversion() == dpiversion_s:
                            logger.info(f"当前 DPI 版本已是 {dpiversion_s}，无需重新安装")
                            follow_up_mode = 1
                        else:
                            # 当前版本不满足，尝试从备份目录恢复
                            logger.info("当前 DPI 版本不满足要求，扫描备份目录...")

                            # 清理当前 DPI
                            if xsa.isdir("/opt/dpi"):
                                logger.info("清理当前 DPI 程序...")
                                xsa.stop()
                                xsa.rm("/opt/dpi")

                            # 扫描备份目录查找匹配版本
                            logger.info(f"扫描备份目录：{path_list_scan_dpi}")
                            break_flag = False

                            for path_tmp in path_list_scan_dpi:
                                if not xsa.isdir(path_tmp):
                                    logger.info(f"备份目录不存在：{path_tmp}")
                                    continue

                                # 查找版本文件
                                for path_ver in xsa.listdir(path=path_tmp, args="-type f -name ver.txt", maxdepth=2):
                                    dpipath_tmp = path_tmp.rstrip("/") + "/" + os.path.dirname(path_ver)
                                    logger.info(f"检查备份版本：{dpipath_tmp}")

                                    if xsa.get_dpiversion(dpipath_tmp) == dpiversion_s:
                                        # 找到匹配版本，执行恢复
                                        follow_up_mode = 1
                                        logger.info(f"找到匹配版本 {dpiversion_s}，从备份恢复...")

                                        cmd = f"cp -r {dpipath_tmp} /opt/dpi"
                                        logger.info(f"执行命令：{cmd}")
                                        xsa.cmd(cmd)
                                        xsa.cmd("ldconfig")
                                        time.sleep(3)

                                        break_flag = True
                                        break

                                if break_flag:
                                    break

                            if not break_flag:
                                logger.info(f"未找到版本 {dpiversion_s} 的可用备份，需要全新安装")
                                follow_up_mode = 2

                    # 根据模式执行相应操作
                    if follow_up_mode == 0:
                        # 无需操作
                        pass

                    elif follow_up_mode == 1:
                        # 执行模式切换
                        logger.info(f"执行版本 {dpiversion_s} 模式切换到 {dpimode_s}...")
                        result_mod_switch = xsa.mod_switch(
                            mode=dpimode_s,
                            modified_param=switch_param_s_dict,
                            pcicfg=pcicfg,
                            timeout=900
                        )

                        if not result_mod_switch["result"]:
                            mark += result_mod_switch["mark"]
                            logger.error(f"版本 {dpiversion_s} 模式切换失败")

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
                        logger.info(f"执行版本 {dpiversion_s} 全新安装，模式 {dpimode_s}...")

                        ftp_path_s = config.get(f"{sheet_name}_ftp_path_{dpiversion_s}", None)
                        if not ftp_path_s:
                            raise RuntimeError(f"请在配置页签中配置 ftp 参数：ftp_path_{dpiversion_s}")

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
                            user="weihang",
                            password="Qq111222",
                            upms=False,
                            dpipath_bak=path_dpibak
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

                    logger.info(">>>>>>>>>> 源 DPI 安装完成 <<<<<<<<<<")

                    # ==================== 执行目标操作 ====================
                    if installtype == "模式切换":
                        # 执行模式切换
                        logger.info(">>>>>>>>>> 执行目标 DPI 模式切换 <<<<<<<<<<")
                        logger.info(f"切换参数：版本 {dpiversion_s}，模式 {dpimode_d}")
                        logger.info(f"开关参数：{switch_param_d_dict}")
                        logger.info(f"PCI 配置：{pcicfg}")

                        result_mod_switch = xsa.mod_switch(
                            mode=dpimode_d,
                            modified_param=switch_param_d_dict,
                            pcicfg=pcicfg,
                            timeout=900
                        )

                        if not result_mod_switch["result"]:
                            mark += result_mod_switch["mark"]
                            logger.error(f"版本 {dpiversion_d} 模式切换失败")

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

                        logger.info(">>>>>>>>>> 目标 DPI 模式切换完成 <<<<<<<<<<")

                    elif installtype == "升级":
                        # 执行版本升级
                        logger.info(">>>>>>>>>> 执行目标 DPI 版本升级 <<<<<<<<<<")

                        # 预修改 xsa.json 配置
                        logger.info(f"预修改 xsa.json 配置：{xsa_modify_dict}")
                        xsa.modify_xsajson(**xsa_modify_dict)

                        # 执行升级
                        logger.info(f"执行版本升级：{dpiversion_s} -> {dpiversion_d}")

                        ftp_path_d = config.get(f"{sheet_name}_ftp_path_{dpiversion_d}", None)
                        if not ftp_path_d:
                            raise RuntimeError(f"请在配置页签中配置 ftp 参数：ftp_path_{dpiversion_d}")

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
                            timeout=600,
                            user="weihang",
                            password="Qq111222",
                            upms=True,
                            dpipath_bak=path_dpibak,
                            xsa_modify_dict=xsa_modify_dict
                        )

                        if not response["result"]:
                            mark += response["mark"]
                            logger.error(f"版本 {dpiversion_d} 升级失败")

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

                        logger.info(">>>>>>>>>> 目标 DPI 版本升级完成 <<<<<<<<<<")

                # ==================== 写入最终结果 ====================
                logger.info(f"用例执行完成：{case_name}，结果：{result}")
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

    # 关闭连接
    xsa.client.close()
    logger.info("=" * 80)
    logger.info("所有用例执行完成")
    logger.info("=" * 80)


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
