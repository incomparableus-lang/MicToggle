; MicToggle.nsi - установщик MicToggle (NSIS 3, Unicode)
;
; Собирается build.ps1:
;   makensis /DVERSION=1.0.0 /DAPPROOT=<папка проекта> installer\MicToggle.nsi
;
; Ставится в профиль пользователя (%LOCALAPPDATA%\Programs\MicToggle), без UAC.

Unicode true

!include "MUI2.nsh"
!include "FileFunc.nsh"

!define APPNAME "MicToggle"
!define PUBLISHER "MicToggle"
!define APPEXE "MicToggle.exe"
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\MicToggle"
!define RUN_KEY "Software\Microsoft\Windows\CurrentVersion\Run"

!ifndef VERSION
  !define VERSION "1.0.0"
!endif
!ifndef APPROOT
  !define APPROOT ".."
!endif

Name "${APPNAME} ${VERSION}"
OutFile "${APPROOT}\dist\MicToggle-Setup-${VERSION}.exe"
InstallDir "$LOCALAPPDATA\Programs\MicToggle"
InstallDirRegKey HKCU "Software\MicToggle" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 64
BrandingText "${APPNAME} ${VERSION}"
ShowInstDetails show
ShowUninstDetails show

VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "${APPNAME}"
VIAddVersionKey "FileDescription" "Установщик ${APPNAME}"
VIAddVersionKey "FileVersion" "${VERSION}.0"
VIAddVersionKey "ProductVersion" "${VERSION}"
VIAddVersionKey "LegalCopyright" "MIT License, 2026"
VIAddVersionKey "CompanyName" "${PUBLISHER}"

!define MUI_ICON "${APPROOT}\MicToggle.ico"
!define MUI_UNICON "${APPROOT}\MicToggle.ico"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APPEXE}"
!define MUI_FINISHPAGE_RUN_TEXT "Запустить ${APPNAME} сейчас"
!define MUI_FINISHPAGE_LINK "Что умеет ${APPNAME}"
!define MUI_FINISHPAGE_LINK_LOCATION "https://github.com/incomparableus-lang/MicToggle"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "Russian"

; ------------------------------------------------------------------ установка

Section "Программа" SecMain
  SectionIn RO

  ; обновление поверх запущенной копии
  nsExec::Exec 'taskkill /IM "${APPEXE}" /F'

  SetOutPath "$INSTDIR"
  File /r "${APPROOT}\dist\MicToggle\*.*"
  File "${APPROOT}\MicToggle.ico"
  File "${APPROOT}\VERSION"
  File "${APPROOT}\README.md"
  File "${APPROOT}\LICENSE"

  WriteRegStr HKCU "Software\MicToggle" "InstallDir" "$INSTDIR"

  CreateShortcut "$SMPROGRAMS\${APPNAME}.lnk" "$INSTDIR\${APPEXE}" "" "$INSTDIR\MicToggle.ico" 0

  WriteUninstaller "$INSTDIR\Uninstall.exe"

  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0

  WriteRegStr HKCU "${UNINST_KEY}" "DisplayName" "${APPNAME}"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINST_KEY}" "Publisher" "${PUBLISHER}"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\MicToggle.ico"
  WriteRegStr HKCU "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINST_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "${UNINST_KEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoRepair" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "EstimatedSize" $0
SectionEnd

Section /o "Значок на рабочем столе" SecDesktop
  CreateShortcut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\${APPEXE}" "" "$INSTDIR\MicToggle.ico" 0
SectionEnd

Section "Запускать при входе в Windows" SecAutostart
  WriteRegStr HKCU "${RUN_KEY}" "MicToggle" '"$INSTDIR\${APPEXE}"'
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecMain} "MicToggle и его файлы."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} "Ярлык на рабочем столе."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecAutostart} "Микрофон под контролем сразу после входа в Windows."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; ------------------------------------------------------------------ удаление

Function un.onInit
  SetShellVarContext current
FunctionEnd

Section "Uninstall"
  nsExec::Exec 'taskkill /IM "${APPEXE}" /F'

  Delete "$SMPROGRAMS\${APPNAME}.lnk"
  Delete "$DESKTOP\${APPNAME}.lnk"

  ; автозапуск снимаем только если он ведёт на нашу копию
  ReadRegStr $0 HKCU "${RUN_KEY}" "MicToggle"
  ${If} $0 == '"$INSTDIR\${APPEXE}"'
    DeleteRegValue HKCU "${RUN_KEY}" "MicToggle"
  ${EndIf}

  DeleteRegKey HKCU "Software\MicToggle"
  DeleteRegKey HKCU "${UNINST_KEY}"

  RMDir /r "$INSTDIR"
SectionEnd