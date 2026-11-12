# Decision log

Every design decision in this project, why it was made, what else was possible, and what to
change if you adapt it to another system. Update it whenever a decision is made or reversed.

Format: **Decision** / **Why** / **Trade-off or known gap** / **To adapt**.

---

## Data

### D1. Tablets only, single-ingredient only
- **Decision:** `01_download_data.py` keeps only labels whose `how_supplied` text mentions tablets,
  with exactly one `substance_name` and no " and " in the generic name.
- **Why:** The project concept changed to single-drug tablets. Combination products would mix two
  drugs' doses and warnings in one label, which makes question labelling and the later weight-based
  dose calculator ambiguous.
- **Known gap:** openFDA has no dosage-form field, so "tablet" is a text match on `how_supplied`. A
  combination label with one `substance_name` and no " and " in its generic name would get through.
  Only atorvastatin and methotrexate were spot-checked.
- **To adapt:** For other forms (injections, inhalers) change the `how_supplied` match. For
  combinations, drop `is_single_ingredient` but then labels and questions need to be ingredient-aware.
  For another source (DailyMed SPL XML, EMA in the EU) the section names and nesting differ, so
  `get_section_text` and `CHUNK_SECTIONS` would need rewriting.

### D2. Page through results until 100 single-ingredient labels are kept
- **Decision:** `fetch_drug` requests pages and filters as it goes, instead of one request of 100.
- **Why:** With one request, combination labels used up the cap (amlodipine: 81 of 210 were combinations).
- **To adapt:** The manifest records `total`, `saved` and `skipped_combination` per drug. Keep that
  habit for any new source so you can explain what was dropped.

### D3. Corpus = one reference label per drug (20 labels)
- **Decision:** `03_reference.py` picks one label per drug (prefers original NDA labels, then newest).
- **Why:** One authoritative source per drug makes hand-labelling 200+ questions and measuring
  recall@k and citation accuracy well defined.
- **Trade-off:** A small, clean corpus makes retrieval easier than real life. There are no conflicting
  or duplicate sources, so results will look better than they would on messy data.
- **Known gap:** "Newest NDA" sometimes picks unrepresentative labels (gabapentin gives Gralise,
  lamotrigine gives Lamictal XR, metoprolol gives Toprol XL, sertraline gives Finjozy, and some are
  repackager labels). Revisit before trusting the corpus.
- **To adapt:** A bigger corpus needs dedupe and versioning. `set_id`, `version` and `effective_time`
  are already stored on every chunk for that.

---

## Chunking (`04_chunk_data.py`)

### D4. Two chunkers: section-aware (main) and fixed-size (baseline)
- **Decision:** Build both from the same text.
- **Why:** If section-aware does not beat fixed-size on recall@k and MRR, the extra effort is not
  justified. It is also a row in the planned ablation table.
- **To adapt:** If a new system has no section structure, fixed-size is the only option.

### D5. Chunk size 1,500 characters, fixed-size overlap 200
- **Decision:** `MAX_CHARS = 1500`, `FIXED_OVERLAP = 200`.
- **Why:** Reasonable defaults: big enough to hold a whole dosing rule, small enough to match a
  question. **They have not been tuned.**
- **To adapt:** Embedding models limit input in tokens, not characters (about 4 characters per token
  in English). Check the model's limit and tune size against recall@k. Treat these as parameters to
  test.

### D6. Chunk text starts with a header ("Apixaban | dosage_and_administration | 2.1 ...")
- **Why:** A chunk is searched on its own text. The header puts the drug and section into that text,
  so a search for "apixaban dosing" can match even if the passage never repeats the drug name.
- **To adapt:** Dense (embedding) retrieval often benefits from this too. Test with and without.

### D7. Remove duplicate items inside a section (`get_section_text`)
- **Decision:** Drop any item whose text is contained in another item of the same section.
- **Why:** openFDA often stores the full section in one item and repeats each subsection as its own
  item. Joining everything indexed the same sentences twice.
- **To adapt:** This is a quirk of openFDA's JSON. Other sources will have their own duplication.

### D8. Drop the Highlights summary before the first numbered heading
- **Decision:** If the text before the first heading contains cross-references like "(2.1)", drop it.
- **Why:** It is a short summary of the subsections that follow, so it only adds duplicates.
- **Known gap:** It is a heuristic. A Highlights fragment may survive (see the open items).

