#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
从 RDM 平台提取发布路径信息 - 基于 HTML 解析的稳定版本
直接从列表页提取发布路径，不需要进入详情页
支持单个项目和多个项目提取
"""

import os
import sys
import time
import json
import re
from datetime import datetime
from playwright.sync_api import sync_playwright, Page
from utils.common import setup_logging

logger = setup_logging(log_file_path="log/rdm_extractor.log", logger_name="rdm_extractor")
from bs4 import BeautifulSoup


def get_base_dir():
    """获取程序基准目录，兼容 PyInstaller exe 和源码运行两种模式"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_release_path_info(
    base_url: str = "https://10.128.4.196:2000",
    username: str = "weihang",
    password: str = "12345678",
    project_name: str = "信息安全执行单元V1.0.6.0",
    headless: bool = True,
    debug: bool = True,
    verbose: bool = False
) -> dict:
    """
    从 RDM 平台提取单个项目的发布路径信息

    Args:
        base_url: RDM 平台地址
        username: 用户名
        password: 密码
        project_name: 项目名称
        headless: 是否无头模式
        debug: 是否开启调试模式（保存截图和步骤）
        verbose: 是否输出详细日志

    Returns:
        dict: 包含 success, data, error 等字段
    """
    # exe 模式下设置浏览器路径
    if getattr(sys, 'frozen', False):
        base_dir = get_base_dir()
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(base_dir, "browsers")

    with sync_playwright() as p:
        # 优先使用 Chrome，如果不存在则尝试 Edge，最后使用 Chromium
        browser = None
        for channel in ["chrome", "msedge", "chromium"]:
            try:
                browser = p.chromium.launch(
                    headless=headless,
                    channel=channel  # 使用系统浏览器
                )
                if verbose:
                    print(f"使用浏览器: {channel}")
                break
            except Exception as e:
                if verbose:
                    print(f"尝试 {channel} 失败: {str(e)[:100]}")
                continue

        if not browser:
            raise RuntimeError("未找到可用的浏览器，请安装 Chrome 或 Edge")

        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()

        try:
            # 登录
            _login(page, base_url, username, password, debug, verbose)

            # 提取项目数据
            result = _extract_single_project(page, project_name, debug, verbose)

            return result

        finally:
            page.close()
            context.close()
            browser.close()


