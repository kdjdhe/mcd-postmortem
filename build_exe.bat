@echo off
REM 构建 mcd-postmortem.exe（PyInstaller onefile）
REM 前置：安装 uv（https://docs.astral.sh/uv/），在仓库根目录执行本脚本
setlocal
cd /d "%~dp0"

if not exist .build-venv (
    uv venv .build-venv --python 3.12 || exit /b 1
    uv pip install --python .build-venv\Scripts\python.exe pyinstaller "Pillow>=10.4,<13" || exit /b 1
)

.build-venv\Scripts\python.exe -m PyInstaller --onefile --clean --noconfirm ^
    --collect-submodules mcd_postmortem ^
    --name mcd-postmortem ^
    --distpath dist-exe --workpath build\pyinstaller --specpath build ^
    exe_entry.py || exit /b 1

echo.
echo 构建完成: dist-exe\mcd-postmortem.exe
echo 自检: dist-exe\mcd-postmortem.exe demo --json
endlocal
