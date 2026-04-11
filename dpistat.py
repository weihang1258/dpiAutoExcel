#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2023/3/14 14:01
# @Author  : weihang
# @File    : dpistat.py
import itertools
import re
import sys
import time
from common import setup_logging
from socket_linux import SocketLinux
logger = setup_logging(log_file_path="log/dpistat.log", logger_name="dpistat")

action2marex_policy = {"eu_plc": "/dev/shm/xsa/marex_eupolicy.stat",
                       "pcapdump": "/dev/shm/xsa/marex_pcapdump.stat",
                       "mirr": "/dev/shm/xsa/marex_mirrorvlan.stat",
                       "vpn_block": "/dev/shm/xsa/marex_vpn_block.stat"}
class CheckDpiStat(SocketLinux):
    def __init__(self, client: tuple):
        super().__init__(client)
        self.xrt_dict = self.xrt2dict()
        self.xrtinfo_dict = self.xrtinfo2dict()

    def xrt2dict(self):
        path = "/dev/shm/xsa/xrt.stat"
        res = dict()
        response = self.cmd("cat %s" % path)
        # logger.info(response)
        response2list = response.strip().split("\n")
        head = re.findall(r"[A-Z]\w+(?: [a-z]+)?", response2list[0].strip())
        for line in response2list[1:]:
            line2list = line.strip().split()
            res[line2list[0]] = dict(zip(head[1:], line2list[1:]))
        self.xrt_dict = res
        return res

    def xrtinfo2dict(self):
        path = "/dev/shm/xsa/xrtinfo.stat"
        res = dict()
        response = self.cmd("cat %s|grep dev -A 15" % path)
        # logger.info(response)
        response2list = response.strip().split("\n")
        head = re.findall(r"\w+", response2list[0].strip())
        for line in response2list[1:]:
            line2list = line.strip().split()
            res[line2list[0]] = dict(zip(head[1:], line2list[1:]))
        return res

    def port_for_snmp2dict(self):
        path = "/dev/shm/xsa/port_for_snmp.stat"
        res = dict()
        response = self.cmd("cat %s" % path)
        # logger.info(response)
        response2list = response.strip().split("\n")
        head = re.findall(r"(?:RX |TX )?\w+", response2list[0].strip())
        for line in response2list[1:]:
            line2list = line.strip().split()
            res[line2list[0]] = dict(zip(head[1:], line2list[1:]))
        return res

    def flow2dict(self):
        path = "/dev/shm/xsa/flow.stat"
        res = dict()
        response = self.cmd("cat %s|grep all -A 70" % path)
        # logger.info(response)
        response2list = response.strip().split("\n")
        for line in response2list:
            line = line.strip()
            if line:
                key, value = line.split()
                key = key.rstrip(":")
                res[key] = value
        return res

    def check_flow(self):
        err_list = list()
        flow2dict = self.flow2dict()
        for key, val in flow2dict.items():
            if "fail" in key:
                if val != "0":
                    err_list.append({key: val})
                    logger.error("\t失败项:%s\t解决方法：检查内存分配是否太少" % {key: val})
        return err_list

    def httpxdr2dict(self):
        path = "/dev/shm/xsa/httpxdr.stat"
        res = dict()
        response = self.cmd("cat %s" % path)
        # logger.info(response)
        response2list = response.strip().split("\n")
        head = re.findall(r"\w+", response2list[0].strip())
        for line in response2list[1:]:
            line2list = line.strip().split()
            res[line2list[0]] = dict(zip(head[1:], line2list[1:]))
        return res

    def check_httpxdr(self):
        err_list = list()
        httpxdr2dict1 = self.httpxdr2dict()
        for thread, data in httpxdr2dict1.items():
            for field, val in data.items():
                if val != "0":
                    err_list.append({"thread": thread, field: val})
                    logger.error("失败项:%s\t解决方法：检查内存分配是否太少" % {"thread": thread, field: val})
        return err_list

    def commem2dict(self):
        path = "/dev/shm/xsa/commem.stat"
        res = dict()
        response = self.cmd("cat %s|grep all -B1" % path)
        # logger.info(response)
        response2list = response.strip().split("\n")
        head = re.findall(r"\w+", response2list[0].strip())
        for line in response2list[1:]:
            line2list = line.strip().split()
            res[line2list[1]] = dict(zip(head[2:], line2list[2:]))
        return res

    def check_commem(self):
        err_list = list()
        commem2dict1 = self.commem2dict()
        for posi, data in commem2dict1.items():
            if data["errcnt"] != "0":
                err = {"posi": posi}
                err.update(data)
                err_list.append(err)
                if posi == "4" and int(data["blks"]) >= int(data["curcnt"]) * 1.5:
                    logger.error("失败项:%s\t无需解决，快照量并发量过大导致失败" % err)
                else:
                    logger.error("失败项:%s\t解决方法：对应增加%s号内存池，xsa.json中flow.compool.blk%s" % (err, posi, posi))
        return err_list

    def msgtask2dict(self):
        path = "/dev/shm/xsa/msgtask.stat"
        res = dict()
        response = self.cmd("cat %s" % path)
        # logger.info(response)
        for blk in response.strip().split("\n\n"):
            wtask, ftask = blk.split("ftask")
            ftask = "ftask" + ftask
            title, wtask = wtask.split("wtask")
            wtask = "wtask" + wtask
            title2dict = dict()
            taskname = None
            for tmp in title.strip().split(","):
                key, value = tmp.split(":")
                key = key.strip()
                value = value.strip()
                if key == "msgtask":
                    taskname = value
                else:
                    title2dict[key] = value
            res[taskname] = title2dict
            # logger.info(wtask,"\n\n")
            # logger.info(ftask)
            for key, content in [("wtask", wtask), ("ftask", ftask)]:
                # logger.info(content)
                res[taskname][key] = dict()
                content2list = content.strip().split("\n")
                head = re.findall(r"\w+", content2list[0].strip())
                for line in content2list[1:]:
                    line2list = line.strip().split()
                    res[taskname][key][line2list[0]] = dict(zip(head[1:], line2list[1:]))
        return res

    def check_msgtask(self):
        err_list = list()
        msgtask2dict1 = self.msgtask2dict()
        for fothread_name, data in msgtask2dict1.items():
            for wkthread, data1 in data["wtask"].items():
                if int(data1["send_msg_cnt"]) >= 100:
                    err = {"fothread_name": fothread_name, "wkthread": wkthread, "send_msg_cnt": data1["send_msg_cnt"]}
                    err_list.append(err)
                    logger.error("失败项:%s\t解决方法：fo对应的cpu过少，需要增加" % err)
        return err_list

    def eu_urlnode2dict(self):
        path = "/dev/shm/xsa/eu_urlnode.stat"
        res = dict()
        response = self.cmd("cat %s|grep all -A20" % path)
        # logger.info(response)
        response2list = response.strip().split("\n")
        for line in response2list[1:]:
            line = line.strip()
            if line:
                key, value = line.split()
                key = key.rstrip(":")
                res[key] = value
        return res

    def check_eu_urlnode(self):
        err_list = list()
        eu_urlnode2dict1 = self.eu_urlnode2dict()
        for key, val in eu_urlnode2dict1.items():
            if "fail" in key:
                if val != "0":
                    err_list.append({key: val})
                    logger.error("失败项:%s\t解决方法：eu缓存url的内存过小，需要增加" % {key: val})
        return err_list

    def eu_restore2dict(self):
        path = "/dev/shm/xsa/eu_restore.stat"
        res = dict()
        response = self.cmd("cat %s|grep 'all$' -A30" % path)
        # logger.info(response)
        response2list = response.strip().split("\n")
        for line in response2list[1:]:
            line = line.strip()
            if line:
                key, value = line.split()
                key = key.rstrip(":")
                res[key] = value
        return res

    def check_eu_restore(self):
        err_list = list()
        data = self.eu_restore2dict()
        for key, val in data.items():
            if "fail" in key:
                if val != "0":
                    err_list.append({key: val})
                    logger.error("失败项:%s\t解决方法：eu缓存文件的内存过小，需要增加" % {key: val})
        return err_list

    def mirrorvlan2dict(self):
        path = "/dev/shm/xsa/mirrorvlan.stat"
        res = dict()
        res["detail"] = dict()
        response = self.cmd("cat %s|grep total -A50" % path)
        # logger.info(response)
        blk2list = response.strip().split("\n\n")
        tmp_list = blk2list[0].strip().split("\n")
        head_list = tmp_list[1].strip().split()
        for line in tmp_list[2:]:
            line = line.strip()
            if line:
                key2value = list(zip(head_list, line.split()))
                res["detail"][key2value[0][1]] = dict(key2value[1:])
        tmp_list = blk2list[1].strip().split("\n")
        head_list = tmp_list[0].strip().split()
        value_list = tmp_list[1].strip().split()
        res.update(dict(zip(head_list, value_list)))
        return res

    def check_mirrorvlan(self):
        err_list = list()
        data = self.mirrorvlan2dict()
        for key, val in data.items():
            if "fail" in key:
                if val != "0":
                    err_list.append({key: val})
                    logger.error("镜像缓存失败项:%s\t解决方法：mirrorvlan镜像缓存的内存过小，需要增加" % {key: val})
            if key == "detail":
                for posi, data1 in val.items():
                    if data1["failed"] != "0":
                        err_list.append(val)
                        logger.error("镜像发包失败项:%s\t解决方法：需定位" % val)
        return err_list

    def pcapdump2dict(self):
        path = "/dev/shm/xsa/pcapdump.stat"
        res = dict()
        res["detail"] = dict()
        response = self.cmd("cat %s" % path)
        # logger.info(response)
        blk2list = response.strip().split("\n\n")
        tmp_list = blk2list[0].strip().split("\n")
        head_list = tmp_list[0].strip().split()
        for line in tmp_list[1:]:
            line = line.strip()
            if line:
                key2value = list(zip(head_list, line.split()))
                res["detail"][key2value[0][1]] = dict(key2value[1:])
        tmp_list = blk2list[1].strip().split("\n")
        head_list = tmp_list[0].strip().split()
        value_list = tmp_list[1].strip().split()
        res.update(dict(zip(head_list, value_list)))
        return res

    def check_pcapdump(self):
        err_list = list()
        data = self.pcapdump2dict()
        for key, val in data.items():
            if "_err" in key:
                if val != "0":
                    err_list.append({key: val})
                    logger.error("pcapdump写文件失败项:%s\t解决方法：需定位" % {key: val})
            if key == "detail":
                for wkthread, data1 in val.items():
                    for field, field_val in data1.items():
                        if "_err" in field and field_val != "0":
                            err_list.append(data1)
                            logger.error("pcapdump包缓存处理失败项:%s\t解决方法：需定位" % val)
        return err_list

    def xdrtxtlog22dict(self):
        path = "/dev/shm/xsa/xdrtxtlog2.stat"
        res = dict()
        response = self.cmd(args=f"cat {path}", bufsize=5120)
        # logger.info(response)
        response2list = response.strip().split("\n")
        head = re.findall(r"\w+", response2list[0].strip())
        for line in response2list[1:]:
            line2list = line.strip().split()
            res[line2list[0]] = dict(zip(head[1:], line2list[1:]))
        return res

    def uploadfile2dict(self):
        path = "/dev/shm/xsa/uploadfile.stat"
        res = dict()
        res["detail"] = dict()
        response = self.cmd("cat %s" % path)
        # logger.info(response)
        blk2list = response.strip().split("\n\n")
        line2list = blk2list[0].strip().split("\n")
        res.update(dict(map(lambda x: x.strip().split(":", 1), line2list[0].strip().split(","))))
        key, value = line2list[1].split(",", 1)[0].strip().split()
        res[key] = {"value": value}
        res[key].update(
            dict(map(lambda x: x.strip().split(":"), line2list[1].split(",", 1)[1].strip().rstrip(",").split(","))))
        for line in line2list[2:5]:
            key, value = line.split(",", 1)[0].strip().split()
            res[key] = {"value": value}
            res[key].update(
                dict(map(lambda x: x.strip().split(":"), line.split(",", 1)[1].strip().rstrip(";").split(";"))))
        for line in line2list[5:7]:
            for key, value in map(lambda x: x.strip().split(":"), line.strip().split(",")):
                res[key] = value
        for content in blk2list[1:]:
            line2list = content.strip().split("\n")
            srcdir = dict(map(lambda x: x.strip().split(":"), line2list[-1].strip().split(",")))["srcdir"]
            tmp = dict()
            for i in range(len(line2list) - 1):
                line = line2list[i]
                abc_field = dict()
                if i == 4:
                    key, value = line.strip().split(":")
                    abc_field[key] = dict()
                    for abc_field_detail in value.strip().split(","):
                        m, n = abc_field_detail.strip().split("=")
                        abc_field[key][m] = n
                    tmp.update(abc_field)
                elif i == 5:
                    tmp.update(dict(map(lambda x: x.strip().split("="), line.strip().split(","))))
                else:
                    tmp.update(dict(map(lambda x: x.strip().split(":"), line.strip().split(","))))
            if srcdir in res["detail"]:
                res["detail"][srcdir].append(tmp)
            else:
                res["detail"][srcdir] = [tmp]
        return res

    def eu_policy2dict(self):
        path = "/dev/shm/xsa/eu_policy.stat"
        res = dict()
        response = self.cmd("cat %s|grep all -A30" % path)
        # logger.info(response)
        response2list = response.strip().split("\n")
        for line in response2list[1:]:
            line = line.strip()
            if line:
                key, value = line.split()
                key = key.rstrip(":")
                res[key] = value
        return res

    def check_xrt(self):
        """检查xrt出现了哪些错误"""
        err_list = list()
        xrt2dict1 = self.xrt2dict()
        time.sleep(6)
        xrt2dict2 = self.xrt2dict()
        for key in xrt2dict2.keys():
            if key.startswith("0"):
                if xrt2dict2[key]["LState"] == "0":
                    logger.error("%s\t 网卡端口未点亮\t解决方法：检查光纤物理连接" % key)
                    continue
                elif int(xrt2dict2[key]["RX missed"]) - int(xrt2dict1[key]["RX missed"]) != 0:
                    logger.error("%s\t 收包missed\t解决方法：增加对应io核" % key)
                    err_list.append({key: "missed"})
                elif int(xrt2dict2[key]["RX errors"]) - int(xrt2dict1[key]["RX errors"]) != 0:
                    logger.error("%s\t 收包errors，线路问题\t解决方法：检查光纤物理连接,或者更换光模块" % key)
                elif int(xrt2dict2[key]["TX errors"]) - int(xrt2dict1[key]["TX errors"]) != 0:
                    logger.error("%s\t 发包errors，线路问题\t解决方法：检查光纤物理连接,或者更换光模块" % key)
                elif int(xrt2dict2[key]["TX fails"]) - int(xrt2dict1[key]["TX fails"]) != 0:
                    logger.error("%s\t 发包fails，...\t解决方法：..." % key)
                elif int(xrt2dict2[key]["Enque fails"]) - int(xrt2dict1[key]["Enque fails"]) != 0:
                    logger.error("%s\t io-wk收包队列失败\t解决方法：增加对应wk核" % key)
                else:
                    pass
        return err_list

    def check_xrtinfo(self):
        err_list = list()
        datadict1 = self.xrtinfo2dict()
        time.sleep(6)
        datadict2 = self.xrtinfo2dict()
        for key in datadict2.keys():
            if key.startswith("0"):
                if int(datadict2[key]["io_send_fail_towk"]) - int(datadict1[key]["io_send_fail_towk"]) != 0:
                    logger.error("%s\t io-wk包转发失败\t解决方法：增加对应wk核" % key)
                    err_list.append({key: "io_send_fail_towk"})
                elif int(datadict2[key]["wk_mirr_fail"]) - int(datadict1[key]["wk_mirr_fail"]) != 0:
                    logger.error("%s\twk_mirr_fail\t解决方法：..." % key)
                elif int(datadict2[key]["wkpkt_error"]) - int(datadict1[key]["wkpkt_error"]) != 0:
                    logger.error("%s\twkpkt_error\t解决方法：..." % key)
                else:
                    pass
        return err_list

    def check_time_main(self):
        """检查线程时间与系统时间相差10s以上，就返回True"""
        path = "/dev/shm/xsa/time_main.stat"
        res = False
        response = self.cmd("cat %s" % path)
        cur_time = int(self.cmd("date +%s"))
        for i in list(map(lambda x: cur_time - int(x), re.findall(r"time[:=](16\d+)", response, re.M))):
            if i > 10:
                logger.error("出现线程卡死，请检查！")
                logger.error(response)
                logger.error("当前时间:%s" % cur_time)
                res = True
                break
        return res

    def check_monitor_dpi(self, tailn: int = None):
        """返回重启超过1次的进程"""
        path = "/var/log/monitor_dpi.log"
        res = dict()
        if tailn:
            response = self.cmd(f"tail -n {tailn} {path}").strip()
        else:
            response = self.cmd("cat %s" % path).strip()
        # logger.info(response)
        for key, value in re.findall(r"dpi_monitor~\s*(/opt/dpi/\w+) is start run, run times (\d)", response, re.M):
            # logger.info(key, value)
            res[key] = value
        for key in res.copy():
            if res[key] == "1":
                res.pop(key)
        return res

    def xsarun_time(self):
        """返回xsa运行时间"""
        res = 0
        cmd = 'ps -eo etime,args|grep "/opt/dpi/xsa"|grep -v grep'
        response = self.cmd(cmd).strip()
        if response:
            if '-' in response:
                day, hms = response.split()[0].split('-')
            else:
                day = 0
                hms = response.split()[0]
            tmp = hms.split(":")
            if len(tmp) == 2:
                m, s = tmp
                h = 0
            else:
                h, m, s = tmp
            res = int(day) * 24 * 60 * 60 + int(h) * 60 * 60 + int(m) * 60 + int(s)
        return res

    def dpirun_time(self):
        """返回dpi程序运行时间"""
        res = dict()
        cmd = 'ps -eo etime,args|grep "/opt/dpi"|grep -v grep'
        content = self.cmd(cmd).strip()

        for line in content.strip().split("\n"):
            if not line:
                continue
            time_tmp, proc_tmp = line.strip().split()[:2]
            if not proc_tmp.startswith("/opt/dpi/"):
                continue
            # proc = proc_tmp[9:]
            proc = proc_tmp
            if time_tmp:
                if '-' in time_tmp:
                    day, hms = time_tmp.split()[0].split('-')
                else:
                    day = 0
                    hms = time_tmp.split()[0]
                tmp = hms.split(":")
                if len(tmp) == 2:
                    m, s = tmp
                    h = 0
                else:
                    h, m, s = tmp
                time = int(day) * 24 * 60 * 60 + int(h) * 60 * 60 + int(m) * 60 + int(s)
                res[proc] = time
        return res

    def datarpt_conn2dict(self):
        path = "/dev/shm/xsa/datarpt_conn.stat"
        res = dict()
        response = self.cmd("cat %s" % path)
        # logger.info(response)
        response2list = response.strip().split("\n")
        thread = None
        head_fileds = None
        for line in response2list:
            line = line.strip()
            if not line:
                continue
            if line.startswith("report thread "):
                thread = line.lstrip("report thread ").rstrip(":")
            elif line.startswith("ipaddr"):
                head_fileds = line.split()
            else:
                head_values = line.split()
                if thread in res:
                    res[thread].append(dict(zip(head_fileds, head_values)))
                else:
                    res[thread] = [dict(zip(head_fileds, head_values))]
        return res

    def check_datarpt_conn(self):
        err_list = list()
        datadict = self.datarpt_conn2dict()
        for key, var_list in datadict.items():
            logger.info(var_list)
            for val in var_list:
                if int(val["socket"]) < 0:
                    logger.error("线程编号：%s\tip：%-16s\t端口：%-5s\tsocket：%-5s\t解决方法：检测配置和服务端的端口监听情况" % (
                        key, val["ipaddr"], val["port"], val["socket"]))
                    err_list.append({"thread": key}.update(val))
        return err_list

    def datarpt2dict(self):
        path = "/dev/shm/xsa/datarpt.stat"
        res = dict()
        tmp = res
        response = self.cmd("cat %s|grep 'total :' -A 500" % path)
        response2list = response.strip().split("\n")
        for line in response2list:
            if ":" in line:
                key = line.split(":", maxsplit=1)[0].strip()
                tmp[key] = {}
                tmp = tmp[key]
            else:
                key, val = line.strip().split(maxsplit=1)
                tmp[key.strip()] = val.strip()
        return res

    def proto_app_2list(self):
        """将proto.app.stat解析成list格式"""
        path = "/dev/shm/xsa/proto.app.stat"
        res = list()
        response = self.cmd("cat %s" % path)
        response2list = response.strip().split("\n")
        head_list = response2list[0].strip().split()
        flag = False
        for line in response2list:
            if line.startswith("pid"):
                # head_list = line.strip().split(maxsplit=9)[:9]
                head_list = line.strip().split()
                flag = True
                continue
            if flag:
                values = line.strip().split()
                if len(head_list) != len(values):
                    logger.error(f"协议字段数量不一致\n协议头：{head_list}\n协议值:{values}")
                    min_count = min(len(head_list), len(values))
                    res.append(dict(zip(head_list[:min_count], values[:min_count])))
                else:
                    res.append(dict(zip(head_list, values)))
        return res

    def marex_eupolicy2dict(self, path="/dev/shm/xsa/marex_eupolicy.stat"):
        """解析/dev/shm/xsa/marex_eupolicy.stat成dict格式"""
        res = {"policy": {}, "rule match": {"total": 0, "data": {}}}
        cmd = f"touch {path}"
        self.cmd(cmd)
        response = self.cmd("cat %s" % path)
        response2block = response.strip().split("\n\n")
        for line in response2block[0].strip().split("\n")[1:]:
            for field in line.strip().split(","):
                key, val = field.split()
                res["policy"][key] = val
        block_1 = response2block[1].strip().split("\n")
        res["rule match"]["total"] = block_1[0].split(":")[1].split()[0]
        for line in block_1[2:]:
            key, val = line.strip().split()
            res["rule match"]["data"][key] = val
        return res

    def get_policy_total(self, action):
        '''
        获取策略加载成功数量
        :param action: eu_plc、pcapdump、mirr、vpn_block
        :return:
        '''
        path = action2marex_policy[action]
        return self.marex_eupolicy2dict(path=path)["policy"]["total"]

    def xdrtxtlog2dict(self):
        path = "/dev/shm/xsa/xdrtxtlog.stat"
        res = dict()
        response = self.cmd(args=f"cat {path}", bufsize=5120)
        # logger.info(response)
        response2list = response.strip().split("\n")
        head = re.findall(r"\w+", response2list[0].strip())
        for line in response2list[1:]:
            line2list = line.strip().split()
            res[line2list[0]] = dict(zip(head[1:], line2list[1:]))
        return res

    def wait_fopen(self, timeout=600):
        """
        等待dpi开始写文件，/dev/shm/xsa/xdrtxtlog.stat中
        :param timeout:等待时间，默认600s
        """
        logger.info("等待dpi写文件完成，超时时间:%s" % timeout)
        cur_time = time.time()
        while time.time() - cur_time <= timeout:
            try:
                xdrtxtlog2dict = self.xdrtxtlog2dict()
                fopen_ok = xdrtxtlog2dict["all"]["fopen_ok"]
                fclose_cnt = xdrtxtlog2dict["all"]["fclose_cnt"]
                if fopen_ok != fclose_cnt:
                    return True
                else:
                    time.sleep(2)
            except Exception:
                time.sleep(2)
                continue
        raise RuntimeError(f"wait_fopen超时，总共等待时间：{time.time() - cur_time}")

    def wait_fclose(self, timeout=600):
        """
        等待dpi写文件完成，/dev/shm/xsa/xdrtxtlog.stat中
        :param timeout:等待时间，默认600s
        """
        logger.info("等待dpi写文件完成，超时时间:%s" % timeout)
        cur_time = time.time()
        while time.time() - cur_time <= timeout:
            try:
                xdrtxtlog2dict = self.xdrtxtlog2dict()
                fopen_ok = xdrtxtlog2dict["all"]["fopen_ok"]
                fclose_cnt = xdrtxtlog2dict["all"]["fclose_cnt"]
                if fopen_ok == fclose_cnt:
                    return True
                else:
                    time.sleep(2)
            except Exception:
                time.sleep(2)
                continue
        raise RuntimeError(f"wait_fclose超时，总共等待时间：{time.time() - cur_time}")

    def wait_socket_fopen(self, timeout=60):
        """
        等待dpi开始写文件，/dev/shm/xsa/datarpt.stat中
        :param timeout:等待时间，默认600s
        """
        logger.info("等待socket写文件开始，超时时间:%s" % timeout)
        datarpt2dict = self.datarpt2dict()
        fopen_ok_s = datarpt2dict["process total"]["proc_logfile_open_succ"]
        # fclose_cnt_s = datarpt2dict["process total"]["proc_upload_file_write_cnt"]
        cur_time = time.time()
        while time.time() - cur_time <= timeout:
            try:
                datarpt2dict = self.datarpt2dict()
                fopen_ok_e = datarpt2dict["process total"]["proc_logfile_open_succ"]
                fclose_cnt_e = datarpt2dict["process total"]["proc_upload_file_close"]
                if fopen_ok_s != fopen_ok_e or fopen_ok_e != fclose_cnt_e:
                    return True
                else:
                    time.sleep(1)
            except Exception:
                time.sleep(2)
                continue
        raise RuntimeError(f"wait_socket_fopen，总共等待时间：{time.time() - cur_time}")

    def wait_socket_fclose(self, timeout=60):
        """
        等待dpi结束写文件，/dev/shm/xsa/datarpt.stat中
        :param timeout:等待时间，默认600s
        """
        logger.info("等待socket写文件完成，超时时间:%s" % timeout)
        cur_time = time.time()
        fopen_ok_e = None
        fclose_cnt_e = None
        while time.time() - cur_time <= timeout:
            try:
                datarpt2dict = self.datarpt2dict()
                fopen_ok_e = datarpt2dict["process total"]["proc_logfile_open_succ"]
                fclose_cnt_e = datarpt2dict["process total"]["proc_upload_file_close"]
                if fopen_ok_e == fclose_cnt_e:
                    return True
                else:
                    time.sleep(2)
            except Exception:
                time.sleep(2)
                continue
        raise RuntimeError(f"wait_socket_fclose，fopen_ok_e:{fopen_ok_e},fclose_cnt_e:{fclose_cnt_e}总共等待时间：{time.time() - cur_time}")

    def adms_idc_debug2dict(self, param=None):
        """
        将adms_idc_debug.stat转化为dict
        :param param: 获取dict结果中key对应的值，直接返回响应的value
        :return:
        """
        path = "/dev/shm/xsa/adms_idc_debug.stat"
        res = dict()
        response = self.cmd(args=f"cat {path} |grep 'worktask: all' -A40", bufsize=5120)
        # logger.info(response)
        response2list = response.strip().split("\n")
        for line in response2list[1:]:
            line2list = line.strip().split(":", 1)
            res[line2list[0].strip()] = line2list[1].strip()
        if param:
            return res.get(param, "")
        return res

    def eublock2dict(self):
        path = "/dev/shm/xsa/eublock.stat"
        res = dict()
        response = self.cmd("cat %s" % path)
        # logger.info(response)
        response2list = response.strip().split("\n")
        head = re.findall(r"\w+", response2list[0].strip())
        for line in response2list[1:]:
            line2list = line.strip().split()
            res[line2list[0]] = dict(zip(head[1:], line2list[1:]))
        self.xrt_dict = res
        return res

