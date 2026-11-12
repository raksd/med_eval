# Medicines Information Assistant with a Safety and Evaluation Harness

A clinician-style medicines Q&A assistant that answers from FDA drug labels and cites its sources.
The assistant is not the point of the project. The real centrepiece is the harness around it:
evaluations, guardrails and red-teaming, treated like a small clinical safety project.

> **Not for clinical use.** This is a learning and research project. Do not use it to make
> medical decisions.

## Project status

| Step | Status |
|---|---|
| 1. Ingestion: section-aware chunks with metadata | done |
| 2. Retrieval: BM25 + embeddings, reciprocal rank fusion, reranker | in progress (BM25 done, not yet evaluated) |
| 3. Generation: structured output (answer, chunk citations, confidence, refusal reason) | planned |
| 4. Tool use: RxNorm drug-name normalisation, deterministic dose calculator | planned |
| 5. Guardrails | planned |
| Evaluation suite (200+ hand-labelled questions, ablations, LLM judge) | planned |
| FastAPI, Docker, CI (ruff, pytest, eval smoke test), Azure demo | planned |

## Pipeline (scripts run in order)

Why each design choice was made, and what to change to adapt it to another system, is in
[DECISIONS.md](DECISIONS.md).

Run from the project root with the virtual environment active.

| Script | What it does | Output |
|---|---|---|
| `01_download_data.py` | Downloads openFDA drug labels: **tablets only** and **single-ingredient only** (no combination products), for 20 drugs | `data/raw/<date>/` |
| `02_inspect_data.py` | Reports which label sections exist and the NDA (original) vs ANDA (generic) split | printout |
| `03_reference.py` | Picks one reference label per drug (prefers original NDA labels, then newest) | `data/reference/<drug>.json` |
| `04_chunk_data.py` | Splits the reference labels into chunks for retrieval (two methods, see below) | `data/chunks/*.jsonl` |
| `05_inspect_chunks.py` | Checks the chunks: empty or repeated chunks, size spread, missing drugs, tiny chunks | printout |
| `06_bm25_search.py` | Keyword search (BM25) written from scratch: tokenise, build an index once, rank chunks for a question. Importable by later scripts | printout of top chunks for example questions |
| `07_eval_retrieval.py` | Scores retrieval against `data/eval/questions.csv`: hit@k and MRR on both chunk files | printout |

The corpus is **one reference label per drug (20 labels)**. This gives every question a single
authoritative source, which keeps hand-labelling 200+ questions and measuring recall@k and
citation accuracy well defined.

## Why we chunk

A label is tens of thousands of characters long, but a question such as "what is the starting
dose of apixaban?" is answered by one or two short paragraphs. We cut the labels into small
pieces (chunks) once, up front, so that later:

1. **Retrieval** can search the chunks and return the few that match a question.
2. **Generation** is given only those chunks, answers from them, and cites their IDs.

Reasons not to search whole labels:

- **Matching:** a small, focused chunk matches a question far better than a huge document that
  covers dosing, side effects and storage all at once.
- **Cost and accuracy:** giving the LLM a whole label makes it slower, more expensive and more
  likely to miss the relevant passage.
- **Citations:** a citation like `apixaban:41a133ef:dosage_and_administration:0` points a
  clinician to a specific passage they can check. "It is somewhere in this label" is not checkable.

Why not look up "section 2.3" directly? The question never says "2.3", so the system has to work
out which part of the label matches, and that needs something to search over. Section numbers are
also not a stable address: 2.3 means something different in every drug's label, older labels have
no numbered headings at all, and some answers span several sections.

How we cut matters in a medicines assistant. If a chunk splits a dosing rule in half, retrieval
may return only half of it and the answer could be wrong or incomplete.

## Two chunking methods

We build both so we can measure which retrieves better. This is the "fixed-size vs section-aware
chunking" row in the planned ablation table.

**Section-aware chunks (main method)** follow the label's own structure.

- Split at numbered headings such as "2.1 Recommended Dose" and "2.2 Missed Dose".
- Small neighbouring subsections are merged up to 1,500 characters; longer ones are split at
  sentence boundaries.
- Every chunk starts with a header like `Apixaban | dosage_and_administration | 2.1 ...`, so the
  chunk's text itself says which drug and section it belongs to.
- The Highlights summary at the top of each section is dropped, because the full subsections
  repeat it.
- Example: apixaban dosing becomes 4 chunks, and each holds whole subsections, so a rule such as
  "2.5 mg twice daily if two of these three characteristics apply" stays in one piece.

**Fixed-size chunks (baseline)** ignore the structure.

- All sections are joined into one long text and cut into 1,500-character windows.
- Each window starts 1,300 characters after the previous one, so consecutive windows overlap by
  200 characters, which makes it less likely that a sentence is cut in half with no context.
- A cut can land in the middle of a dosing rule, or one chunk can contain the end of one section
  and the start of the next.

Current output: 901 section-aware chunks and 785 fixed-size chunks across the 20 drugs.

### Chunk metadata

Each chunk is one JSON line with: `chunk_id`, `drug`, `set_id`, `version`, `effective_time`,
`label_type` (NDA/ANDA), `section`, `subsection`, `text` and `char_count`.

### Known limitations

- A chunk's `subsection` label means "the chunk starts here". Small subsections are merged, so a
  chunk labelled "2.1" may also contain 2.2. This matters when judging citation accuracy.
- Headings are found with a text pattern, not a parser, so a stray number could be mistaken for a
  heading. Older-format labels (many generics) have no numbered headings and are split by size only.
- HTML tables (for example dosing tables) are skipped for now. They will matter for the dose
  calculator tool.

## Data notes

- openFDA labels have no dosage-form field, so "tablet" is matched on the `how_supplied` text.
- openFDA often stores a section's full text in one item and repeats each subsection as its own
  item. `get_section_text` removes these duplicates before chunking, so the same sentences are not
  indexed twice.
- openFDA parent sections also contain their child sections (for example `use_in_specific_populations`
  contains `pregnancy`, and `clinical_pharmacology` contains `pharmacokinetics`). Chunking both
  produced 134 identical chunks, which would fill the top-k results with the same text. The rule
  now is: **skip a child section only if its text is already inside its parent's text for the same
  label.** Dropping the parents instead would have lost 34-43% of their text (lactation, renal and
  hepatic impairment, pharmacodynamics), and dropping all children would have lost text in labels
  that have no parent section. Older-format labels such as furosemide and prednisone keep this
  content inside `precautions`, so their chunks carry that section name.
