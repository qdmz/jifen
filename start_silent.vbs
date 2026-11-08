' Launch Jifen Mall in background (no console window).
' ASCII only: wscript parses this file as ANSI, do NOT put non-ASCII text here.
Set fso = CreateObject("Scripting.FileSystemObject")
d = fso.GetParentFolderName(WScript.ScriptFullName)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = d
sh.Run "pythonw """ & d & "\app.py""", 0, False
