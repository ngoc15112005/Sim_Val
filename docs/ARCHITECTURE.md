# ARCHITECTURE.md — Kiến trúc hệ thống

---

## A. Database Schema

### ERD

```
┌──────────┐       ┌──────────┐       ┌─────────────────┐
│ regions  │──1:N──│  clubs   │──1:N──│ club_ratings    │
└──────────┘       └────┬─────┘       └─────────────────┘
                        │
                        │ 1:N
                        ▼
                   ┌──────────┐
                   │ players  │────N:1──┐
                   └──────────┘         │
                                        ▼
                                   ┌──────────┐
                                   │  roles   │
                                   └──────────┘

┌──────────────┐
│ tournaments  │──1:N──┬── tournament_participants ──N:1── clubs
└──────────────┘       │
                       ├── matches ──N:1── clubs (team_a, team_b, winner, loser)
                       │      │
                       │      └──1:N── match_maps
                       │
                       └── club_ratings
```

### Bảng chi tiết

#### `regions` — Khu vực
| Cột | Kiểu | Mô tả |
|-----|------|-------|
| id | INTEGER PK | |
| name | VARCHAR(50) | Pacific, Americas, EMEA, China |
| slug | VARCHAR(20) UNIQUE | `pacific`, `americas`, `emea`, `china` |

#### `clubs` — Câu lạc bộ
| Cột | Kiểu | Mô tả |
|-----|------|-------|
| id | INTEGER PK | |
| name | VARCHAR(100) | Tên đầy đủ |
| short_code | VARCHAR(5) UNIQUE | PRX, FNC, EDG... |
| region_id | FK → regions.id | Khu vực |
| base_rating | INTEGER | Rating khởi điểm (0-100) |
| current_rating | INTEGER | Rating hiện tại sau các giải |
| is_active | BOOLEAN | Đang hoạt động |

#### `players` — Tuyển thủ *(dành cho tương lai)*
| Cột | Kiểu | Mô tả |
|-----|------|-------|
| id | INTEGER PK | |
| name | VARCHAR(100) | |
| age | INTEGER | Tuổi |
| club_id | FK → clubs.id | Đội hiện tại |
| role_id | FK → roles.id | Vị trí |
| rating | INTEGER | Chỉ số cá nhân |
| is_active | BOOLEAN | |

#### `roles` — Vị trí *(dành cho tương lai)*
| Cột | Kiểu |
|-----|------|
| id | INTEGER PK |
| name | VARCHAR(30) UNIQUE | Duelist, Initiator, Controller, Sentinel, Flex |

#### `tournaments` — Giải đấu
| Cột | Kiểu | Mô tả |
|-----|------|-------|
| id | INTEGER PK | |
| type | VARCHAR(20) | `major`, `master`, `champion` |
| name | VARCHAR(100) | Tên hiển thị |
| status | VARCHAR(20) | `setup` → `swiss`/`groups` → `playoffs` → `finished` |
| created_at | DATETIME | Thời gian tạo |

#### `tournament_participants` — Đội tham gia
| Cột | Kiểu | Mô tả |
|-----|------|-------|
| id | INTEGER PK | |
| tournament_id | FK → tournaments.id | |
| club_id | FK → clubs.id | |
| seed | INTEGER | Hạt giống (1-N) |
| region | VARCHAR(20) | Khu vực |
| final_rank | INTEGER | Hạng chung cuộc (NULL = chưa xong) |

#### `matches` — Trận đấu
| Cột | Kiểu | Mô tả |
|-----|------|-------|
| id | INTEGER PK | |
| tournament_id | FK → tournaments.id | |
| round_type | VARCHAR(20) | `swiss`, `group`, `upper`, `lower`, `grand` |
| round_name | VARCHAR(30) | `swiss_round1`, `upper_quarterfinal_1`, `grand_final` |
| match_order | INTEGER | Thứ tự hiển thị |
| team_a_id | FK → clubs.id | Đội A |
| team_b_id | FK → clubs.id | Đội B |
| team_a_score | INTEGER | Số map thắng (NULL = chưa đấu) |
| team_b_score | INTEGER | |
| winner_id | FK → clubs.id | |
| loser_id | FK → clubs.id | |
| status | VARCHAR(20) | `pending`, `completed` |
| is_manual | BOOLEAN | True nếu nhập tay |

#### `match_maps` — Chi tiết map
| Cột | Kiểu | Mô tả |
|-----|------|-------|
| id | INTEGER PK | |
| match_id | FK → matches.id | |
| map_number | INTEGER | 1, 2, 3, 4, 5 |
| team_a_score | INTEGER | |
| team_b_score | INTEGER | |
| winner_id | FK → clubs.id | |

#### `club_ratings` — Lịch sử rating
| Cột | Kiểu | Mô tả |
|-----|------|-------|
| id | INTEGER PK | |
| club_id | FK → clubs.id | |
| tournament_id | FK → tournaments.id | |
| rating_before | INTEGER | Rating trước giải |
| rating_after | INTEGER | Rating sau giải |

---

## B. Engine Modules

### `engine/tournament.py` — Quản lý vòng đấu

| Hàm | Mô tả |
|-----|-------|
| `create_tournament(type, name, club_ids)` | Tạo giải mới |
| `generate_bracket(tournament)` | Sinh bracket ban đầu (Swiss R1 hoặc Groups) |
| `progress_tournament(tournament)` | Tiến tới vòng tiếp theo |
| `simulate_all_pending(tournament)` | Tự động sim tất cả trận còn lại |

