"""Create only a new toy database; never overwrite an existing user file."""
import argparse
import csv
from pathlib import Path
import sqlite3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with (Path(__file__).parent.parent / "local-csv" / "sales.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    with args.output.open("xb"):
        pass
    with sqlite3.connect(args.output) as db:
        db.execute("CREATE TABLE sales (date TEXT, category TEXT, revenue REAL)")
        db.executemany("INSERT INTO sales VALUES (?, ?, ?)",
                       [(r["date"], r["category"], float(r["revenue"])) for r in rows])
    print(args.output.resolve())


if __name__ == "__main__":
    main()
