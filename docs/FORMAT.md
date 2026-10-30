# FORMAT.md — Hệ thống ký hiệu & cấu trúc giải đấu

---

## A. Hệ thống ký hiệu (Shorthand Notation)

### A.1. Map score

```
13*-8 W     → Tuyển thủ thắng 13-8 (dấu * ở score của tuyển thủ)
10-13* W    → Tuyển thủ thắng 13-10 (score tuyển thủ 13, * ở bên phải)
12*-14 L    → Tuyển thủ thua 12-14
13-1* L     → Tuyển thủ thua 1-13
```

**Quy tắc**:
- `<scoreA>-<scoreB>*` → dấu `*` luôn nằm ở điểm của **tuyển thủ**
- `W` / `L` xác nhận kết quả thắng/thua
- Score của tuyển thủ có thể nằm bên trái hoặc bên phải dấu `-`

### A.2. Series result

```
=>2*-0(98%)     → Tuyển thủ thắng series 2-0, tỉ lệ 98%
->2-0*(91%)     → Tuyển thủ thua series 0-2, tỉ lệ 91%
=>1*-2(98%)     → Tuyển thủ thua 1-2
=>3*-2(99%)     → Tuyển thủ thắng 3-2 (BO5)
```

**Quy tắc**:
- `=>` hoặc `->` đánh dấu dòng kết quả series
- Số có `*` là số map thắng của tuyển thủ
- `(XX%)` là tỉ lệ thắng ước tính

### A.3. Swiss record & round tags

```
1-0      → Swiss record: 1 thắng, 0 thua
1-1      → Swiss record: 1 thắng, 1 thua
#1       → Vị trí chung cuộc số 1
#9-10    → Đồng hạng 9-10 (bị loại ở Swiss)
```

### A.4. Bracket tags (tên đầy đủ trong code)

| Ký hiệu shorthand | Tên đầy đủ trong code | Ý nghĩa |
|-------------------|----------------------|---------|
| `up-qt` | `upper_quarterfinal` | Tứ kết nhánh thắng |
| `up-sm` | `upper_semifinal` | Bán kết nhánh thắng |
| `up-fn` | `upper_final` | Chung kết nhánh thắng |
| `lo-r1` | `lower_round1` | Nhánh thua vòng 1 |
| `lo-qt` | `lower_quarterfinal` | Tứ kết nhánh thua |
| `lo-sm` | `lower_semifinal` | Bán kết nhánh thua |
| `lo-fn` | `lower_final` | Chung kết nhánh thua |
| `g-fn` | `grand_final` | Chung kết tổng |

### A.5. Mùa giải flow (Chế độ Cốt truyện - VCT Season Circuit)

```
OQ (Open Qualifier: 16 Non-partner → 4 suất) 
  → KO (Kick-off: 8 Partner + 4 OQ = 12 đội) → MJ (Major: 8 đội)
  → S1 (Stage 1: 12 đội) → MT (Master: 12 đội) & [ EWC ] (16 đội)
  → S2 (Stage 2: 12 đội) → CP (Champion: 16 đội)
  → Year-End Hall of Fame & Recap
```


---

## B. Cấu trúc giải đấu (VCT 2025)

### B.1. Major (8 đội) — Masters Bangkok

