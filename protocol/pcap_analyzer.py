#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2024/4/17
# @Author  : weihang
# @File    : pcap_analyzer.py
# @Desc    : PCAP分析和比较工具函数

import copy
import io
import os
import socket
import struct
import re

from scapy.all import rdpcap, wrpcap, TCP, IP, Packet, PacketList, Ether, Dot1Q, IPv6, ARP, UDP, SCTP, ICMP, Raw
from scapy.layers.http import HTTP
from scapy.utils import PcapReader

from utils.common import setup_logging

logger = setup_logging(log_file_path="log/pcap_analyzer.log", logger_name="pcap_analyzer")

# HTTP 请求方法正则（预编译）
HTTP_REQUEST_METHOD_PATTERN = re.compile(
    rb"(?:GET|POST|PUT|DELETE|CONNECT|OPTIONS|TRACE|PATCH|HEAD)\s/[^\r\n]*?\sHTTP/\d\.\d\r\n(?:[^\r\n]+?:\s[^\r\n]*?\r\n)*?\r\n"
)


def _parse_packet_data(pkt_data, link_type, stats, seen, result, debug, endian):
    """
    解析单个数据包，提取四元组
    """
    try:
        # -------------------------
        # 根据链路层类型确定起始偏移
        # -------------------------
        offset = 0
        eth_type = None

        # Ethernet (1)
        if link_type == 1:
            if len(pkt_data) < 14:
                return
            offset = 14
            eth_type = struct.unpack("!H", pkt_data[12:14])[0]

        # Raw IP (101, 228, 229)
        elif link_type in (101, 228, 229):
            if len(pkt_data) < 1:
                return
            # 通过 IP 版本号判断
            version = (pkt_data[0] >> 4) & 0x0F
            if version == 4:
                eth_type = 0x0800
            elif version == 6:
                eth_type = 0x86DD
            else:
                stats["non_ip"] += 1
                return
            offset = 0

        # Linux cooked capture (113)
        elif link_type == 113:
            if len(pkt_data) < 16:
                return
            eth_type = struct.unpack("!H", pkt_data[14:16])[0]
            offset = 16

        # Linux cooked capture v2 (276)
        elif link_type == 276:
            if len(pkt_data) < 20:
                return
            eth_type = struct.unpack("!H", pkt_data[0:2])[0]
            offset = 20

        # Null/Loopback (0)
        elif link_type == 0:
            if len(pkt_data) < 4:
                return
            # 读取协议族字段（4字节）
            proto_family = struct.unpack(endian + "I", pkt_data[0:4])[0]
            # 2 = IPv4, 24/28/30 = IPv6 (取决于系统)
            if proto_family == 2:
                eth_type = 0x0800
            elif proto_family in (24, 28, 30):
                eth_type = 0x86DD
            else:
                stats["non_ip"] += 1
                return
            offset = 4

        # 其他不支持的链路层类型
        else:
            stats["unsupported_linktype"] += 1
            if debug:
                print(f"[WARN] Unsupported link type: {link_type}")
            return

        # -------------------------
        # 处理 VLAN 标签（仅以太网）
        # -------------------------
        if link_type == 1:
            while eth_type in (0x8100, 0x88A8):
                stats["vlan"] += 1
                if len(pkt_data) < offset + 4:
                    break
                eth_type = struct.unpack("!H", pkt_data[offset + 2:offset + 4])[0]
                offset += 4

        # -------------------------
        # 解析 IP 层
        # -------------------------
        # IPv4
        if eth_type == 0x0800:
            stats["ipv4"] += 1

            if len(pkt_data) < offset + 20:
                return

            ip_header = pkt_data[offset:offset + 20]
            ihl = (ip_header[0] & 0x0F) * 4
            protocol = ip_header[9]

            src_ip = socket.inet_ntoa(ip_header[12:16])
            dst_ip = socket.inet_ntoa(ip_header[16:20])

            l4_offset = offset + ihl

        # IPv6
        elif eth_type == 0x86DD:
            stats["ipv6"] += 1

            if len(pkt_data) < offset + 40:
                return

            ip_header = pkt_data[offset:offset + 40]
            protocol = ip_header[6]

            src_ip = socket.inet_ntop(socket.AF_INET6, ip_header[8:24])
            dst_ip = socket.inet_ntop(socket.AF_INET6, ip_header[24:40])

            l4_offset = offset + 40

        else:
            stats["non_ip"] += 1
            return

        # -------------------------
        # 解析传输层 (TCP / UDP)
        # -------------------------
        if protocol in (6, 17):
            if len(pkt_data) < l4_offset + 4:
                return

            src_port, dst_port = struct.unpack(
                "!HH", pkt_data[l4_offset:l4_offset + 4]
            )
        else:
            stats["non_tcp_udp"] += 1
            return

        four_tuple = (src_ip, src_port, dst_ip, dst_port)

        if four_tuple not in seen:
            seen.add(four_tuple)
            result.append({
                "src_ip": src_ip,
                "src_port": src_port,
                "dst_ip": dst_ip,
                "dst_port": dst_port
            })

    except Exception as e:
        stats["parse_error"] += 1
        if debug:
            print("[ERROR] Packet parse failed:", e)


