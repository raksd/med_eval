#%%
"""Download a pilot snapshot of openFDA prescription drug labels (single-ingredient tablets only).
 
Run from the project root with the virtual environment active:
    python download_pilot.py
 
Output:
    data/raw/<YYYY-MM-DD>/<drug>.json   raw API response, one file per drug
    data/raw/<YYYY-MM-DD>/manifest.json what was queried, when, and how many labels
"""

import json
import os
import time
import requests
from datetime import date, datetime, timezone
from pathlib import Path

API_URL = "https://api.fda.gov/drug/label.json"
MAX_LABELS_PER_DRUG = 100  # pilot cap on single-ingredient labels kept per drug
PAGE_SIZE = 100
PAUSE_SECONDS = 0.5

DRUGS = [
    "warfarin",
    "apixaban",
    "clopidogrel",
    "atorvastatin",
    "simvastatin",
    "gabapentin",
    "prednisone",
    "methotrexate",
    "metformin",
    "sertraline",
    "amlodipine",
    "metoprolol",
    "lisinopril",
    "furosemide",
    "levothyroxine",
    "lamotrigine",
    "levetiracetam",
    "ciprofloxacin",
    "tramadol",
    "hydroxychloroquine",
]

#returns FDa search string for a given drug, limited to tablet products
def build_query(drug: str) -> str:
    # openFDA labels have no dosage-form field, so match the how_supplied text.
    # Search does no stemming, so both "tablet" and "tablets" must be listed.
    return (
        f'openfda.generic_name:"{drug}" '
        'AND openfda.product_type:"HUMAN PRESCRIPTION DRUG" '
        'AND how_supplied:(tablet tablets)'
    )


def is_single_ingredient(label: dict) -> bool:
    """One active substance and no 'X and Y' generic name (combination products have both)."""
    openfda = label.get("openfda", {})
    substances = openfda.get("substance_name", [])
    generic_names = openfda.get("generic_name", [])
    if len(substances) != 1:
        return False
    return not any(" and " in name.lower() for name in generic_names)


def fetch_page(drug: str, api_key: str|None, skip: int) -> dict|None:
    #Parametrs become the part of url after the '?' as query string
    params={"search": build_query(drug), "limit": PAGE_SIZE, "skip": skip}
    if api_key:    #only add if the key is available
        params["api_key"] = api_key

    response = requests.get(API_URL, params=params, timeout=60) # give up after 60 seconds
    if response.status_code == 404:  # no matches (or paged past the last result)
        return None
    response.raise_for_status()  # anyother error - stops scipts with clear msg
    return response.json()        # convert reply text into response dictionary


# get single-ingredient labels for the drug from the openFDA API, up to MAX_LABELS_PER_DRUG
def fetch_drug(drug: str, api_key: str|None) -> dict|None:
    kept = []
    skipped_combination = 0
    total = None
    skip = 0

    while len(kept) < MAX_LABELS_PER_DRUG:
        page = fetch_page(drug, api_key, skip)
        if page is None:
            break
        total = page.get("meta", {}).get("results", {}).get("total")
        results = page.get("results", [])

        for label in results:
            if is_single_ingredient(label):
                kept.append(label)
            else:
                skipped_combination += 1

        skip += PAGE_SIZE
        if not results or (total is not None and skip >= total):
            break
        time.sleep(PAUSE_SECONDS)

    if total is None:  # first request found nothing
        print(f"Drug {drug} not found (404).")
        return None

    kept = kept[:MAX_LABELS_PER_DRUG]
    return {"meta": {"results": {"total": total}}, "skipped_combination": skipped_combination, "results": kept}

# main function 


def main() -> None:
    api_key = os.environ.get("OPENFDA_API_KEY")
    snapshot_dir=Path("data/raw") / date.today().isoformat() # folder with todays date to get data
    snapshot_dir.mkdir(parents=True, exist_ok=True)  # create the directory if it doesn't exist


    # build a dictionary to save values as key value pair
    manifest = {
        "source": API_URL,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),  # exact time of download
        "max_labels_per_drug": MAX_LABELS_PER_DRUG,
        "filters": "tablets (how_supplied text match), single-ingredient only",
        "used_api_key": bool(api_key),     # True/False only; we never store the key itself
        "drugs": [],                       # filled in below
    }


    #loop over the for each data 
    for drug in DRUGS:
        data = fetch_drug(drug, api_key)

        # if nothing matches 
        if data is None:
            print(f"{drug} No match found, Check the spelling")
            manifest["drugs"].append({"drug": drug, "query": build_query(drug), "total":0, "saved":0})
            time.sleep(PAUSE_SECONDS)
            continue  # skip to the next drug if no data is found


        # Case2 if we get drug name
        results= data.get("results", [])
        total=data.get("meta", {}).get("results", {}).get("total")  # get.() Handles missing keys if wither result or total is missing



        #save raw date for each drug as json
        file_path = snapshot_dir / f"{drug.replace(' ', '_')}.json"
        file_path.write_text(json.dumps(data), encoding="utf-8")

        skipped = data.get("skipped_combination", 0)
        print(f"{drug}: {len(results)} labels saved ({skipped} combination labels skipped)")


        manifest["drugs"].append({"drug": drug, "query": build_query(drug), "total": total, "saved": len(results),
                                  "skipped_combination": skipped,
                                  "file":file_path.name,
                                  "set_ids": [r.get("set_id") for r in results]})

        time.sleep(PAUSE_SECONDS)

    (snapshot_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    print(f"Data download complete. Manifest saved to {snapshot_dir / 'manifest.json'}")


    #  Json drug files and manifest is the inventory/index  of data

    # End of main function
if __name__ == "__main__":
    main()


