@echo off
REM GENERATED FROM research_modules.yaml - edit the manifest, not this file
REM STATS-07  Tail and extreme-risk statistics
REM Canonical implementation: research/risk/gate.py::tail_metrics, research/risk/gate.py::capital_consequence
REM
REM This file is an EXECUTION INTERFACE. It contains no research logic: it
REM forwards to the shared runner, which calls the adapter named in the
REM manifest, which calls the canonical implementation above.
setlocal
for %%I in ("%~dp0..\..") do set "AEGIS_ROOT=%%~fI"
call "%AEGIS_ROOT%\tools\aegis_module.bat" STATS-07 %*
exit /b %ERRORLEVEL%