def _extract_4tuple_from_pcapng(f, debug, stats, seen, result):
    """
    解析 PCAP-NG 格式文件
    """
    link_type = 1  # 默认以太网
    endian = "<"  # PCAP-NG 默认小端序

    while True:
        # 读取块头（Block Type + Block Total Length）
        block_header = f.read(8)
        if len(block_header) < 8:
            break

        try:
            block_type = struct.unpack("<I", block_header[:4])[0]
            block_len = struct.unpack("<I", block_header[4:8])[0]

            if block_len < 12:  # 最小块大小
                break

            # 读取块数据（不包括已读的8字节头和4字节尾）
            remaining = block_len - 8
            block_data = f.read(remaining)
            if len(block_data) < remaining:
                break

            # Interface Description Block (IDB) - 获取链路层类型
            if block_type == 0x00000001:
                if len(block_data) >= 4:
                    link_type = struct.unpack("<H", block_data[:2])[0]
                    if debug:
                        print(f"[DEBUG] PCAP-NG Link type: {link_type}")

            # Enhanced Packet Block (EPB)
            elif block_type == 0x00000006:
                if len(block_data) < 20:
                    continue

                # EPB 结构: Interface ID(4) + Timestamp(8) + Captured Len(4) + Packet Len(4) + Packet Data
                captured_len = struct.unpack("<I", block_data[16:20])[0]

                if len(block_data) < 20 + captured_len:
                    continue

                pkt_data = block_data[20:20 + captured_len]
                stats["total_packets"] += 1

                _parse_packet_data(pkt_data, link_type, stats, seen, result, debug, endian)

            # Simple Packet Block (SPB)
            elif block_type == 0x00000003:
                if len(block_data) < 4:
                    continue

                packet_len = struct.unpack("<I", block_data[:4])[0]

                if len(block_data) < 4 + packet_len:
                    continue

                pkt_data = block_data[4:4 + packet_len]
                stats["total_packets"] += 1

                _parse_packet_data(pkt_data, link_type, stats, seen, result, debug, endian)

        except Exception as e:
            if debug:
                print(f"[ERROR] Block parse failed: {e}")
            break

    if debug:
        print("\n[STATS]")
        for k, v in stats.items():
            print(f"{k}: {v}")
        print("unique_4tuple:", len(result))

    return result


