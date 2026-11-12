#%%
"""Step 6: BM25 keyword search over the chunks, written by hand.

Run from the project root:
    python 06_bm25_search.py

Reads:  data/chunks/section_aware.jsonl
Shows:  the top chunks for a few example questions
Later scripts reuse build_index() and search().
"""
import json
import math
import re
from collections import Counter
from pathlib import Path

CHUNK_FOLDER = Path("data/chunks")

# Common words that carry little meaning. "not", "no" and "without" are kept on purpose
# because "not recommended" means something different from "recommended" (see DECISIONS.md D13).
STOPWORDS = {"the", "a", "an", "of", "and", "is", "to", "in",
             "with", "or", "for", "on", "are", "as", "at", "that", "by",
             "have", "been", "may", "see"}

K1 = 1.5   # how quickly repeating a word stops helping (higher = repeats help for longer)
B = 0.75   # how strongly long chunks are penalised (0 = no penalty, 1 = full penalty)


#%%
def tokenize(text: str) -> list[str]:
    """Lowercase text and return its words and numbers. Decimals like 2.5 stay together."""
    words = re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", text.lower())
    return [word for word in words if word not in STOPWORDS]


def read_jsonl(path: Path) -> list[dict]:
    rows = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(row) for row in rows]


#%%
def build_index(chunks: list[dict]) -> dict:
    """Do the counting once, up front, so each search is fast.

    The index holds, for every chunk: its word counts and its length; and across all chunks:
    the average length and each word's IDF weight (rare words weigh more).
    """
    tokenized = [tokenize(chunk["text"]) for chunk in chunks]
    term_counts = [Counter(tokens) for tokens in tokenized]
    lengths = [len(tokens) for tokens in tokenized]

    # document frequency: in how many chunks does each word appear at least once?
    document_freq = Counter()
    for counts in term_counts:
        for word in counts:
            document_freq[word] += 1

    n = len(chunks)
    idf = {word: math.log(1 + (n - df + 0.5) / (df + 0.5)) for word, df in document_freq.items()}

    return {
        "chunks": chunks,
        "term_counts": term_counts,
        "lengths": lengths,
        "avg_len": sum(lengths) / n,
        "idf": idf,
    }


def score_chunk(index: dict, query_words: list[str], i: int) -> float:
    """BM25 score of chunk number i for the question's words."""
    counts = index["term_counts"][i]
    length_norm = 1 - B + B * index["lengths"][i] / index["avg_len"]

    total = 0.0
    for word in query_words:
        tf = counts[word]          # times the word appears in this chunk (0 if absent)
        if tf == 0:
            continue
        total += index["idf"][word] * tf * (K1 + 1) / (tf + K1 * length_norm)
    return total


def search(index: dict, query: str, k: int = 5) -> list[tuple[dict, float]]:
    """Return the top k (chunk, score) pairs, best first. Chunks that share no word are left out."""
    query_words = tokenize(query)
    scores = [score_chunk(index, query_words, i) for i in range(len(index["chunks"]))]
    best = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
    return [(index["chunks"][i], scores[i]) for i in best if scores[i] > 0]


#%%
EXAMPLE_QUESTIONS = [
    "starting dose of warfarin",
    "apixaban dosage twice daily",
    "can simvastatin be taken with amlodipine",
]


def main() -> None:
    chunks = read_jsonl(CHUNK_FOLDER / "section_aware.jsonl")
    index = build_index(chunks)
    print(f"Indexed {len(chunks)} chunks, {len(index['idf'])} distinct words, "
          f"average length {index['avg_len']:.0f} words\n")

    for question in EXAMPLE_QUESTIONS:
        print(f"Question: {question}")
        for chunk, score in search(index, question, k=3):
            preview = chunk["text"].split("\n", 1)[-1][:110]
            print(f"  {score:5.2f}  {chunk['chunk_id']}")
            print(f"         {preview}")
        print()


if __name__ == "__main__":
    main()