```
Thể thức:
  Swiss Stage:   8 đội → 4 đi tiếp, 4 bị loại
  Playoffs:      4 đội Double Elimination

Swiss Stage:
  ┌──────────┬──────────────────────────────────┐
  │ Vòng     │ Mô tả                            │
  ├──────────┼──────────────────────────────────┤
  │ Round 1  │ Bốc thăm ngẫu nhiên (4 trận)     │
  │          │ → 4 đội 1-0, 4 đội 0-1           │
  ├──────────┼──────────────────────────────────┤
  │ Round 2  │ 1-0 vs 1-0 (2 trận)              │
  │          │ → 2 đội 2-0 (ĐI TIẾP), 2 đội 1-1 │
  │          │ 0-1 vs 0-1 (2 trận)              │
  │          │ → 2 đội 1-1, 2 đội 0-2 (LOẠI)    │
  ├──────────┼──────────────────────────────────┤
  │ Round 3  │ 1-1 vs 1-1 (2 trận)              │
  │          │ → 2 đội 2-1 (ĐI TIẾP), 2 đội 1-2 │
  │          │   (LOẠI)                         │
  └──────────┴──────────────────────────────────┘
  → 4 đội vào Playoffs (seed 1-4)
  → 4 đội bị loại (hạng 5-8)

Playoffs (4-team Double Elimination):
  ┌──────────────────────┬───────────┐
  │ Trận                 │ BO3/BO5   │
  ├──────────────────────┼───────────┤
  │ upper_semifinal_1    │ BO3       │
  │ upper_semifinal_2    │ BO3       │
  │ upper_final          │ BO3       │
  │ lower_round1         │ BO3       │
  │ lower_final          │ BO5       │
  │ grand_final          │ BO5       │
  └──────────────────────┴───────────┘

  Seed: 1 vs 4, 2 vs 3 tại Upper Semifinals
```

### B.2. Master (12 đội) — Masters Toronto

```
Thể thức:
  4 đội auto-qualify (Stage 1 winners 4 khu vực)
  8 đội đánh Swiss (Stage 1 2nd + 3rd place)
  → 4 Swiss qualifiers + 4 auto = 8 đội Playoffs

Swiss Stage (8 đội):
  ┌──────────┬──────────────────────────────────┐
  │ Vòng     │ Mô tả                            │
  ├──────────┼──────────────────────────────────┤
  │ Round 1  │ Bốc thăm (4 trận)                │
  │          │ → 4 đội 1-0, 4 đội 0-1           │
  ├──────────┼──────────────────────────────────┤
  │ Round 2  │ 1-0 vs 1-0 (2 trận)              │
  │          │ → 2 đội 2-0 (ĐI TIẾP)            │
  │          │ 0-1 vs 0-1 (2 trận)              │
  │          │ → 2 đội 0-2 (LOẠI)               │
  ├──────────┼──────────────────────────────────┤
  │ Round 3  │ 1-1 vs 1-1 (2 trận)              │
  │          │ → 2 đội 2-1 (ĐI TIẾP)            │
  │          │ → 2 đội 1-2 (LOẠI)               │
  └──────────┴──────────────────────────────────┘
  → 4 Swiss qualifiers tham gia Playoffs

Playoffs (8-team Double Elimination):
  4 seed 1 bốc thăm thứ tự → lần lượt chọn đối thủ từ Swiss

  ┌───────────────────────────┬───────────┐
  │ Trận                      │ BO3/BO5   │
  ├───────────────────────────┼───────────┤
  │ upper_quarterfinal_1..4   │ BO3       │
  │ upper_semifinal_1         │ BO3       │
  │ upper_semifinal_2         │ BO3       │
  │ upper_final               │ BO3       │
  │ lower_round1_1            │ BO3       │
  │ lower_round1_2            │ BO3       │
  │ lower_quarterfinal_1      │ BO3       │
  │ lower_quarterfinal_2      │ BO3       │
  │ lower_semifinal           │ BO3       │
  │ lower_final               │ BO5       │
  │ grand_final               │ BO5       │
  └───────────────────────────┴───────────┘

  Cross bracket:
    lower_quarterfinal_1 = W(lower_round1_1) vs L(upper_semifinal_2)
    lower_quarterfinal_2 = W(lower_round1_2) vs L(upper_semifinal_1)
```

### B.3. Champion (16 đội) — Champions

```
Thể thức:
  Group Stage:   4 bảng × 4 đội (GSL format)
                 → 2 đội/bảng đi tiếp = 8 đội
  Playoffs:      8 đội Double Elimination

Group Stage (GSL):
  Mỗi bảng:
    opening1:           A1 vs A2
    opening2:           A3 vs A4
    winners_match:      W(opening1) vs W(opening2)  → seed 1 vào Playoffs
    elimination_match:  L(opening1) vs L(opening2)  → thua = bị loại
    decider_match:      L(winners_match) vs W(elimination_match) → seed 2

  → 2 đội × 4 bảng = 8 đội vào Playoffs

Playoffs (8-team Double Elimination):
  (Giống hệt bracket của Master)
```

