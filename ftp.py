#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2024/3/11 15:27
# @Author  : weihang
# @File    : ftp.py
import io
from ftplib import FTP_TLS, FTP
from common import setup_logging

logger = setup_logging(log_file_path="log/ftp.log", logger_name="ftp")
class FTPclient:
    def __init__(self, host, user, passwd, encode="utf-8"):
        self.host = host
        self.user = user
        self.passwd = passwd
        self.encode = encode
        self.connect()

    # def __del__(self):
    #     self.ftp.quit()

    def connect(self):
        """
        连接 FTP 服务器
        """
        logger.info(f"Connecting to FTP server: {self.host}, user: {self.user}, encode: {self.encode}")
        try:
            # 连接FTP服务器
            self.ftp = FTP_TLS(host=self.host)
            self.ftp.encoding = self.encode
            self.ftp.login(self.user, self.passwd)
            self.ftp.prot_p()
        except Exception as e:
            logger.warning(f"FTP_TLS failed, trying FTP instead: {e}")
            try:
                self.ftp = FTP(host=self.host)
                self.ftp.encoding = self.encode
                self.ftp.login(self.user, self.passwd)
                logger.info("Connected to FTP server using plain FTP")
            except Exception as e:
                logger.error(f"Failed to connect to FTP server: {e}")
                self.ftp = None  # 连接失败，确保 self.ftp 为空
                raise

    def close(self):
        """
        关闭 FTP 连接，防止资源泄漏
        """
        if self.ftp:
            try:
                self.ftp.quit()
                logger.info("FTP connection closed.")
            except Exception as e:
                logger.warning(f"Error while closing FTP connection: {e}")
            finally:
                self.ftp = None  # 清除对象，避免重复使用

    def __del__(self):
        """
        析构函数，确保对象销毁时断开连接
        """
        self.close()

    def downloadfo(self, remotefile: str):
        dir, name = remotefile.rsplit("/", 1)
        self.ftp.cwd(dir)
        lf = io.BytesIO()
        self.ftp.retrbinary('RETR {}'.format(name), lf.write)
        lf.seek(0)
        return lf

    def download(self, remotefile: str, localfile: str):
        lf = self.downloadfo(remotefile=remotefile)
        with open(localfile, "wb") as f:
            f.write(lf.read())
        lf.close()

    def uploadfo(self, lf: io.BytesIO, remotefile: str):
        dir, name = remotefile.rsplit("/", 1)
        self.ftp.cwd(dir)
        lf.seek(0)
        self.ftp.storbinary('STOR {}'.format(name), lf)

    def upload(self, localfile: str, remotefile: str):
        with open(localfile, "rb") as lf:
            self.uploadfo(lf=io.BytesIO(lf.read()), remotefile=remotefile)

    def list_dir(self, remotedir: str):
        """
        列出 FTP 服务器上指定目录下的文件和子目录
        :param remotedir: 远程目录路径
        :return: 包含文件和子目录的列表
        """
        try:
            logger.info(f"Listing directory: {remotedir}")
            self.ftp.cwd(remotedir)  # 切换到指定目录
            items = self.ftp.nlst()  # 获取目录下的文件和子目录列表
            return items
        except Exception as e:
            logger.info(f"Error listing directory {remotedir}: {e}")
            return []

    def file_exists(self, remotefile: str) -> bool:
        """
        更准确地判断远程路径是否是文件，而不是目录
        :param remotefile: 完整远程文件路径
        :return: True 表示确实是一个文件，False 表示不存在或是个目录
        """
        try:
            size = self.ftp.size(remotefile)
            return size is not None  # 能获取到文件大小即是文件
        except Exception as e:
            logger.debug(f"Not a file or does not exist: {remotefile}, error: {e}")
            return False

    def dir_exists(self, remotedir: str) -> bool:
        """
        判断 FTP 上指定目录是否存在
        :param remotedir: 远程目录路径，如 /path/to/dir
        :return: True 表示目录存在，False 表示不存在
        """
        current = self.ftp.pwd()  # 保存当前工作目录
        try:
            self.ftp.cwd(remotedir)
            self.ftp.cwd(current)  # 切回来
            return True
        except Exception as e:
            logger.warning(f"Directory does not exist or inaccessible '{remotedir}': {e}")
            return False


if __name__ == '__main__':
    # path_var = "ftp://172.31.128.180/02测试/PD2172212_信息安全执行单元V1.0.0.0（信安EU）/V1.0.1.5/DPI/ubuntu/ACT-DPI-ISE-1.0.1.5-1_20240118111733.tar.gz"
    # host, path_tmp = path_var.lstrip("ftp://").split("/", 1)
    host = "172.31.128.180"
    remotedir = "/02测试/PD240160350_信息安全执行单元V1.0.5.0（信安EU）/V1.0.4.7"
    # remotefile = "/" + path_tmp
    print(host)
    print(remotedir)
    ftp = FTPclient(host=host, user="weihang", passwd="12345678")
    logger.info(ftp.list_dir(remotedir=remotedir))
    # ftp.download(remotefile=remotefile, localfile=r"D:\weihang\Desktop\test.tar.gz")