if __name__ == '__main__':
    # c = SSHManager(host="172.31.139.147", user="root", passwd="Rzx!@!*baizhao", port=22)
    # ssh = SSHManager(host="172.31.140.98", user="root", passwd="yhce123!@#", port=22)
    a = CheckDpiStat(("10.12.131.81", 9000))
    print(a.datarpt2dict())
    print(a.wait_socket_fclose())
    # print(a.cmd("cat /dev/shm/xsa/datarpt.stat|grep 'total' -A 500"))
    # print(pow(2, 3))
    # logger.info(a.mirrorvlan2dict().get("detail",{}).get(str(pow(2, 2)), {}))
    # logger.info(a.pcapdump2dict().get("write_blk", 0))
    # logger.info(a.marex_eupolicy2dict())
    # logger.info(list(itertools.chain(a.datarpt_conn2dict().values())))
    # logger.info(a.marex_eupolicy2dict("/dev/shm/xsa/marex_vpn_block.stat"))
    # logger.info("\n".join(list(map(lambda x: f'{x[0]}: {x[1]}',a.check_monitor_dpi().items()))))

    # module2value = {
    #     "flow": 2,
    #     "xdr": 1,
    #     "httpproto": 1,
    #     "proto": 1,
    #     "wkxdr": 1,
    #     "httpxdr": 1,
    #     "mirrorvlan": 1,
    #     "pcapdump": 1,
    #     "eu": 1,
    #     "eublock": 1,
    #     "tcpsegment": 1,
    #     "transmit": 2,
    #     "tcpmsg": 1,
    #     "uploadfile": 1,
    #     "foxdr": 2,
    #     "xdrtxtlog": 1
    # }
    # # 100G ["E810-C"]  10G网卡 ["82599ES", "x710"] 1G ["I350", "VMXNET3"]
    # pciname2attribute = {
    #     "I350 Gigabit Network Connection 1521": {"speed": 1000},
    #     "VMXNET3 Ethernet Controller 07b0": {"speed": 1000},
    #     "82599ES 10-Gigabit SFI/SFP+ Network Connection 10fb": {"speed": 10000},
    #     "Ethernet Controller X710 for 10GbE SFP+ 1572": {"speed": 10000},
    #     "Ethernet Controller E810-C for QSFP 1592": {"speed": 100000}
    # }
    # module2cpucount = {
    #     "xdrstator": {"xdrstator.xstator_cpu": 1},
    #     "flow": {"dpi.marex_cpu": 1},
    #     "pcapdump": {"pcapdump.cpu": 1},
    #     "uploadfile": {"uploadfile.cpu": 1},
    #     "datarpt": {"datarpt.proc_core": 1, "datarpt.rpt_core": 1}
    # }
    # # pcis = {"rx": ["0000:04:00.0", "0000:04:00.1", "0000:83:00.0"], "rst": ["0000:85:00.0"]}
    # pcis = {"rx": ["0000:03:00.0", "0000:03:00.2"]}
