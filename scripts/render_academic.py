"""Re-export the user's current lecture without authoring or writing its JSON."""

from pathlib import Path
import argparse
import hashlib
import json
import tempfile

import fitz
from ctrltea import store
from ctrltea.exporter import build_docx, to_pdf
from ctrltea.models import LectureDocument
from ctrltea.theme import MODERN_ACADEMIC, CLASSICAL_TEXTBOOK, PALETTES
from render_examples import verify_content


def run(output, all_themes=False):
    output.mkdir(parents=True, exist_ok=True)
    source = store.ROOT / "examples/academic-control.document.json"
    raw = source.read_bytes()
    document = LectureDocument.model_validate_json(raw)
    previous_data = store.DATA
    reports = {}
    try:
        with tempfile.TemporaryDirectory(prefix="ctrltea-academic-") as temporary:
            store.DATA = Path(temporary)
            store.init()
            variants = [
                ("Style_A_Modern", MODERN_ACADEMIC, "cinnamon"),
                ("CtrlTea_Lecture_Academic", CLASSICAL_TEXTBOOK, "cinnamon"),
            ]
            if all_themes:
                variants.extend(
                    ("academic-control-" + t, CLASSICAL_TEXTBOOK, t) for t in PALETTES
                )
            for name, typography, theme in variants:
                path = output / (name + ".docx")
                report = build_docx(document, path, typography=typography, theme=theme)
                pdf = to_pdf(path)
                report.update(verify_content(document, path))
                with fitz.open(pdf) as pages:
                    report["pages"] = len(pages)
                    report["fonts"] = sorted(
                        {f[3] for p in pages for f in p.get_fonts()}
                    )
                    assert any("LatinModernMath" in n for n in report["fonts"])
                    assert all(
                        p.get_text(clip=fitz.Rect(0, 0, 595, 799)).strip()
                        != "انتهت المحاضرة"
                        for p in pages
                    )
                assert source.read_bytes() == raw
                report.update(
                    scientific_json_unchanged=True,
                    theme=theme,
                    source_sha256=hashlib.sha256(raw).hexdigest(),
                )
                reports[name] = report
                print(
                    name,
                    report["pages"],
                    report["equations"],
                    report["figures"],
                    flush=True,
                )
    finally:
        store.DATA = previous_data
    (output / "verification.json").write_text(
        json.dumps(reports, ensure_ascii=False, indent=2)
    )
    return reports


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=store.ROOT / "examples/academic-exports"
    )
    parser.add_argument("--all-themes", action="store_true")
    args = parser.parse_args()
    run(args.output.resolve(), args.all_themes)
