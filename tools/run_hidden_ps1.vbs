Option Explicit

Dim shell, args, scriptPath, i, extraArgs, command

Set args = WScript.Arguments
If args.Count < 1 Then
    WScript.Quit 2
End If

scriptPath = args.Item(0)
extraArgs = ""
For i = 1 To args.Count - 1
    extraArgs = extraArgs & " " & Quote(args.Item(i))
Next

command = "powershell.exe -WindowStyle Hidden -NoProfile -NonInteractive -ExecutionPolicy Bypass -File " & Quote(scriptPath) & extraArgs

Set shell = CreateObject("WScript.Shell")
shell.Run command, 0, False

Function Quote(value)
    Quote = Chr(34) & Replace(CStr(value), Chr(34), Chr(34) & Chr(34)) & Chr(34)
End Function
