"""Load the supplied reference-based examples through the same API as the UI."""

import argparse
import json
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]


def seed(base="http://127.0.0.1:8765"):
    output = {}
    with httpx.Client(base_url=base, timeout=180, trust_env=False) as c:
        for key, course_name, pdf in [
            ("control", "نظم التحكم الآلي 1", "control-original.pdf"),
            ("statistics", "الإحصاء", "statistics-original.pdf"),
        ]:
            course = c.post("/api/courses", json={"name": course_name, "doctor": ""})
            course.raise_for_status()
            cid = course.json()["id"]
            doc = json.loads((ROOT / f"examples/{key}.document.json").read_text())
            row = c.post(
                f"/api/courses/{cid}/lectures", json={"title": doc["title"], "number": "01"}
            )
            row.raise_for_status()
            lid = row.json()["id"]
            source = c.post(
                f"/api/lectures/{lid}/sources",
                files={
                    "file": (
                        pdf,
                        (ROOT / "examples/references" / pdf).read_bytes(),
                        "application/pdf",
                    )
                },
                data={"role": "primary", "priority": "0"},
            )
            source.raise_for_status()
            sid = source.json()["source"]["id"]
            token = "CONTROL_PDF" if key == "control" else "STATISTICS_PDF"
            for section in doc["sections"]:
                for block in section["blocks"]:
                    for ref in block["refs"]:
                        if ref["source_id"] == token:
                            ref["source_id"] = sid
            result = c.post(
                f"/api/lectures/{lid}/authoring/import", json={"result": doc, "revision": 0}
            )
            result.raise_for_status()
            output[key] = {"course_id": cid, "lecture_id": lid, "source_id": sid}
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    args = parser.parse_args()
    print(json.dumps(seed(args.url), ensure_ascii=False, indent=2))
