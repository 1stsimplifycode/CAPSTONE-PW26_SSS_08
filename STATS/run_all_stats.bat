@echo off
REM GENERATED FROM research_modules.yaml - edit the manifest, not this file
REM Master runner for the 16 STATS modules, in dependency-safe order.
setlocal EnableDelayedExpansion
for %%I in ("%~dp0..") do set "AEGIS_ROOT=%%~fI"

set /a PASS=0
set /a FAIL=0
set /a SKIP=0
set /a BLOCK=0
set /a PENDING=0
set "FAILED_LIST="

echo ============================================================
echo  STATISTICS PIPELINE  (16 modules)
echo ============================================================

echo.
echo [01/16] STATS-01  Data and integrity profile
call "%AEGIS_ROOT%\STATS\01_data_integrity_profile\run.bat" %*
set "RC=!ERRORLEVEL!"
if "!RC!"=="0" ( set /a PASS+=1 ) else if "!RC!"=="5" ( set /a SKIP+=1 ) else if "!RC!"=="6" ( set /a PENDING+=1 ) else if "!RC!"=="3" ( set /a BLOCK+=1 ) else ( set /a FAIL+=1 & set "FAILED_LIST=!FAILED_LIST! STATS-01" )

echo.
echo [02/16] STATS-02  Universe and survivorship statistics
call "%AEGIS_ROOT%\STATS\02_universe_survivorship\run.bat" %*
set "RC=!ERRORLEVEL!"
if "!RC!"=="0" ( set /a PASS+=1 ) else if "!RC!"=="5" ( set /a SKIP+=1 ) else if "!RC!"=="6" ( set /a PENDING+=1 ) else if "!RC!"=="3" ( set /a BLOCK+=1 ) else ( set /a FAIL+=1 & set "FAILED_LIST=!FAILED_LIST! STATS-02" )

echo.
echo [03/16] STATS-03  Descriptive and distributional statistics
call "%AEGIS_ROOT%\STATS\03_descriptive_distributions\run.bat" %*
set "RC=!ERRORLEVEL!"
if "!RC!"=="0" ( set /a PASS+=1 ) else if "!RC!"=="5" ( set /a SKIP+=1 ) else if "!RC!"=="6" ( set /a PENDING+=1 ) else if "!RC!"=="3" ( set /a BLOCK+=1 ) else ( set /a FAIL+=1 & set "FAILED_LIST=!FAILED_LIST! STATS-03" )

echo.
echo [04/16] STATS-04  Market and microstructure-proxy statistics
call "%AEGIS_ROOT%\STATS\04_market_microstructure\run.bat" %*
set "RC=!ERRORLEVEL!"
if "!RC!"=="0" ( set /a PASS+=1 ) else if "!RC!"=="5" ( set /a SKIP+=1 ) else if "!RC!"=="6" ( set /a PENDING+=1 ) else if "!RC!"=="3" ( set /a BLOCK+=1 ) else ( set /a FAIL+=1 & set "FAILED_LIST=!FAILED_LIST! STATS-04" )

echo.
echo [05/16] STATS-05  Regime statistics
call "%AEGIS_ROOT%\STATS\05_regime_statistics\run.bat" %*
set "RC=!ERRORLEVEL!"
if "!RC!"=="0" ( set /a PASS+=1 ) else if "!RC!"=="5" ( set /a SKIP+=1 ) else if "!RC!"=="6" ( set /a PENDING+=1 ) else if "!RC!"=="3" ( set /a BLOCK+=1 ) else ( set /a FAIL+=1 & set "FAILED_LIST=!FAILED_LIST! STATS-05" )

echo.
echo [06/16] STATS-06  Dependence and propagation statistics
call "%AEGIS_ROOT%\STATS\06_dependence_propagation\run.bat" %*
set "RC=!ERRORLEVEL!"
if "!RC!"=="0" ( set /a PASS+=1 ) else if "!RC!"=="5" ( set /a SKIP+=1 ) else if "!RC!"=="6" ( set /a PENDING+=1 ) else if "!RC!"=="3" ( set /a BLOCK+=1 ) else ( set /a FAIL+=1 & set "FAILED_LIST=!FAILED_LIST! STATS-06" )

echo.
echo [07/16] STATS-07  Tail and extreme-risk statistics
call "%AEGIS_ROOT%\STATS\07_tail_extreme_risk\run.bat" %*
set "RC=!ERRORLEVEL!"
if "!RC!"=="0" ( set /a PASS+=1 ) else if "!RC!"=="5" ( set /a SKIP+=1 ) else if "!RC!"=="6" ( set /a PENDING+=1 ) else if "!RC!"=="3" ( set /a BLOCK+=1 ) else ( set /a FAIL+=1 & set "FAILED_LIST=!FAILED_LIST! STATS-07" )

echo.
echo [08/16] STATS-08  Episode and event statistics
call "%AEGIS_ROOT%\STATS\08_episode_event_statistics\run.bat" %*
set "RC=!ERRORLEVEL!"
if "!RC!"=="0" ( set /a PASS+=1 ) else if "!RC!"=="5" ( set /a SKIP+=1 ) else if "!RC!"=="6" ( set /a PENDING+=1 ) else if "!RC!"=="3" ( set /a BLOCK+=1 ) else ( set /a FAIL+=1 & set "FAILED_LIST=!FAILED_LIST! STATS-08" )

