#%%
"""Inspect the latest openFDA snapshot so we can see the real data structure.
 
Run from the project root with the virtual environment active:
    python 02_inspect_data.py
 
It only reads files in data/raw/. It changes nothing.
"""
#%%
import json
import re
from collections import Counter
from pathlib import Path

SECTIONS = [
    "indications_and_usage",
    "dosage_and_administration",
    "contraindications",
    "warnings",
    "warnings_and_cautions",
    "boxed_warning",
    "adverse_reactions",
    "drug_interactions",
    "use_in_specific_populations",
    "overdosage",
]


def find_latest_folder():
    """Folders are named by date, so the last one in sorted order is the newest."""
    raw_folder = Path("data/raw")
    if not raw_folder.exists():
        raise SystemExit("No data/raw folder found. Run the download script first.")
 
    folders = sorted(path for path in raw_folder.iterdir() if path.is_dir())
    if not folders:
        raise SystemExit("No snapshot found. Run the download script first.")
    return folders[-1]


def load_labels(file):
    """Return the list of labels saved in one drug file."""
    data = json.loads(file.read_text(encoding="utf-8"))
    return data.get("results", [])

def count_sections(labels):  # for the sections we selected  at the top, count then and get the labels
    counts={}
    for section in SECTIONS:
        counts[section]=0
        for label in labels:
            if label.get(section):
                counts[section] += 1
    return counts


def count_label_types(labels):
    """Count original (NDA) and generic (ANDA) labels from the application number. each drug needs one reference label, 
    #preferring the originator’s (NDA) label, because generics copy it."""
    nda = 0
    anda = 0
    for label in labels:
        numbers = label.get("openfda", {}).get("application_number", [])
        if numbers and numbers[0].startswith("ANDA"):
            anda += 1
        elif numbers and numbers[0].startswith("NDA"):
            nda += 1
    return nda, anda


def find_label_with_dosage(labels):
    """Return the first label that has a dosage_and_administration section."""
    for label in labels:
        if label.get("dosage_and_administration"):
            return label
    return None



def print_drug_summary(name, labels):
    counts = count_sections(labels)
    nda, anda = count_label_types(labels)
 
    parts = []
    for section, number in counts.items():
        parts.append(f"{section}={number}")
 
    print(f"{name}: {len(labels)} labels saved")
    print("  sections:", ", ".join(parts))
    print(f"  original (NDA): {nda}, generic (ANDA): {anda}\n")




def print_example_label(label):
    """Print the identifiers and the start of the dosage section of one label."""
    openfda = label.get("openfda", {})
    dosage = label.get("dosage_and_administration", [])
 
    print("-" * 60)
    print("ONE LABEL IN DETAIL")
    print("top-level fields:", sorted(label.keys()))
    print("openfda fields:", sorted(openfda.keys()))
    print("set_id:", label.get("set_id"))
    print("version:", label.get("version"))
    print("effective_time:", label.get("effective_time"))
    print("generic name:", openfda.get("generic_name"))
    print("brand name:", openfda.get("brand_name"))
    print("manufacturer:", openfda.get("manufacturer_name"))
    print("\nFirst 600 characters of dosage_and_administration:\n")
    print(" ".join(dosage)[:600])




def main():
    folder = find_latest_folder()
    print("Snapshot:", folder, "\n")
 
    example_label = None
 
    for file in sorted(folder.glob("*.json")):
        if file.name == "manifest.json":  # the download record, not drug data
            continue
 
        labels = load_labels(file)
        print_drug_summary(file.stem, labels)
 
        if example_label is None:
            example_label = find_label_with_dosage(labels)
 
    if example_label is not None:
        print_example_label(example_label)
 


if __name__ == "__main__":
    main()