def extract_4tuple_from_pcap(pcap_input, debug=False):
    """
    解析 PCAP 文件并提取四元组，支持多种链路层类型

    支持的格式：
    - 标准 PCAP (微秒/纳秒精度)
    - 以太网 (link type 1)
    - Raw IP (link type 101, 228, 229)
    - Linux cooked capture (link type 113)
    - Linux cooked capture v2 (link type 276)
    - Null/Loopback (link type 0)

    :param pcap_input: str(文件路径) 或 bytes 或 BytesIO对象
    :param debug: 是否打印调试信息
    :return: list[dict]
    """

    stats = {
        "total_packets": 0,
        "non_ip": 0,
        "non_tcp_udp": 0,
        "ipv4": 0,
        "ipv6": 0,
        "vlan": 0,
        "parse_error": 0,
        "unsupported_linktype": 0,
    }

    try:
        # -------------------------
        # 打开文件
        # -------------------------
        need_close = False  # 默认不需要关闭
        if isinstance(pcap_input, str):
            if not os.path.exists(pcap_input):
                print("测试文件不存在，跳过直接运行测试")
                return []
            f = open(pcap_input, "rb")
            need_close = True
        elif isinstance(pcap_input, bytes):
            f = io.BytesIO(pcap_input)
            need_close = False
        elif isinstance(pcap_input, io.BytesIO):
            f = pcap_input
            need_close = False
        else:
            raise TypeError("pcap_input 必须是 str 或 bytes 或 BytesIO对象")

        result = []
        seen = set()

        # -------------------------
        # 读取 global header
        # -------------------------
        global_header = f.read(24)
        if len(global_header) < 24:
            raise ValueError("文件太小，不是合法 PCAP")

        magic_be = struct.unpack(">I", global_header[:4])[0]
        magic_le = struct.unpack("<I", global_header[:4])[0]

        # 检查是否是 PCAP-NG 格式
        if magic_be == 0x0a0d0d0a or magic_le == 0x0a0d0d0a:
            if debug:
                print("[DEBUG] 检测到 PCAP-NG 格式")
            # PCAP-NG 格式处理
            f.seek(0)
            return _extract_4tuple_from_pcapng(f, debug, stats, seen, result)

        # 判断字节序和时间戳精度
        is_nanosecond = False
        if magic_be == 0xa1b2c3d4:
            endian = ">"
        elif magic_be == 0xa1b23c4d:
            endian = ">"
            is_nanosecond = True
        elif magic_le == 0xa1b2c3d4:
            endian = "<"
        elif magic_le == 0xa1b23c4d:
            endian = "<"
            is_nanosecond = True
        else:
            raise ValueError("无法识别 PCAP Magic Number")

        # 读取链路层类型
        link_type = struct.unpack(endian + "I", global_header[20:24])[0]

        if debug:
            print(f"[DEBUG] PCAP endian: {'Big' if endian == '>' else 'Little'}")
            print(f"[DEBUG] Timestamp precision: {'Nanosecond' if is_nanosecond else 'Microsecond'}")
            print(f"[DEBUG] Link type: {link_type}")

        pkt_hdr_struct = struct.Struct(endian + "IIII")

        # -------------------------
        # 逐包解析
        # -------------------------
        while True:
            pkt_header = f.read(16)
            if len(pkt_header) < 16:
                break

            try:
                _, _, incl_len, _ = pkt_hdr_struct.unpack(pkt_header)
            except Exception as e:
                stats["parse_error"] += 1
                if debug:
                    print("[ERROR] Packet header unpack failed:", e)
                continue

            pkt_data = f.read(incl_len)
            if len(pkt_data) < incl_len:
                break

            stats["total_packets"] += 1

            try:
                # -------------------------
                # 根据链路层类型确定起始偏移
                # -------------------------
                offset = 0
                eth_type = None

                # Ethernet (1)
                if link_type == 1:
                    if len(pkt_data) < 14:
                        continue
                    offset = 14
                    eth_type = struct.unpack("!H", pkt_data[12:14])[0]

                # Raw IP (101, 228, 229)
                elif link_type in (101, 228, 229):
                    if len(pkt_data) < 1:
                        continue
                    # 通过 IP 版本号判断
                    version = (pkt_data[0] >> 4) & 0x0F
                    if version == 4:
                        eth_type = 0x0800
                    elif version == 6:
                        eth_type = 0x86DD
                    else:
                        stats["non_ip"] += 1
                        continue
                    offset = 0

                # Linux cooked capture (113)
                elif link_type == 113:
                    if len(pkt_data) < 16:
                        continue
                    eth_type = struct.unpack("!H", pkt_data[14:16])[0]
                    offset = 16

                # Linux cooked capture v2 (276)
                elif link_type == 276:
                    if len(pkt_data) < 20:
                        continue
                    eth_type = struct.unpack("!H", pkt_data[0:2])[0]
                    offset = 20

                # Null/Loopback (0)
                elif link_type == 0:
                    if len(pkt_data) < 4:
                        continue
                    # 读取协议族字段（4字节）
                    proto_family = struct.unpack(endian + "I", pkt_data[0:4])[0]
                    # 2 = IPv4, 24/28/30 = IPv6 (取决于系统)
                    if proto_family == 2:
                        eth_type = 0x0800
                    elif proto_family in (24, 28, 30):
                        eth_type = 0x86DD
                    else:
                        stats["non_ip"] += 1
                        continue
                    offset = 4

                # 其他不支持的链路层类型
                else:
                    stats["unsupported_linktype"] += 1
                    if debug:
                        print(f"[WARN] Unsupported link type: {link_type}")
                    continue

                # -------------------------
                # 处理 VLAN 标签（仅以太网）
                # -------------------------
                if link_type == 1:
                    while eth_type in (0x8100, 0x88A8):
                        stats["vlan"] += 1
                        if len(pkt_data) < offset + 4:
                            break
                        eth_type = struct.unpack("!H", pkt_data[offset + 2:offset + 4])[0]
                        offset += 4

                # -------------------------
                # 解析 IP 层
                # -------------------------
                # IPv4
                if eth_type == 0x0800:
                    stats["ipv4"] += 1

                    if len(pkt_data) < offset + 20:
                        continue

                    ip_header = pkt_data[offset:offset + 20]
                    ihl = (ip_header[0] & 0x0F) * 4
                    protocol = ip_header[9]

                    src_ip = socket.inet_ntoa(ip_header[12:16])
                    dst_ip = socket.inet_ntoa(ip_header[16:20])

                    l4_offset = offset + ihl

                # IPv6
                elif eth_type == 0x86DD:
                    stats["ipv6"] += 1

                    if len(pkt_data) < offset + 40:
                        continue

                    ip_header = pkt_data[offset:offset + 40]
                    protocol = ip_header[6]

                    src_ip = socket.inet_ntop(socket.AF_INET6, ip_header[8:24])
                    dst_ip = socket.inet_ntop(socket.AF_INET6, ip_header[24:40])

                    l4_offset = offset + 40

                else:
                    stats["non_ip"] += 1
                    continue

                # TCP / UDP
                if protocol in (6, 17):
                    if len(pkt_data) < l4_offset + 4:
                        continue

                    src_port, dst_port = struct.unpack(
                        "!HH", pkt_data[l4_offset:l4_offset + 4]
                    )
                else:
                    stats["non_tcp_udp"] += 1
                    continue

                four_tuple = (src_ip, src_port, dst_ip, dst_port)

                if four_tuple not in seen:
                    seen.add(four_tuple)
                    result.append({
                        "src_ip": src_ip,
                        "src_port": src_port,
                        "dst_ip": dst_ip,
                        "dst_port": dst_port
                    })

            except Exception as e:
                stats["parse_error"] += 1
                if debug:
                    print("[ERROR] Packet parse failed:", e)

        if debug:
            print("\n[STATS]")
            for k, v in stats.items():
                print(f"{k}: {v}")
            print("unique_4tuple:", len(result))

        return result

    except Exception as e:
        print("[FATAL ERROR]", e)
        return []

    finally:
        if "need_close" in locals() and need_close and hasattr(f, 'close'):
            f.close()