def get_multiple_projects_release_paths(
    projects: list,
    base_url: str = "https://10.128.4.196:2000",
    username: str = "weihang",
    password: str = "12345678",
    headless: bool = True,
    debug: bool = True,
    verbose: bool = False
) -> dict:
    """
    一次登录，获取多个项目的发布路径信息

    Args:
        projects: 项目名称列表
        base_url: RDM 平台地址
        username: 用户名
        password: 密码
        headless: 是否无头模式
        debug: 是否开启调试模式
        verbose: 是否输出详细日志

    Returns:
        dict: {project_name: {version: [paths]}, ...}
    """
    all_results = {}

    # exe 模式下设置浏览器路径
    if getattr(sys, 'frozen', False):
        base_dir = get_base_dir()
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(base_dir, "browsers")

    with sync_playwright() as p:
        # 优先使用 Chrome，如果不存在则尝试 Edge，最后使用 Chromium
        browser = None
        for channel in ["chrome", "msedge", "chromium"]:
            try:
                browser = p.chromium.launch(
                    headless=headless,
                    channel=channel  # 使用系统浏览器
                )
                if verbose:
                    print(f"使用浏览器: {channel}")
                break
            except Exception as e:
                if verbose:
                    print(f"尝试 {channel} 失败: {str(e)[:100]}")
                continue

        if not browser:
            raise RuntimeError("未找到可用的浏览器，请安装 Chrome 或 Edge")

        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()

        try:
            # 登录一次
            _login(page, base_url, username, password, debug, verbose)

            # 循环处理每个项目
            for idx, project_name in enumerate(projects, 1):
                if verbose:
                    print(f"\n{'='*60}")
                    print(f"正在处理项目 {idx}/{len(projects)}: {project_name}")
                    print(f"{'='*60}")

                try:
                    result = _extract_single_project(page, project_name, debug, verbose)

                    if result["success"]:
                        all_results[project_name] = result["data"]
                        if verbose:
                            print(f"[成功] 提取 {len(result['data'])} 个版本")
                    else:
                        # 失败时不保存错误数据，只记录日志
                        if verbose:
                            print(f"[失败] {result['error']}")

                except Exception as e:
                    # 异常时不保存错误数据，只记录日志
                    if verbose:
                        print(f"[异常] {str(e)}")

                # 如果不是最后一个项目，返回首页准备下一个
                if idx < len(projects):
                    if verbose:
                        print(f"\n准备处理下一个项目...")

                    # 尝试返回首页（带重试）
                    home_success = False
                    for retry in range(2):
                        try:
                            timeout = 30000 if retry == 0 else 60000  # 第2次加长超时
                            page.goto(base_url + "/main.do", timeout=timeout)
                            time.sleep(3)
                            home_success = True
                            break
                        except Exception as e:
                            if verbose:
                                print(f"第 {retry + 1} 次返回首页失败: {str(e)}")
                            if retry == 0:
                                # 第1次失败，尝试点击 home 图标
                                try:
                                    page.click('img.rdm-home', timeout=15000)
                                    time.sleep(2)
                                    home_success = True
                                    break
                                except:
                                    pass

                    if not home_success and verbose:
                        print("警告：无法返回首页，可能影响下一个项目的处理")

        finally:
            page.close()
            context.close()
            browser.close()

    return all_results


def _login(page: Page, base_url: str, username: str, password: str, debug: bool, verbose: bool):
    """登录 RDM 平台"""
    if verbose:
        print("正在登录...")

    page.goto(base_url, timeout=60000)
    page.fill('input[id="userName"]', username)
    page.fill('input[type="password"]', password)
    page.click('input[type="submit"][value*="登录"]')
    page.wait_for_load_state("networkidle", timeout=30000)
    time.sleep(2)

    if verbose:
        print("登录成功")


