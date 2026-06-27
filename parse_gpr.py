import json, re

with open(r'C:\Users\JNgoc\.local\share\opencode\tool-output\tool_f07c1fd47001ocbWKdQrMxPrTE', 'r', encoding='utf-8') as f:
    data = json.load(f)
html = data['parse']['text']['*']

# Split by table - only use the first major ranking table
# Find the first <table> with rows
tables = re.split(r'<table[^>]*>', html)
print(f'Found {len(tables)} table-like sections')

# Use the first large table that has ranking data
all_rows = re.findall(r'<td>(\d+)\s*</td>\s*<td[^>]*>.*?title="([^"]+)".*?</td>\s*<td>\s*(?:<b>)?(\d+)(?:</b>)?\s*</td>', html, re.DOTALL)

# Only take rows where rank is between 1-30 (first table)
rows = [(int(r), n, int(s)) for r, n, s in all_rows if 1 <= int(r) <= 30]
print(f'Rows with rank 1-30: {len(rows)}')

# Take first occurrence of each rank (from the first table)
seen_ranks = set()
unique_rows = []
for rank, name, score in rows:
    if rank not in seen_ranks:
        seen_ranks.add(rank)
        unique_rows.append((rank, name, score))
        if len(seen_ranks) >= 30:
            break

print(f'Unique rows: {len(unique_rows)}')
for rank, name, score in unique_rows:
    print(f'{rank:2d}. {name:35s} {score}')