def get_synNo(pkts) -> list:
    """
    获取TCP SYN/SA包的索引列表

    :param pkts: 包列表
    :return: SYN/SA包索引列表
    """
    ret = list()
    ack_seq = list()

    for i in range(len(pkts)):
        pkt = pkts[i]
        if TCP in pkt and pkt[TCP].flags.flagrepr() == "S":
            ret.append(i)
            ack_seq.append(pkt[TCP].seq + 1)
        elif TCP in pkt and pkt[TCP].flags.flagrepr() == "SA":
            ret.append(i)
            ack_seq.append(pkt[TCP].ack)
        else:
            pass

    ack_seq = list(set(ack_seq))
    for i in range(len(pkts)):
        pkt = pkts[i]
        if TCP in pkt and pkt[TCP].flags.flagrepr() == "A" and len(pkt[TCP].payload) == 0 and pkt[TCP].seq in ack_seq:
            ret.append(i)
            ack_seq.remove(pkt[TCP].seq)

    if ack_seq:
        logger.info(f"缺少部分ack。对应的seq为：{ack_seq}")

    return sorted(ret)


def get_tuple(pkt):
    """
    从包中提取四元组信息

    :param pkt: Scapy包对象
    :return: 四元组字典
    """
    ret = {'l3': None, 'l4': None, 'l5': None, 'sip': None, 'dip': None, 'sport': None, 'dport': None}

    if pkt.haslayer(IPv6):
        ret['l3'] = 'IPv6'
        ret['sip'] = pkt[IPv6].fields['src']
        ret['dip'] = pkt[IPv6].fields['dst']
    elif pkt.haslayer(IP):
        ret['l3'] = 'IP'
        ret['sip'] = pkt[IP].fields['src']
        ret['dip'] = pkt[IP].fields['dst']
    elif pkt.haslayer(ARP):
        ret['l3'] = 'ARP'
        return ret
    else:
        logger.warning('unknown L3 protocol:')
        return ret

    if pkt.haslayer(TCP):
        ret['l4'] = 'TCP'
        ret['sport'] = pkt[TCP].fields['sport']
        ret['dport'] = pkt[TCP].fields['dport']
    elif pkt.haslayer(UDP):
        ret['l4'] = 'UDP'
        ret['sport'] = pkt[UDP].fields['sport']
        ret['dport'] = pkt[UDP].fields['dport']
    elif pkt.haslayer(SCTP):
        ret['l4'] = 'SCTP'
        ret['sport'] = pkt[SCTP].fields['sport']
        ret['dport'] = pkt[SCTP].fields['dport']
    elif pkt.haslayer(ICMP):
        ret['l4'] = 'ICMP'
    elif "ICMPv6" in str(pkt.layers()):
        ret['l4'] = 'ICMPv6'
    else:
        logger.warning('unknown L4 protocol:')
        return ret

    if pkt.haslayer(HTTP):
        ret['l5'] = 'HTTP'
    else:
        pass

    return ret


