@echo off
echo =======================================================
echo           SYNCING WITH GITHUB REPOSITORY
echo =======================================================

echo.
echo Step 1: Adding all new and modified files...
git add .

echo.
echo Step 2: Committing changes...
git commit -m "Regular update"

echo.
echo Step 3: Pushing changes to GitHub...
git push origin master

echo.
echo =======================================================
echo           SYNC COMPLETE.
echo =======================================================
echo.
pause