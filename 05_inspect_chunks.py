#%%
"""Step 5: check the chunks written by 04_chunk_data.py. Read-only, changes nothing.

Run from the project root:
    python 05_inspect_chunks.py
"""
import json
import statistics
from collections import Counter
from pathlib import Path

CHUNK_FOLDER = Path("data/chunks")
REFERENCE_FOLDER = Path("data/reference")
TINY = 150    # chunks shorter than this are listed for review
LIMIT = 1700  # section-aware chunks should stay below this (MAX_CHARS plus the header)


#%%
def read_jsonl(path: Path) -> list[dict]:
    rows = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(row) for row in rows]


#%%
def check_basics(rows: list[dict], name: str) -> None:
    """Empty text, repeated chunk IDs, and the spread of chunk sizes."""
    ids = [row["chunk_id"] for row in rows]
    sizes = [row["char_count"] for row in rows]
    empty = [row["chunk_id"] for row in rows if not row["text"].strip()]

    print(f"{name}: {len(rows)} chunks")
    print(f"  unique chunk_ids: {len(ids) == len(set(ids))}")
    print(f"  empty chunks: {len(empty)}")
    print(f"  chars min/median/max: {min(sizes)} / {statistics.median(sizes)} / {max(sizes)}")


def check_drugs(rows: list[dict], name: str) -> None:
    """Every reference drug should have chunks."""
    expected = {file.stem for file in REFERENCE_FOLDER.glob("*.json")}
    found = {row["drug"] for row in rows}
    print(f"  drugs with chunks: {len(found)} of {len(expected)}; missing: {sorted(expected - found)}")


def list_tiny(rows: list[dict]) -> None:
    tiny = [row for row in rows if row["char_count"] < TINY]
    print(f"  chunks under {TINY} chars: {len(tiny)}")
    for row in tiny:
        print(f"    {row['chunk_id']} ({row['char_count']}): {row['text'][-70:]!r}")


def list_oversized(rows: list[dict]) -> None:
    big = [row for row in rows if row["char_count"] > LIMIT]
    print(f"  chunks over {LIMIT} chars: {len(big)}")


def list_repeated_text(rows: list[dict]) -> None:
    """The same passage indexed twice would inflate retrieval scores, so look for it."""
    bodies = Counter(row["text"].split("\n", 1)[-1] for row in rows)
    repeated = {body: n for body, n in bodies.items() if n > 1}
    print(f"  chunk bodies that appear more than once: {len(repeated)}")
    for body, n in list(repeated.items())[:3]:
        print(f"    x{n}: {body[:80]!r}")


def sections_without_headings(rows: list[dict]) -> None:
    """Chunks with no subsection: older-format labels, or short sections."""
    empty = Counter(row["section"] for row in rows if row["subsection"] == "")
    print(f"  chunks with no subsection heading: {sum(empty.values())} of {len(rows)}")
    print(f"    most common sections: {empty.most_common(4)}")


#%%
def chunks_per_drug(aware: list[dict], fixed: list[dict]) -> None:
    a = Counter(row["drug"] for row in aware)
    f = Counter(row["drug"] for row in fixed)
    print("chunks per drug (section-aware / fixed-size)")
    for drug in sorted(a):
        print(f"  {drug:20} {a[drug]:4} / {f[drug]:4}")


def show_sample(rows: list[dict], drug: str, section: str) -> None:
    """Print one chunk in full so you can judge readability by eye."""
    for row in rows:
        if row["drug"] == drug and row["section"] == section:
            print(f"\nSample: {row['chunk_id']}")
            print(row["text"])
            return
    print(f"\nNo chunk found for {drug} / {section}")


#%%
def main() -> None:
    aware = read_jsonl(CHUNK_FOLDER / "section_aware.jsonl")
    fixed = read_jsonl(CHUNK_FOLDER / "fixed_size.jsonl")

    check_basics(aware, "section-aware")
    check_drugs(aware, "section-aware")
    list_tiny(aware)
    list_oversized(aware)
    list_repeated_text(aware)
    sections_without_headings(aware)

    print()
    check_basics(fixed, "fixed-size")
    check_drugs(fixed, "fixed-size")
    list_repeated_text(fixed)

    print()
    chunks_per_drug(aware, fixed)
    show_sample(aware, "warfarin", "dosage_and_administration")


if __name__ == "__main__":
    main()
