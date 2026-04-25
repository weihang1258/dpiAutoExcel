#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2023/3/7 9:22
# @Author  : weihang
# @File    : ssh_dpi.py
import os
import time
from functools import reduce

import paramiko
from utils.common import wait_until, get_port_unused, setup_logging
from sshtunnel import SSHTunnelForwarder

logger = setup_logging(log_file_path="log/ssh.log", logger_name="ssh")


def ssh_tunnel(host, port, username, password, remote_host, remote_port, allow_agent=False):
    server = SSHTunnelForwarder(
        ssh_address_or_host=(host, port),
        ssh_username=username,
        ssh_password=password,
        # ssh_pkey=paramiko.RSAKey.from_private_key_file(r"C:\Users\weihang.ACT-TELECOM\.ssh\id_rsa", "yhce123!@#"),
        remote_bind_address=(remote_host, remote_port),
        # local_bind_address=('0.0.0.0', get_port_unused()),
        allow_agent=allow_agent
    )
    server.start()
    server._check_is_started()
    print(server.is_active)
    return server


class VerificationSsh:
    """SSH 客户端，用于与远程 Linux 设备建立 SSH 连接并执行命令。

    支持普通用户登录和 root 权限切换，支持 SSH 隧道配置。

    Attributes:
        host (str): 远程主机地址
        username (str): SSH 用户名
        password (str): SSH 密码
        port (int): SSH 端口
        root_pwd (str): root 密码（用于权限提升）
        c: Paramiko Channel 对象，用于执行命令

    Examples:
        >>> ssh = VerificationSsh("192.168.1.100", "user", "pass", 22)
        >>> result = ssh.channel_exec_cmd("ls -la")
    """

    def __init__(self, host, username, password, port, root_pwd=None, tunnel_configs: list = None):
        """初始化 SSH 客户端。

        Args:
            host: 远程主机地址
            username: SSH 用户名
            password: SSH 密码
            port: SSH 端口
            root_pwd: root 密码（用于权限提升）
            tunnel_configs: SSH 隧道配置列表，
                格式如 [{"host": host, "port": port, "username": username, "password": password}]
        """
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.root_pwd = root_pwd
        self.ssh = paramiko.SSHClient()
        self.tunnel_configs = tunnel_configs
        # if self.tunnel_config:
        #     self.tunnel = ssh_tunnel(remote_host=host, remote_port=port, **tunnel_config)
        #     self.host = "127.0.0.1"
        #     self.port = self.tunnel.local_bind_port
        if self.tunnel_configs:
            for i in range(len(tunnel_configs)):
                if i == 0:
                    self.c = VerificationSsh(**tunnel_configs[i]).c
                else:
                    self.tunnel(**tunnel_configs[i])
            self.tunnel(host=self.host, port=self.port, username=self.username, password=self.password)
        else:
            self.c = self.chanel()
        if self.username != 'root' and self.root_pwd:
            self.root(pwd=self.root_pwd)

        # self.c.setblocking(1)
        # self.c.timeout = None
    def __del__(self):
        try:
            if hasattr(self, 'c') and self.c:
                self.c.close()
        except:
            pass
        try:
            if self.ssh:
                self.ssh.close()
        except:
            pass

    def root(self, pwd):
        time.sleep(0.1)
        # # 先判断提示符，然后下一步在开始发送命令，这样大部分机器就都不会出现问题
        # buff = b''
        # while not buff.endswith(b'$ '):
        #     resp = self.c.recv(9999)
        #     buff += resp
        #     time.sleep(0.1)
        # ssh_dpi.send(' export LANG=en_US.UTF-8 \n') #解决错误的关键，编码问题
        # ssh_dpi.send('export LANGUAGE=en \n')

        self.c.send(b'su - \n')
        buff = b""
        while not (buff.endswith('密码：'.encode()) or buff.endswith(b'Password: ')):  # true
            resp = self.c.recv(9999)
            buff += resp
        self.c.send(pwd)
        self.c.send(b'\n')
        buff = b""
        while not (buff.endswith(b'# ') or buff.endswith(b'$ ')):
            resp = self.c.recv(9999)
            buff += resp
        if buff.endswith(b'$ '):
            self.ssh.close()
            raise RuntimeError('超级管理员登录失败！')

    def tunnel(self, host, port, username, password, timeout=3):
        # self.c.setblocking(0)
        # self.c.settimeout(timeout)
        time.sleep(0.1)
        # # 先判断提示符，然后下一步在开始发送命令，这样大部分机器就都不会出现问题
        # buff = b''
        # while not buff.endswith(b'$ ') or not buff.endswith(b'# '):
        #     resp = self.c.recv(9999)
        #     buff += resp
        #     time.sleep(0.1)
        # ssh_dpi.send(' export LANG=en_US.UTF-8 \n') #解决错误的关键，编码问题
        # ssh_dpi.send('export LANGUAGE=en \n')

        self.c.send(('ssh %s@%s -p %s \n' % (username, host, port)).encode())
        buff = b""
        while not (buff.endswith('密码：'.encode()) or buff.endswith(b'assword: ') or buff.endswith(b'(yes/no/[fingerprint])? ')) :  # true
            resp = self.c.recv(9999)
            # print(1111,resp)
            buff += resp
        if buff.endswith(b'(yes/no/[fingerprint])? '):
            self.c.send(b"yes")
            self.c.send(b'\n')
            buff = b""
            while not (buff.endswith('密码：'.encode()) or buff.endswith(b'assword: ')):  # true
                resp = self.c.recv(9999)
                # print(2222, resp)
                buff += resp
        self.c.send(password)
        self.c.send(b'\n')
        buff = b""
        while not (buff.endswith(b'# ') or buff.endswith(b'$ ') or  buff.endswith('密码：'.encode()) or buff.endswith(b'assword: ')) :
            resp = self.c.recv(9999)
            # print(3333, resp)
            buff += resp
        if buff.endswith('密码：'.encode()) or buff.endswith(b'assword: '):
            self.ssh.close()
            raise RuntimeError(f'ssh登录{host}-{port}失败！')
        elif buff.endswith(b'# ') or buff.endswith(b'$ '):
            print(f'ssh登录{host}-{port}成功！')
        # self.c.timeout = None
        # self.c.setblocking(1)


    def chanel(self) -> paramiko.channel.Channel:
        """创建 SSH Channel 并建立连接。

        Returns:
            paramiko.channel.Channel: SSH Channel 对象
        """
        self.ssh = paramiko.SSHClient()
        self.ssh.load_system_host_keys()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        # print(self.host, self.port, self.username, self.password)
        self.ssh.connect(hostname=self.host, port=int(self.port), username=self.username, password=self.password,
                         timeout=5)
        # stdin, stdout, stderr = s.exec_command(cmd)
        # print(str(stdout.read()))
        # print(str(stdout.read()))
        # if str(stdout.read()).find('This account is currently not available.') != -1:
        #     return [False, 'This account is currently not available.']
        print(f'ssh登录{self.host}-{self.port}成功！')
        self.login_prefix = self.ssh.invoke_shell().recv(9999)
        self.ssh.invoke_shell().sendall("pwd")
        self.ssh.invoke_shell().sendall("\n")
        aa = self.ssh.invoke_shell().recv(9999)
        print(f"aa:{aa}")
        return self.ssh.invoke_shell()

    def write(self, cmd):
        self.c.send(cmd)  # 放入要执行的命令

    def channel_exec_cmd(self, cmd, key=b'', endwith=(b'# ', b'#'), timeout=3, allinfo=False):
        cmd = cmd if type(cmd) == bytes else cmd.encode()
        buff = b''
        time.sleep(0.1)
        start_time = time.time()
        self.c.send(cmd)  # 放入要执行的命令
        self.c.send(b'\n')
        print(222222)
        while not reduce(lambda x, y: x or y, list(map(lambda x: buff.endswith(x), endwith))) and not (
                key != b"" and key in buff):
            if not timeout:
                end_time = time.time()
                if end_time - start_time > timeout:
                    break
            resp = self.c.recv(9999)
            buff += resp
            print(f"resp:{resp}")
        resp = self.c.recv(9999)
        print(f"resp:{resp}")
        buff += resp


        result = buff.strip().split(b'\r\n',cmd.count(b"\r\n")+1)[-1].rsplit(b"\r\n", 1)[0] if buff.count(b"\r\n") != 1 else b""
        print([cmd, buff, result])
        if allinfo:
            return buff
        else:
            return result


