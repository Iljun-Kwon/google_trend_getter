import csv
import re
from pathlib import Path

def parse_query(raw: str):
    s = str(raw).strip()
    s = s.replace(" ", "")
    return s

def parse_value(raw: str) -> int | None:
    if raw is None:
        return None
    s = str(raw).strip()

    # 2) 급등 -> 5000
    if s == "급등":
        return 5000

    # Normalize: remove spaces
    s = s.replace(" ", "")

    # Match things like:
    # +123% , 123% , +1,234% , 1,234% , +5000 , 5000
    m = re.fullmatch(r"\+?([\d,]+)%?", s)
    if not m:
        return None

    num = m.group(1).replace(",", "")
    if not num.isdigit():
        return None

    return int(num)


def clean_related_queries(input_csv: Path, output_csv: Path):
    text = input_csv.read_text(encoding="utf-8-sig", errors="replace")
    lines = text.splitlines()

    # delete anything before RISING
    start = None
    for i, line in enumerate(lines):
        if line.strip().upper() == "RISING":
            start = i + 1
            break
    if start is None:
        raise ValueError("RISING not found in file.")

    # check if line exist after RISING
    rising_block_lines = [ln for ln in lines[start:] if ln.strip()]
    if not rising_block_lines:
        raise ValueError("No lines after RISING.")

    reader = csv.reader(rising_block_lines)
    out_rows = [("query", "value")]

    for r in reader:
        if len(r) < 2:
            continue

        query = parse_query(r[0].strip())
        value_int = parse_value(r[1].strip())

        out_rows.append((query, "" if value_int is None else str(value_int)))

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerows(out_rows)

    print(f"Saved: {output_csv}")


#if __name__ == "__main__":
#    clean_related_queries(INPUT_CSV, OUTPUT_CSV)
