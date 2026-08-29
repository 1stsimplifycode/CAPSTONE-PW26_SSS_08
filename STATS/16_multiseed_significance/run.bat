@echo off
REM GENERATED FROM research_modules.yaml - edit the manifest, not this file
REM STATS-16  Multi-seed and statistical significance
REM Canonical implementation: research/evaluation/multiseed.py, scripts/run_multiseed.py, research/statistics/tests.py, research/statistics/power.py
REM
REM This file is an EXECUTION INTERFACE. It contains no research logic: it
REM forwards to the shared runner, which calls the adapter named in the
REM manifest, which calls the canonical implementation above.
setlocal
for %%I in ("%~dp0..\..") do set "AEGIS_ROOT=%%~fI"
call "%AEGIS_ROOT%\tools\aegis_module.bat" STATS-16 %*
exit /b %ERRORLEVEL%
