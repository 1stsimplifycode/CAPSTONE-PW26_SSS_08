@echo off
REM GENERATED FROM research_modules.yaml - edit the manifest, not this file
REM STATS-10  Validation and verification metrics
REM Canonical implementation: research/evaluation/metrics.py::classification_metrics, research/evaluation/metrics.py::confusion_counts, research/evaluation/metrics.py::confusion_matrix_frame, research/evaluation/metrics.py::per_class_report, research/evaluation/metrics.py::verification_report
REM
REM This file is an EXECUTION INTERFACE. It contains no research logic: it
REM forwards to the shared runner, which calls the adapter named in the
REM manifest, which calls the canonical implementation above.
setlocal
for %%I in ("%~dp0..\..") do set "AEGIS_ROOT=%%~fI"
call "%AEGIS_ROOT%\tools\aegis_module.bat" STATS-10 %*
exit /b %ERRORLEVEL%
