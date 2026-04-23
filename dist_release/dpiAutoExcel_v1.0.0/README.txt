dpiAutoExcel 自动化测试工具 v1.0.0
=========================================

【快速开始】

1. 复制"用例_升级_模板.xlsx"，重命名为实际用例文件
   例如：信安_升级_v1.0.7.0.xlsx

2. 打开 Excel 文件，修改"配置"sheet 中的 RDM 和 FTP 凭证

3. 双击运行以下脚本之一：
   - bat_init.ps1   ：通过 PowerShell 执行，自动生成各 sheet 对应的执行脚本
   - main_exe.exe -f 信安_升级_v1.0.7.0.xlsx -s install

4. 执行结果和日志会写入 exe 同级目录下的 report/ 和 log/ 目录


【命令行参数】

  -f <文件>    指定 Excel 用例文件路径（必需）
  -s <sheet>   指定要执行的 sheet 名称（默认：install）
  -ps1         初始化 PowerShell 执行脚本（生成 exec_ps1/ 目录）
  -bat         初始化 bat 执行脚本（生成 exec_bat/ 目录）


【前置要求】

  - Windows 10 及以上
  - Chrome 或 Edge 浏览器（用于访问 RDM 平台）
  - RDM 平台账号权限


【常见问题】

  Q: 杀毒软件报警？
  A: 请将 main_exe.exe 添加到信任列表，这是正常的打包程序行为。

  Q: 首次运行报错"未找到浏览器"？
  A: 这表示系统没有安装 Chrome 或 Edge，请安装其中任意一款浏览器。

  Q: versions.json 是什么？
  A: RDM 版本缓存文件，由程序自动管理，删除后会自动重新获取。

  Q: 执行失败如何排查？
  A: 查看 exe 同级目录下的 log/common.log 日志文件。