def rst_check(pcap, direction):
    """
    封堵包检查

    :param pcap: 包路径或者二进制文件
    :param direction: 封堵包方向，0：上行，1：下行
    :return: 错误列表
    """
    err_list = list()
    pkts = rdpcap(pcap) if type(pcap) in (str, io.IOBase) else pcap
    # PcapReader只能迭代一次，需要转换为列表以便多次访问
    if isinstance(pkts, PcapReader):
        pkts = list(pkts)
    pf = Pcap2Flowtable(pkts)
    pf.pkts_parser()

    for flow_id, data in pf.flowtable.tables.items():
        flag = True
        for i in data["pktNo"]:
            pkt = pkts[i]
            tuple_tmp = get_tuple(pkt)
            tmp_id = '_'.join([
                tuple_tmp["l3"], tuple_tmp["l4"],
                tuple_tmp["sip"], str(tuple_tmp["sport"]),
                tuple_tmp["dip"], str(tuple_tmp["dport"])
            ])

            if TCP not in pkt:
                continue

            # 上行封堵包
            if direction == 0 and pkt["TCP"].flags.flagrepr() == "RPA" and (
                    (flow_id == tmp_id and not data["direction"]) or
                    (flow_id != tmp_id and data["direction"])):
                flag = False
                break
            # 下行封堵包
            elif direction == 1 and pkt["TCP"].flags.flagrepr() == "RPA" and (
                    (flow_id == tmp_id and data["direction"]) or
                    (flow_id != tmp_id and not data["direction"])):
                flag = False
                break

        if flag:
            err_list.append(f"流{flow_id}，缺少封堵包")

    return err_list[:200]


