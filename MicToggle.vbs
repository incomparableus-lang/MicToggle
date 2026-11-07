' MicToggle — запуск без окна консоли.
' Двойной клик по этому файлу (или ярлык MicToggle.lnk) кладёт значок в трей.

Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")

folder = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = folder

pythonw = folder & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(pythonw) Then
    MsgBox "Не найден " & pythonw & vbCrLf & _
           "Создайте окружение: py -3.12 -m venv .venv && .venv\Scripts\pip install -r requirements.txt", _
           vbExclamation, "MicToggle"
    WScript.Quit 1
End If

sh.Run """" & pythonw & """ ""mic_toggle.pyw""", 0, False