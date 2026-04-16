#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""构建发布包脚本：一键打包 exe + Excel 模板 + ps1 脚本"""
import subprocess
import sys
import os
import shutil
import zipfile

PROJ_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(PROJ_DIR, "dist_release")
BUILD_DIR = os.path.join(DIST_DIR, "build_temp")
RELEASE_DIR = os.path.join(DIST_DIR, "dpiAutoExcel_v1.0.0")
VERSION = "v1.0.0"


def run_cmd(cmd, cwd=None):
    print(f"\n>>> {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=cwd or PROJ_DIR)
    if r.returncode != 0:
        sys.exit(f"命令失败 (exit {r.returncode})")


def main():
    # 1. 安装 pyinstaller
    print("=== 1. 安装构建依赖 ===")
    run_cmd([sys.executable, "-m", "pip", "install", "pyinstaller", "-q"])

    # 2. 清理旧构建目录
    print("\n=== 2. 清理旧构建目录 ===")
    # 杀掉可能正在运行的 main_exe 进程，避免文件被占用
    subprocess.run("taskkill /F /IM main_exe.exe 2>nul", shell=True)
    if os.path.exists(DIST_DIR):
        import time
        time.sleep(1)
        shutil.rmtree(DIST_DIR, ignore_errors=True)
    os.makedirs(RELEASE_DIR)
    print(f"    已创建: {RELEASE_DIR}")

    # 3. PyInstaller 打包
    print("\n=== 3. PyInstaller 打包 main.exe ===")

    # 需要声明为 hidden-import 的第三方模块
    hidden_imports = [
        "playwright",
        "openpyxl",
        "yaml",
        "requests",
        "bs4",
        "ntplib",
        "dpiinstall",
        "extract_release_path",
    ]
    hidden_args = []
    for mod in hidden_imports:
        hidden_args += ["--hidden-import", mod]

    pyinstaller_cmd = [
        "pyinstaller",
        "--name", "main_exe",
        "--onefile",
        "--console",
        "--collect-all", "playwright",
        "--workpath", BUILD_DIR,
        f"--distpath={RELEASE_DIR}",
    ] + hidden_args + [
        os.path.join(PROJ_DIR, "main.py"),
    ]

    run_cmd(pyinstaller_cmd)

    # 4. 复制支持文件
    print("\n=== 4. 复制支持文件 ===")
    src_files = {
        os.path.join(PROJ_DIR, "用例_升级_模板.xlsx"): "用例_升级_模板.xlsx",
        os.path.join(PROJ_DIR, "bat_init.ps1"): "bat_init.ps1",
    }
    for src, name in src_files.items():
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(RELEASE_DIR, name))
            print(f"    已复制: {name}")
        else:
            print(f"    警告: 文件不存在: {src}")

    # 5. 生成 README.txt
    print("\n=== 5. 生成 README.txt ===")
    readme = """dpiAutoExcel 自动化测试工具 v1.0.0
=========================================

【快速开始】

1. 复制"用例_升级_模板.xlsx"，重命名为实际用例文件
   例如：信安_升级_v1.0.7.0.xlsx

2. 打开 Excel 文件，修改"配置"sheet 中的 RDM 和 FTP 凭证

3. 双击运行以下脚本之一：
   - bat_init.ps1   ：通过 PowerShell 执行，自动生成各 sheet 对应的执行脚本
   - main_exe.exe -f 信安_升级_v1.0.7.0.xlsx -s install

4. 执行结果和日志会写入 exe 同级目录下的 report/ 和 log/ 目录


【命令行参数】

  -f <文件>    指定 Excel 用例文件路径（必需）
  -s <sheet>   指定要执行的 sheet 名称（默认：install）
  -ps1         初始化 PowerShell 执行脚本（生成 exec_ps1/ 目录）
  -bat         初始化 bat 执行脚本（生成 exec_bat/ 目录）


【前置要求】

  - Windows 10 及以上
  - Chrome 或 Edge 浏览器（用于访问 RDM 平台）
  - RDM 平台账号权限


【常见问题】

  Q: 杀毒软件报警？
  A: 请将 main_exe.exe 添加到信任列表，这是正常的打包程序行为。

  Q: 首次运行报错"未找到浏览器"？
  A: 这表示系统没有安装 Chrome 或 Edge，请安装其中任意一款浏览器。

  Q: versions.json 是什么？
  A: RDM 版本缓存文件，由程序自动管理，删除后会自动重新获取。

  Q: 执行失败如何排查？
  A: 查看 exe 同级目录下的 log/common.log 日志文件。
"""
    with open(os.path.join(RELEASE_DIR, "README.txt"), "w", encoding="utf-8") as f:
        f.write(readme)
    print("    已生成: README.txt")

    # 6. 生成版本说明
    print("\n=== 6. 生成版本说明 ===")
    changelog = """版本说明 - v1.0.0
==================

本次发布：
- 全新打包发布，脱离 Python 环境运行
- 使用 PyInstaller onefile 单文件模式
- 依赖系统 Chrome/Edge 浏览器
- 内置版本缓存管理（versions.json）

系统要求：Windows 10 及以上
前置软件：Chrome 或 Edge 浏览器
"""
    with open(os.path.join(RELEASE_DIR, "版本说明.txt"), "w", encoding="utf-8") as f:
        f.write(changelog)
    print("    已生成: 版本说明.txt")

    # 7. 打包为 zip
    print("\n=== 7. 打包为 zip ===")
    zip_path = os.path.join(DIST_DIR, f"dpiAutoExcel_{VERSION}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(RELEASE_DIR):
            for file in files:
                fp = os.path.join(root, file)
                arcname = os.path.relpath(fp, DIST_DIR)
                zf.write(fp, arcname)
                print(f"    添加: {arcname}")

    print(f"\n{'='*50}")
    print(f"构建完成！")
    print(f"发布目录: {RELEASE_DIR}")
    print(f"zip 文件: {zip_path}")


if __name__ == "__main__":
    main()