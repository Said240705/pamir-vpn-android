; Дополнения к установщику Tauri (tauri.conf.json → bundle.windows.nsis.installerHooks).
;
; До 0.3.0 программа называлась «Mognu» и стояла в %LOCALAPPDATA%\Mognu. С 0.3.0 она «Mognu VPN» и ставится
; в %LOCALAPPDATA%\Mognu VPN. Старую копию тихо удаляем её же деинсталлятором (ярлыки и запись в «Программах»
; уходят вместе с ней). Ключ, вход и настройки лежат отдельно — в %APPDATA%\app.mognu.desktop и
; %LOCALAPPDATA%\app.mognu.desktop — и остаются: удаление идёт как обновление (/UPDATE), без стирания данных.

; Папка с картинками Mognu (installer/): шаблон installer.nsi берёт отсюда окна «Готово!» и удаления
!define MOGNU_ART "${__FILEDIR__}"

Var MognuMoved
; /MOGNURUN — так установщик запускает автообновление программы (src/update.rs): после установки открыть Mognu снова
Var MognuRun

!macro NSIS_HOOK_PREINSTALL
  StrCpy $MognuMoved 0
  StrCpy $MognuRun 0
  ClearErrors
  ${GetOptions} $CMDLINE "/MOGNURUN" $R9
  ${IfNot} ${Errors}
    StrCpy $MognuRun 1
    ; программа уже выходит сама: дадим ей закрыться и отпустить файлы
    Sleep 1500
  ${EndIf}
  ${If} ${FileExists} "$LOCALAPPDATA\Mognu\uninstall.exe"
  ${AndIf} "$INSTDIR" != "$LOCALAPPDATA\Mognu"
    ExecWait '"$LOCALAPPDATA\Mognu\uninstall.exe" /S /UPDATE _?=$LOCALAPPDATA\Mognu'
    RMDir /r "$LOCALAPPDATA\Mognu"
    StrCpy $MognuMoved 1
  ${EndIf}
!macroend

!macro NSIS_HOOK_POSTINSTALL
  ; Автообновление (/MOGNURUN) — открываем обновлённую программу. Обновление из 0.2.x: её командный файл после
  ; установки запускает программу по старому пути, которого уже нет, поэтому новую копию тоже открываем сами.
  ${If} $MognuRun = 1
    nsis_tauri_utils::RunAsUser "$INSTDIR\${MAINBINARYNAME}.exe" ""
  ${ElseIf} $MognuMoved = 1
  ${AndIf} ${Silent}
    nsis_tauri_utils::RunAsUser "$INSTDIR\${MAINBINARYNAME}.exe" ""
  ${EndIf}
!macroend
