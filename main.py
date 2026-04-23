import argparse
import os
import sys
from glob import glob
import time
import datetime
from utils.common import logger, gettime
from business.install import install
from business.log_key import log_key
from business.log_audit import log_audit
from business.log_active import log_active
from business.eu_policy import eu_policy
from business.mirrorvlan import mirrorvlan
from business.pcapdump import pcapdump
from business.bzip import bzip
from io_handler.excel import Excel
from core.excel_reader import parser_excel


# =============================================================================
# Sheet Handler 配置 - 配置驱动替代硬编码
# =============================================================================

class SheetHandler:
    """Sheet 处理器基类"""

    def __init__(self, handler_func, group_name=None):
        self.handler_func = handler_func
        self.group_name = group_name

    def execute(self, p_excel, sheet_name, get_s_excel_path, path_save, tmp_sheets=None):
        """执行处理函数"""
        kwargs = {
            'p_excel': p_excel,
            'sheets': [sheet_name],
            'path': get_s_excel_path(),
            'newpath': path_save
        }

        # 特殊 sheet 需要额外参数
        if sheet_name == "actdomain发包":
            sheets_actdomain_list = ["actdomain入向", "actdomain出向", "acturl入向", "acturl出向", "actdomain"]
            kwargs['sheets_actdomain_list'] = sheets_actdomain_list
            kwargs['sheets_sendpkt'] = "actdomain发包"
            kwargs.pop('sheets', None)  # log_active 不接受 sheets 参数
            if tmp_sheets is not None:
                tmp_sheets.extend(sheets_actdomain_list)

        return self.handler_func(**kwargs)


# Sheet Handler 映射表
# 格式: {sheet_name: SheetHandler}
SHEET_HANDLERS = {
    # 日志类 sheet
    "accesslog": SheetHandler(log_key, "日志"),
    "s_accesslog": SheetHandler(log_key, "日志"),
    "monitor": SheetHandler(log_key, "日志"),
    "filter": SheetHandler(log_key, "日志"),
    "mirrorvlan_log": SheetHandler(log_key, "日志"),
    "pcapdump_log": SheetHandler(log_key, "日志"),
    "vpn_block": SheetHandler(log_key, "日志"),
    "vpn_block_kk": SheetHandler(log_key, "日志"),
    "vpn_block_inner": SheetHandler(log_key, "日志"),
    "dns_parse": SheetHandler(log_key, "日志"),
    "fz_filter": SheetHandler(log_key, "日志"),

    # 策略类 sheet
    "block": SheetHandler(eu_policy, "策略"),
    "fz_block": SheetHandler(eu_policy, "策略"),

    # 单独处理的 sheet
    "mirrorvlan": SheetHandler(mirrorvlan, "其他"),
    "pcapdump": SheetHandler(pcapdump, "其他"),
    "audit": SheetHandler(log_audit, "审计"),
    "bzip": SheetHandler(bzip, "其他"),

    # 安装升级 sheet
    "install": SheetHandler(install, "安装"),

    # 活跃日志 sheet (特殊处理)
    "actdomain发包": SheetHandler(log_active, "活跃日志"),
}

# Sheet 分组配置
SHEET_GROUPS = {
    "日志": ["accesslog", "s_accesslog", "monitor", "filter", "mirrorvlan_log",
            "pcapdump_log", "vpn_block", "vpn_block_kk", "vpn_block_inner",
            "dns_parse", "fz_filter"],
    "策略": ["block", "fz_block"],
    "其他": ["mirrorvlan", "pcapdump", "bzip"],
    "审计": ["audit"],
    "安装": ["install"],
    "活跃日志": ["actdomain发包"],
}


def get_handler_for_sheet(sheet_name):
    """
    根据 sheet 名称获取对应的处理器

    :param sheet_name: sheet 名称
    :return: SheetHandler 或 None
    """
    return SHEET_HANDLERS.get(sheet_name)


