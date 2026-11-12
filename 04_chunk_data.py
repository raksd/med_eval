#%%
"""Step 4: split the reference labels into chunks for retrieval.

Run from the project root with the virtual environment active:
    python 04_chunk_data.py

Reads:  data/reference/<drug>.json
Writes: data/chunks/section_aware.jsonl   split on the label's own structure (main method)
        data/chunks/fixed_size.jsonl      baseline for the ablation: fixed windows, ignores structure
"""
import json
import re
from pathlib import Path

REFERENCE_FOLDER = Path("data/reference")
OUTPUT_FOLDER = Path("data/chunks")

# Clinician-relevant sections. Older-format labels use "warnings"/"precautions", newer ones
# use "warnings_and_cautions"; a label simply has whichever exist. Tables (*_table) are skipped.
CHUNK_SECTIONS = [
    "boxed_warning",
    "indications_and_usage",
    "dosage_and_administration",
    "dosage_forms_and_strengths",
    "contraindications",
    "warnings_and_cautions",
    "warnings",
    "precautions",
    "adverse_reactions",
    "drug_interactions",
    "use_in_specific_populations",
    "pregnancy",
    "pediatric_use",
    "geriatric_use",
    "overdosage",
    "clinical_pharmacology",
    "mechanism_of_action",
    "pharmacokinetics",
    "how_supplied",
]

# openFDA's parent sections already contain their child sections (for example
# use_in_specific_populations contains pregnancy). Each child maps to the parents that may hold it.
PARENTS_OF = {
    "pregnancy": ["use_in_specific_populations", "precautions"],
    "pediatric_use": ["use_in_specific_populations", "precautions"],
    "geriatric_use": ["use_in_specific_populations", "precautions"],
    "drug_interactions": ["precautions"],
    "mechanism_of_action": ["clinical_pharmacology"],
    "pharmacokinetics": ["clinical_pharmacology"],
}

MAX_CHARS = 1500       # section-aware: max size of a chunk body
FIXED_CHARS = 1500     # fixed-size: window length
FIXED_OVERLAP = 200    # fixed-size: how much each window repeats of the previous one

# A subsection heading is a number like "2.1" or "5.3.2" at a word start, followed by a capital letter.
HEADING = re.compile(r"(?<!\S)(\d{1,2}(?:\.\d{1,2})+) (?=[A-Z])")
# Highlights text is full of cross-references like "(2.1)"; real prose is not.
CROSS_REF = re.compile(r"\(\d{1,2}(?:\.\d{1,2})*")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


#%%
def get_section_text(label: dict, section: str) -> str:
    """Return the section as one string with duplicate items removed, or "" if missing.

    openFDA often stores the full section text in one item AND repeats each subsection as
    its own item, so joining everything would index the same sentences twice.
    """
    items = label.get(section) or []
    items = [i.strip() for i in items if i.strip()]   # clean + drop empties
    items = list(dict.fromkeys(items))                # remove exact repeats

    keep = []
    for i, item in enumerate(items):
        is_duplicate = False
        for j, other in enumerate(items):
            if j != i and item in other:   # a different item contains this one
                is_duplicate = True
        if not is_duplicate:
            keep.append(item)

    return " ".join(keep)


#%%
def is_inside_parent(label: dict, section: str) -> bool:
    """True if this child section's text already appears inside one of its parent sections."""
    child = " ".join(get_section_text(label, section).split())
    if not child:
        return False
    for parent in PARENTS_OF.get(section, []):
        if child in " ".join(get_section_text(label, parent).split()):
            return True
    return False


def usable_sections(label: dict) -> list[tuple[str, str]]:
    """(section, text) for every section worth chunking, skipping children that a parent already holds."""
    result = []
    for section in CHUNK_SECTIONS:
        text = get_section_text(label, section)
        if text and not is_inside_parent(label, section):
            result.append((section, text))
    return result


#%%
def heading_label(body: str) -> str:
    """Short readable name for a subsection: its number plus the first few words."""
    return " ".join(body.split()[:8])


def split_subsections(text: str) -> list[tuple[str, str]]:
    """Split one section's text at numbered headings. Returns (subsection, body) pairs."""
    matches = list(HEADING.finditer(text))
    if not matches:
        return [("", text)]   # older-format label: no numbered headings, keep as one piece

    pieces = []
    # Text before the first heading is the section title plus the Highlights summary.
    # Drop it when it is cross-reference bullets; it repeats what the subsections say.
    intro = text[: matches[0].start()].strip()
    if intro and not CROSS_REF.search(intro):
        pieces.append(("", intro))

    for k, match in enumerate(matches):
        end = matches[k + 1].start() if k + 1 < len(matches) else len(text)
        body = text[match.start():end].strip()
        pieces.append((heading_label(body), body))
    return pieces


