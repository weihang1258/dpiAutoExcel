#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2024/4/17
# @Author  : weihang
# @File    : dpi_helper.py
# @Desc    : DPI设备初始化和配置工具函数


def dpi_init(dpi, xsa_json=None, mod_cfg=None, xdr_template_pattern=None):
    """
    初始化 DPI 设备配置

    :param dpi: Dpi对象
    :param xsa_json: xsa.json配置修改字典，格式如 {"devinfo.province_id": 117, "httpxdr.compool_blk_posi": 2}
                     键使用点号分隔表示嵌套路径
    :param mod_cfg: 模式配置字典
    :param xdr_template_pattern: XDR模板模式字典
    :return: True
    """
    modify_flag = False

    # 修改cfg文件
    if mod_cfg:
        modfile = dpi.get_modfile_from_modcfg()
        modcfg2dict = dpi.modcfg2dict("/opt/dpi/" + modfile, effective=False)
        for k, v in mod_cfg.copy().items():
            current_val = modcfg2dict.get(k)
            if current_val is None:
                from utils.common import logger
                logger.info(f"{modfile} | {k} | {v} | add")
                modify_flag = True
            elif str(current_val) == str(v):
                mod_cfg.pop(k)
                logger.info(f"{modfile} | {k} | {current_val} == {v} | ok")
            else:
                from utils.common import logger
                logger.info(f"{modfile} | {k} | {current_val} --> {v} | modify")
                modify_flag = True
        if mod_cfg:
            dpi.modify_modcfg("/opt/dpi/" + modfile, **mod_cfg)

    # 修改xsa.json
    if xsa_json:
        from utils.common import logger
        xsa_dict = dpi.json_get(path="/opt/dpi/xsaconf/xsa.json")
        changes_to_apply = dict()  # 记录需要修改的项

        for k, v in xsa_json.copy().items():
            path_parts = k.split(".")
            val_tmp = xsa_dict
            for i in path_parts[:-1]:
                if i.isdigit():
                    i = int(i)
                val_tmp = val_tmp[i]
            # 获取当前值进行比较
            last_key = path_parts[-1]
            if last_key.isdigit():
                last_key = int(last_key)
            current_val = val_tmp.get(last_key)

            if current_val == v:
                # 值相同，不需要修改，从列表中移除
                xsa_json.pop(k)
                logger.info(f"xsa.json | {k} | {current_val} == {v} | ok")
            else:
                # 值不同，记录修改
                logger.info(f"xsa.json | {k} | {current_val} --> {v} | modify")
                modify_flag = True
                changes_to_apply[k] = v

        # 如果有需要修改的配置项，调用 modify_xsajson
        if modify_flag and changes_to_apply:
            dpi.modify_xsajson(path="/opt/dpi/xsaconf/xsa.json", **changes_to_apply)

    # 修改xdr_template.json中的配置
    if xdr_template_pattern:
        from utils.common import logger
        xdr_template_dict = dpi.json_get(path="/opt/dpi/xdrconf/rule/xdr_template.json")
        for k, v in xdr_template_pattern.items():
            if "." in k:
                templete, xieyiname, key = k.split(".")
                for i in range(len(xdr_template_dict["pattern"])):
                    if xdr_template_dict["pattern"][i]["templete"] == templete and xdr_template_dict["pattern"][i]["xieyiname"] == xieyiname:
                        if xdr_template_dict["pattern"][i][key] != v:
                            logger.info(f"xdr_template.json | {templete}.{xieyiname},{i}.{key} | {xdr_template_dict['pattern'][i][key]} --> {v} | modify")
                        xdr_template_dict["pattern"][i][key] = v
        dpi.json_put(xdr_template_dict, "/opt/dpi/xdrconf/rule/xdr_template.json")

    return True


if __name__ == '__main__':
    # 测试代码
    print("DPI初始化工具模块")