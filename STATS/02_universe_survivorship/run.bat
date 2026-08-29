@echo off
REM GENERATED FROM research_modules.yaml - edit the manifest, not this file
REM STATS-02  Universe and survivorship statistics
REM Canonical implementation: research/data/universe.py::LiquidityProxyUniverse.churn, research/data/universe.py::LiquidityProxyUniverse.turnover_stats
REM
REM This file is an EXECUTION INTERFACE. It contains no research logic: it
REM forwards to the shared runner, which calls the adapter named in the
REM manifest, which calls the canonical implementation above.
setlocal
for %%I in ("%~dp0..\..") do set "AEGIS_ROOT=%%~fI"
call "%AEGIS_ROOT%\tools\aegis_module.bat" STATS-02 %*
exit /b %ERRORLEVEL%
