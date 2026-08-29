@echo off
REM GENERATED FROM research_modules.yaml - edit the manifest, not this file
REM STATS-05  Regime statistics
REM Canonical implementation: research/regime/detection.py::index_descriptors, research/regime/detection.py::select_order, research/regime/detection.py::bootstrap_stability
REM
REM This file is an EXECUTION INTERFACE. It contains no research logic: it
REM forwards to the shared runner, which calls the adapter named in the
REM manifest, which calls the canonical implementation above.
setlocal
for %%I in ("%~dp0..\..") do set "AEGIS_ROOT=%%~fI"
call "%AEGIS_ROOT%\tools\aegis_module.bat" STATS-05 %*
exit /b %ERRORLEVEL%
