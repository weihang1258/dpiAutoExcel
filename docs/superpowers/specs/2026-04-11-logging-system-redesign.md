# 日志系统重新设计方案

**日期：** 2026-04-11
**项目：** DPI 安装升级测试框架
**方案类型：** 最小改动方案

---

## 一、需求概述

### 1.1 核心需求

1. 每次执行程序生成唯一会话ID
2. 每个用例生成独立的日志文件
3. 日志输出格式更加合理、优雅、美观
4. 用例之间有明显的分隔标识
5. 用例名称显示明显

### 1.2 设计决策

- **会话定义：** 每次运行 `main.py` 算一个会话
- **日志文件组织：** 只保存单个用例日志文件，无总览文件
- **控制台输出：** 实时显示所有用例的日志（混合输出）
- **日志文件命名：** `{会话ID}_{用例名称}.log`
- **日志存放位置：** 统一存放在 `logs/` 目录下

---

## 二、整体架构

### 2.1 核心改动点

1. 修改 `common.py` 中的 `setup_logging` 函数，支持新的日志格式
2. 在 `main.py` 启动时生成会话ID
3. 在 `dpiinstall.py` 中为每个用例动态创建独立的 logger 和日志文件
4. 用例执行完毕后关闭当前 logger

### 2.2 数据流

```
main.py 启动
  ↓
生成会话ID (YYYYMMDDHHMMSS)
  ↓
遍历用例
  ↓
每个用例开始 → 创建新 logger (logs/{会话ID}_{用例名}.log)
  ↓
执行用例 → 日志输出到控制台 + 当前用例日志文件
  ↓
用例结束 → 关闭当前 logger
  ↓
下一个用例...
```

---

## 三、详细设计

### 3.1 会话ID生成

**位置：** `main.py` 程序启动时

**格式：** `YYYYMMDDHHMMSS`（例如：`20260411143025`）

**实现：**
```python
import datetime

# 在 main.py 开头生成会话ID
session_id = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
```

**传递方式：**
- 将 `session_id` 作为参数传递给 `install` 函数
- `install` 函数签名增加 `session_id` 参数

**示例：**
```python
# main.py
session_id = datetime.datetime.now().strftime('%Y%m%d%H%M%S')

# 调用 install 时传入
install(..., session_id=session_id)
```

---

### 3.2 日志格式改进

**位置：** `common.py` 中的 `setup_logging` 函数

**时间戳格式：**
- 原格式：`2026-04-11 14:30:25-install-INFO-消息`
- 新格式：`[2026-04-11 14:30:25] [install] [INFO] 消息`

**日志级别符号前缀：**
- INFO → `✓ INFO`
- WARNING → `⚠ WARNING`
- ERROR → `✗ ERROR`
- DEBUG → `DEBUG`（保持不变）

**实现方式：**
```python
# 修改 Formatter 格式
file_format = logging.Formatter(
    '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
console_format = logging.Formatter(
    '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
```

**符号前缀添加方式：**
在记录日志时手动添加符号前缀：
```python
logger.info("✓ 安装成功")
logger.warning("⚠ 未找到备份")
logger.error("✗ 连接失败")
```

---

### 3.3 用例分隔样式

**位置：** `dpiinstall.py` 中每个用例开始执行时

**分隔样式：**
```
──────────────────────────────────────────────────────────────────────────────
用例：全新安装
──────────────────────────────────────────────────────────────────────────────
```

**实现方式：**
```python
def print_case_separator(case_name, logger):
    """打印用例分隔符"""
    separator = "─" * 78
    logger.info(separator)
    logger.info(f"用例：{case_name}")
    logger.info(separator)
```

**调用时机：**
- 在 `dpiinstall.py` 的 `install` 函数中，每个用例开始执行前调用

---

### 3.4 用例级别 Logger 管理

**位置：** `dpiinstall.py` 中的 `install` 函数

**实现逻辑：**

#### 3.4.1 创建用例 logger