def is_log_sheet(sheet_name):
    """检查是否为日志类 sheet"""
    return sheet_name in SHEET_GROUPS.get("日志", [])


def is_policy_sheet(sheet_name):
    """检查是否为策略类 sheet"""
    return sheet_name in SHEET_GROUPS.get("策略", [])


def is_skip_sheet(sheet_name):
    """检查是否为需要跳过的 sheet"""
    return sheet_name in ["设备初始化配置", "配置", "IP规范"]


def create_bat():
    if not os.path.isdir("exec_bat"):
        os.mkdir("exec_bat")

    content1 = r"""@echo off
setlocal enabledelayedexpansion

:: 获取当前批处理文件的完整路径和文件名（不带路径）
set "full_filepath=%~f0"
set "full_filename=%~nx0"

:: 切换到当前批处理文件所在目录
cd /d "%~dp0.."

:: 显示当前执行目录
echo Current Directory: %CD%

:: 显示完整路径和文件名（用于调试）
echo Full Filepath: %full_filepath%
echo Full Filename: %full_filename%

:: 提取文件名中的 FILENAME
:: 假设文件名格式为 main_exe-FILENAME-SHEETNAME.bat
for /f "tokens=2 delims=-" %%a in ("%full_filename%") do set "filename=%%a"


:: 去掉 sheetname 中的 .bat 后缀
set "filename=!filename:.bat=!"

:: 显示提取的文件名和工作表名
echo Extracted Filename: %filename%

:: 如果提取的参数为空，则输出错误信息
if "%filename%"=="" (
    echo ERROR: Filename not extracted properly.
    pause
    exit /b
)

:: 执行目标命令
echo Executing: .\main_exe -f "%filename%"
.\main_exe -f "%filename%"

pause
"""
    content2 = r"""@echo off
setlocal enabledelayedexpansion

:: 获取当前批处理文件的完整路径和文件名（不带路径）
set "full_filepath=%~f0"
set "full_filename=%~nx0"

:: 切换到当前批处理文件所在目录
cd /d "%~dp0.."

:: 显示当前执行目录
echo Current Directory: %CD%

:: 显示完整路径和文件名（用于调试）
echo Full Filepath: %full_filepath%
echo Full Filename: %full_filename%

:: 提取文件名中的 FILENAME 和 SHEETNAME
:: 假设文件名格式为 main_exe-FILENAME-SHEETNAME.bat
for /f "tokens=2 delims=-" %%a in ("%full_filename%") do set "filename=%%a"
for /f "tokens=3 delims=-" %%b in ("%full_filename%") do set "sheetname=%%b"

:: 去掉 sheetname 中的 .bat 后缀
set "sheetname=!sheetname:.bat=!"

:: 显示提取的文件名和工作表名
echo Extracted Filename: %filename%
echo Extracted Sheetname: %sheetname%

:: 如果提取的参数为空，则输出错误信息
if "%filename%"=="" (
    echo ERROR: Filename not extracted properly.
    pause
    exit /b
)
if "%sheetname%"=="" (
    echo ERROR: Sheetname not extracted properly.
    pause
    exit /b
)

:: 执行目标命令
echo Executing: .\main_exe -f "%filename%" -s "%sheetname%"
.\main_exe -f "%filename%" -s "%sheetname%"

pause
"""

    for file in glob("*.xlsx"):
        if file.startswith("~$"):
            continue
        xls = Excel(file)
        bookname = xls.workbook.name
        sheet_names = xls.workbook.sheet_names
        logger.info(xls.workbook.sheet_names)
        logger.info(xls.workbook.name)
        # 生成全量执行脚本
        with open(f"exec_bat/main_exe-{bookname}.bat", "w") as f:
            f.write(content1)

        for sheet_name in sheet_names:
            with open(f"exec_bat/main_exe-{bookname}-{sheet_name}.bat", "w") as f:
                f.write(content2)
        xls.close()