### D9. Skip a child section only if its text is already inside its parent's text
- **Decision:** `PARENTS_OF` plus `is_inside_parent` in `04_chunk_data.py`.
- **Why:** openFDA parent sections contain their children (`use_in_specific_populations` contains
  `pregnancy`, and so on). Chunking both made 134 identical chunks, which fill the top-k with the
  same text and inflate recall@k.
- **Alternatives rejected (with numbers):** Dropping the parents would lose 43% of
  `use_in_specific_populations` (lactation, renal, hepatic) and 34% of `clinical_pharmacology`.
  Dropping all children would lose text for labels with no parent section.
- **Result:** 1,100 chunks became 901 (section-aware), 949 became 785 (fixed-size), with 0 repeats.
  Furosemide and prednisone keep this text inside `precautions`.
- **To adapt:** `PARENTS_OF` is hand-written for openFDA's section names. A new source needs its own
  map, or a generic check that finds chunks whose text is inside another chunk.

### D10. The same section list feeds both chunkers
- **Why:** So the ablation compares chunking methods on identical text, not different text.

---

## Evaluation

### D11. Label questions with an evidence phrase, not a chunk ID
- **Decision:** Each question has a short phrase copied from the label that contains the answer. A
  script marks every chunk containing the phrase as correct.
- **Why:** Chunk IDs change whenever chunking changes (they did today). Phrase labels survive
  re-chunking and work for both chunk files.
- **Rule for writing questions:** Phrase them as a clinician would, not in the label's own words,
  or BM25 will look better than it is.
- **To adapt:** For a corpus that changes often, store the evidence phrase and the source ID, and
  re-run the matching step.
- **Retrieval score vs answer score:** Retrieval metrics ask "did search find the passage?". They
  do not say whether the final answer is right, which is measured later (faithfulness, correctness).

### D15. How retrieval is scored (`07_eval_retrieval.py`)
- **Decision:** A chunk is correct for a question if it belongs to the question's drug and its
  normalised text (lowercase, whitespace collapsed) contains the evidence phrase. For each question we
  take the rank of the first correct chunk in the top 10. **hit@k** = share of questions with a
  correct chunk in the top k (k = 1, 3, 5, 10). **MRR** = average of 1/rank (0 if not in the top 10).
- **Why:** hit@k answers "does the right passage reach the generator?". MRR rewards ranking it
  higher. Several chunks can be correct (the phrase can appear in more than one), and any counts.
- **Search is not told the drug.** The question text alone goes in, as it will in the real
  assistant. The drug column is only used for labelling.
- **A question whose phrase is in no chunk counts as a miss** and prints a warning. In the
  section-aware file that usually means a typo in the phrase. In the fixed-size file it can mean the
  chunker split the phrase across two chunks, which is a real weakness of that method.
- **Known gap:** the metric credits any chunk with the phrase, even if the surrounding chunk would not
  let a model answer fully. Answer quality is measured later, not here.
- **First run (4 starter questions, not a conclusion):** section-aware hit@5 0.50, MRR 0.21;
  fixed-size hit@5 0.25, MRR 0.17. Four questions is far too few to compare chunkers. Numbers become
  meaningful at 200+.
- **To adapt:** Any retriever that returns chunk IDs can be dropped into `evaluate` unchanged. For
  a source without stable text (scanned PDFs), use human-judged relevance instead of phrase matching.

---

## Retrieval

### D12. Build BM25 ourselves first
- **Decision:** Write BM25 in about 20 lines rather than using `rank_bm25`.
- **Why:** The aim is understanding, we control tokenising (doses like `2.5 mg`, `CYP3A4`), and there
  is one fewer dependency.
- **What it costs:** Library code is tested and faster. At ~900 chunks, speed does not matter.
- **Check:** Once ours works, compare its scores with `rank_bm25` as a test.
- **IDF version:** `idf = ln(1 + (N - df + 0.5) / (df + 0.5))`, the Lucene form used by
  Elasticsearch. It is never negative. As far as I know `rank_bm25` uses a different form (it can go
  negative for very common words and then floors them), so match the versions before comparing
  scores, or the numbers will not agree.
  Worked example from our data (N = 901 chunks): `mg` (in 281 chunks) 1.16, `warfarin` (67) 2.59,
  `apixaban` (45) 2.99.
