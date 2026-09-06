Set WshShell = CreateObject("WScript.Shell")
Set WshExec = WshShell.Exec("cmd /c netstat -aon | findstr "":3000 "" | findstr LISTENING")
Do While WshExec.Status = 0
    WScript.Sleep 50
Loop
listening = Trim(WshExec.StdOut.ReadAll())

If Len(listening) = 0 Then
    WshShell.CurrentDirectory = "C:\Git\JRDB_data"
    WshShell.Run "cmd /c cd /d C:\Git\JRDB_data && set PATH=C:\Program Files\nodejs;C:\Program Files\MySQL\MySQL Server 8.0\bin;%PATH% && npx ts-node src\server.ts > .server-startup.log 2>&1", 0, False
End If