### B.4. EWC (16 đội) — Esports World Cup

```
Thể thức:
  Group Stage:   4 bảng × 4 đội (GSL format)
                 → 2 đội/bảng đi tiếp = 8 đội
  Playoffs:      8 đội Single Elimination (Loại trực tiếp đơn)

Group Stage (GSL):
  Giống format của Champion (4 bảng A/B/C/D, 5 trận/bảng, BO3).
  Rổ hạt giống:
    Pool 1: Vô địch VCT Stage 1 của 4 khu vực
    Pool 2: Á quân VCT Stage 1 của 4 khu vực
    Pool 3: Hạt giống 1 vòng loại khu vực EWC
    Pool 4: Hạt giống 2 vòng loại khu vực EWC
  Bảo vệ khu vực: Tối đa 1 đội/khu vực mỗi bảng.

Playoffs (8-team Single Elimination):
  ┌───────────────────────┬───────────┐
  │ Trận                  │ BO3/BO5   │
  ├───────────────────────┼───────────┤
  │ quarterfinal_1        │ BO3       │
  │ quarterfinal_2        │ BO3       │
  │ quarterfinal_3        │ BO3       │
  │ quarterfinal_4        │ BO3       │
  │ semifinal_1           │ BO3       │
  │ semifinal_2           │ BO3       │
  │ third_place_match     │ BO3       │
  │ grand_final           │ BO5       │
  └───────────────────────┴───────────┘

  Ràng buộc bốc thăm:
    - Nhất bảng gặp Nhì bảng khác.
    - 2 đội cùng bảng nằm ở 2 nửa nhánh đấu đối diện (không thể tái đấu trước Chung kết tổng).
    - Thua tại Bán kết sẽ xuống thi đấu trận Tranh Hạng 3 (third_place_match).
    - Thua tại Tứ kết bị loại (Top 5-8).
```

---

### B.5. Open Qualifier (Vòng tuyển chọn mở khu vực — 16 đội Non-Partner)

```
Quy mô:          16 đội Non-partner mỗi khu vực
Số suất đi tiếp: 4 đội giành vé tham dự VCT Kickoff
Tổng số trận:    43 trận / khu vực (33 Swiss + 10 Playoffs)
Cấu trúc:        2 Giai đoạn: Swiss Stage (16 đội) + Double Elimination Playoffs (8 đội)

Giai đoạn 1: Swiss Stage (16 đội, 3 Thắng đi tiếp / 3 Thua bị loại, tối đa 5 vòng, 33 trận)
  - BO1 cho các trận thông thường (R1, R2, R3 nhánh 1-1).
  - BO3 cho các trận quyết định đi tiếp hoặc bị loại (R3 2-0/0-2, R4 2-1/1-2, R5 2-2).
  - Không tái đấu đối thủ cũ trong giai đoạn Swiss.
  - Phân bổ trận đấu:
    * Vòng 1 (0-0): 8 BO1 (8 trận)
    * Vòng 2 (1-0 & 0-1): 8 BO1 (8 trận)
    * Vòng 3 (2-0 BO3 x2, 1-1 BO1 x4, 0-2 BO3 x2): 4 BO3 + 4 BO1 (8 trận)
    * Vòng 4 (2-1 BO3 x3, 1-2 BO3 x3): 6 BO3 (6 trận)
    * Vòng 5 (2-2 BO3 x3): 3 BO3 (3 trận)
  - Kết quả Swiss:
    * 8 đội vượt qua: 2 đội (3-0), 3 đội (3-1), 3 đội (3-2) → Xếp hạt giống 1-8 vào Playoffs.
    * 8 đội bị loại: 2 đội (0-3), 3 đội (1-3), 3 đội (2-3).

Giai đoạn 2: Double Elimination Playoffs (8 đội, tất cả trận BO3, dừng ngay khi đủ 4 vé)
  - Upper R1:
    * M1: Seed 1 vs Seed 8
    * M2: Seed 4 vs Seed 5
    * M3: Seed 2 vs Seed 7
    * M4: Seed 3 vs Seed 6
  - Upper R2 (Tranh vé Kickoff 1 & 2):
    * M5: Winner M1 vs Winner M2 → Winner giành Suất Kickoff #1!
    * M6: Winner M3 vs Winner M4 → Winner giành Suất Kickoff #2!
  - Lower R1 (Thua bị loại):
    * M7: Loser M1 vs Loser M2 → Loser bị loại.
    * M8: Loser M3 vs Loser M4 → Loser bị loại.
  - Lower Qualification (Tranh vé Kickoff 3 & 4):
    * M9: Winner M7 vs Loser M5 → Winner giành Suất Kickoff #3!
    * M10: Winner M8 vs Loser M6 → Winner giành Suất Kickoff #4!
  - Dừng giải ngay sau M9 & M10: Đã xác định đủ 4 đội giành vé Kickoff cùng 8 đội Partner!
```

