@echo off
echo ==========================================
echo  VULKAN BLOCKS - Original Project (All 5 Phases)
echo ==========================================
echo.
echo Starting Vulkan Blocks...

if exist "README.md" (
    echo [OK] README.md found
) else (
    echo [ERROR] README.md not found!
    pause
    exit /b 1
)

echo.
echo Checking phase plan files...
if exist "PHASE_1_PLAN.md" echo [OK] Phase 1 Plan found
if exist "PHASE_2_PLAN.md" echo [OK] Phase 2 Plan found
if exist "PHASE_3_PLAN.md" echo [OK] Phase 3 Plan found
if exist "PHASE_4_PLAN.md" echo [OK] Phase 4 Plan found

echo.
echo Checking Python daemon...
if exist "python\vulkan\node\main.py" (
    echo [OK] Python daemon found
) else (
    echo [WARNING] Python daemon not found in expected location
)

echo.
echo Checking Rust build...
if exist "Cargo.lock" (
    echo [OK] Cargo.lock found
) else (
    echo [WARNING] Cargo.lock not found
)

echo.
echo ==========================================
echo  Vulkan Blocks setup complete!
echo ==========================================
pause