def create_ps1():
    if not os.path.isdir("exec_ps1"):
        os.mkdir("exec_ps1")

    content1 = r'''# 获取当前 PowerShell 脚本的完整路径和文件名
$FullFilePath = $MyInvocation.MyCommand.Path
$FullFileName = [System.IO.Path]::GetFileName($FullFilePath)

# 切换到当前脚本所在目录的上一级目录
$ScriptDir = Split-Path -Parent $FullFilePath
$TargetDir = Split-Path -Parent $ScriptDir
Set-Location -Path $TargetDir

# 显示当前执行目录
Write-Host "Current Directory: $($PWD.Path)"

# 提取文件名中的 FILENAME
$Parts = $FullFileName -split "-"
if ($Parts.Count -ge 2) {
    $FileName = $Parts[1] -replace "\.ps1$", ""  # 去掉 .ps1 后缀
} else {
    Write-Host "ERROR: Filename not extracted properly." -ForegroundColor Red
    Pause
    Exit
}

# 显示提取的文件名
Write-Host "Extracted Filename: $FileName"

# 设置 PowerShell 窗口标题
$Host.UI.RawUI.WindowTitle = "$FileName"

# 检查是否提取成功
if ([string]::IsNullOrEmpty($FileName)) {
    Write-Host "ERROR: Filename extraction failed." -ForegroundColor Red
    Pause
    Exit
}

# 执行目标命令
$Command = "./main_exe -f `"$FileName`""
Write-Host "Executing: $Command"
Invoke-Expression $Command

Pause
'''

    content2 = r'''# 获取当前 PowerShell 脚本的完整路径和文件名
$FullFilePath = $MyInvocation.MyCommand.Path
$FullFileName = [System.IO.Path]::GetFileName($FullFilePath)

# 切换到当前脚本所在目录的上一级目录
$ScriptDir = Split-Path -Parent $FullFilePath
$TargetDir = Split-Path -Parent $ScriptDir
Set-Location -Path $TargetDir

# 显示当前执行目录
Write-Host "Current Directory: $($PWD.Path)"

# 提取文件名中的 FILENAME 和 SHEETNAME
$Parts = $FullFileName -split "-"
if ($Parts.Count -ge 3) {
    $FileName = $Parts[1]
    $SheetName = $Parts[2] -replace "\.ps1$", ""  # 去掉 .ps1 后缀
} else {
    Write-Host "ERROR: Filename or Sheetname not extracted properly." -ForegroundColor Red
    Pause
    Exit
}

# 显示提取的文件名和工作表名
Write-Host "Extracted Filename: $FileName"
Write-Host "Extracted Sheetname: $SheetName"

# 设置 PowerShell 窗口标题
$Host.UI.RawUI.WindowTitle = "$FileName-$SheetName"

# 检查是否提取成功
if ([string]::IsNullOrEmpty($FileName) -or [string]::IsNullOrEmpty($SheetName)) {
    Write-Host "ERROR: Filename or Sheetname extraction failed." -ForegroundColor Red
    Pause
    Exit
}

# 执行目标命令
$Command = "./main_exe -f `"$FileName`" -s `"$SheetName`""
Write-Host "Executing: $Command"
Invoke-Expression $Command

Pause
'''

    for file in glob("*.xlsx"):
        if file.startswith("~$"):
            continue
        xls = Excel(file)
        bookname = xls.workbook.name
        sheet_names = xls.workbook.sheet_names
        logger.info(xls.workbook.sheet_names)
        logger.info(xls.workbook.name)

        # 生成全量执行脚本
        with open(f"exec_ps1/main_exe-{bookname}.ps1", "w", encoding="utf-8") as f:
            f.write(content1)

        for sheet_name in sheet_names:
            with open(f"exec_ps1/main_exe-{bookname}-{sheet_name}.ps1", "w", encoding="utf-8") as f:
                f.write(content2)
        xls.close()

    logger.info("PowerShell scripts created successfully in 'exec_ps1' directory.")