def split_long(text: str) -> list[str]:
    """Cut text longer than MAX_CHARS into parts, preferring sentence boundaries."""
    if len(text) <= MAX_CHARS:
        return [text]

    parts = []
    current = ""
    for sentence in SENTENCE_END.split(text):
        while len(sentence) > MAX_CHARS:   # one huge sentence: hard cut
            if current:
                parts.append(current)
                current = ""
            parts.append(sentence[:MAX_CHARS])
            sentence = sentence[MAX_CHARS:]
        if current and len(current) + 1 + len(sentence) > MAX_CHARS:
            parts.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        parts.append(current)
    return parts


def pack_pieces(pieces: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Merge neighbouring small pieces up to MAX_CHARS; split big ones. Returns (subsection, text)."""
    chunks = []
    current_heading, current_text = "", ""
    for heading, body in pieces:
        for part in split_long(body):
            if current_text and len(current_text) + 1 + len(part) <= MAX_CHARS:
                current_text += " " + part
            else:
                if current_text:
                    chunks.append((current_heading, current_text))
                current_heading, current_text = heading, part
    if current_text:
        chunks.append((current_heading, current_text))
    return chunks


#%%
def label_type(label: dict) -> str:
    """Return NDA (original), ANDA (generic) or other."""
    numbers = label.get("openfda", {}).get("application_number", [])
    if numbers and numbers[0].startswith("ANDA"):
        return "ANDA"
    if numbers and numbers[0].startswith("NDA"):
        return "NDA"
    return "other"


def make_record(label: dict, drug: str, chunk_id: str, section: str, subsection: str, text: str) -> dict:
    """One chunk plus the metadata we need later for filtering and citations."""
    return {
        "chunk_id": chunk_id,
        "drug": drug,
        "set_id": label.get("set_id"),
        "version": label.get("version"),
        "effective_time": label.get("effective_time"),
        "label_type": label_type(label),
        "section": section,
        "subsection": subsection,
        "text": text,
        "char_count": len(text),
    }

#Section-aware chunks follow the label's own structure
#"2.1 Recommended Dose" and "2.2 Missed Dose"
def chunk_section_aware(label: dict, drug: str) -> list[dict]:
    set_id = (label.get("set_id") or "")[:8]
    records = []
    for section, text in usable_sections(label):
        for n, (subsection, body) in enumerate(pack_pieces(split_subsections(text))):
            # A short header on every chunk tells the retriever (and the LLM) where it came from.
            header = " | ".join(part for part in [drug.title(), section, subsection] if part)
            records.append(make_record(label, drug, f"{drug}:{set_id}:{section}:{n}",
                                       section, subsection, f"{header}\n{body}"))
    return records

#join all the sections into one long text and cut it into windows of 1,500 characters
def chunk_fixed_size(label: dict, drug: str) -> list[dict]:
    """Baseline: same text as section-aware, but cut into windows with no regard to structure."""
    set_id = (label.get("set_id") or "")[:8]

    full_text = ""
    section_starts = []   # (offset where the section begins, section name)
    for section, text in usable_sections(label):
        section_starts.append((len(full_text), section))
        full_text += text + "\n\n"

    records = []
    step = FIXED_CHARS - FIXED_OVERLAP
    for n, start in enumerate(range(0, len(full_text), step)):
        if start > 0 and len(full_text) - start <= FIXED_OVERLAP:
            break   # the rest was already covered by the previous window's overlap
        window = full_text[start:start + FIXED_CHARS].strip()
        if not window:
            continue
        section = [name for offset, name in section_starts if offset <= start][-1]  # section where it starts
        records.append(make_record(label, drug, f"{drug}:{set_id}:fixed:{n}", section, "", window))
    return records


#%%
def write_jsonl(records: list[dict], path: Path) -> None:
    lines = [json.dumps(record, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    files = sorted(REFERENCE_FOLDER.glob("*.json"))
    if not files:
        raise SystemExit("No files in data/reference. Run 03_reference.py first.")

    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    section_aware, fixed_size = [], []

    for file in files:
        drug = file.stem
        label = json.loads(file.read_text(encoding="utf-8"))
        a = chunk_section_aware(label, drug)
        f = chunk_fixed_size(label, drug)
        section_aware += a
        fixed_size += f
        print(f"{drug}: {len(a)} section-aware chunks, {len(f)} fixed-size chunks")

    write_jsonl(section_aware, OUTPUT_FOLDER / "section_aware.jsonl")
    write_jsonl(fixed_size, OUTPUT_FOLDER / "fixed_size.jsonl")
    print(f"\nTotal: {len(section_aware)} section-aware, {len(fixed_size)} fixed-size. Saved in {OUTPUT_FOLDER}")


if __name__ == "__main__":
    main()