def compare_pcap(pcap_exp, pcap_act, flowsplit=False, ignore_syn=False, **kwargs):
    """
    比较两个PCAP文件

    :param pcap_exp: 预期PCAP文件路径或包列表
    :param pcap_act: 实际PCAP文件路径或包列表
    :param flowsplit: 是否按流分割
    :param ignore_syn: 是否忽略SYN包
    :param kwargs: 其他参数，用于指定特定层的期望值，如 TCP={seq: 1000}
    :return: 无返回值，成功则无异常
    :raises RuntimeError: 比较失败时抛出异常
    """
    rd_exp = pcap_exp if type(pcap_exp) in (list, PacketList) else rdpcap(pcap_exp)
    rd_act = pcap_act if type(pcap_act) in (list, PacketList) else rdpcap(pcap_act)

    # 对比包数
    if len(rd_exp) != len(rd_act):
        raise RuntimeError(f"预期包数-实际包数：【{len(rd_exp)}-{len(rd_act)}】")
    err_list = list()
    if flowsplit:
        pcap_info_exp = Pcap2Flowtable(rd_exp)
        pcap_info_exp.pkts_parser()
        tables_exp = pcap_info_exp.flowtable.tables
        pcap_info_act = Pcap2Flowtable(rd_act)
        pcap_info_act.pkts_parser()
        tables_act = pcap_info_act.flowtable.tables
    else:
        tables_exp = {"完整包": {"pktNo": list(range(len(rd_exp)))}}
        tables_act = {"完整包": {"pktNo": list(range(len(rd_act)))}}

    if len(tables_exp) != len(tables_act):
        raise RuntimeError(f"预期流数-实际流数：【{len(rd_exp)}-{len(rd_act)}】")

    for flowname, tmp in tables_exp.items():
        if len(err_list) > 10:
            break
        pktNo_exp = tmp["pktNo"]

        # 针对发生包的syn有乱序的自动排序调整
        if ignore_syn:
            tmp_syn_list = [None, None, None]
            seq_tmp = None
            pop_list = list()
            s = copy.deepcopy(pktNo_exp)
            for i in range(len(pktNo_exp)):
                pktNo = pktNo_exp[i]
                pkt_exp = rd_exp[pktNo]
                if pkt_exp.haslayer("TCP") and pkt_exp["TCP"].flags.flagrepr() == "S":
                    tmp_syn_list[0] = pktNo
                    seq_tmp = pkt_exp["TCP"].seq + 1
                    pop_list.append(i)
                elif pkt_exp.haslayer("TCP") and pkt_exp["TCP"].flags.flagrepr() == "SA":
                    tmp_syn_list[1] = pktNo
                    seq_tmp = pkt_exp["TCP"].ack
                    pop_list.append(i)
                elif pkt_exp.haslayer("TCP") and pkt_exp["TCP"].flags.flagrepr() == "A" and pkt_exp[
                    "TCP"].seq == seq_tmp and len(pkt_exp["TCP"].payload) == 0:
                    tmp_syn_list[2] = pktNo
                    pop_list.append(i)
                else:
                    pass
            for i in sorted(pop_list)[::-1]:
                pktNo_exp.pop(i)
            for syn in tmp_syn_list[::-1]:
                if syn is not None:
                    pktNo_exp.insert(0, syn)
            d = copy.deepcopy(pktNo_exp)
            if len(s) != len(d):
                logger.debug(s)
                logger.debug(pop_list)
                logger.debug(tmp_syn_list)
                logger.debug(d)

        if flowname in tables_act:
            pktNo_act = tables_act[flowname]["pktNo"]
        else:
            err_list.append(f"实际pcap中无流信息{flowname}")
            break

        if len(pktNo_exp) != len(pktNo_act):
            err_list.append(f"指定流{flowname}中包数不一致，预期包数：{len(pktNo_exp)}，实际包数：{len(pktNo_act)}")
            break

        synNo = list()
        if ignore_syn:
            synNo = get_synNo(list(map(lambda x: rd_exp[x], pktNo_exp)))
            # logger.info(synNo)
        for i in range(len(pktNo_exp)):
            if len(err_list) > 10:
                break
            record = dict()
            pkt_exp = rd_exp[pktNo_exp[i]]
            pkt_act = rd_act[pktNo_act[i]]

            if len(pkt_exp) != len(pkt_act):
                err_list.append(f"指定流{flowname}，第{i + 1}个包的包长不一致，预期{len(pkt_exp)}-实际{len(pkt_act)}")
                # wrpcap(r"D:\weihang\Desktop\1.pcap", rd_exp)
                # wrpcap(r"D:\weihang\Desktop\2.pcap", rd_act)
                # logger.info(len(pkt_exp), len(pkt_act))
                logger.info([pktNo_exp, pktNo_act])
                logger.info([pktNo_exp[i], pktNo_act[i]])
                break

            # 不对比syn包的具体内容
            if synNo and i in synNo:
                synNo.remove(i)
                continue

            # 提取每层信息，层-key:val
            tuple_exp = dict()
            tuple_act = dict()
            for layer in pkt_exp.layers():
                val = pkt_exp[layer].fields
                layer_name = str(layer).split("'")[1].split(".")[-1]
                if layer_name in tuple_exp:
                    record[layer_name] += 1
                    tuple_exp[f"{layer_name}{record[layer_name]}"] = val
                else:
                    tuple_exp[layer_name] = val
                    record[layer_name] = 0
            for layer in pkt_act.layers():
                val = pkt_act[layer].fields
                layer_name = str(layer).split("'")[1].split(".")[-1]
                if layer_name in tuple_act:
                    record[layer_name] += 1
                    tuple_act[f"{layer_name}{record[layer_name]}"] = val
                else:
                    tuple_act[layer_name] = val
                    record[layer_name] = 0

            # 查询抓包中的指定预期值
            for layer, k2v in kwargs.items():
                for key, val in k2v.items():
                    tuple_exp[layer].pop(key)
                    if tuple_act[layer][key] != val:
                        err_list.append(
                            f"指定流{flowname}，第{i + 1}个包{layer}层，预期{key}-实际{key}：【{val}-{tuple_act[layer][key]}】")

            for layer in tuple_exp.keys():
                # if layer in kwargs:
                #     continue
                for key, val in tuple_exp[layer].items():
                    if len(err_list) > 10:
                        break
                    if layer not in tuple_act:
                        err_list.append(f"指定流{flowname}，第{i + 1}个包缺少{layer}层")
                    elif key not in tuple_act[layer]:
                        err_list.append(f"指定流{flowname}，第{i + 1}个包{layer}层，缺少key值{key}")
                    elif tuple_exp[layer][key] != tuple_act[layer][key]:
                        err_list.append(
                            f"指定流{flowname}，第{i + 1}个包{layer}层，预期{key}-实际{key}：【{tuple_exp[layer][key]}-{tuple_act[layer][key]}】")
                    else:
                        pass

    if err_list:
        raise RuntimeError("\n".join(err_list))


class FlowTable:
    """流表类"""

    def __init__(self):
        self.__flow = {"l3": None, "l4": None, "l5": None, "up_pkts": 0, "down_pkts": 0, "up_bytes": 0, "down_bytes": 0,
                       "update_time": float(), "status": None, "sip": None, "sport": None, "dip": None, "dport": None,
                       "direction": None, "payload": {"up": b"", "down": b""}}
        # direction为1表示方向是反的
        self.tables = dict()

    def add(self, l3, l4, sip, sport, dip, dport):
        tmp_flow = copy.deepcopy(self.__flow)
        flow_id = '_'.join([l3, l4, sip, str(sport), dip, str(dport)])
        tmp_flow["sip"], tmp_flow["sport"], tmp_flow["dip"], tmp_flow["dport"], tmp_flow["l3"], tmp_flow["l4"] = (
            sip, sport, dip, dport, l3, l4)
        self.tables[flow_id] = tmp_flow
        return tmp_flow


