; Дополнения к установщику Tauri (tauri.conf.json → bundle.windows.nsis.installerHooks).
;
; До 0.3.0 программа называлась «Mognu» и стояла в %LOCALAPPDATA%\Mognu. С 0.3.0 она «Mognu VPN» и ставится
; в %LOCALAPPDATA%\Mognu VPN. Старую копию тихо удаляем её же деинсталлятором (ярлыки и запись в «Программах»
; уходят вместе с ней). Ключ, вход и настройки лежат отдельно — в %APPDATA%\app.mognu.desktop и
; %LOCALAPPDATA%\app.mognu.desktop — и остаются: удаление идёт как обновление (/UPDATE), без стирания данных.

Var MognuMoved

!macro NSIS_HOOK_PREINSTALL
  StrCpy $MognuMoved 0
  ${If} ${FileExists} "$LOCALAPPDATA\Mognu\uninstall.exe"
  ${AndIf} "$INSTDIR" != "$LOCALAPPDATA\Mognu"
    ExecWait '"$LOCALAPPDATA\Mognu\uninstall.exe" /S /UPDATE _?=$LOCALAPPDATA\Mognu'
    RMDir /r "$LOCALAPPDATA\Mognu"
    StrCpy $MognuMoved 1
  ${EndIf}
!macroend

!macro NSIS_HOOK_POSTINSTALL
  ; Обновление из 0.2.x: её командный файл после установки запускает программу по старому пути, которого уже нет,
  ; поэтому новую копию открываем сами.
  ${If} $MognuMoved = 1
  ${AndIf} ${Silent}
    nsis_tauri_utils::RunAsUser "$INSTDIR\${MAINBINARYNAME}.exe" ""
  ${EndIf}
!macroend
