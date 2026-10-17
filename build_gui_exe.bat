@echo off
REM 构建 mcd-postmortem-gui.exe（PyInstaller onefile，无控制台）
REM 前置：安装 uv（https://docs.astral.sh/uv/），在仓库根目录执行本脚本
setlocal
cd /d "%~dp0"

if not exist .build-venv (
    uv venv .build-venv --python 3.12 || exit /b 1
)
uv pip install --python .build-venv\Scripts\python.exe pyinstaller "Pillow>=10.4,<13" "customtkinter>=5.2" || exit /b 1

REM --collect-submodules：规则引擎用 pkgutil 动态发现，漏了会静默少报事件。
REM --collect-data：带上下载的 icon.ico；--collect-all：customtkinter 主题资源。
.build-venv\Scripts\python.exe -m PyInstaller --onefile --windowed --clean --noconfirm ^
    --collect-submodules mcd_postmortem ^
    --collect-data mcd_postmortem ^
    --collect-all customtkinter ^
    --icon "%~dp0mcd_postmortem\gui\icon.ico" ^
    --name mcd-postmortem-gui ^
    --distpath dist-exe --workpath build\pyinstaller-gui --specpath build ^
    gui_entry.py || exit /b 1

echo.
echo 构建完成: dist-exe\mcd-postmortem-gui.exe
endlocal
