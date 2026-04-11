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
6. 记录所有模块的日志到统一的日志文件

### 1.2 设计决策

- **会话定义：** 每次运行 `main.py` 算一个会话
- **日志文件组织：** 只保存单个用例日志文件，无总览文件
- **控制台输出：** 实时显示所有用例的日志（混合输出）
- **日志文件命名：** 由执行函数硬编码决定
  - 按用例拆分：`{会话ID}_{sheet名称}_{用例名称}.log`
  - 按 sheet 拆分：`{会话ID}_{sheet名称}.log`
- **日志存放位置：** 统一存放在 `logs/` 目录下
- **日志记录范围：** 记录所有模块的日志到统一文件
- **Sheet 执行方式：** 串行执行，不考虑并发

---

## 二、整体架构

### 2.1 核心改动点

1. 修改 `common.py` 中的 `setup_logging` 函数，优化日志格式
2. 在 `main.py` 启动时生成会话ID
3. 创建 `DynamicFileHandler` 类，实现动态切换日志输出文件
4. 在 `dpiinstall.py` 的 `install` 函数中：
   - Sheet 开始时创建 DynamicFileHandler
   - 根据硬编码策略决定日志拆分方式
   - 用例切换时动态切换日志文件（如果策略是按用例拆分）
   - Sheet 结束时关闭 DynamicFileHandler
5. 将 DynamicFileHandler 添加到所有模块的全局 logger

### 2.2 数据流

```
main.py 启动
  ↓
生成会话ID (YYYYMMDDHHMMSS)
  ↓
遍历 Sheet（串行）
  ↓
每个 Sheet 开始 → 创建 DynamicFileHandler
                 → 添加到所有模块的 logger
                 → 根据策略创建初始日志文件
  ↓
遍历用例
  ↓
每个用例开始 → 如果策略是按用例拆分：切换到新的日志文件
             → 打印用例分隔符
  ↓
执行用例 → 所有模块的日志输出到当前日志文件
         → 控制台实时显示
  ↓
用例结束
  ↓
下一个用例...
  ↓
Sheet 结束 → 关闭 DynamicFileHandler
  ↓
下一个 Sheet...
```

### 2.3 分层日志策略（已废弃）

**原设计：** 用例日志记录测试流程，模块日志记录技术细节

**新设计：** 所有模块的日志统一输出到当前日志文件

**优势：**
- 日志完整，便于问题定位
- 无需查看多个日志文件
- 实现简单，无需修改其他模块

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

### 3.3 DynamicFileHandler 实现

**位置：** 新建 `log_handler.py` 文件

**功能：** 动态切换日志输出文件，支持按用例或按 sheet 拆分日志

**实现：**
```python
import logging
import os

class DynamicFileHandler(logging.Handler):
    """
    动态切换输出文件的日志 Handler

    该 Handler 可以在运行时动态切换输出文件，支持：
    1. 按用例拆分日志：每个用例一个独立的日志文件
    2. 按 sheet 拆分日志：每个 sheet 一个日志文件
    """

    def __init__(self, log_dir="logs"):
        """
        初始化 DynamicFileHandler

        Args:
            log_dir: 日志文件存放目录
        """
        super().__init__()
        self.log_dir = log_dir
        self.current_handler = None
        self.current_file = None

        # 确保日志目录存在
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

    def switch_file(self, log_file):
        """
        切换到新的日志文件

        Args:
            log_file: 日志文件名（相对路径或绝对路径）
        """
        # 如果是相对路径，添加日志目录前缀
        if not os.path.isabs(log_file):
            log_file = os.path.join(self.log_dir, log_file)

        # 如果目标文件与当前文件相同，不切换
        if self.current_file == log_file:
            return

        # 关闭当前 handler（先 flush 避免日志丢失）
        if self.current_handler:
            self.current_handler.flush()
            self.current_handler.close()

        # 创建新的 FileHandler
        self.current_handler = logging.FileHandler(log_file, encoding='utf-8')
        self.current_handler.setLevel(logging.DEBUG)

        # 设置格式
        formatter = logging.Formatter(
            '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.current_handler.setFormatter(formatter)

        self.current_file = log_file

    def emit(self, record):
        """
        发送日志记录到当前文件

        Args:
            record: 日志记录
        """
        if self.current_handler:
            self.current_handler.emit(record)

    def close(self):
        """关闭 Handler"""
        if self.current_handler:
            self.current_handler.close()
        super().close()
```

