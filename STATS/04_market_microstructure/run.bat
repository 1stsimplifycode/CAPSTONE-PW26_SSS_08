@echo off
REM GENERATED FROM research_modules.yaml - edit the manifest, not this file
REM STATS-04  Market and microstructure-proxy statistics
REM Canonical implementation: research/market/features.py::MARKET_FEATURES, research/market/features.py::MICROSTRUCTURE_PROXIES, research/market/features.py::MICROSTRUCTURE_NOT_MEASURED, research/market/features.py::coverage_report
REM
REM This file is an EXECUTION INTERFACE. It contains no research logic: it
REM forwards to the shared runner, which calls the adapter named in the
REM manifest, which calls the canonical implementation above.
setlocal
for %%I in ("%~dp0..\..") do set "AEGIS_ROOT=%%~fI"
call "%AEGIS_ROOT%\tools\aegis_module.bat" STATS-04 %*
exit /b %ERRORLEVEL%
