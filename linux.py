#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2023/3/14 9:39
# @Author  : weihang
# @File    : linux.py
import os
import re
import json
from collections import OrderedDict, defaultdict
from io import BytesIO
from ssh import SSHManager


class Linux:
    def __init__(self, ssh: SSHManager):
        self.ssh = ssh

    def mkdir(self, path):
        if self.exist_dir(path):
            return
        cmd = 'mkdir -p %s' % path
        self.ssh.ssh_exec_cmd(cmd)

    def chomd_x(self, path):
        cmd = 'chmod +x %s' % path
        self.ssh.ssh_exec_cmd(cmd)

    def reboot(self):
        cmd = 'reboot'
        self.ssh.ssh_exec_cmd(cmd)

    def get_cpu_dict(self):
        cmd = 'lscpu'
        res = self.ssh.ssh_exec_cmd(cmd).decode()
        return self._split_pairs(res)

    def _split_pairs(self, info, split_flag=":"):
        """
        将成对信息改成字典格式，如：
        Architecture:          x86_64
        CPU op-mode(s):        32-bit, 64-bit

        :param info:
        :return:
        """
        res = dict()
        for line in info.strip().split('\n'):
            if ':' in line:
                key, value = line.strip().split(split_flag, 1)
            else:
                key, value = line.strip().split(split_flag, 1)
            res[key.strip()] = value.strip()
        return res

    def get_numa(self):
        """
        返回numa信息，比如：{'1': '12-23,36-47', '0': '0-11,24-35'}
        :return:
        """
        res = dict()
        cpu_dict = self.get_cpu_dict()
        for key in cpu_dict.keys():
            search = re.search(r'NUMA.+\D(\d+)+ CPU', key)
            if search:
                id = search.group(1)
                value = cpu_dict[key]
                res[id] = value
        return res

    def get_cpulist(self):
        """[['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11'], ['12', '13', '14', '15', '16', '17', '18', '19', '20', '21', '22', '23']]"""
        numa = self.get_numa()
        res = list()
        for key in sorted(numa.keys()):
            line_numa = numa[key]
            tmp_list = list()
            for i in line_numa.strip().split(','):
                start, end = i.strip().split('-')
                for j in range(int(start), int(end) + 1):
                    tmp_list.append(str(j))
            res.append(tmp_list)
        return res

    def _get_ethname(self):
        """
        获取已网卡名为维度的字典
        :return:
        """
        cmd = 'ip a'
        res = self.ssh.ssh_exec_cmd(cmd)
        ethinfos = list()
        lines = str(res).strip().split('\n')

        tmp = list()
        start, end = 0, 0
        for line in lines:
            if re.match(r'[0-9]+', line):
                ethinfos.append(tmp)
                tmp = [line]
            else:
                tmp.append(line)
        ethinfos.append(tmp)
        ethinfos = ethinfos[1:]
        res = defaultdict(lambda: None)
        for ethinfo in ethinfos:
            for line in ethinfo:
                if re.match(r'[0-9]+', line):
                    ethname = line.strip().split()[1].rstrip(':')
                    state = re.search(r'state (\S+) ', line).group(1)
                    cmd = "ethtool -i %s|grep bus-info|awk '{print $2}'" % ethname
                    pci = self.ssh_exec_cmd(cmd).strip()
                    if ethname not in res:
                        res[ethname] = defaultdict(lambda: None)
                    res[ethname]['state'] = state
                    res[ethname]['pci'] = pci
                elif r'link/ether ' in line:
                    mac = line.strip().split()[1]
                    res[ethname]['mac'] = mac
                elif 'inet ' in line:
                    ipv4 = line.strip().split()[1].split(r'/')[0]
                    netmaskv4 = line.strip().split()[1].split(r'/')[1]
                    res[ethname]['ipv4'] = ipv4
                    res[ethname]['netmaskv4'] = netmaskv4
                elif 'inet6 ' in line:
                    ipv6 = line.strip().split()[1].split(r'/')[0]
                    netmaskv6 = line.strip().split()[1].split(r'/')[1]
                    res[ethname]['ipv6'] = ipv6
                    res[ethname]['netmaskv6'] = netmaskv6
                else:
                    pass

        return res

    def _get_pci2ethname(self):
        """
        将以网卡名名为key的字典改成以pci为key
        :param ethname_dict:
        :return:
        """
        ethname_dict = self._get_ethname()
        res = defaultdict(lambda: None)
        for key, value in ethname_dict.items():
            if value['pci']:
                res[value['pci']] = value
                res[value['pci']]['ethname'] = key
                del res[value['pci']]['pci']
        return res

    def get_eth(self):
        """
        获取网卡信息，以pci为key的字典，如：
        0000:03:00.3, {'state': 'DOWN', 'ethname': 'enp3s0f3', 'model': 'I350', 'type': 'Gigabit', 'mac': '04:25:c5:83:8a:f4', 'manufacturer': 'Intel','numa_id':1})
        0000:03:00.2, {'state': 'DOWN', 'ethname': 'enp3s0f2', 'model': 'I350', 'type': 'Gigabit', 'mac': '04:25:c5:83:8a:f3', 'manufacturer': 'Intel'})
        :return:
        """
        ethnamebypci = self._get_pci2ethname()
        res = defaultdict(lambda: None)
        cmd = 'lspci|grep Eth'
        info = self.ssh.ssh_exec_cmd(cmd).decode()
        for line in info.strip().split('\n'):
            fields = line.strip().split()
            pci = fields[0]
            if len(pci) == 7:
                pci = '0000:' + pci
            manufacturer = fields[3]
            model = fields[5]
            type = fields[6]
            if pci not in res:
                res[pci] = defaultdict(lambda: None)
            res[pci]['manufacturer'] = manufacturer
            res[pci]['model'] = model
            res[pci]['type'] = type
            res[pci]['numa_id'] = self.ssh.ssh_exec_cmd("cat /sys/bus/pci/devices/%s/numa_node" % pci).strip()
            if pci in ethnamebypci:
                res[pci].update(ethnamebypci[pci])
        return res

    def get_numa2pciinfo_by_ssh(self):
        devbind_file = self.ssh.ssh_exec_cmd(
            "find / -type f -name dpdk-devbind.py -perm 755|head -n 1").decode().strip()
        # print(devbind_file)
        cmd = """%s -s |  grep ':'  | awk -F " "  '{print $0; cmd="echo numa,`cat /sys/bus/pci/devices/"$1"/numa_node`"; system(cmd) }' """"" % devbind_file
        content = self.ssh.ssh_exec_cmd(cmd).decode()
        # print(content)
        pci_info = dict()
        res = dict()
        for line in content.strip().split("\n"):
            line = line.strip()
            pci_info_tmp = dict()
            if line.startswith("numa,"):
                numa = line.lstrip("numa,")
                if numa not in res:
                    res[numa] = list()
                res[numa].append(pci_info)
            else:
                tmp1, tmp = line.split(" ", 1)
                pci_info_tmp["pci"] = tmp1
                tmp2, tmp = tmp.lstrip("'").split("' ", 1)
                pci_info_tmp["name"] = tmp2
                for i in tmp.split(" "):
                    if "=" in i:
                        key, value = i.split("=")
                        pci_info_tmp[key] = value
            pci_info = pci_info_tmp
        return res

    def numa2cpu_seg(self):
        """
        通过ssh获取lscpu的数据，形式字典格式，并增加字段numa2cpu :	 {'0': [['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10'], ['24', '25', '26', '27', '28', '29', '30', '31', '32', '33', '34']], '1': [['12', '13', '14', '15', '16', '17', '18', '19', '20', '21', '22'], ['36', '37', '38', '39', '40', '41', '42', '43', '44', '45', '46']]}
        :param ssh_dpi:
        :return:
        """
        result = dict()
        response = self.ssh.ssh_exec_cmd("lscpu").decode()
        for line in response.strip().split('\n'):
            # print(line)
            key, value = line.strip().split(":", 1)
            value = value.strip()
            result[key] = value
        numa2cpu = dict()
        for i in range(int(result["NUMA upper_node(s)"])):
            key = "NUMA upper_node%s CPU(s)" % i
            numa2cpu[str(i)] = list()
            for j in result[key].split(","):
                s, e = j.split("-", 1)
                numa2cpu[str(i)].append(list(map(lambda x: str(x), range(int(s), int(e) + 1))))
        result["numa2cpu"] = numa2cpu
        return result

    def get_cpu_info(self):
        """
                通过ssh获取CPU信息
                :param cmd:
                :return:
                [0]:查看物理CPU个数
                [1]:查看每个物理CPU中core的个数(即核数)
                [2]:查看逻辑CPU的个数
                [4]:查看CPU信息（型号）
                """
        try:
            cup_No = self.ssh.ssh_exec_cmd('cat /proc/cpuinfo| grep "physical id"| sort| uniq| wc -l')
            cpu_core_No = self.ssh.ssh_exec_cmd('cat /proc/cpuinfo| grep "cpu cores"| uniq')
            cpu_logic_No = self.ssh.ssh_exec_cmd('cat /proc/cpuinfo| grep "processor"| wc -l')
            cpu_model_No = self.ssh.ssh_exec_cmd('cat /proc/cpuinfo | grep name | cut -f2 -d: | uniq -c')

            return [int(cup_No), int(str(cpu_core_No).split(':')[1]), int(cpu_logic_No),
                    str(cpu_model_No).strip().split(' ', 1)[1].lstrip()]
        except Exception as e:
            print(e)

    def get_free_info(self):
        """
                通过ssh执行远程命令获取内存信息
                :param cmd:
                :return:
                [0]:内存总量
                [1]:已占用
                [2]:未占用
                [4]:shared
                [5]:buffers
                [6]:cached
                """
        try:
            free_info = self.ssh.ssh_exec_cmd('free -g |grep Mem')

            return str(free_info).strip().split()[1:]
        except Exception as e:
            print(e)

    def get_disk_info(self):
        """
                通过ssh执行远程命令获取硬盘信息
                :param cmd:
                :return:
                {key:val}:硬盘名和大小（单位GB），比如 {'sda': 1000.2, 'sdb': 1000.2}

                """
        try:
            res = self.ssh.ssh_exec_cmd("fdisk -l |grep '/dev/sd.[：:]'").decode()
            # print(res)
            disk_info = dict()
            for line in str(res).strip().split('\n'):
                m, n = line.strip().split(",")[0].split(":", 1)
                key = m.rsplit("/", 1)[1]
                val = n.strip()
                disk_info[key] = val
            return disk_info
        except Exception as e:
            print('get_disk_info', e)

    def servers_info(self):
        """
                通过ssh执行远程命令获取设备信息
                :param cmd:
                :return:
                [0]:CPU信息
                [1]:硬盘总量，单位GB
                [2]:内存信息

                """
        try:
            cpu_info = self.get_cpu_info()
            disk_info = self.get_disk_info()
            free_info = self.get_free_info()

            return [cpu_info, disk_info, free_info]

        except Exception as e:
            print(e)

    def listdir(self, path, key=None):
        """
                通过ssh执行远程命令获取目录下文件
                :param cmd:
                :return:
                [0]:目录下文件
                """
        try:
            # if key is None:
            #     str1 =  "find . -name '*' ! -name '.'"
            # else:
            #     str1 = "find . -name '%s'" % key
            # res = self.ssh_exec_cmd(cmd=str1,path=path)
            # new_list = list()
            # for i in str(res).strip().split('\n'):
            #     new_list.append(i[2:])
            # return new_list
            if key is None:
                key = ''
            cmd = 'ls -rt %s' % key
            # print cmd
            return str(self.ssh.ssh_exec_cmd(cmd=cmd, path=path)).strip().split()
        except Exception as e:
            print(e)

    def countdir(self, path, key=None):
        try:
            if key is None:
                str1 = "find . -name '*' ! -name '.'|wc -l"
            else:
                str1 = "find . -name '%s'|wc -l" % key
            res = int(self.ssh.ssh_exec_cmd(cmd=str1, path=path))
            return res
        except Exception as e:
            print(e)

    def cleandir(self, path, key=None):
        try:
            if key is None:
                str1 = r"find . -name '*' ! -name '.' -exec rm -f {} \;"
            else:
                str1 = r"find . -name '%s' -exec rm -f {} \;" % key
            self.ssh.ssh_exec_cmd(cmd=str1, path=path)
        except Exception as e:
            print(e)

    def deldir(self, path):
        try:
            path = str(path).rstrip('/')
            str1 = "rm -rf %s" % path
            self.ssh.ssh_exec_cmd(cmd=str1)
        except Exception as e:
            print(e)

    def get_es_data(self, type_id):
        path = list()
        count = 0
        if type_id == 3:
            path.append('/appslog/act/data/elasticsearch/in/accesslog')
        elif type_id == 4:
            path.append('/appslog/act/data/elasticsearch/in/alarm_isms')
        elif type_id == 5:
            path.append('/appslog/act/data/elasticsearch/in/block_isms')
        elif type_id == 8:
            path.append('/appslog/act/data/elasticsearch/in/domain_activelog')
            path.append('/appslog/act/data/elasticsearch/in/ip_activelog')
        for i in path:
            res = self.ssh.ssh_exec_cmd('ls %s |wc -l' % i)
            # print '-1',type(res),'1-'
            count += int(res)
        return count

    def get_count(self):
        return int(self.ssh.ssh_exec_cmd('ls |wc -l'))

    def exist_path(self, path):
        res = self.ssh._exec_command('du -b %s' % path)
        # print(res)
        if len(res) == 0:
            return False
        else:
            return True

    def exist_file(self, path):
        res = self.ssh._exec_command('ls -l %s|head -n 1|grep ^-' % path)
        # print res
        if len(res) == 0:
            return False
        else:
            return True

    def exist_dir(self, path):
        res = self.ssh._exec_command('ls -ld %s| grep "^d"' % path)
        # print res
        if len(res) == 0:
            return False
        else:
            return True

    def get_cpu_free_by_proc(self, proc_name):
        '''
        获取指定进程占用的CPU和内存
        :param proc_name: 进程名称列表
        :return: 元组
        cpu_usr:CPU占用率
        free_usr:free占用率
        '''
        cpu_usr = 0.0
        free_usr = 0.0
        # if len(proc_name) > 10:
        #     name = proc_name[:10]
        # else:
        #     name = proc_name
        # str1 = "top -b -n2 |grep ' %s'|awk '{print $9,$10,$11,$12}'"
        str1 = "ps -ef|grep '%s$' |grep -v 'grep'|awk '{print $2}'" % proc_name
        tmp = ' '
        for i in str(self.ssh.ssh_exec_cmd(str1)).strip().split('\n'):
            tmp += '-p %s ' % i

        str2 = "top %s -b -n 2" % tmp
        res_str2 = str(self.ssh.ssh_exec_cmd(str2)).strip().split('\n')
        res = list()
        for i in range(len(res_str2) - 1, -1, -1):
            if 'PID USER' in res_str2[i]:
                res = res_str2[i + 1:]
                break

        for line in res:
            tmp = str(line).strip().split()
            cpu_usr += round(float(tmp[-4]), 1)
            free_usr += round(float(tmp[-3]), 1)

        # str1 = "top -p $(ps -ef|grep '%s$' |grep -v 'grep'|awk '{print $2}') -p 2432 -b -n 2" % name

        return round(cpu_usr, 1), round(free_usr, 1)

    # 获取服务器当前时间
    def getsystime(self):
        return str(self.ssh.ssh_exec_cmd('date "+%Y-%m-%d %H:%M:%S"')).strip()

    # 获取文件的修改时间
    def get_dir_date(self, path):
        return str(self.ssh.ssh_exec_cmd('date -r %s "+%%Y-%%m-%%d %%H:%%M:%%S"' % path)).strip()

    def wget_ftp(self, user, password, ftp_path, local_path):
        # cmd = "wget  --ftp-user=ceshi --ftp-password=act123  ftp://172.31.134.180/02测试/CD1907061_中国电信统一DPI/V1.0.1.0/dpi_telecom_V1.0.1.0_9_20191125/ACT-TDPI-dpi_telecom-V1.0.1.0-9_20191125170900.tar.gz -P /home"
        cmd = "wget  --ftp-user=%s --ftp-password=%s  %s -P %s" % (
            user, password, ftp_path, local_path)
        # print(cmd)
        self.ssh.ssh_exec_cmd(cmd)
        local_file = str(local_path).rstrip('/') + '/' + str(ftp_path).strip().split('/')[-1]
        # print(local_file)
        if self.exist_file(local_file):
            return True
        else:
            return False

    def untar(self, file_path, save_path=None):
        if save_path is None:
            save_path = '/'.join(str(file_path).strip().split('/')[:-1])
        cmd = 'tar -xzvf %s' % file_path
        # print cmd
        self.ssh.ssh_exec_cmd(cmd=cmd, path=save_path)

    def walk_files(self, path: str):
        dir_list = list()
        file_list = list()
        cmd = "find ./ -type f"
        res = self.ssh.ssh_exec_cmd(cmd=cmd, path=path).decode()
        res_list = res.split("\n")
        for i in res_list:
            if i.strip():
                rela_path = i.lstrip("./")
                file_list.append(rela_path)
        return file_list

    def routeinfo(self):
        res = defaultdict(lambda: None)
        cmd = "route -n"
        response = self.ssh.ssh_exec_cmd(cmd).decode()
        lines = response.strip().split("\n")
        if len(lines) > 2:
            head_list = lines[1].strip().split()
            for line in lines[2:]:
                fields = line.strip().split()
                tmp_dict = dict(zip(head_list, fields))
                key = tmp_dict.pop("Destination")
                res[key] = tmp_dict
        return res

    def name2rota(self):
        res = dict()
        cmd = "lsblk -d -o name,rota"
        response = self.ssh.ssh_exec_cmd(cmd).decode().strip()
        lines = response.split("\n")
        # head = lines[0].split()
        for line in lines[1:]:
            fileds = line.strip().split()
            if len(fileds) == 2:
                res[fileds[0]] = fileds[1]
        return res

    def name2ssdhhd(self):
        ssdhhd = {"0": "SSD", "1": "HDD"}
        return dict(map(lambda x: (x[0], ssdhhd[x[1]]), self.name2rota().items()))

    def mtu(self, eth, value=2000):
        cmd = "ifconfig %s|grep mtu|awk '{print $4}'" % eth
        mtu = self.ssh.ssh_exec_cmd(cmd)
        if int(mtu) != value:
            cmd = f"ifconfig {eth} mtu {value}"
            self.ssh.ssh_exec_cmd(cmd)

    def get(self, remotepath, locatpath):
        if not self.exist_file(remotepath):
            raise RuntimeError(f"远程文件不存在:{remotepath}")
        if os.path.isfile(locatpath):
            os.remove(locatpath)
        self.ssh._sftp.get(remotepath=remotepath, localpath=locatpath)

    def getfo(self, remotepath):
        if not self.exist_file(remotepath):
            raise RuntimeError(f"远程文件不存在:{remotepath}")
        fl =BytesIO()
        self.ssh._sftp.getfo(remotepath=remotepath, fl=fl)
        fl.seek(0)
        return fl

    def put(self, locatpath, remotepath):
        if not os.path.isfile(locatpath):
            raise RuntimeError(f"本地文件不存在:{locatpath}")
        self.ssh.ssh_exec_cmd(f"rm -rf {remotepath}")
        self.ssh._sftp.put(localpath=locatpath, remotepath=remotepath)

    def putfo(self, fl: BytesIO, remotepath):
        self.ssh.ssh_exec_cmd(f"rm -rf {remotepath}")
        fl.seek(0)
        self.ssh._sftp.putfo(remotepath=remotepath, fl=fl)

    def md5(self, remotepath):
        return  self.ssh.ssh_exec_cmd("md5sum %s|awk {'print $1'}" % remotepath).strip()
if __name__ == '__main__':
    ssh = SSHManager(host='172.31.140.105', user='root', passwd='yhce123!@#', port=22)
    linux = Linux(ssh)
    # print(linux.get_disk_info())
    # print(linux.name2ssdhhd())
    # ssh_dpi.mkdir('/home/tmp1')
    # print linux.getsystime()
    # print linux.get_cpu_info()
    # print linux.get_free_info()
    # print linux.get_disk_info()
    # print linux.get_count()
    # a = linux.ssh_exec_cmd('cat /tmp/syscfg.json')
    # print a, type(a)
    # b = json.loads(a, _encoding='utf-8', object_pairs_hook=OrderedDict)
    # a = linux._get_ethname()
    # print linux.get_numa()
    # for k,v in linux.get_eth().items():
    #     print(k,v)
    # print linux.ssh_exec_cmd("cat /sys/bus/pci/devices/0000:82:00.1/numa_node")
    # print(linux.mtu("ens224",value=2000))
    print(linux.tcpdump_stop())
    print(linux.tcpdump_start("/home/001-过滤-目的IP+目的端口（入向）_A.pcap", extended="port 8000"))

