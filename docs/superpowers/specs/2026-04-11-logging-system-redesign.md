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
- **分层日志策略：** 用例日志记录测试流程，模块日志记录技术细节

---

## 二、整体架构

### 2.1 核心改动点

1. 修改 `common.py` 中的 `setup_logging` 函数，优化日志格式
2. 在 `main.py` 启动时生成会话ID
3. 在 `dpiinstall.py` 中为每个用例动态创建独立的 logger 和日志文件
4. 用例执行完毕后关闭当前 logger
5. 保持其他模块的日志不变，实现分层日志

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
执行用例 → 用例日志输出到控制台 + 当前用例日志文件
         → 模块日志输出到各自的日志文件（comm.log、dpi.log 等）
  ↓
用例结束 → 关闭当前 logger
  ↓
下一个用例...
```

### 2.3 分层日志策略

**用例日志（dpiinstall.py）：**
- 记录测试流程和业务逻辑
- 包含：用例分隔符、参数解析、执行步骤、结果信息
- 每个用例独立文件，便于问题定位

**模块日志（其他模块）：**
- 记录技术细节和底层操作
- 包含：SSH 连接、FTP 传输、Linux 命令、DPI 操作等
- 保持原有日志文件（comm.log、dpi.log、linux.log 等）
- 便于调试技术问题

**优势：**
- 用例日志简洁清晰，专注于测试流程
- 模块日志详细完整，便于技术调试
- 互不干扰，各司其职

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

**改动点：**
- 在 `setup_logging` 函数中修改 Formatter 格式
- 无需修改现有的日志调用代码

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

**核心原则：**
- 不替换全局 logger
- 直接使用 `case_logger` 对象记录日志
- 需要时将 `case_logger` 作为参数传递给其他函数

#### 3.4.1 创建用例 logger

```python
def create_case_logger(session_id, case_name, logger_name="install"):
    """为单个用例创建独立的 logger"""
    # 清理用例名称
    safe_case_name = sanitize_case_name(case_name)

    # 生成日志文件名
    log_file = f"logs/{session_id}_{safe_case_name}.log"

    # 创建新的 logger（使用唯一的 logger_name）
    case_logger = setup_logging(
        log_file_path=log_file,
        logger_name=f"{logger_name}_{session_id}_{safe_case_name}",
        encoding="utf-8"
    )

    return case_logger
```

#### 3.4.2 用例执行流程

```python
# dpiinstall.py

# 模块级别的全局 logger（用于非用例场景）
logger = setup_logging(log_file_path="log/install.log", logger_name="install")

def install(..., session_id):
    """安装/升级主函数"""

    # 用例循环
    for case_name, case_list in cases.items():
        # 创建用例专属 logger
        case_logger = create_case_logger(session_id, case_name)

        # 打印用例分隔
        print_case_separator(case_name, case_logger)

        try:
            # 执行用例时，使用 case_logger 记录日志
            case_logger.info("开始执行用例...")

            # 调用其他函数时，传递 case_logger
            result = execute_case(case_list, case_logger, ...)

            case_logger.info(f"用例执行完成：{result}")
        except Exception as e:
            case_logger.error(f"用例执行失败：{e}")
        finally:
            # 关闭 logger handlers
            for handler in case_logger.handlers[:]:
                handler.close()
                case_logger.removeHandler(handler)
```

#### 3.4.3 函数参数化

需要将 `logger` 作为参数传递的函数：

**主要函数：**
1. `execute_case` - 执行单个用例
2. `dpi_install` - DPI 安装函数
3. 其他在 `dpiinstall.py` 中定义的辅助函数

**实现示例：**
```python
def execute_case(case_list, logger, ...):
    """执行单个用例"""
    logger.info("解析用例参数...")

    # 使用传入的 logger 记录日志
    logger.info(f"安装类型：{installtype}")
    logger.info(f"源版本：{dpiversion_s}，目标版本：{dpiversion_d}")

    # 调用其他函数时继续传递 logger
    result = dpi_install(..., logger=logger, ...)

    return result