class Pcap2Flowtable:
    """PCAP转流表类"""

    def __init__(self, pcap):
        self.flowtable = FlowTable()
        # PcapReader只能迭代一次，需要转换为列表以便多次访问
        if isinstance(pcap, PcapReader):
            self.pkts = list(pcap)
        elif type(pcap) not in (list, PacketList, PcapReader):
            self.pkts = PcapReader(pcap)
        else:
            self.pkts = pcap

    def into_filed(self, flow, field_name, field_value, name_surfix='', forced=False):
        field_name = field_name + name_surfix
        if forced:
            flow[field_name] = field_value
        else:
            if field_name not in flow:
                flow[field_name] = field_value

    def pkt_parser(self, pkt, No):
        """
        建流或者流关联

        :param pkt: Scapy包对象
        :param No: 包序号
        """
        if not pkt.layers():
            raise RuntimeError(f'Error: packet has no layers')
        if pkt.layers()[0] != Ether:
            raise RuntimeError(f'Error: first layer is {pkt.layers()[0]}, expected Ether')

        tuple6 = get_tuple(pkt)
        l3 = tuple6["l3"]
        l4 = tuple6["l4"]
        sip = tuple6["sip"]
        sport = tuple6["sport"]
        dip = tuple6["dip"]
        dport = tuple6["dport"]
        flow_id = '_'.join([l3, l4, sip, str(sport), dip, str(dport)])
        flow_id_fx = '_'.join([l3, l4, dip, str(dport), sip, str(sport)])

        if flow_id in self.flowtable.tables:
            flow = self.flowtable.tables[flow_id]
            flow_id_zz = flow_id
            direction = 'up'
        elif flow_id_fx in self.flowtable.tables:
            flow = self.flowtable.tables[flow_id_fx]
            flow_id_zz = flow_id_fx
            direction = 'down'
        else:
            flow = self.flowtable.add(l3=l3, l4=l4, sip=sip, sport=sport, dip=dip, dport=dport)
            flow_id_zz = '_'.join([l3, l4, sip, str(sport), dip, str(dport)])
            direction = 'up'

        # 添加包编号
        if "pktNo" in flow:
            flow["pktNo"].append(No)
        else:
            flow["pktNo"] = [No]

        # 流方向判定,包方向判定
        if l4 == "TCP":
            raw_payload = Raw(pkt[l4].payload)
            has_load = raw_payload.fields.get("load", b"")
            is_syn = pkt[l4].flags.value == 2
            is_http = has_load.startswith((b"GET", b"POST"))

            if (is_syn or is_http) and flow["direction"] is None and direction == 'down':
                flow["direction"] = 1

        # 包解析开始
        layers = pkt.layers()
        deal_layers_record = dict()
        no_flag = ['', '1', '2', '3', '4']
        tmp_seq, tmp_ack = 0, 0
        for layer in layers:
            # 预防多重IP和多重vlan，对字段名称加以区分
            if layer in deal_layers_record:
                name_surfix = no_flag[deal_layers_record[layer]]
            else:
                name_surfix = ''
            # Ether解析
            fields = pkt[layer].fields
            if layer == Ether:
                ether_protos = {33024: Dot1Q, 2048: IP}
                if direction == 'up':
                    self.into_filed(flow, "mac_src", fields.get("src"), name_surfix)
                    self.into_filed(flow, "mac_dst", fields.get("dst"), name_surfix)
                else:
                    self.into_filed(flow, "mac_src", fields.get("dst"), name_surfix)
                    self.into_filed(flow, "mac_dst", fields.get("src"), name_surfix)
            # Dot1Q解析
            elif layer == Dot1Q:
                self.into_filed(flow, direction + "_vlan", fields.get("vlan"), name_surfix)
                self.into_filed(flow, direction + "_prio", fields.get("prio"), name_surfix)
            # IP解析
            elif layer in (IP, IPv6):
                if direction == 'up':
                    self.into_filed(flow, "sip", fields.get("src"), name_surfix)
                    self.into_filed(flow, "dip", fields.get("dst"), name_surfix)
                else:
                    self.into_filed(flow, "sip", fields.get("dst"), name_surfix)
                    self.into_filed(flow, "dip", fields.get("src"), name_surfix)
                self.into_filed(flow, "ip_version", fields.get("version"), name_surfix)
            # TCP/UDP解析
            elif layer in (TCP, UDP):
                if direction == 'up':
                    self.into_filed(flow, "sport", fields.get("sport"), name_surfix)
                    self.into_filed(flow, "dport", fields.get("dport"), name_surfix)
                else:
                    self.into_filed(flow, "sport", fields.get("dport"), name_surfix)
                    self.into_filed(flow, "dport", fields.get("sport"), name_surfix)
                tmp_seq = fields.get("seq")
                tmp_ack = fields.get("ack")
                _ = tmp_seq, tmp_ack  # suppress unused variable warning
                # 提取MSS
                if layer == TCP and "S" in fields.get("flags").flagrepr():
                    if "options" in fields:
                        options = dict(fields.get("options"))
                        if "MSS" in options:
                            mss = options["MSS"]
                            flow["mss"] = min(flow["mss"], mss) if "mss" in flow else mss
                # Raw解析
                raw_payload = Raw(pkt[layer].payload)
                if raw_payload.load.strip(b"\x00"):
                    load = raw_payload.load
                    flow["payload"][direction] += load

                    if "all" in flow["payload"]:
                        flow["payload"]["all"].append({direction: load})
                    else:
                        flow["payload"]["all"] = [{direction: load}]

                    max_payload_len = pkt[layer].payload.__len__()
                    flow["max_payload_len"] = max(flow["max_payload_len"],
                                                  max_payload_len) if "max_payload_len" in flow else max_payload_len
                    # 判断是否为http，提取http字段(GET、POST、PUT、DELETE、CONNECT、OPTIONS、TRACE、PATCH、HEAD)
                    if layer == TCP and HTTP_REQUEST_METHOD_PATTERN.match(load):
                        flow["l5"] = "HTTP"
                        http_fields = get_http_request_fields(load)
                    elif layer == TCP and load[0:5] == b'HTTP/':
                        http_fields = get_http_response_fields(load)
                    else:
                        http_fields = None
                    if http_fields and "http" in flow:
                        flow["http"].append(http_fields)
                    elif http_fields and "http" not in flow:
                        flow["http"] = [http_fields]
                    else:
                        pass

            # 记录已经处理的数据层
            if layer in deal_layers_record:
                deal_layers_record[layer] += 1
            else:
                deal_layers_record[layer] = 1

        # 包数、字节数统计
        if direction + "_pkts" in flow:
            flow[direction + "_pkts"] += 1
        else:
            flow[direction + "_pkts"] = 1
        if direction + "_bytes" in flow:
            flow[direction + "_bytes"] += len(pkt)
        else:
            flow[direction + "_bytes"] = len(pkt)

    def pkts_parser(self):
        """解析所有包并规范化流方向"""
        count = 0
        for pkt in self.pkts:
            self.pkt_parser(pkt, count)
            count += 1
        for key, flow in list(self.flowtable.tables.items()):
            if flow["direction"] == 1:
                parts = key.split("_")
                if len(parts) != 6:
                    raise RuntimeError(f'Error: flow_id format error, expected 6 parts, got {len(parts)}: {key}')
                f0, f1, f2, f3, f4, f5 = parts
                key_new = "_".join([f0, f1, f4, f5, f2, f3])
                if key_new not in self.flowtable.tables:
                    self.flowtable.tables[key_new] = self.flowtable.tables.pop(key)
                else:
                    raise RuntimeError(f"更改流方向：{key}-->{key_new}，但是{key_new}已经存在")


