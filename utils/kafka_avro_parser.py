"""
kafka_avro_parser.py — Kafka Avro 二进制文件解析工具

功能：根据 Avro Schema (.avsc) 解析 Kafka 传输的二进制数据文件。

处理思路：
  1. 加载 Avro Schema 文件（.avsc）
  2. 读取 Kafka 二进制文件
  3. 使用 fastavro.schemaless_reader 按 Schema 逐条解析记录
  4. 通过 BytesIO.tell() 精确追踪每条记录消耗的字节数，实现可靠的多记录迭代
  5. 返回结构化的 dict 列表，便于后续处理

关键点：
  - Kafka 传输的 Avro 数据不含容器头（无 magic/sync marker），
    每条记录是裸 Avro 编码，需用 schemaless_reader 逐条读取
  - houseId 等字段的 zigzag 编码值（如 0xd00f40）不是记录分隔符，
    不能用作记录边界标记
  - 正确的迭代方式：解析一条记录后，BytesIO 的读取位置即为下一条记录的起点
"""

import json
from io import BytesIO
from typing import List, Literal

import fastavro


def parse_kafka_avro_file(
    filepath: str,
    schema_path: str,
    output_format: Literal["dict", "list"] = "dict",
) -> List:
    """
    根据 Avro Schema 解析 Kafka 二进制文件。

    参数:
        filepath:       Kafka 二进制文件路径
        schema_path:    Avro Schema (.avsc) 文件路径
        output_format:  输出格式，"dict" 返回字典列表，"list" 返回值列表
                        （按 schema 字段顺序排列），默认 "dict"

    返回:
        output_format="dict"  → List[dict]，每条记录为一个 dict
        output_format="list"  → List[list]，每条记录为按字段顺序排列的值列表

    用法示例:
        >>> records = parse_kafka_avro_file("data.bin", "schema.avsc")
        >>> values = parse_kafka_avro_file("data.bin", "schema.avsc", output_format="list")
    """
    if output_format not in ("dict", "list"):
        raise ValueError(f"output_format 必须为 'dict' 或 'list'，当前值: {output_format}")

    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)
    parsed_schema = fastavro.parse_schema(schema)

    # 仅在 list 格式时提取字段顺序
    field_names = None
    if output_format == "list":
        field_names = [field["name"] for field in schema["fields"]]

    with open(filepath, "rb") as f:
        data = f.read()

    records = []
    offset = 0
    file_size = len(data)

    while offset < file_size:
        bio = BytesIO(data[offset:])
        try:
            record = fastavro.schemaless_reader(bio, parsed_schema)
        except (ValueError, IndexError, KeyError) as e:
            # Avro 解析错误，停止迭代
            remaining = file_size - offset
            if remaining > 0:
                import logging
                logging.getLogger(__name__).warning(
                    f"[警告] 停止解析，剩余 {remaining} 字节未处理，原因: {e}"
                )
            break
        consumed = bio.tell()
        if output_format == "list":
            records.append([record[name] for name in field_names])
        else:
            records.append(record)
        offset += consumed

    return records
