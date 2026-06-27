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

### A.5. Mùa giải flow

```
KO (Kick-off) → MJ (Major)
S1 (Stage 1)  → MT (Master)
S2 (Stage 2)  → CP (Champion)
```

Mỗi mùa: KO → MJ | S1 → MT | S2 → CP

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

---

## C. Quy tắc BO3 / BO5

| Loại trận | BO3/BO5 |
|-----------|---------|
| Tất cả Swiss / Group | BO3 |
| Upper Bracket (tất cả các vòng) | BO3 |
| Lower Round 1, Quarterfinal, Semifinal | BO3 |
| **Lower Final** | **BO5** |
| **Grand Final** | **BO5** |