def get_http_request_fields(load):
    """
    解析HTTP请求

    Args:
        load: HTTP载荷 (bytes)

    Returns:
        dict: 包含 method, uri, version, headers 等字段
    """
    res = dict()
    http, _ = load.split(b'\r\n\r\n', 1)
    http_lines = http.split(b'\r\n')
    method, uri, version = http_lines[0].split()
    res['method'] = method
    res['uri'] = uri
    res['version'] = version
    for line in http_lines[1:]:
        key, value = line.split(b":", 1)
        res[key.strip()] = value.strip()
    return res


def get_http_response_fields(load):
    """
    解析HTTP响应

    Args:
        load: HTTP响应载荷 (bytes)

    Returns:
        dict: 包含 version, code, description, headers 等字段
    """
    res = dict()
    http, _ = load.split(b'\r\n\r\n', 1)
    http_lines = http.split(b'\r\n')
    version, code, description = http_lines[0].split()
    res['version'] = version
    res['code'] = code
    res['description'] = description
    for line in http_lines[1:]:
        key, value = line.split(b":", 1)
        res[key.strip()] = value.strip()
    return res


if __name__ == '__main__':
    # 测试代码
    print("PCAP分析工具模块")
    from device.tcpdump import Tcpdump
    tcpdump = Tcpdump(("10.12.131.32", 9000), tmppath="/home/tmp/tmp.pcap", eth="enp6s0f1", extended="port 8000")
    # print(tcpdump.tcpdump_start())
    # time.sleep(22)
    # print(tcpdump.tcpdump_stop())
    print(tcpdump.getsize("/home/tmp/tmp.pcap"))
    # tcpdump.path = "/home/tmp/tmp.pcap"
    # print(tcpdump.pcap_get("aaaa.pcap"))
    # pkt = tcpdump.getfo("/home/tmp/tmp.pcap",gzip=True)
    pkt = tcpdump.pcap_getfo()
    print(type(pkt))
    print(extract_4tuple_from_pcap(pkt))
    # sys.exit()
