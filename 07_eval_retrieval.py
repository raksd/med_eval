#%%
"""Step 7: measure how well search finds the right chunk.

Run from the project root:
    python 07_eval_retrieval.py

Reads:  data/eval/questions.csv  (id, question, drug, expected_answer, evidence_phrase)
        data/chunks/section_aware.jsonl and fixed_size.jsonl
Prints: per-question results and hit@k / MRR for each chunk file.

A chunk counts as CORRECT for a question if it belongs to the question's drug and its text
contains the evidence phrase. Chunk IDs are never written by hand (see DECISIONS.md D11).
"""
import csv
import importlib
from pathlib import Path

bm25 = importlib.import_module("06_bm25_search")

QUESTIONS_FILE = Path("data/eval/questions.csv")
CHUNK_FILES = ["section_aware.jsonl", "fixed_size.jsonl"]
K_VALUES = (1, 3, 5, 10)     # hit@k is reported for each of these
MAX_K = max(K_VALUES)        # we retrieve this many and look at the top of the list


#%%
def normalise(text: str) -> str:
    """Lowercase and collapse all whitespace, so line breaks never stop a phrase matching."""
    return " ".join(text.lower().split())


def read_questions(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def correct_chunk_ids(chunks: list[dict], drug: str, phrase: str) -> set[str]:
    phrase = normalise(phrase)
    return {c["chunk_id"] for c in chunks
            if c["drug"] == drug and phrase in normalise(c["text"])}


#%%
def evaluate(chunks: list[dict], questions: list[dict]) -> list[dict]:
    """Run every question through BM25 and record where the first correct chunk ranked."""
    index = bm25.build_index(chunks)
    results = []
    for q in questions:
        correct = correct_chunk_ids(chunks, q["drug"], q["evidence_phrase"])
        retrieved = [chunk["chunk_id"] for chunk, _ in bm25.search(index, q["question"], k=MAX_K)]

        rank = None   # 1 = first result; None = no correct chunk in the top MAX_K
        for position, chunk_id in enumerate(retrieved, start=1):
            if chunk_id in correct:
                rank = position
                break
        results.append({"id": q["id"], "question": q["question"], "n_correct": len(correct),
                        "rank": rank, "retrieved": retrieved})
    return results


def summarise(results: list[dict]) -> dict:
    n = len(results)
    summary = {f"hit@{k}": sum(1 for r in results if r["rank"] and r["rank"] <= k) / n
               for k in K_VALUES}
    summary["MRR"] = sum(1 / r["rank"] for r in results if r["rank"]) / n
    return summary


#%%
def main() -> None:
    questions = read_questions(QUESTIONS_FILE)
    print(f"{len(questions)} questions from {QUESTIONS_FILE}")

    for filename in CHUNK_FILES:
        chunks = bm25.read_jsonl(bm25.CHUNK_FOLDER / filename)
        results = evaluate(chunks, questions)

        print(f"\n=== {filename} ({len(chunks)} chunks) ===")
        for r in results:
            rank = r["rank"] if r["rank"] else "-"
            print(f"  {r['id']}  first correct at rank {rank:>2}   "
                  f"(correct chunks for this question: {r['n_correct']})")
            if r["n_correct"] == 0:
                print("        warning: no chunk contains the evidence phrase "
                      "(typo in the phrase, or the chunker split it)")
            elif r["rank"] is None:
                print("        top 3 retrieved:", r["retrieved"][:3])

        summary = summarise(results)
        print("  " + "   ".join(f"{name} {value:.2f}" for name, value in summary.items()))


if __name__ == "__main__":
    main()