class SSHManager(object):
    """SSH 连接管理器。

    简化版的 SSH 客户端，用于执行远程命令。

    Attributes:
        host (str): 远程主机地址
        user (str): SSH 用户名
        passwd (str): SSH 密码
        port (int): SSH 端口
        root_pwd (str): root 密码
        ssh: Paramiko SSHClient 对象
    """

    def __init__(self, host, user=None, passwd=None, port=22, root_pwd=None, tunnel_config: dict = None):
        建ssh连接
        :param host:
        :param user:
        :param passwd:
        :param port:
        :param tunnel_config: ssh隧道，格式如：{"host":host, "port":port, "username":username, "password":password}
        """
        self._host = host
        if user is None:
            self._usr = 'root'
        else:
            self._usr = user
        self._passwd = passwd
        self._port = port
        self._root_pwd = root_pwd
        # self.tunnel_config = tunnel_config
        if tunnel_config:
            self.tunnel = ssh_tunnel(remote_host=host, remote_port=port, **tunnel_config)
            self._host = "127.0.0.1"
            self._port = self.tunnel.local_bind_port
        try:
            self._ssh = self._ssh_connect()
        except Exception as e:
            self._ssh = self._ssh_connect()
        self._sftp = self._sftp_connect()
        self._channel = self.channel()

    def __del__(self):
        try:
            if self._ssh:
                self._ssh.close()
            if self._sftp:
                self._sftp.close()
            if self.tunnel:
                self.tunnel.close()
        except Exception as e:
            print(e)
            if str(e) not in (
                    "'NoneType' object has no attribute 'time'", "'SSHManager' object has no attribute 'tunnel'",
                    "'NoneType' object has no attribute 'current_thread'"):
                raise

    def _sftp_connect(self):
        transport = None
        try:
            transport = paramiko.Transport((self._host, self._port))
            transport.connect(username=self._usr, password=self._passwd)
            return paramiko.SFTPClient.from_transport(transport)
        except Exception as e:
            if transport:
                try:
                    transport.close()
                except:
                    pass
            raise RuntimeError("sftp connect failed [%s]" % str(e))

    def _ssh_connect(self):
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            # 连接服务器
            ssh.connect(hostname=self._host,
                        port=self._port,
                        username=self._usr,
                        password=self._passwd,
                        timeout=5)
            return ssh
        except Exception as e:
            print("ssh_dpi connected to [host:%s, port:%s, usr:%s, passwd:%s] failed," % (
                self._host, self._port, self._usr, self._passwd), e)
            time.sleep(3)
            # 重试前先关闭之前的连接
            try:
                ssh.close()
            except:
                pass
            # 重新创建ssh对象并连接服务器
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(hostname=self._host,
                        port=self._port,
                        username=self._usr,
                        password=self._passwd,
                        timeout=5)
            print("ssh_dpi reconnected to [host:%s, usr:%s, passwd:%s] success" %
                  (self._host, self._usr, self._passwd))
            return ssh

    def ssh_exec_cmd(self, cmd, path='~') -> bytes:
        """
        通过ssh连接到远程服务器，执行给定的命令
        :param cmd: 执行的命令
        :param path: 命令执行的目录
        :return: 返回结果
        """
        try:
            result = self._exec_command('cd ' + path + ';' + cmd)
            # print cmd
            # print(result)
            return result
        except Exception:
            raise RuntimeError('exec cmd [%s] failed' % cmd)

    def ssh_exec_file(self, local_file, remote_file, proc="/bin/bash", param="", exec_path="~"):
        """
        执行远程的脚本文件
        :param local_file: 本地文件
        :param remote_file: 远程文件
        :param proc: 执行解释器
        :param param: 执行参数
        :param exec_path: 执行目录
        :return:
        """
        try:
            if not self.is_file_exist(local_file):
                raise RuntimeError('File [%s] not exist' % local_file)
            # if not self.is_shell_file(local_file):
            #     raise RuntimeError('File [%s] is not a shell file' % local_file)

            self.check_remote_file(local_file, remote_file)

            result = self._exec_command(
                'chmod +x ' + remote_file + '; cd' + exec_path + ';' + proc + ' ' + remote_file + ' ' + param)
            # print('exec shell result: ', result)
            return result
        except Exception as e:
            raise RuntimeError('ssh_dpi exec shell failed [%s]' % str(e))

    def is_shell_file(self, file_name):
        return file_name.endswith('.sh')

    def is_file_exist(self, file_name):
        try:
            with open(file_name, 'r'):
                return True
        except Exception as e:
            return False

    def check_remote_file(self, local_file, remote_file):
        """
        检测远程的脚本文件和当前的脚本文件是否一致，如果不一致，则上传本地脚本文件
        :param local_file:
        :param remote_file:
        :return:
        """
        try:
            result = self._exec_command('find' + remote_file)
            if len(result) == 0:
                self._upload_file(local_file, remote_file)
            else:
                lf_size = os.path.getsize(local_file)
                result = self._exec_command('du -b' + remote_file)
                rf_size = int(result.split('\t')[0])
                if lf_size != rf_size:
                    self._upload_file(local_file, remote_file)
        except Exception as e:
            print(e)
            raise RuntimeError("check error [%s]" % str(e))

    def _upload_file(self, local_file, remote_file):
        """
        通过sftp上传本地文件到远程
        :param local_file:
        :param remote_file:
        :return:
        """
        try:
            self._sftp.put(local_file, remote_file)
        except Exception as e:
            raise RuntimeError('upload failed [%s]' % str(e))

    def _download_file(self, remote_file, local_file):
        """
        通过sftp下载远程文件到本地
        :param local_file:
        :param remote_file:
        :return:
        """
        try:
            self._sftp.get(remote_file, local_file)
        except Exception as e:
            raise RuntimeError('upload failed [%s]' % str(e))

    def _exec_command(self, cmd):
        """
        通过ssh执行远程命令
        :param cmd:
        :return:
        """
        try:
            stdin, stdout, stderr = self._ssh.exec_command(cmd)
            stdin.close()
            return stdout.read()
        except Exception as e:
            raise RuntimeError('Exec command [%s] failed' % str(cmd))

    def _exec_command1(self, cmd, step):
        """
        通过ssh执行远程命令
        :param cmd:
        :return:
        """
        try:
            stdin, stdout, stderr = self._ssh.exec_command(cmd)
            time.sleep(2)
            stdin.write(step)
            return stdout.read()
        except Exception as e:
            raise RuntimeError('Exec command [%s] failed' % str(cmd))

    def expr_until(self, expr, value, timeout=60):
        time_tmp = int(self.ssh_exec_cmd('date +%s').strip())
        res = False
        while int(self.ssh_exec_cmd('date +%s').strip()) - time_tmp <= timeout:
            self.ssh_exec_cmd(cmd=expr).strip()
            if self.ssh_exec_cmd(cmd=expr).strip() == value:
                res = True
                break
            time.sleep(1)
        return res

    def channel(self) -> paramiko.channel.Channel:
        if self._root_pwd:
            c = self._ssh.invoke_shell()
            # print(type(c))
            time.sleep(0.1)
            # 先判断提示符，然后下一步在开始发送命令，这样大部分机器就都不会出现问题
            buff = b''
            while not buff.endswith(b'$ '):
                resp = c.recv(9999)
                buff += resp
                time.sleep(0.1)
            # ssh_dpi.send(' export LANG=en_US.UTF-8 \n') #解决错误的关键，编码问题
            # ssh_dpi.send('export LANGUAGE=en \n')

            c.send(b'su - \n')
            buff = b""
            while not (buff.endswith('密码：'.encode()) or buff.endswith(b'Password: ')):  # true
                resp = c.recv(9999)
                buff += resp
            c.send(self._root_pwd)
            c.send(b'\n')
            buff = b""
            while not (buff.endswith(b'# ') or buff.endswith(b'$ ')):
                resp = c.recv(9999)
                buff += resp
            if buff.endswith(b'$ '):
                self._ssh.close()
                raise RuntimeError('超级管理员登录失败！')
            return c
        else:
            return self._ssh.invoke_shell()

    def channel_write(self, cmd):
        self._channel.send(cmd)  # 放入要执行的命令

    def channel_exec_cmd(self, cmd: bytes, key=b'', endwith=(b'# ', b'#'), timeout=3, allinfo=False):
        buff = b''
        time.sleep(0.1)
        start_time = time.time()
        self._channel.send(cmd)  # 放入要执行的命令
        self._channel.send(b'\n')

        while not reduce(lambda x, y: x or y, list(map(lambda x: buff.endswith(x), endwith))) and not (
                key != b"" and key in buff):
            if not timeout:
                end_time = time.time()
                if end_time - start_time > timeout:
                    break
            resp = self._channel.recv(9999)
            buff += resp
            print("aaa",resp)
        print("bbb",buff)
        # result = resp.lstrip(b'\r\n').rsplit(b"\r\n", 1)[0]
        result = buff.split(cmd, 1)[1].lstrip(b'\r\n').rsplit(b"\r\n", 1)[0] if cmd in buff else ""

        if allinfo:
            return buff
        else:
            return result


if __name__ == '__main__':
    ssh_dpi = SSHManager('172.31.140.13', user='root', passwd='embed220', port=22)
    # tunnel = ssh_tunnel(**{"host": '172.31.140.98', "port": 22, "username": 'root', "password": 'yhce123!@#',
    #                        "remote_host": "172.31.140.98", "remote_port": 22})
    # ssh_dpi = SSHManager('127.0.0.1', user='root', passwd='yhce123!@#', port=tunnel.local_bind_port)
    # ssh_dpi = SSHManager('172.31.140.102', user='root', passwd='yhce123!@#', port=22,
    #                      tunnel_config={"host": '172.31.140.98', "port": 22, "username": 'root',"password": 'yhce123!@#'})
    # ssh_dpi = SSHManager('172.31.140.102', user='rzxsystemuser', passwd='Changeme2020_sj#$%#act', root_pwd="yhce123!@#",
    #                      port=22)
    # print(ssh_dpi.ssh_exec_cmd("ip a").decode())
    # print(ssh_dpi.channel_exec_cmd(cmd=b'pwd',allinfo=True))
    # ssh_dpi = VerificationSsh(host='172.31.140.13', username='root', password='embed220', port=22, root_pwd="embed220")

    # ssh_dpi = VerificationSsh(host='172.31.140.105', username='root', password='yhce123!@#', port=22, root_pwd=None, tunnel_configs=[
    #         {"host": '172.31.140.102', "port": 22, "username": 'root', "password": 'yhce123!@#'}
    #     ])
    a = ssh_dpi.channel_exec_cmd(cmd=b"su admin")
    print(a)