---

### 3.4 用例分隔样式

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

### 3.5 日志文件命名策略（硬编码）

**位置：** `dpiinstall.py` 的 `install` 函数

**实现方式：**
```python
def install(..., session_id):
    """安装/升级主函数"""

    # 导入需要添加 DynamicFileHandler 的模块
    import common
    import dpi
    import comm
    import ftp
    import dpistat
    import socket_linux
    import dpiinstall

    modules = [
        common, dpi, comm, ftp,
        dpistat, socket_linux, dpiinstall
    ]

    # Sheet 循环
    for sheet_name in sheets:
        # 创建 DynamicFileHandler
        dynamic_handler = DynamicFileHandler()

        # 添加到所有模块的 logger
        for module in modules:
            if hasattr(module, 'logger'):
                module.logger.addHandler(dynamic_handler)

        try:
            # 硬编码：根据 sheet 名称决定日志拆分策略
            if sheet_name == "install":
                # 按用例拆分
                log_strategy = "by_case"
            elif sheet_name == "upgrade":
                # 按 sheet 拆分
                log_strategy = "by_sheet"
            else:
                # 默认按用例拆分
                log_strategy = "by_case"

            # 根据策略创建初始日志文件
            if log_strategy == "by_sheet":
                log_file = f"{session_id}_{sheet_name}.log"
                dynamic_handler.switch_file(log_file)

            # 用例循环
            for case_name, case_list in cases.items():
                # 如果策略是按用例拆分，切换到新的日志文件
                if log_strategy == "by_case":
                    safe_case_name = sanitize_case_name(case_name)
                    log_file = f"{session_id}_{sheet_name}_{safe_case_name}.log"
                    dynamic_handler.switch_file(log_file)

                # 打印用例分隔符
                print_case_separator(case_name, logger)

                # 执行用例
                # ...

        finally:
            # 确保 DynamicFileHandler 被关闭
            dynamic_handler.close()
            for module in modules:
                if hasattr(module, 'logger'):
                    module.logger.removeHandler(dynamic_handler)
```

---

### 3.6 需要添加 DynamicFileHandler 的模块列表

**验证结果：**

| 模块 | 是否有 logger | 说明 |
|------|--------------|------|
| `common` | ✓ 有 | 通用工具模块 |
| `dpi` | ✓ 有 | DPI 操作模块 |
| `comm` | ✓ 有 | 通信模块 |
| `ftp` | ✓ 有 | FTP 传输模块 |
| `dpistat` | ✓ 有 | DPI 状态检查模块 |
| `socket_linux` | ✓ 有 | Socket 通信模块 |
| `dpiinstall` | ✓ 有 | 安装/升级模块 |
| `linux` | ✗ 没有 | 类模块，不使用 logger |
| `ssh` | ✗ 没有 | 函数模块，不使用 logger |
| `excel` | ✗ 没有 | 类模块，不使用 logger |

**需要添加 DynamicFileHandler 的模块：**
1. `common` - 通用工具模块
2. `dpi` - DPI 操作模块
3. `comm` - 通信模块
4. `ftp` - FTP 传输模块
5. `dpistat` - DPI 状态检查模块
6. `socket_linux` - Socket 通信模块
7. `dpiinstall` - 安装/升级模块

**控制台输出说明：**
- DynamicFileHandler 只处理文件输出
- 控制台输出由各模块原有的 console handler 处理
- 控制台输出不受 DynamicFileHandler 影响
- 所有模块的日志都会实时显示在控制台

**实现方式：**
```python
# 在 install 函数中
import common
import dpi
import comm
import ftp
import dpistat
import socket_linux
import dpiinstall

modules = [
    common, dpi, comm, ftp,
    dpistat, socket_linux, dpiinstall
]

# 添加 DynamicFileHandler
for module in modules:
    if hasattr(module, 'logger'):
        module.logger.addHandler(dynamic_handler)
```

**日志级别控制：**
- DynamicFileHandler 默认设置为 `DEBUG` 级别，记录所有日志
- 如需调整，可以在创建后调用 `dynamic_handler.setLevel(logging.INFO)` 等

---

### 3.7 错误处理和边界情况

#### 3.7.1 日志目录不存在
- `DynamicFileHandler` 初始化时自动创建日志目录

#### 3.7.2 用例名称包含特殊字符
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

#### 3.7.3 同一用例多次执行
- 日志文件会被覆盖
- 这是预期行为，保持不变

