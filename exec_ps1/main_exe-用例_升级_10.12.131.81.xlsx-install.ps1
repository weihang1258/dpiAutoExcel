# 获取当前 PowerShell 脚本的完整路径和文件名
$FullFilePath = $MyInvocation.MyCommand.Path
$FullFileName = [System.IO.Path]::GetFileName($FullFilePath)

# 切换到当前脚本所在目录的上一级目录
$ScriptDir = Split-Path -Parent $FullFilePath
$TargetDir = Split-Path -Parent $ScriptDir
Set-Location -Path $TargetDir

# 显示当前执行目录
Write-Host "Current Directory: $($PWD.Path)"

# 提取文件名中的 FILENAME 和 SHEETNAME
$Parts = $FullFileName -split "-"
if ($Parts.Count -ge 3) {
    $FileName = $Parts[1]
    $SheetName = $Parts[2] -replace "\.ps1$", ""  # 去掉 .ps1 后缀
} else {
    Write-Host "ERROR: Filename or Sheetname not extracted properly." -ForegroundColor Red
    Pause
    Exit
}

# 显示提取的文件名和工作表名
Write-Host "Extracted Filename: $FileName"
Write-Host "Extracted Sheetname: $SheetName"

# 设置 PowerShell 窗口标题
$Host.UI.RawUI.WindowTitle = "$FileName-$SheetName"

# 检查是否提取成功
if ([string]::IsNullOrEmpty($FileName) -or [string]::IsNullOrEmpty($SheetName)) {
    Write-Host "ERROR: Filename or Sheetname extraction failed." -ForegroundColor Red
    Pause
    Exit
}

# 执行目标命令
$Command = "./main_exe -f `"$FileName`" -s `"$SheetName`""
Write-Host "Executing: $Command"
Invoke-Expression $Command

Pause