**Swiss logic** (Major & Master):
- `_generate_swiss_round1(tournament, participants)` — Bốc thăm ngẫu nhiên
- `_generate_swiss_next_round()` — Ghép cặp cùng record
- `_finalize_swiss()` — Chọn đội đi tiếp, sinh bracket Playoffs

**Group Stage logic** (Champion):
- `_generate_groups()` — 4 bảng × 4 đội
- `_resolve_group_placeholder_matches()` — Sinh Winners/Elimination/Decider match sau mỗi bảng

**Playoffs logic**:
- `_generate_playoffs()` — Sinh bracket 4-team hoặc 8-team Double Elim
- `_generate_master_quarterfinals()` — Bốc thăm thứ tự auto-qualify chọn đối thủ Swiss
- `_resolve_playoff_placeholder_matches()` — Điền TBD slot sau khi có kết quả
- `_fill_cross_bracket()` — Cross bracket Lower Quarterfinal
- `_finalize_tournament()` — Gán hạng #1-#8

### `engine/match.py` — Mô phỏng trận đấu

| Hàm | Mô tả |
|-----|-------|
| `simulate_match(match, streak_a, streak_b)` | Sinh kết quả ngẫu nhiên có trọng số |
| `resolve_manual_match(match, maps_input)` | Nhập tay tỉ số map |
| `_calc_win_rate(rating_a, rating_b, streak_a, streak_b)` | Tính xác suất thắng |
| `_gen_map_score(our_rating, their_rating)` | Sinh tỉ số map ngẫu nhiên |

**Xác suất thắng** dựa trên chênh lệch rating + form bonus (streak):

| Chênh lệch | Win rate |
|-----------|----------|
| 0-5 | ~50% |
| 5-15 | ~55-62% |
| 15-30 | ~68-80% |
| >30 | ~86-90% |

### `engine/parser.py` — Parse shorthand

| Hàm | Mô tả |
|-----|-------|
| `parse_map_line('13*-8 W')` | Parse 1 dòng map score |
| `parse_series_line('=>2*-0(98%) 1-0')` | Parse dòng kết quả series |
| `parse_match_block(text)` | Parse cả block match (đối thủ + maps + series) |
| `maps_to_shorthand(maps_data)` | Ngược lại: structured → shorthand lines |

### `engine/rating.py` — Cập nhật rating

| Hàm | Mô tả |
|-----|-------|
| `update_ratings(tournament)` | Cập nhật rating tất cả đội sau khi giải kết thúc |

Hệ thống ELO đơn giản: hạng càng cao → cộng càng nhiều điểm, giới hạn [40, 100].

---

## C. API Routes

### Pages

| Route | Method | Mô tả |
|-------|--------|-------|
| `/` | GET | Dashboard: tạo giải + lịch sử |
| `/tournament/<id>` | GET | Giao diện bracket từng giải |

### API

| Route | Method | Mô tả |
|-------|--------|-------|
| `/api/clubs` | GET | Danh sách CLB (filter `?region=`) |
| `/api/regions` | GET | Danh sách khu vực |
| `/api/tournament/start` | POST | Tạo giải mới `{type, name, club_ids}` |
| `/api/tournament/<id>` | GET | Trạng thái giải + participants + matches |
| `/api/tournament/<id>/match/<mid>/sim` | POST | Tự động sim 1 trận |
| `/api/tournament/<id>/match/<mid>/manual` | POST | Nhập tay kết quả 1 trận `{maps}` |
| `/api/tournament/<id>/sim-all` | POST | Sim toàn bộ giải |
| `/api/tournament/<id>/progress` | POST | Tiến tới vòng tiếp theo |
| `/api/parser/test` | POST | Test parse shorthand `{text}` |

---

## D. Data Flow

```
┌─────────┐    HTTP/JSON    ┌──────────┐    SQLAlchemy    ┌──────────┐
│ Browser │ ←─────────────→ │  Flask   │ ←─────────────→ │  SQLite  │
│ (JS)    │   GET/POST      │  routes  │   query/commit  │  (val.db)│
└─────────┘                 └────┬─────┘                 └──────────┘
                                 │
                                 │ Python calls
                                 ▼
                          ┌──────────────┐
                          │   engine/    │
                          │ tournament   │
                          │ match        │
                          │ parser       │
                          │ rating       │
                          └──────────────┘

1. User → Browser (click "Tao giai", pick team, click "Roll")
2. Browser → `fetch('/api/...')` → Flask route
3. Flask → `engine/*.py` → xử lý logic
4. Engine → `db.session` → SQLite
5. Response → JSON → Browser → render HTML
```

---

## E. Cách thêm giải đấu mới

1. Thêm config vào `TOURNAMENT_TYPES` trong `config.py`
2. Nếu cần format bracket mới → thêm logic vào `engine/tournament.py`
3. Frontend tự nhận diện từ `tournament.type`

## F. Cách migrate database

1. Thêm cột/bảng vào `models.py`
2. Chạy: `python -c "from app import create_app; from models import db; db.create_all(app=create_app())"`
3. Hoặc tích hợp Flask-Migrate (Alembic) nếu cần versioned migrations
