"""
tests/__init__.py
Đăng ký tự động dọn dẹp toàn bộ dữ liệu test (test campaigns, test tournaments, test save files)
ngay khi quá trình chạy test hoàn tất, đảm bảo không bao giờ để sót save test trong cơ sở dữ liệu
và thư mục saves/ của người dùng.
"""
import atexit


def _auto_cleanup():
    try:
        from scripts.clean_test_data import clean_all_test_data
        clean_all_test_data()
    except Exception as e:
        # Im lặng nếu có lỗi dọn dẹp khi process đang thoát
        pass


atexit.register(_auto_cleanup)