#### 3.7.4 DynamicFileHandler 未正确关闭
- 可能导致文件句柄泄漏
- 使用 try-finally 确保清理

**实现：**
```python
# Sheet 循环
for sheet_name in sheets:
    # 创建 DynamicFileHandler
    dynamic_handler = DynamicFileHandler()

    # 添加到所有模块的 logger
    modules = [common, dpi, comm, ftp, dpistat, socket_linux, dpiinstall]
    for module in modules:
        if hasattr(module, 'logger'):
            module.logger.addHandler(dynamic_handler)

    try:
        # Sheet 执行逻辑
        # ...
    finally:
        # 确保 DynamicFileHandler 被关闭
        dynamic_handler.close()
        for module in modules:
            if hasattr(module, 'logger'):
                module.logger.removeHandler(dynamic_handler)
```

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

#### 文件 3：`log_handler.py`（新建）
- 创建 `DynamicFileHandler` 类
- 实现动态切换日志文件功能

#### 文件 4：`dpiinstall.py`
- 修改 `install` 函数签名，增加 `session_id` 参数
- 添加 `sanitize_case_name` 函数清理用例名称
- 添加 `print_case_separator` 函数打印用例分隔符
- 在 sheet 循环中创建 DynamicFileHandler
- 硬编码日志拆分策略
- 用例切换时动态切换日志文件
- Sheet 结束时关闭 DynamicFileHandler

### 4.2 改动范围估算
- 约 4 个文件（3 个修改，1 个新建）
- 新增约 150-200 行代码
- 修改约 30-50 行现有代码

---

## 五、核心特性总结

1. ✅ 每次运行生成唯一会话ID（格式：YYYYMMDDHHMMSS）
2. ✅ 支持按用例或按 sheet 拆分日志文件
3. ✅ 日志统一存放在 `logs/` 目录
4. ✅ 日志格式优化：`[2026-04-11 14:30:25] [install] [INFO] 消息`
5. ✅ 用例分隔清晰（横线分隔 + 用例名单独一行）
6. ✅ 控制台实时显示所有用例日志
7. ✅ 记录所有模块的日志到统一文件
8. ✅ 错误处理完善（特殊字符清理、Handler 生命周期管理）
9. ✅ 不影响其他模块的日志逻辑
10. ✅ Sheet 串行执行，无需考虑并发

---

## 六、方案选择理由

### 6.1 选择 DynamicFileHandler 的原因

1. **不破坏现有结构：** 无需修改其他模块的函数签名
2. **灵活性高：** 可以动态切换日志输出目标
3. **易于维护：** 集中管理日志输出逻辑
4. **向后兼容：** 保持现有的日志文件结构

### 6.2 选择硬编码策略的原因

1. **简单直接：** 无需增加配置项
2. **明确可控：** 每个 sheet 的策略在代码中明确定义
3. **易于理解：** 新人可以快速理解日志拆分逻辑
4. **便于调试：** 策略逻辑集中在一处，便于排查问题

### 6.3 选择在 sheet 开始时创建 Handler 的原因

1. **职责清晰：** Handler 的生命周期与 sheet 绑定
2. **资源管理：** 便于统一管理文件句柄
3. **易于扩展：** 未来如果需要按 sheet 并行，只需为每个 sheet 创建独立的 Handler

---

## 七、实施注意事项

### 7.1 测试策略

1. **单元测试：** 测试 `DynamicFileHandler`、`sanitize_case_name` 等辅助函数
2. **集成测试：** 测试完整的 sheet 执行流程，验证日志文件正确生成
3. **边界测试：** 测试特殊字符用例名、多次执行同一用例等边界情况

### 7.2 向后兼容

1. 保持其他模块的日志文件不变（原有日志文件仍然生成）
2. 保持现有的日志级别（DEBUG、INFO、WARNING、ERROR）
3. 保持现有的日志调用方式

### 7.3 性能考虑

1. 每个用例切换日志文件会有轻微性能开销
2. 日志文件数量会随用例数量增加
3. 建议定期清理旧的日志文件

---

## 八、后续优化方向

如果后续需要进一步优化，可以考虑：

1. **日志压缩：** 自动压缩过期的日志文件
2. **日志清理：** 自动清理过期日志文件
3. **日志分析：** 提供日志分析工具，提取关键信息
4. **日志聚合：** 提供工具聚合多个日志文件，便于查看
