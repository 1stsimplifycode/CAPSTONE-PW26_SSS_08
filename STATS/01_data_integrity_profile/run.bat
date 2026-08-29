@echo off
REM GENERATED FROM research_modules.yaml - edit the manifest, not this file
REM STATS-01  Data and integrity profile
REM Canonical implementation: research/market/features.py::coverage_report, research/data/dataset.py::FEATURE_BLOCKS
REM
REM This file is an EXECUTION INTERFACE. It contains no research logic: it
REM forwards to the shared runner, which calls the adapter named in the
REM manifest, which calls the canonical implementation above.
setlocal
for %%I in ("%~dp0..\..") do set "AEGIS_ROOT=%%~fI"
call "%AEGIS_ROOT%\tools\aegis_module.bat" STATS-01 %*
exit /b %ERRORLEVEL%
