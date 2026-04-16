import argparse
import os
import sys
from glob import glob
import time
import datetime
from common import logger, gettime
from dpiinstall import install
from excel import Excel
from read_write_excel import parser_excel


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

if __name__ == '__main__':
    # 添加命令行参数解析
    parser = argparse.ArgumentParser(description='自动化测试执行脚本')
    parser.add_argument('-f', '--file', type=str, required=False,
                        help='Excel文件路径，例如: 用例_移动.xlsx')
    parser.add_argument('-s', '--sheet', type=str, required=False,
                        help='指定要执行的sheet名称，不指定则执行全部')
    parser.add_argument('-bat', '--bat', action='store_true', default=False, help='初始化bat文件')
    parser.add_argument('-ps1', '--ps1', action='store_true', default=False, help='初始化ps1文件')
    args = parser.parse_args()

    if args.bat:
        create_bat()
        sys.exit()
    elif args.ps1:
        create_ps1()
        sys.exit()


    def run(excel_path, sheet=None):
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
            if sheet:
                tmp_sheets = [sheet]
            else:
                # tmp_sheets = list(p_excel.get("sheet_name2heads", dict()).keys())
                tmp_sheets = list()
                for sheet_name, cases in p_excel.get("sheet_name2cases", dict()).items():
                    if [i for i in list(map(lambda x: x[0].get("执行状态", 0), cases.values())) if
                        i not in (0, "0", "", None)]:
                        tmp_sheets.append(sheet_name)

                tmp_sheets.remove("设备初始化配置") if "设备初始化配置" in tmp_sheets else None
                tmp_sheets.remove("配置") if "配置" in tmp_sheets else None
                tmp_sheets.remove("IP规范") if "IP规范" in tmp_sheets else None

            sheet_name2minutes = dict()
            for sheet_name in tmp_sheets:
                # 开始时间
                start_time = time.time()

                if sheet_name in ["install"]:
                    install(p_excel=p_excel, sheets=[sheet_name], path=get_s_excel_path(), newpath=path_save, session_id=session_id)
                else:
                    logger.error(f"sheet:{sheet_name}需要添加内部直接方法，将直接跳过")

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

            # 删除多余的sheet
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

            # 统计用例执行情况并添加到结果统计sheet中
            logger.info("统计用例执行情况")
            p1_excel = parser_excel(path=path_save)
            xlsx = Excel(path_save)
            xlsx.workbook.sheets.add(name="结果统计", after=xlsx.workbook.sheets[-1])
            sheet_name2statistics = dict()
            statistics_list = list()
            actdomain_send_flag = False
            for sheet_name, cases in p1_excel.get("sheet_name2cases", dict()).items():

                count_exe = count_unexe = count_pass = count_fail = count_noresult = 0

                # 非活跃的处理
                for casename, case_list in cases.items():
                    if case_list[0].get("执行状态", 0) not in (0, "0", "", None):
                        count_exe += 1
                        cases_result = case_list[0].get("结果", None)
                        if cases_result == "Pass":
                            count_pass += 1
                        elif cases_result == "Failed":
                            count_fail += 1
                        else:
                            count_noresult += 1
                    else:
                        count_unexe += 1


                success_rate = count_pass / count_exe if count_exe else 0.0
                sheet_name2statistics[sheet_name] = {"count_exe": count_exe, "count_unexe": count_unexe,
                                                     "count_pass": count_pass, "count_fail": count_fail,
                                                     "count_noresult": count_noresult, "success_rate": success_rate}

                statistics_list.append(
                    [sheet_name, count_exe, count_pass, count_fail, count_noresult, f"{success_rate:.2%}",
                     f"{sheet_name2minutes.get(sheet_name, 0)} 分钟"])
                logger.info(
                    f"sheet:{sheet_name}\tcount_exe:{count_exe}\tcount_pass:{count_pass}\tcount_fail:{count_fail}\tcount_noresult:{count_noresult}\tsuccess_rate:{success_rate:.2%}")

            # 转换为小时和分钟
            total_minutes = sum(sheet_name2minutes.values())
            hours = int(total_minutes * 60 // 3600)
            minutes = int(((total_minutes * 60) % 3600) // 60)
            logger.info(f"执行总耗时：{hours} 小时 {minutes} 分钟")

            statistics_list = [["sheet", "执行数量", "成功数量", "失败数量", "未执行数量", "成功率",
                                "执行时间"]] + statistics_list + [
                                  ["", "", "", "", "", "", f"{hours} 小时 {minutes} 分钟"]]
            xlsx.write_range_values(sheet_index="结果统计", value=statistics_list, row1=0, col1=0)

            xlsx.save(path=path_save)
            xlsx.close()

        finally:

            # 确保所有资源都被正确关闭
            if 'xlsx' in locals():
                try:
                    xlsx.close()
                except:
                    pass


    # if not args.file:
    #     for file in glob("*.xlsx"):
    #         run(file)
    # else:
    #     run(excel_path=args.file, sheet=args.sheet)

    # # # # run(excel_path="用例_移动131.xlsx", sheet="mirrorvlan")
    for i in range(1):
        logger.info(str(i))
        run(excel_path=r"E:\PycharmProjects\dpiAutoExcel\用例_升级.xlsx", sheet="install")
