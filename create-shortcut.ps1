$batPath      = "C:\Git\JRDB_data\start.bat"
$shortcutPath = [System.IO.Path]::Combine([System.Environment]::GetFolderPath('Desktop'), 'JRDB start.lnk')

$shell    = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath       = "cmd.exe"
$shortcut.Arguments        = "/k `"$batPath`""
$shortcut.WorkingDirectory = "C:\Git\JRDB_data"
$shortcut.Description      = 'JRDB Portal'
$shortcut.WindowStyle      = 1
$shortcut.Save()

Write-Host "Shortcut created: $shortcutPath"