- **To adapt:** Engines like Elasticsearch and Qdrant provide BM25 and let you control tokenising
  (custom analyzer in Elasticsearch; sparse vectors you compute yourself in Qdrant, or its text
  index; check current docs). The scoring loop would be replaced, but the tokeniser can be reused.
  **The same tokenising rules must apply to chunks and questions**, or terms will not match.

### D13. Tokeniser: lowercase, keep decimals together, small stopword list
- **Decision:** `re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", text.lower())`, then drop stopwords.
- **Why decimals stay whole:** Doses are the core content. `2.5` must stay one token, otherwise it
  becomes `2` and `5` and matches any chunk that mentions a 2 and a 5 anywhere.
- **Why a short, hand-made stopword list:** BM25 already gives common words low weight, so stopwords
  help less than expected. Standard lists include "not", "no" and "without", which change meaning in
  medicine ("not recommended", "no dose adjustment"), so we do not drop those. The list is in
  `06_bm25_search.py`.
- **Bug found while writing it:** a stray space in the regex made every token carry a trailing space,
  so stopwords never matched and `2.5` lost its `2`. Lesson: print the tokens and look at them.
- **Known gaps:** `CYP3A4` stays one token, but `P-gp` becomes `p` and `gp`; `patient's` becomes
  `patient` and `s`. Check whether this hurts on real questions.
- **To adapt:** The same function must tokenise chunks and queries. Another language or a system
  with its own analyzer (Elasticsearch) needs the equivalent rules configured there.

### D14. Shape of `06_bm25_search.py`: build the index once, then search
- **Decision:** Three steps. `build_index(chunks)` tokenises every chunk, counts words per chunk,
  and computes each word's IDF and the average chunk length. `score_chunk` scores one chunk for a
  question. `search(index, query, k)` scores all chunks and returns the top k. The index is a plain
  dict, so later scripts can `import` the functions without any class.
- **Why:** Counting is the slow part and does not depend on the question, so it is done once. Each
  question then only does lookups. The same `build_index` / `search` pair is reused by the retrieval
  eval (07), so the eval runs exactly the code the assistant will run.
- **Parameters:** `K1 = 1.5` and `B = 0.75` are the usual defaults. They are **not tuned** for
  drug labels. Once the eval exists, try K1 in 1.2-2.0 and B in 0.5-0.9 and compare recall@k.
- **Search scans every chunk.** Fine for 901 chunks. A real engine (Elasticsearch, Qdrant) keeps an
  inverted index (word -> chunks containing it) so it only touches chunks that share a query word.
- **First observations (no eval yet, so these are impressions, not measurements):** BM25 matches
  words, not meaning. There is no stemming, so "dose" and "dosage" are different tokens. For
  "starting dose of warfarin" the top 3 were drug_interactions and warnings chunks that repeat
  "warfarin", not the dosing chunk. Whether this is a real weakness is what the eval is for.
- **To adapt:** To use Elasticsearch or Qdrant, keep `tokenize` and the chunk files and replace
  `build_index` / `search`. To tune for another domain, change `STOPWORDS`, `K1` and `B`, and
  measure on that domain's questions.

---

## Open items to revisit

- Dosing **tables** are skipped. They matter for the weight-based dose calculator.
- `tramadol:...:contraindications:1` (130 chars) ends in `( 4 )`, which looks like a Highlights
  fragment that survived D8. Not yet investigated.
- Reference-label picks (D3) need review.
- Chunk size and overlap (D5) are untuned.
- Only 2 drugs were spot-checked for combination products (D1).
- Highlights bullets survive D8 in some chunks: the amlodipine dosage chunk 0 contains
  "( 2.1 )" bullets and the warfarin contraindications chunk 0 ends with "( 4 , 5.7 , 8.1 )". Likely
  the cross-reference pattern expects "(2.1)" with no inner spaces. Probably also explains the tramadol
  "( 4 )" chunk. Check `CROSS_REF` in `04_chunk_data.py`.
- `06_bm25_search.py` cannot be imported with a plain `import` (file name starts with a digit), so
  scripts use `importlib`. Consider renaming to `bm25.py`.
