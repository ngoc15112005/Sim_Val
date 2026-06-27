# VAL SIM — VALORANT Tournament Simulator

Trình mô phỏng giải đấu quốc tế VALORANT Champions Tour (VCT), phục vụ cho trò chơi quản lý đội tuyển.

---

## Chạy nhanh

```bash
cd val-sim
pip install flask flask-sqlalchemy
python seed.py        # Nạp 48 CLB Tier 1 + 4 khu vực
python app.py         # Khởi động server
# Mở trình duyệt: http://localhost:5000
```

---

## Chức năng chính

- **Tạo giải đấu**: Major (8 đội), Master (12 đội), Champion (16 đội)
- **Chọn đội thủ công** hoặc **fill random** từ 48 CLB Tier 1 (Pacific, Americas, EMEA, China)
- **Tự động sinh bracket** theo format VCT 2025: Swiss Stage, Group Stage, Double Elimination
- **Mô phỏng trận đấu** với weighted random (rating + phong độ)
- **Nhập tỷ số tay** từng trận nếu muốn can thiệp
- **Parse shorthand** từ file `.txt` match log (`13*-8 W`)
- **Lưu lịch sử** giải đấu vào database

---

## Công nghệ

| Thành phần | Công nghệ |
|------------|-----------|
| Backend | Python 3 + Flask |
| Database | SQLite (qua Flask-SQLAlchemy) |
| Frontend | Jinja2 + Vanilla JS + CSS |
| Lưu trữ | SQLite file (`instance/val.db`) |

---

## Cấu trúc thư mục

```
val-sim/
├── app.py                  # Flask entry point
├── config.py               # Cấu hình giải đấu, slot region
├── models.py               # Database schema (8 bảng)
├── seed.py                 # Nạp dữ liệu 48 CLB
├── routes.py               # API + page routes
├── engine/
│   ├── tournament.py       # Vòng đấu: Swiss, Group, Double Elim
│   ├── match.py            # Mô phỏng trận (weighted random + nhập tay)
│   ├── parser.py           # Parse shorthand match log
│   └── rating.py           # Cập nhật rating sau giải
├── templates/
│   ├── base.html           # Layout chung
│   ├── index.html          # Dashboard tạo giải
│   └── tournament.html     # Giao diện bracket
├── static/
│   └── style.css           # Theme tối
├── docs/
│   ├── README.md           # File này
│   ├── FORMAT.md           # Hệ thống ký hiệu + format 3 giải
│   └── ARCHITECTURE.md     # Kiến trúc hệ thống
└── instance/
    └── val.db              # SQLite database (tự sinh)
```

---

## Tài liệu liên quan

- [FORMAT.md](FORMAT.md) — Hệ thống ký hiệu shorthand và cấu trúc 3 loại giải
- [ARCHITECTURE.md](ARCHITECTURE.md) — Database schema, engine modules, API routes
