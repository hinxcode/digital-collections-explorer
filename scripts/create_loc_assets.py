"""
This script generates the essential assets (embedding index and metadata) required for Digital Collections Explorer
by converting `beto_idx.pt` provided by Mahowald and Lee (https://zenodo.org/records/11538437) into `item_ids.pt` and `metadata.json`

The output assets can be placed directly in the `data/embeddings` folder, allowing the FastAPI server to access them
in the same way as we do in our public demo at https://digital-collections-explorer.com/
"""

import base64
import json

import pandas as pd
import torch

ORIGINAL_INDEX_PATH = "input/beto_idx.pt"
CSV_PATH = "input/merged_files.csv"
FINAL_METADATA_PATH = "output/metadata.json"
FINAL_INDEX_PATH = "output/item_ids.pt"


def generate_assets():
    # --- 1. Load the original beto_idx.pt file ---
    original_idx = torch.load(ORIGINAL_INDEX_PATH)
    total_items = len(original_idx)
    print(f"Found {total_items} entries in the original index.")

    # --- 2. Build a lookup table from merged_files.csv ---
    df = pd.read_csv(CSV_PATH)
    df.dropna(subset=["p1_item_id", "file_url"], inplace=True)
    df["iiif_id"] = df["file_url"].apply(
        lambda url: url.split("/")[5] if isinstance(url, str) else None
    )
    df.dropna(subset=["iiif_id"], inplace=True)
    iiif_to_p1_lookup = pd.Series(df.p1_item_id.values, index=df.iiif_id).to_dict()

    # --- 3. Generate new index and metadata ---
    final_metadata = {}
    final_beto_idx = []

    for image_url in original_idx:
        # a. Extract iiif_id
        try:
            iiif_id = image_url.split("/")[5]
        except IndexError:
            b64_key = base64.urlsafe_b64encode(
                f"ERROR_PARSING_{len(final_beto_idx)}".encode("utf-8")
            ).decode("utf-8")
            final_beto_idx.append(b64_key)
            final_metadata[b64_key] = {
                "error": f"Could not parse iiif_id from URL: {image_url}"
            }
            continue

        # b. Generate Base64 key
        b64_key = base64.urlsafe_b64encode(iiif_id.encode("utf-8")).decode("utf-8")

        # c. Append key to the new index
        final_beto_idx.append(b64_key)

        # d. Find p1_item_id
        p1_item_id = iiif_to_p1_lookup.get(iiif_id, "p1_item_id_not_found")

        # e. Assemble the new metadata object
        url_base = f"https://tile.loc.gov/image-services/iiif/{iiif_id}"
        paths = {
            "original": f"{url_base}/full/pct:100/0/default.jpg",
            "processed": f"{url_base}/full/2000,/0/default.jpg",
            "thumbnail": f"{url_base}/full/400,/0/default.jpg",
        }
        final_metadata[b64_key] = {
            "type": "image",
            "iiif_id": iiif_id,
            "url": p1_item_id,
            "paths": paths,
        }

    # --- 4. Final Save and Validation ---
    with open(FINAL_METADATA_PATH, "w") as f:
        json.dump(final_metadata, f, indent=4)
    print(
        f"Successfully saved {FINAL_METADATA_PATH} with {len(final_metadata)} entries."
    )

    torch.save(final_beto_idx, FINAL_INDEX_PATH)
    print(f"Successfully saved {FINAL_INDEX_PATH} with {len(final_beto_idx)} entries.")

    assert len(original_idx) == len(
        final_beto_idx
    ), "CRITICAL: Final index length does not match original!"


if __name__ == "__main__":
    generate_assets()