```python
def create_case_logger(session_id, case_name, logger_name="install"):
    """为单个用例创建独立的 logger"""
    # 清理用例名称
    safe_case_name = sanitize_case_name(case_name)

    # 生成日志文件名
    log_file = f"logs/{session_id}_{safe_case_name}.log"

    # 创建新的 logger
    case_logger = setup_logging(
        log_file_path=log_file,
        logger_name=f"{logger_name}_{session_id}_{case_name}",
        encoding="utf-8"
    )

    return case_logger
```

#### 3.4.2 用例执行流程

```python
# install 函数中
# 保存原始全局 logger 的引用
from common import logger as global_logger

for case_name, case_list in cases.items():
    # 创建用例专属 logger
    case_logger = create_case_logger(session_id, case_name)

    # 临时替换全局 logger（如果其他模块使用全局 logger）
    import common
    original_logger = common.logger
    common.logger = case_logger

    # 打印用例分隔
    print_case_separator(case_name, case_logger)

    try:
        # 执行用例（使用 case_logger 记录日志）
        # 所有日志调用都会使用 case_logger
        # ...
    finally:
        # 用例结束，关闭 logger handlers
        for handler in case_logger.handlers[:]:
            handler.close()
            case_logger.removeHandler(handler)

        # 恢复全局 logger
        common.logger = original_logger
```

**注意：** 如果 `dpiinstall.py` 中使用全局 `logger` 对象，需要在用例执行前临时替换为 `case_logger`，执行后恢复。

---

### 3.5 错误处理和边界情况

#### 3.5.1 日志目录不存在
- `setup_logging` 函数已有处理：自动创建日志目录

#### 3.5.2 用例名称包含特殊字符
- 用例名称可能包含 `/`、`\`、`:` 等文件系统不支持的字段
- 需要对用例名称进行清理，替换特殊字符为下划线

**实现：**
```python
import re

def sanitize_case_name(case_name):
    """清理用例名称，移除或替换文件系统不支持的字段"""
    # 替换特殊字符为下划线
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', case_name)
    return sanitized
```

#### 3.5.3 同一用例多次执行
- 日志文件会被覆盖（当前 `setup_logging` 会清空已存在的文件）
- 这是预期行为，保持不变

#### 3.5.4 logger 未正确关闭
- 可能导致文件句柄泄漏
- 使用 try-finally 确保清理

---

## 四、实现步骤

### 4.1 需要修改的文件

#### 文件 1：`common.py`
- 修改 `setup_logging` 函数中的日志格式
- 时间戳格式：`[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s`
- 日期格式：`datefmt='%Y-%m-%d %H:%M:%S'`

#### 文件 2：`main.py`
- 在程序启动时生成会话ID
- 将会话ID传递给 `install` 函数

#### 文件 3：`dpiinstall.py`
- 修改 `install` 函数签名，增加 `session_id` 参数
- 添加 `sanitize_case_name` 函数清理用例名称
- 添加 `create_case_logger` 函数创建用例级别 logger
- 添加 `print_case_separator` 函数打印用例分隔符
- 在用例循环中为每个用例创建独立 logger
- 用例结束时关闭 logger handlers

### 4.2 改动范围估算
- 约 3 个文件
- 新增约 50-80 行代码
- 修改约 10-20 行现有代码

---

## 五、核心特性总结

1. ✅ 每次运行生成唯一会话ID（格式：YYYYMMDDHHMMSS）
2. ✅ 每个用例独立日志文件（命名：`{会话ID}_{用例名称}.log`）
3. ✅ 日志统一存放在 `logs/` 目录
4. ✅ 日志格式优化：`[2026-04-11 14:30:25] [install] [INFO] 消息`
5. ✅ 日志级别添加符号前缀（✓ INFO、⚠ WARNING、✗ ERROR）
6. ✅ 用例分隔清晰（横线分隔 + 用例名单独一行）
7. ✅ 控制台实时显示所有用例日志
8. ✅ 错误处理完善（特殊字符清理、logger 生命周期管理）

---

## 六、方案选择理由

选择**最小改动方案**的原因：
1. 项目规模适中，不需要过度设计
2. 改动最小，风险可控
3. 能快速实现需求
4. 后续如果需要，可以逐步重构为会话管理器方案