echo.
echo [09/16] STATS-09  Leakage and split verification
call "%AEGIS_ROOT%\STATS\09_leakage_verification\run.bat" %*
set "RC=!ERRORLEVEL!"
if "!RC!"=="0" ( set /a PASS+=1 ) else if "!RC!"=="5" ( set /a SKIP+=1 ) else if "!RC!"=="6" ( set /a PENDING+=1 ) else if "!RC!"=="3" ( set /a BLOCK+=1 ) else ( set /a FAIL+=1 & set "FAILED_LIST=!FAILED_LIST! STATS-09" )

echo.
echo [10/16] STATS-10  Validation and verification metrics
call "%AEGIS_ROOT%\STATS\10_validation_verification\run.bat" %*
set "RC=!ERRORLEVEL!"
if "!RC!"=="0" ( set /a PASS+=1 ) else if "!RC!"=="5" ( set /a SKIP+=1 ) else if "!RC!"=="6" ( set /a PENDING+=1 ) else if "!RC!"=="3" ( set /a BLOCK+=1 ) else ( set /a FAIL+=1 & set "FAILED_LIST=!FAILED_LIST! STATS-10" )

echo.
echo [11/16] STATS-11  Calibration and uncertainty
call "%AEGIS_ROOT%\STATS\11_calibration_uncertainty\run.bat" %*
set "RC=!ERRORLEVEL!"
if "!RC!"=="0" ( set /a PASS+=1 ) else if "!RC!"=="5" ( set /a SKIP+=1 ) else if "!RC!"=="6" ( set /a PENDING+=1 ) else if "!RC!"=="3" ( set /a BLOCK+=1 ) else ( set /a FAIL+=1 & set "FAILED_LIST=!FAILED_LIST! STATS-11" )

echo.
echo [12/16] STATS-12  Error analysis
call "%AEGIS_ROOT%\STATS\12_error_analysis\run.bat" %*
set "RC=!ERRORLEVEL!"
if "!RC!"=="0" ( set /a PASS+=1 ) else if "!RC!"=="5" ( set /a SKIP+=1 ) else if "!RC!"=="6" ( set /a PENDING+=1 ) else if "!RC!"=="3" ( set /a BLOCK+=1 ) else ( set /a FAIL+=1 & set "FAILED_LIST=!FAILED_LIST! STATS-12" )

echo.
echo [13/16] STATS-13  Baseline comparison
call "%AEGIS_ROOT%\STATS\13_baseline_comparison\run.bat" %*
set "RC=!ERRORLEVEL!"
if "!RC!"=="0" ( set /a PASS+=1 ) else if "!RC!"=="5" ( set /a SKIP+=1 ) else if "!RC!"=="6" ( set /a PENDING+=1 ) else if "!RC!"=="3" ( set /a BLOCK+=1 ) else ( set /a FAIL+=1 & set "FAILED_LIST=!FAILED_LIST! STATS-13" )

echo.
echo [14/16] STATS-14  Ablation study
call "%AEGIS_ROOT%\STATS\14_ablation_study\run.bat" %*
set "RC=!ERRORLEVEL!"
if "!RC!"=="0" ( set /a PASS+=1 ) else if "!RC!"=="5" ( set /a SKIP+=1 ) else if "!RC!"=="6" ( set /a PENDING+=1 ) else if "!RC!"=="3" ( set /a BLOCK+=1 ) else ( set /a FAIL+=1 & set "FAILED_LIST=!FAILED_LIST! STATS-14" )

echo.
echo [15/16] STATS-15  Robustness and generalization
call "%AEGIS_ROOT%\STATS\15_robustness_generalization\run.bat" %*
set "RC=!ERRORLEVEL!"
if "!RC!"=="0" ( set /a PASS+=1 ) else if "!RC!"=="5" ( set /a SKIP+=1 ) else if "!RC!"=="6" ( set /a PENDING+=1 ) else if "!RC!"=="3" ( set /a BLOCK+=1 ) else ( set /a FAIL+=1 & set "FAILED_LIST=!FAILED_LIST! STATS-15" )

echo.
echo [16/16] STATS-16  Multi-seed and statistical significance
call "%AEGIS_ROOT%\STATS\16_multiseed_significance\run.bat" %*
set "RC=!ERRORLEVEL!"
if "!RC!"=="0" ( set /a PASS+=1 ) else if "!RC!"=="5" ( set /a SKIP+=1 ) else if "!RC!"=="6" ( set /a PENDING+=1 ) else if "!RC!"=="3" ( set /a BLOCK+=1 ) else ( set /a FAIL+=1 & set "FAILED_LIST=!FAILED_LIST! STATS-16" )

echo.
echo ============================================================
echo  STATISTICS PIPELINE SUMMARY
echo ============================================================
echo   Successful          : !PASS!
echo   Failed              : !FAIL!
echo   Skipped (protected) : !SKIP!
echo   Blocked             : !BLOCK!
echo   Not yet executed    : !PENDING!
if not "!FAILED_LIST!"=="" echo   Failed modules      :!FAILED_LIST!
echo ============================================================

REM A pipeline with any failed module never reports success. Skipped and
REM not-yet-executed modules are expected states, not failures.
if !FAIL! GTR 0 ( echo [aegis] STATISTICS PIPELINE: FAILED & exit /b 1 )
echo [aegis] STATISTICS PIPELINE: OK
exit /b 0
