#!/usr/bin/env python3
"""Build the bundled real-CV reference JSON from the cited Zenodo dataset."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import urllib.request
import zipfile
from pathlib import Path

RECORD_URL = "https://zenodo.org/records/15730784"
PROCESSED_URL = (
    "https://zenodo.org/api/records/15730784/files/1_processed%20_data.zip/content"
)
RAW_URL = "https://zenodo.org/api/records/15730784/files/0_raw_data.zip/content"
PROCESSED_SHA256 = "cab1057d203839f1edcb00ad48625212097ff0d673801145eb0c92816899fb62"
RAW_SHA256 = "0ad46235fa55efc2bd52e49caa0d2e864c943ac9306becfc6bd0e4da1ac4667d"
PROCESSED_FILE_SHA256 = "8edf5a999a689b58cd1c410ea2d250bce3eeedad9bbfe0efbaa7972a453129df"
PROCESSED_MEMBER = "4_CV_additives.txt"
OUTPUT = Path(__file__).resolve().parents[1] / "demo" / "data" / "all_iron_rfb_cv.json"

SAMPLES = (
    {
        "id": "fecl2_nh4cl",
        "name": "FeCl₂ + NH₄Cl",
        "composition": "0.8 M FeCl₂ + 3 M NH₄Cl",
        "ph": 3.5,
        "columns": ("c", "d"),
        "raw_member": "0_CV/7_CV_FeCl2+NH4Cl.mpt",
        "color": "#087b61",
    },
    {
        "id": "fecl2_nh4cl_glycine",
        "name": "+ glycine",
        "composition": "0.8 M FeCl₂ + 3 M NH₄Cl + 1 M glycine",
        "ph": 3.5,
        "columns": ("e", "f"),
        "raw_member": "0_CV/8_CV_FeCl2+NH4Cl+Glycine.mpt",
        "color": "#315e86",
    },
    {
        "id": "fecl2_nh4cl_glycine_lactic",
        "name": "+ glycine + lactic acid",
        "composition": "0.8 M FeCl₂ + 3 M NH₄Cl + 1 M glycine + 1 M lactic acid",
        "ph": 3.5,
        "columns": ("g", "h"),
        "raw_member": "0_CV/12_CV_FeCl2+NH4Cl+Glycine+Lactic_acid.mpt",
        "color": "#a35d1d",
    },
)


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "SciencesLoop-data-builder/1"})
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - pinned public data
        return response.read()


def verify(payload: bytes, expected: str, label: str) -> None:
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise ValueError(f"{label} SHA-256 mismatch: expected {expected}, received {actual}")


def raw_protocol(raw_zip: zipfile.ZipFile, member: str) -> dict[str, object]:
    header = raw_zip.read(member).decode("latin-1").splitlines()[:65]
    joined = "\n".join(header)
    required = ("dE/dt               10,000", "E1 (V)              -1,200", "nc cycles           2")
    if not all(marker in joined for marker in required):
        raise ValueError(f"unexpected CV protocol header in {member}")
    return {
        "scan_rate_mV_s": 10.0,
        "potential_start_V": 0.0,
        "potential_vertex_V": -1.2,
        "cycles_recorded": 2,
        "analysis_cycle": 2,
    }


def parse_columns(text: str) -> dict[str, list[float | None]]:
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    columns: dict[str, list[float | None]] = {name: [] for name in reader.fieldnames or [] if name}
    for row in reader:
        for name in columns:
            raw = (row.get(name) or "").strip()
            columns[name].append(None if raw in {"", "NaN"} else float(raw))
    return columns


def main() -> None:
    processed_payload = download(PROCESSED_URL)
    raw_payload = download(RAW_URL)
    verify(processed_payload, PROCESSED_SHA256, "processed archive")
    verify(raw_payload, RAW_SHA256, "raw archive")

    with zipfile.ZipFile(io.BytesIO(processed_payload)) as processed_zip:
        source = processed_zip.read(PROCESSED_MEMBER)
    verify(source, PROCESSED_FILE_SHA256, PROCESSED_MEMBER)
    columns = parse_columns(source.decode("utf-8"))

    samples: list[dict[str, object]] = []
    with zipfile.ZipFile(io.BytesIO(raw_payload)) as raw_zip:
        for sample in SAMPLES:
            potential_column, current_column = sample["columns"]
            points = [
                [potential, current]
                for potential, current in zip(
                    columns[str(potential_column)], columns[str(current_column)], strict=True
                )
                if potential is not None and current is not None
            ]
            samples.append(
                {
                    key: value
                    for key, value in sample.items()
                    if key not in {"columns", "raw_member"}
                }
                | {
                    "protocol": raw_protocol(raw_zip, str(sample["raw_member"])),
                    "point_count": len(points),
                    "points": points,
                }
            )

    output = {
        "schema_version": "1",
        "provenance": "published_processed_experimental_data",
        "display_purpose": "Real-data context only; not an input to the synthetic planner benchmark.",
        "source": {
            "title": "Supplement Data of Anolytes for All-Iron Redox-Flow Batteries",
            "authors": "Marius Engler, Michael Stich, Christoph Baumer, Andreas Bund",
            "doi": "10.5281/zenodo.15730784",
            "record_url": RECORD_URL,
            "license": "CC BY 4.0",
            "processed_member": PROCESSED_MEMBER,
            "processed_archive_sha256": PROCESSED_SHA256,
            "processed_member_sha256": PROCESSED_FILE_SHA256,
            "raw_archive_sha256": RAW_SHA256,
        },
        "measurement": {
            "x": "Working-electrode potential vs Ag/AgCl/KCl (sat'd)",
            "x_unit": "V",
            "y": "Total current density",
            "y_unit": "mA cm⁻²",
            "working_electrode": "5 MHz Cr/Au-coated quartz crystal",
            "reference_electrode": "Ag/AgCl/KCl (sat'd)",
            "counter_electrode": "iron sheet",
            "processing": "Author-processed plotting data; second cycle, smoothed as documented by the authors.",
        },
        "samples": samples,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"wrote {OUTPUT} with {sum(s['point_count'] for s in samples)} points")


if __name__ == "__main__":
    main()
