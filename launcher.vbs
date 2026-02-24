Set WshShell = CreateObject("WScript.Shell")
' 以隐藏窗口(0)模式运行 BAT 脚本，做到彻底干掉黑框
WshShell.Run chr(34) & "D:\WorFlow\AntiGravity\launch.bat" & Chr(34), 0
Set WshShell = Nothing