def run(excel_path, sheet=None):
    """
    执行测试用例

    :param excel_path: Excel 文件路径
    :param sheet: 指定执行的 sheet 名称（可选）
    """
    # 生成会话ID
    session_id = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    logger.info(f"会话ID: {session_id}")

    try:
        p_excel = parser_excel(path=excel_path)
        excel_base, excel_name = os.path.split(excel_path)
        excel_name_save = os.path.join("report", f"{excel_name.split('.')[0]}_{gettime(5)}.xlsx")
        path_save = os.path.join(excel_base, excel_name_save) if excel_base else excel_name_save

        def get_s_excel_path():
            if os.path.isfile(path_save):
                return path_save
            else:
                return excel_path

        # 生成报告
        if not os.path.isdir("report"):
            os.mkdir("report")

        # 获取需要执行的 sheet 列表
        if sheet:
            tmp_sheets = [sheet]
        else:
            tmp_sheets = _get_executable_sheets(p_excel)

        sheet_name2minutes = dict()

        for sheet_name in tmp_sheets:
            # 跳过不需要处理的 sheet
            if is_skip_sheet(sheet_name):
                continue

            # 开始时间
            start_time = time.time()

            # 获取处理器
            handler = get_handler_for_sheet(sheet_name)

            if handler:
                try:
                    handler.execute(
                        p_excel=p_excel,
                        sheet_name=sheet_name,
                        get_s_excel_path=get_s_excel_path,
                        path_save=path_save,
                        tmp_sheets=tmp_sheets if sheet_name == "actdomain发包" else None
                    )
                except Exception as e:
                    import traceback
                    logger.error(f"执行 sheet {sheet_name} 失败: {e}")
                    logger.error(traceback.format_exc())
            else:
                logger.error(f"sheet:{sheet_name} 未找到对应的处理器，将直接跳过")

            # 结束时间
            end_time = time.time()
            # 计算耗时（单位：秒）
            duration = end_time - start_time
            # 转换为小时和分钟
            hours = int(duration // 3600)
            minutes = int((duration % 3600) // 60)
            logger.info(f"sheet:{sheet_name}，执行耗时：{hours} 小时 {minutes} 分钟")
            cur_minutes = int(duration // 60)
            sheet_name2minutes[sheet_name] = cur_minutes

        # 删除多余的 sheet
        _cleanup_report_sheets(path_save, tmp_sheets)

        # 统计用例执行情况并添加到结果统计 sheet 中
        _generate_statistics(path_save, sheet_name2minutes)

    finally:
        logger.info("测试执行完成")


def _get_executable_sheets(p_excel):
    """
    获取需要执行的 sheet 列表

    :param p_excel: 解析后的 Excel 数据
    :return: sheet 名称列表
    """
    tmp_sheets = []
    for sheet_name, cases in p_excel.get("sheet_name2cases", dict()).items():
        # 检查是否有需要执行的用例
        has_executable = any(
            case_list[0].get("执行状态", 0) not in (0, "0", "", None)
            for case_list in cases.values()
        )
        if has_executable:
            tmp_sheets.append(sheet_name)

    # 移除不需要处理的 sheet
    for skip_sheet in ["设备初始化配置", "配置", "IP规范"]:
        if skip_sheet in tmp_sheets:
            tmp_sheets.remove(skip_sheet)

    return tmp_sheets


def _cleanup_report_sheets(path_save, tmp_sheets):
    """
    清理报告中的多余 sheet

    :param path_save: 报告保存路径
    :param tmp_sheets: 需要保留的 sheet 列表
    """
    logger.info(f"整理报告sheet：{path_save}")
    xlsx = None
    try:
        xlsx = Excel(path_save)
        delete_flag = False
        for name in [sheet.name for sheet in xlsx.workbook.sheets]:
            if name not in tmp_sheets:
                try:
                    xlsx.workbook.sheets[name].delete()
                    delete_flag = True
                except Exception as e:
                    logger.warning(f"删除 sheet {name} 失败：{e}")
        if delete_flag:
            xlsx.save(path=path_save)
    except Exception as e:
        logger.error(f"整理报告 sheet 失败：{e}")
    finally:
        if xlsx:
            try:
                xlsx.close()
            except:
                pass


def _generate_statistics(path_save, sheet_name2minutes):
    """
    生成执行统计

    :param path_save: 报告保存路径
    :param sheet_name2minutes: sheet 名称到执行分钟的映射
    """
    logger.info("统计用例执行情况")
    p1_excel = parser_excel(path=path_save)
    xlsx = Excel(path_save)
    xlsx.workbook.sheets.add(name="结果统计", after=xlsx.workbook.sheets[-1])

    statistics_list = list()
    for sheet_name, cases in p1_excel.get("sheet_name2cases", dict()).items():
        count_exe, count_unexe, count_pass, count_fail, count_noresult = _count_case_results(cases)

        success_rate = count_pass / count_exe if count_exe else 0.0
        statistics_list.append(
            [sheet_name, count_exe, count_pass, count_fail, count_noresult, f"{success_rate:.2%}",
             f"{sheet_name2minutes.get(sheet_name, 0)} 分钟"])
        logger.info(
            f"sheet:{sheet_name}\tcount_exe:{count_exe}\tcount_pass:{count_pass}\t"
            f"count_fail:{count_fail}\tcount_noresult:{count_noresult}\tsuccess_rate:{success_rate:.2%}")

    # 计算总耗时
    total_minutes = sum(sheet_name2minutes.values())
    hours = int(total_minutes * 60 // 3600)
    minutes = int(((total_minutes * 60) % 3600) // 60)
    logger.info(f"执行总耗时：{hours} 小时 {minutes} 分钟")

    # 写入统计结果
    header = [["sheet", "执行数量", "成功数量", "失败数量", "未执行数量", "成功率", "执行时间"]]
    footer = [["", "", "", "", "", "", f"{hours} 小时 {minutes} 分钟"]]
    statistics_list = header + statistics_list + footer

    xlsx.write_range_values(sheet_index="结果统计", value=statistics_list, row1=0, col1=0)
    xlsx.save(path=path_save)
    xlsx.close()


def _count_case_results(cases):
    """
    统计用例执行结果

    :param cases: 用例字典
    :return: (执行数, 未执行数, 通过数, 失败数, 无结果数)
    """
    count_exe = count_unexe = count_pass = count_fail = count_noresult = 0

    for case_list in cases.values():
        execute_status = case_list[0].get("执行状态", 0)
        if execute_status in (0, "0", "", None):
            count_unexe += 1
        else:
            count_exe += 1
            cases_result = case_list[0].get("结果", None)
            if cases_result == "Pass":
                count_pass += 1
            elif cases_result == "Failed":
                count_fail += 1
            else:
                count_noresult += 1

    return count_exe, count_unexe, count_pass, count_fail, count_noresult


if __name__ == '__main__':
    # 添加命令行参数解析
    parser = argparse.ArgumentParser(description='自动化测试执行脚本')
    parser.add_argument('-f', '--file', type=str, required=False,
                        help='Excel文件路径，例如: 用例_移动.xlsx')
    parser.add_argument('-s', '--sheet', type=str, required=False, default="install",
                        help='指定要执行的sheet名称（默认：install）')
    parser.add_argument('-bat', '--bat', action='store_true', default=False, help='初始化bat文件')
    parser.add_argument('-ps1', '--ps1', action='store_true', default=False, help='初始化ps1文件')
    args = parser.parse_args()

    if args.bat:
        create_bat()
        sys.exit()
    elif args.ps1:
        create_ps1()
        sys.exit()
    elif args.file:
        run(excel_path=args.file, sheet=args.sheet)
    else:
        run(excel_path="用例_移动_1060.xlsx", sheet="block")
