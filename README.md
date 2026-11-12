# Medicines Information Assistant with a Safety and Evaluation Harness

A clinician-style medicines Q&A assistant that answers from FDA drug labels and cites its sources.
The assistant is not the point. The centrepiece is the harness around it: evaluation, guardrails
and red-teaming.

> **Not for clinical use.** This is a learning and research project. Do not use it to make
> medical decisions.

## Status

| Step | Status |
|---|---|
| Ingestion: section-aware chunks with metadata | done |
| Retrieval: BM25 + embeddings, RRF, reranker | in progress (BM25 and first eval done) |
| Generation: structured output with citations | planned |
| Tools: RxNorm normalisation, dose calculator | planned |
| Guardrails | planned |
| Evaluation suite (200+ labelled questions, ablations, LLM judge) | in progress (4 questions so far) |
| FastAPI, Docker, CI, Azure demo | planned |

## Pipeline

Run the scripts in order from the project root. Corpus: one reference label per drug (20 drugs,
tablets, single-ingredient). Design decisions and how to adapt them are in
[DECISIONS.md](DECISIONS.md).

| Script | What it does |
|---|---|
| `01_download_data.py` | Download openFDA labels |
| `02_inspect_data.py` | Report which sections exist |
| `03_reference.py` | Pick one reference label per drug |
| `04_chunk_data.py` | Chunk labels two ways: section-aware and fixed-size baseline |
| `05_inspect_chunks.py` | Sanity-check the chunks |
| `06_bm25_search.py` | BM25 keyword search written from scratch |
| `07_eval_retrieval.py` | Measure hit@k and MRR against `data/eval/questions.csv` |