def dpi_install(..., logger, ...):
    """DPI 安装函数"""
    logger.info("开始安装...")

    # 使用传入的 logger 记录日志
    # ...

    return result
```

**注意：**
- 所有需要记录用例日志的函数都需要增加 `logger` 参数
- 在函数内部使用传入的 `logger` 而不是全局 `logger`

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

#### 3.5.5 logger_name 唯一性
- 每个用例的 logger_name 必须唯一
- 格式：`{logger_name}_{session_id}_{safe_case_name}`
- 避免多个用例共享同一个 logger

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
- 修改相关函数，增加 `logger` 参数

### 4.2 需要参数化的函数列表

**主要函数：**
1. `install` - 增加 `session_id` 参数
2. `execute_case` - 增加 `logger` 参数（新增函数）
3. `dpi_install` - 增加 `logger` 参数
4. 其他在 `dpiinstall.py` 中定义的辅助函数

**实现方式：**
- 将 `logger` 作为参数传递
- 在函数内部使用传入的 `logger` 记录日志

### 4.3 改动范围估算
- 约 3 个文件
- 新增约 60-100 行代码
- 修改约 20-30 行现有代码
- 需要修改约 10-20 个函数签名

---

## 五、核心特性总结

1. ✅ 每次运行生成唯一会话ID（格式：YYYYMMDDHHMMSS）
2. ✅ 每个用例独立日志文件（命名：`{会话ID}_{用例名称}.log`）
3. ✅ 日志统一存放在 `logs/` 目录
4. ✅ 日志格式优化：`[2026-04-11 14:30:25] [install] [INFO] 消息`
5. ✅ 用例分隔清晰（横线分隔 + 用例名单独一行）
6. ✅ 控制台实时显示所有用例日志
7. ✅ 分层日志策略（用例日志 + 模块日志）
8. ✅ 错误处理完善（特殊字符清理、logger 生命周期管理）
9. ✅ 不影响其他模块的日志逻辑

---

## 六、方案选择理由

### 6.1 选择最小改动方案的原因

1. 项目规模适中，不需要过度设计
2. 改动最小，风险可控
3. 能快速实现需求
4. 后续如果需要，可以逐步重构为会话管理器方案

### 6.2 选择分层日志策略的原因

1. **职责分离：** 用例日志专注于测试流程，模块日志专注于技术细节
2. **可读性强：** 用例日志简洁清晰，不会被大量技术细节淹没
3. **便于调试：** 技术问题可以查看对应的模块日志
4. **改动最小：** 不需要修改其他模块的日志逻辑
5. **向后兼容：** 保持现有的日志文件结构

### 6.3 选择参数化 logger 的原因

1. **明确性：** 函数签名明确表示需要记录日志
2. **灵活性：** 可以根据上下文使用不同的 logger
3. **安全性：** 不依赖全局状态，避免意外修改
4. **可测试性：** 便于单元测试时注入 mock logger

---

## 七、实施注意事项

### 7.1 测试策略

1. **单元测试：** 测试 `sanitize_case_name`、`create_case_logger` 等辅助函数
2. **集成测试：** 测试完整的用例执行流程，验证日志文件正确生成
3. **边界测试：** 测试特殊字符用例名、并发执行等边界情况

### 7.2 向后兼容

1. 保持其他模块的日志文件不变
2. 保持现有的日志级别（DEBUG、INFO、WARNING、ERROR）
3. 保持现有的日志调用方式

### 7.3 性能考虑

1. 每个用例创建新 logger 会有轻微性能开销
2. 日志文件数量会随用例数量增加
3. 建议定期清理旧的日志文件

---

## 八、后续优化方向

如果后续需要进一步优化，可以考虑：

1. **会话管理器：** 封装 logger 创建和管理逻辑
2. **日志聚合：** 提供工具聚合用例日志和模块日志
3. **日志清理：** 自动清理过期日志文件
4. **日志分析：** 提供日志分析工具，提取关键信息
