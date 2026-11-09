"""
scripts/clean_test_data.py
Script dọn dẹp toàn bộ dữ liệu save test (campaigns, tournaments, file json test)
sinh ra trong quá trình chạy unit test, bảo vệ tuyệt đối save game thật của người dùng.
"""
import os
import sys
import glob

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models import db, Campaign, Tournament


def clean_all_test_data():
    app = create_app()
    camp_count = 0
    tour_count = 0
    file_count = 0

    with app.app_context():
        # 1. Xóa các chiến dịch test (tất cả chiến dịch có id != 1 hoặc có chữ Test/Check/alert/Save trong tên)
        test_camps = Campaign.query.filter(
            (Campaign.id != 1) |
            (Campaign.name.ilike('%test%'))
        ).all()
        # Loại trừ campaign 1 của người dùng
        test_camps = [c for c in test_camps if c.id != 1]
        camp_count = len(test_camps)
        for c in test_camps:
            db.session.delete(c)

        # 2. Xóa các giải đấu test (chỉ giữ lại giải đấu thật của người dùng, id=9 EWC Riyadh 2026)
        test_tours = Tournament.query.filter(
            (Tournament.id != 9) &
            (Tournament.name.ilike('%test%') | Tournament.id.in_([1, 2, 3, 4, 5, 6, 7, 8]))
        ).all()
        tour_count = len(test_tours)
        for t in test_tours:
            db.session.delete(t)

        db.session.commit()

    # 3. Xóa các file lưu tạm được test sinh ra trong thư mục saves/
    patterns = [
        'saves/campaign/*test*.json',
        'saves/campaign/*Test*.json',
        'saves/campaign/*Export*.json',
        'saves/single/*test*.json',
        'saves/single/*Test*.json',
    ]
    for p in patterns:
        for fpath in glob.glob(p):
            try:
                os.remove(fpath)
                file_count += 1
            except Exception as e:
                print(f"Lỗi khi xóa file {fpath}: {e}")

    print(f"Cleaned test data: {camp_count} test campaigns, {tour_count} test tournaments, {file_count} test files.")
    return camp_count, tour_count, file_count


if __name__ == '__main__':
    clean_all_test_data()
