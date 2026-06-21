@echo off
chcp 65001 > nul
echo ====================================================
echo  🚀 Bắt đầu quá trình đẩy code lên GitHub...
echo ====================================================
echo.

:: Hiển thị trạng thái hiện tại
git status
echo.

:: Nhập thông điệp commit
set /p commit_msg="👉 Nhập thông điệp commit (Enter để dùng: 'cập nhật code tự động'): "

if "%commit_msg%"=="" (
    set commit_msg=cập nhật code tự động
)

echo.
echo 📥 Đang chuẩn bị các file thay đổi (git add)...
git add .

echo.
echo 💾 Đang tạo bản ghi commit...
git commit -m "%commit_msg%"

echo.
echo 📤 Đang đẩy mã nguồn lên GitHub (git push)...
git push origin main

echo.
echo ====================================================
echo  🎉 Hoàn thành đẩy code!
echo ====================================================
echo.
pause