def _extract_single_project(page: Page, project_name: str, debug: bool, verbose: bool) -> dict:
    """
    提取单个项目的发布路径信息（复用已登录的 page）

    Args:
        page: 已登录的 Playwright Page 对象
        project_name: 项目名称
        debug: 是否开启调试模式
        verbose: 是否输出详细日志

    Returns:
        dict: 包含 success, data, error 等字段
    """
    result = {
        "success": False,
        "data": {},
        "error": None
    }

    if debug:
        result["project_name"] = project_name
        result["timestamp"] = datetime.now().isoformat()
        result["steps"] = []

    steps = []

    def log_step(message):
        steps.append(message)
        if verbose:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

    # 创建临时目录
    temp_dir = os.path.join(os.path.dirname(__file__), "temp_files")
    os.makedirs(temp_dir, exist_ok=True)

    def save_screenshot(name):
        if debug:
            try:
                # 添加项目名称到截图文件名，避免覆盖
                safe_project_name = project_name.replace('/', '_').replace('\\', '_')[:30]
                screenshot_path = os.path.join(temp_dir, f"{safe_project_name}_{name}.png")
                page.screenshot(path=screenshot_path)
                log_step(f"截图已保存：{screenshot_path}")
            except:
                pass

    try:
        # 1. 点击左上角 home 图标展开菜单
        log_step("正在点击左上角 home 图标展开菜单...")
        try:
            page.click('img.rdm-home', timeout=10000)
            time.sleep(2)
            log_step("已点击 home 图标")
        except:
            log_step("点击 home 图标失败，可能菜单已展开")
        save_screenshot("01_home_clicked")

        # 2. 点击"项目管理"（带重试）
        log_step("正在点击项目管理...")
        clicked = False
        for retry in range(3):
            try:
                timeout = 10000 if retry < 2 else 30000  # 第3次用更长的超时
                if retry == 0:
                    # 优先尝试：使用 val 属性选择器
                    page.locator('span[val="项目管理"]').click(timeout=timeout)
                elif retry == 1:
                    # 备选1：使用文本匹配选择器
                    page.locator('span:has-text("项目管理")').first.click(timeout=timeout)
                elif retry == 2:
                    # 备选2：使用 JavaScript 直接触发点击事件
                    log_step("使用 JavaScript 方式点击项目管理...")
                    page.evaluate('document.querySelector(\'span[val="项目管理"]\').click()')
                page.wait_for_load_state("networkidle", timeout=30000)
                time.sleep(2)
                log_step("已进入项目管理页面")
                clicked = True
                break
            except Exception as e:
                if retry < 2:
                    log_step(f"第 {retry + 1} 次点击项目管理失败，准备重试...")
                    # 可能菜单没展开，尝试点击 home 图标
                    try:
                        page.click('img.rdm-home', timeout=5000)
                        time.sleep(1)
                    except:
                        pass
                else:
                    raise Exception(f"点击项目管理失败: {str(e)}")
        save_screenshot("02_project_management")

        # 3. 点击项目进入（带重试）
        log_step("正在进入项目详情...")
        time.sleep(3)  # 等待项目列表加载

        # 在iframe中查找并点击项目链接
        iframe = page.frame_locator('#main')

        # 使用更精确的选择器：查找包含项目名称的链接
        for retry in range(2):
            try:
                timeout = 10000 if retry == 0 else 20000
                # 先尝试精确匹配
                iframe.locator(f'a:has-text("{project_name}")').first.click(timeout=timeout)
                log_step(f"点击项目链接成功：{project_name}")
                break
            except Exception as e:
                if retry == 0:
                    log_step(f"精确匹配失败，尝试部分匹配...")
                    # 尝试部分匹配
                    try:
                        # 提取项目名称的前几个字符进行部分匹配
                        partial_name = project_name.split('V')[0].strip()
                        iframe.locator(f'a:has-text("{partial_name}")').first.click(timeout=20000)
                        log_step(f"使用部分匹配点击成功：{partial_name}")
                        break
                    except Exception as e2:
                        log_step(f"部分匹配也失败，准备重试...")
                        # 刷新页面重试
                        try:
                            page.reload(timeout=30000)
                            time.sleep(3)
                        except:
                            pass
                else:
                    # 修复：使用 e 而不是 e2
                    raise Exception(f"无法点击项目：{str(e)[:100]}")

        # 等待页面跳转到项目详情页
        log_step("等待页面跳转...")
        time.sleep(5)

        # 等待项目详情页的特征元素出现
        try:
            page.wait_for_url("**/entity.jsf**", timeout=10000)
            log_step("已跳转到项目详情页")
        except:
            log_step("等待URL跳转超时，继续执行...")

        log_step("已进入项目详情页面")
        save_screenshot("03_project_detail")

        # 4. 点击"提测申请（亚鸿）"标签 - 使用精确定位（带重试）
        log_step("正在点击提测申请标签页...")

        # 先找到 entityTab frame 对象
        entityTab_frame = None
        for retry in range(2):
            for frame in page.frames:
                if 'entityTab.project.jsf' in frame.url:
                    entityTab_frame = frame
                    log_step(f"找到 entityTab frame: {frame.url[:80]}")
                    break

            if entityTab_frame:
                break
            else:
                if retry == 0:
                    log_step(f"未找到 entityTab frame，等待后重试...")
                    time.sleep(3)
                else:
                    raise Exception("无法找到 entityTab frame")

        # 使用 frame 的 locator 方法精确定位并点击（带重试）
        for retry in range(2):
            try:
                timeout = 10000 if retry == 0 else 20000
                log_step("尝试通过 ID 定位标签 li#li_WF16...")
                entityTab_frame.locator('li#li_WF16').click(timeout=timeout)
                log_step("成功点击 li#li_WF16")
                break
            except Exception as e:
                if retry == 0:
                    log_step(f"通过 ID 定位失败: {str(e)[:100]}")
                    # 备选方案：通过文本定位
                    try:
                        log_step("尝试通过文本定位...")
                        entityTab_frame.locator('li:has-text("提测申请（亚鸿）")').click(timeout=20000)
                        log_step("成功通过文本点击")
                        break
                    except Exception as e2:
                        log_step(f"通过文本定位也失败: {str(e2)[:100]}")
                        # 等待后重试
                        time.sleep(2)
                else:
                    # 修复：使用 e 而不是 e2
                    raise Exception(f"无法点击提测申请标签: {str(e)[:100]}")

        log_step("等待列表内容加载...")
        time.sleep(5)

        # 等待新的 frame 出现
        log_step("等待新 frame 加载...")
        max_wait = 20
        found_list_frame = False
        for i in range(max_wait):
            for frame in page.frames:
                if ('belongList.jsf' in frame.url and 'type=WF16' in frame.url) or \
                   ('list.jsf' in frame.url and 'WF16' in frame.url):
                    found_list_frame = True
                    log_step(f"在第 {i+1} 秒找到列表 frame")
                    break
            if found_list_frame:
                break
            time.sleep(1)

        # 额外等待确保内容完全加载
        time.sleep(3)

        save_screenshot("04_test_application")

        # 5. 获取列表页 HTML 并解析
        log_step("正在查找包含数据的 frame...")

        # 查找 tabs_panel_12 对应的实际 frame 对象
        list_frame = None

        # 方式1: 查找 belongList.jsf 且包含 type=WF16
        for frame in page.frames:
            if 'belongList.jsf' in frame.url and 'type=WF16' in frame.url:
                list_frame = frame
                log_step(f"找到 belongList frame: {frame.url[:100]}")
                break

        # 方式2: 如果没找到，查找 list.jsf 且包含 WF16
        if not list_frame:
            log_step("未找到 belongList frame，尝试查找 list.jsf...")
            for frame in page.frames:
                if 'list.jsf' in frame.url and 'WF16' in frame.url:
                    list_frame = frame
                    log_step(f"找到 list.jsf frame: {frame.url[:100]}")
                    break

        # 方式3: 遍历所有 frame 查找包含表格的
        if not list_frame:
            log_step("尝试在所有 frame 中查找包含表格的...")
            for idx, frame in enumerate(page.frames):
                try:
                    if 'about:blank' in frame.url:
                        continue
                    html = frame.content()
                    # 检查是否包含表格且包含"发布路径"列
                    if 'body-table' in html and 'Fld_A_00031' in html:
                        list_frame = frame
                        log_step(f"在 Frame {idx} 找到包含发布路径的表格: {frame.url[:100]}")
                        break
                except:
                    continue

        if not list_frame:
            raise Exception("无法找到列表 frame")

        # 获取 HTML 内容
        html_content = list_frame.content()

        if debug:
            safe_project_name = project_name.replace('/', '_').replace('\\', '_')[:30]
            html_path = os.path.join(temp_dir, f"{safe_project_name}_list_page.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            log_step(f"列表页 HTML 已保存：{html_path}")

        # 使用 BeautifulSoup 解析
        soup = BeautifulSoup(html_content, 'html.parser')

        # 6. 找到表头，确定列索引
        log_step("正在查找表头...")

        thead = soup.find('table', class_='head-table')
        if not thead:
            raise Exception("未找到表头")

        # 表头有两行，取第二行（真正的列名行）
        header_rows = thead.find_all('tr')
        if len(header_rows) < 2:
            raise Exception("表头结构异常")

        headers = header_rows[1].find_all('th')
        title_index = -1
        release_path_index = -1
        project_index = -1

        for idx, th in enumerate(headers):
            name = th.get('name')
            if name == 'Name':
                title_index = idx
                log_step(f"找到标题列索引：{title_index}")
            elif name == 'Fld_A_00031':
                release_path_index = idx
                log_step(f"找到发布路径列索引：{release_path_index}")
            elif name == 'ProjectID':
                project_index = idx
                log_step(f"找到所属项目列索引：{project_index}")

        if title_index == -1:
            raise Exception("未找到标题列")
        if release_path_index == -1:
            raise Exception("未找到发布路径列")
        if project_index == -1:
            raise Exception("未找到所属项目列")

        # 7. 提取所有记录
        log_step("正在提取所有记录...")

        body_table = soup.find('table', class_='body-table')
        if not body_table:
            raise Exception("未找到数据表格")

        all_rows = body_table.select('tbody tr[id]')
        log_step(f"找到 {len(all_rows)} 条记录")

        data = {}
        for row in all_rows:
            cells = row.find_all('td')

            if title_index >= len(cells) or release_path_index >= len(cells) or project_index >= len(cells):
                continue

            # 获取所属项目
            project_cell = cells[project_index]
            project_text = project_cell.get_text(strip=True)

            # 过滤：只保留指定项目的记录
            # 移除空格进行比较，因为HTML中可能没有空格
            project_name_normalized = project_name.replace(' ', '')
            project_text_normalized = project_text.replace(' ', '')

            if project_name_normalized not in project_text_normalized:
                continue

            title_cell = cells[title_index]
            title = title_cell.get_text(strip=True)

            release_path_cell = cells[release_path_index]
            release_path = release_path_cell.get_text(strip=True)

            if title:
                # 如果标题已存在且新路径不为空，直接替换
                if title in data:
                    if release_path:  # 新路径不为空，直接替换
                        data[title] = release_path
                    # 如果新路径为空，保持原有路径不变
                else:
                    # 标题不存在，直接添加
                    data[title] = release_path
                log_step(f"提取记录：{title[:50]}...")

        if data:
            result["success"] = True
            result["data"] = data
            log_step(f"成功提取 {len(data)} 条记录")
        else:
            log_step("未提取到任何记录")
            result["error"] = "未提取到任何记录"

        save_screenshot("05_final")

    except Exception as e:
        log_step(f"发生错误：{e}")
        result["error"] = str(e)
        save_screenshot("error_final")

    finally:
        if debug:
            result["steps"] = steps

    # 二次处理：提取版本号并重组数据
    if result["success"] and result["data"]:
        log_step("开始二次处理数据...")
        processed_data = process_release_data(result["data"])
        result["data"] = processed_data
        log_step(f"二次处理完成，共 {len(processed_data)} 个版本")

    return result


def process_release_data(raw_data: dict) -> dict:
    """
    二次处理发布路径数据

    从路径中提取版本号，并将该标题下的所有路径归属于该版本号

    Args:
        raw_data: 原始数据，格式为 {title: release_path_string}

    Returns:
        处理后的数据，格式为 {version: [path1, path2, ...]}
    """
    # 版本号正则：从路径中匹配 EU- 或 ISE- 后面的版本号
    version_pattern = re.compile(r'(?:EU-|ISE-|NSE-|DSE-)(\d+\.\d+\.\d+\.\d+-[^_]+)_202')

    processed = {}

    for title, release_path_string in raw_data.items():
        # 按逗号分割路径，去空
        paths = [p.strip() for p in release_path_string.split(',') if p.strip()]

        if not paths:
            continue  # 如果没有路径，跳过

        # 从第一个路径中提取版本号
        version = None
        for path in paths:
            match = version_pattern.search(path)
            if match:
                version = match.group(1)
                break

        if not version:
            continue  # 如果没有匹配到版本号，跳过这组数据

        # 如果版本号不存在，创建新列表
        if version not in processed:
            processed[version] = []

        # 将所有路径添加到该版本号下
        for path in paths:
            if path not in processed[version]:  # 去重
                processed[version].append(path)

    return processed


def save_versions_to_json(
    version_data: dict,
    category: str,
    json_file: str = None
) -> dict:
    """
    保存版本数据到 JSON 文件，并返回对比结果

    Args:
        version_data: 提取的版本数据
                     格式1: {version: [paths]} - 单项目
                     格式2: {project_name: {version: [paths]}} - 多项目
        category: 类型/分类名称，作为 JSON 的 key
        json_file: JSON 文件路径

    Returns:
        对比结果字典:
        {
            "status": "created/updated",
            "category": "分类名称",
            "file": "文件路径",
            "all_versions": ["1.0.6.0-1", "1.0.6.0-2", ...],  # 所有版本号列表
            "changes": {
                "new_versions": ["版本1", "版本2"],
                "updated_versions": {
                    "版本3": {
                        "added_paths": ["新增路径"],
                        "removed_paths": ["删除路径"]
                    }
                },
                "unchanged_versions": ["版本4", "版本5"]
            },
            "summary": {
                "total_versions": 10,
                "new_count": 2,
                "updated_count": 1,
                "unchanged_count": 7
            }
        }
    """
    # 如果 json_file 为 None，使用 exe 目录下的 versions.json
    if json_file is None:
        json_file = os.path.join(get_base_dir(), "versions.json")

    result = {
        "status": "created",
        "category": category,
        "file": json_file,
        "all_versions": [],
        "changes": {
            "new_versions": [],
            "updated_versions": {},
            "unchanged_versions": []
        },
        "summary": {
            "total_versions": 0,
            "new_count": 0,
            "updated_count": 0,
            "unchanged_count": 0
        }
    }

    # 检测数据格式：单项目还是多项目
    # 如果第一个值是字典，说明是多项目格式
    is_multi_project = False
    if version_data:
        first_value = next(iter(version_data.values()))
        if isinstance(first_value, dict) and first_value:
            # 检查第二层的值是否是列表
            second_value = next(iter(first_value.values()))
            if isinstance(second_value, list):
                is_multi_project = True

    # 1. 读取现有 JSON 文件
    existing_data = {}
    if os.path.exists(json_file):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
            result["status"] = "updated"
        except Exception as e:
            # 文件损坏或格式错误，备份后重新创建
            backup_file = json_file + ".backup"
            try:
                os.rename(json_file, backup_file)
            except:
                pass
            existing_data = {}

    # 2. 获取该分类的旧数据
    old_category_data = existing_data.get(category, {})

    # 3. 根据格式处理数据
    if is_multi_project:
        # 多项目格式：过滤空数据后再保存
        new_category_data = {}

        # 收集所有版本号
        all_versions_set = set()

        for project_name, project_versions in version_data.items():
            # 过滤空项目
            if not project_versions:
                continue

            # 过滤空版本
            filtered_versions = {}
            for version, paths in project_versions.items():
                # 过滤空路径列表
                if paths and len(paths) > 0:
                    filtered_versions[version] = paths
                    all_versions_set.add(version)

            # 只保存有数据的项目
            if filtered_versions:
                new_category_data[project_name] = filtered_versions

        result["all_versions"] = sorted(list(all_versions_set))
        result["summary"]["total_versions"] = len(all_versions_set)

        # 对比每个项目的每个版本
        for project_name, project_versions in new_category_data.items():
            old_project_data = old_category_data.get(project_name, {})

            for version, new_paths in project_versions.items():
                version_key = f"{project_name}/{version}"
                new_paths_set = set(new_paths)

                if version not in old_project_data:
                    # 新版本
                    result["changes"]["new_versions"].append(version_key)
                    result["summary"]["new_count"] += 1
                else:
                    # 已存在的版本，检查路径是否有变化
                    old_paths_set = set(old_project_data[version])

                    added_paths = list(new_paths_set - old_paths_set)
                    removed_paths = list(old_paths_set - new_paths_set)

                    if added_paths or removed_paths:
                        # 有变化
                        result["changes"]["updated_versions"][version_key] = {
                            "added_paths": added_paths,
                            "removed_paths": removed_paths
                        }
                        result["summary"]["updated_count"] += 1
                    else:
                        # 无变化
                        result["changes"]["unchanged_versions"].append(version_key)
                        result["summary"]["unchanged_count"] += 1
    else:
        # 单项目格式：过滤空数据后再保存
        new_category_data = {}

        # 收集所有版本号
        all_versions_set = set()

        for version, paths in version_data.items():
            # 过滤空路径列表
            if paths and len(paths) > 0:
                new_category_data[version] = paths
                all_versions_set.add(version)

        result["all_versions"] = sorted(list(all_versions_set))
        result["summary"]["total_versions"] = len(all_versions_set)

        # 对比新旧数据
        for version, new_paths in new_category_data.items():
            new_paths_set = set(new_paths)

            if version not in old_category_data:
                # 新版本
                result["changes"]["new_versions"].append(version)
                result["summary"]["new_count"] += 1
            else:
                # 已存在的版本，检查路径是否有变化
                old_paths_set = set(old_category_data[version])

                added_paths = list(new_paths_set - old_paths_set)
                removed_paths = list(old_paths_set - new_paths_set)

                if added_paths or removed_paths:
                    # 有变化
                    result["changes"]["updated_versions"][version] = {
                        "added_paths": added_paths,
                        "removed_paths": removed_paths
                    }
                    result["summary"]["updated_count"] += 1
                else:
                    # 无变化
                    result["changes"]["unchanged_versions"].append(version)
                    result["summary"]["unchanged_count"] += 1

    # 4. 合并数据（以版本号为维度，追加不同的路径）
    if is_multi_project:
        # 多项目格式：合并每个项目下的每个版本
        merged_category_data = old_category_data.copy()

        for project_name, project_versions in new_category_data.items():
            if project_name not in merged_category_data:
                # 新项目，直接添加
                merged_category_data[project_name] = project_versions
            else:
                # 已存在的项目，合并版本
                old_project_data = merged_category_data[project_name]

                for version, new_paths in project_versions.items():
                    if version not in old_project_data:
                        # 新版本，直接添加
                        old_project_data[version] = new_paths
                    else:
                        # 已存在的版本，合并路径（去重）
                        old_paths = old_project_data[version]
                        merged_paths = list(set(old_paths + new_paths))
                        old_project_data[version] = merged_paths

        existing_data[category] = merged_category_data
    else:
        # 单项目格式：合并每个版本的路径
        merged_category_data = old_category_data.copy()

        for version, new_paths in new_category_data.items():
            if version not in merged_category_data:
                # 新版本，直接添加
                merged_category_data[version] = new_paths
            else:
                # 已存在的版本，合并路径（去重）
                old_paths = merged_category_data[version]
                merged_paths = list(set(old_paths + new_paths))
                merged_category_data[version] = merged_paths

        existing_data[category] = merged_category_data

    # 5. 保存到 JSON 文件
    try:
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        result["error"] = f"保存文件失败: {str(e)}"

    return result


if __name__ == "__main__":
    print("=" * 60)
    print("RDM 平台发布路径提取工具")
    print("=" * 60)
    print()


    # 示例2: 提取多个项目
    print("\n" + "=" * 60)
    print("示例2: 提取多个项目")
    print("-" * 60)
    projects = [
        "信息安全执行单元V1.0.7.0"
    ]

    results = get_multiple_projects_release_paths(
        projects=projects,
        debug=True,
        verbose=True,
        headless=True,username="weihang",password="Qq111222"
    )

    print("\n多个项目结果:")
    print(json.dumps(results, ensure_ascii=False, indent=2))

    print(save_versions_to_json(version_data=results, category="信息安全执行单元"))