---

### B.6. VCT Kickoff (12 đội Double Elimination) — Chuẩn VCT 2025

```
Quy mô:          12 đội / khu vực (8 đội Partner + 4 đội vượt qua Open Qualifier)
Suất đi Major:   Top 2 đội (Vô địch & Á quân) đại diện khu vực đi VCT Major (Masters Bangkok)
Tổng số trận:    Đúng 22 trận / khu vực (11 Nhánh thắng + 10 Nhánh thua + 1 Chung kết tổng)
Hạt giống Byes:  4 đội nhận suất Đặc cách vào thẳng Tứ kết Upper QF:
                 - Năm 1: Top 4 Partner có Story Rating cao nhất
                 - Năm 2+: 4 đội từng đại diện khu vực tham dự Champions năm trước

Sơ đồ nhánh đấu:
1. Nhánh Thắng (Upper Bracket - 11 trận, BO3):
   - Upper Round 1 (4 trận): 4 Partner vs 4 Open Qualifier (Defend the throne)
   - Upper Quarterfinals (4 trận): 4 Byes vs 4 đội thắng Upper R1
   - Upper Semifinals (2 trận)
   - Upper Final (1 trận): Thắng vào Chung kết tổng & GIÀNH VÉ MAJOR #1; Thua xuống Lower Final

2. Nhánh Thua (Lower Bracket - 10 trận):
   - Lower Round 1 (4 trận, BO3): 4 đội thua Upper R1 vs 4 đội thua Upper QF (Thua loại, Hạng 9-12, 0 CP)
   - Lower Round 2 (2 trận, BO3): 4 đội thắng Lower R1 gặp nhau (Thua loại, Hạng 7-8, 0 CP)
   - Lower Round 3 (2 trận, BO3): 2 đội thắng Lower R2 vs 2 đội thua Upper SF (Thua loại, Hạng 5-6, 0 CP)
   - Lower Semifinal (1 trận, BO3): Thua loại, Hạng 4 (+1 CP); Thắng vào Lower Final
   - Lower Final (1 trận, BO5): Thua loại, Hạng 3 (+1 CP); Thắng vào Chung kết tổng & GIÀNH VÉ MAJOR #2

3. Chung kết Tổng (Grand Final - 1 trận, BO5):
   - Winner Upper Final vs Winner Lower Final
   - Vô địch Kickoff: Hạt giống 1 Major + 3 CP
   - Á quân Kickoff: Hạt giống 2 Major + 2 CP
```

---

## C. Quy tắc BO1 / BO3 / BO5


| Loại trận | Thể thức |
|-----------|---------|
| Open Qualifier Swiss thông thường (R1, R2, R3 nhánh 1-1) | **BO1** |
| Open Qualifier Swiss quyết định (R3 2-0/0-2, R4, R5) | **BO3** |
| Open Qualifier Playoffs (toàn bộ 10 trận M1-M10) | **BO3** |
| Tất cả Swiss / Group (Major, Master, Champion, EWC) | **BO3** |
| Upper Bracket (tất cả các vòng) | **BO3** |
| Lower Round 1, Quarterfinal, Semifinal | **BO3** |
| **Trận Tranh Hạng 3 (EWC)** | **BO3** |
| **Lower Final** | **BO5** |
| **Grand Final** | **BO5** |
