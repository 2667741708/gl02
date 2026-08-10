Option Explicit

Dim shell, fileSystem, args, scriptPath, pwshPath, i, extraArgs, command

Set args = WScript.Arguments
If args.Count < 1 Then
    WScript.Quit 2
End If

scriptPath = args.Item(0)
pwshPath = "C:\Program Files\PowerShell\7\pwsh.exe"
Set fileSystem = CreateObject("Scripting.FileSystemObject")
If Not fileSystem.FileExists(pwshPath) Then
    WScript.Quit 3
End If
extraArgs = ""
For i = 1 To args.Count - 1
    extraArgs = extraArgs & " " & Quote(args.Item(i))
Next

command = Quote(pwshPath) & " -WindowStyle Hidden -NoLogo -NoProfile -NonInteractive -File " & Quote(scriptPath) & extraArgs

Set shell = CreateObject("WScript.Shell")
shell.Run command, 0, False

Function Quote(value)
    Quote = Chr(34) & Replace(CStr(value), Chr(34), Chr(34) & Chr(34)) & Chr(34)
End Function
