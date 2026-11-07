@echo off
rem Compile Sable Creek with SDHLT (https://github.com/seedee/SDHLT) or VHLT.
rem Set TOOLS to the folder that holds the compile tools, then run this file.
set TOOLS=C:\sdhlt\tools
cd /d "%~dp0out"
"%TOOLS%\sdHLCSG.exe" -wadinclude sablecreek sablecreek || goto :fail
"%TOOLS%\sdHLBSP.exe" sablecreek || goto :fail
"%TOOLS%\sdHLVIS.exe" -full sablecreek || goto :fail
"%TOOLS%\sdHLRAD.exe" -extra -lights lights.rad sablecreek || goto :fail
echo.
echo Done: out\sablecreek.bsp
goto :eof
:fail
echo Compile failed, see the .log file in out\
