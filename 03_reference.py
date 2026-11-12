#%%
"""Step 3: pick one reference label per drug from the latest snapshot.
 
Rules:
1. Single-ingredient labels only (no kits or combination products).
2. The label must have indications and dosage sections.
3. Prefer original (NDA) labels, then generic (ANDA), then anything else.
4. Within that group, take the newest label.
 
The chosen labels are saved in data/reference/ for you to review.
"""
import json
from pathlib import Path

REQUIRED_SECTIONS = ["indications_and_usage", "dosage_and_administration"]



def find_latest_folder():
    raw_folder = Path("data/raw")
    if not raw_folder.exists():
        raise SystemExit("No data/raw folder found. Run the download script first.")
 
    folders = sorted(path for path in raw_folder.iterdir() if path.is_dir())
    if not folders:
        raise SystemExit("No snapshot found. Run the download script first.")
    return folders[-1]


def load_labels(file):
    data = json.loads(file.read_text(encoding="utf-8"))
    return data.get("results", [])


def is_single_ingredient(label, drug):
    """True if the label has one generic name and it matches the drug."""
    names = label.get("openfda", {}).get("generic_name", [])
    if len(names) != 1:
        return False
    name = names[0].lower()
    return drug in name and " and " not in name

def has_required_sections(label):
    for section in REQUIRED_SECTIONS:
        if not label.get(section):
            return False
    return True



# pick nds lable if not generic and not then newest one
def label_type(label):
    """Return NDA (original), ANDA (generic) or other."""
    numbers = label.get("openfda", {}).get("application_number", [])
    if numbers and numbers[0].startswith("ANDA"):
        return "ANDA"
    if numbers and numbers[0].startswith("NDA"):
        return "NDA"
    return "other"


def effective_time(label):
    return label.get("effective_time", "")


def pick_reference(drug, labels):
    """Return the best label for this drug, or None if nothing suitable."""
    candidates = []
    for label in labels:
        if is_single_ingredient(label, drug) and has_required_sections(label):
            candidates.append(label)
 
    for wanted_type in ["NDA", "ANDA", "other"]:
        group = [label for label in candidates if label_type(label) == wanted_type]
        if group:
            return max(group, key=effective_time)  # newest first
    return None




def main():
    folder = find_latest_folder()
    output_folder = Path("data/reference")
    output_folder.mkdir(parents=True, exist_ok=True)
 
    print("Snapshot:", folder, "\n")
 
    for file in sorted(folder.glob("*.json")):
        if file.name == "manifest.json":
            continue
 
        drug = file.stem
        label = pick_reference(drug, load_labels(file))
 
        if label is None:
            print(f"{drug}: NO SUITABLE LABEL, check this drug by hand")
            continue
 
        (output_folder / f"{drug}.json").write_text(json.dumps(label, indent=2), encoding="utf-8")
 
        openfda = label.get("openfda", {})
        print(f"{drug}: {label_type(label)} | brand {openfda.get('brand_name')} | "
              f"{openfda.get('manufacturer_name')} | route {openfda.get('route')} | "
              f"{label.get('effective_time')}")
 
    print("\nChosen labels saved in", output_folder)
 
 
if __name__ == "__main__":
    main()