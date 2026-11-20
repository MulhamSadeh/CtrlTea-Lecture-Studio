"""Re-export the saved projects without authoring, OCR, or editing lecture data.

PYTHONPATH=backend python scripts/render_examples.py --output examples/exports
"""

from pathlib import Path
import argparse
from collections import Counter
import hashlib
import json
import re
import shutil
import tempfile
import zipfile

from lxml import etree
from ctrltea import bundles, store
from ctrltea.exporter import export_lecture, academic_label, visible_body
from ctrltea.mathml import NS, formulas, omml, segments
from ctrltea.models import LectureDocument
from ctrltea.theme import PALETTES
from ctrltea.text_layout import prose_parts


def verify_content(document, docx):
    with zipfile.ZipFile(docx) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    normalize = lambda s: re.sub(
        r"\s+", "", s.translate({ord(c): None for c in "\u2066\u2069"})
    )
    exported = normalize("".join(root.itertext()))
    count = 0
    for section in document.sections:
        for block in section.blocks:
            fields = [
                re.sub(r"^(?:(?:تعريف|قاعدة|قانون|نظرية|مثال(?: محلول)?|مسألة محلولة|ملاحظة|تنبيه)(?:\s+\d+)?\s*[:：]\s*)+", "", academic_label(block, block.title)) if block.title else "",
                visible_body(block),
                block.problem,
                block.givens,
                block.result,
                *block.steps,
                *block.items,
                *block.headers,
                *[v for row in block.rows for v in row],
            ]
            if block.figure:
                fields.append(block.figure.caption)
            for field in fields:
                fragments = []
                for kind, value in prose_parts(field):
                    fragments.extend([value] if kind == "prose" else value[1])
                for fragment in fragments:
                    for math, part in segments(fragment):
                        if not math and part.strip():
                            assert (
                                normalize(part) in exported
                            ), f"Missing text in block {block.id}: {part[:60]}"
                            count += 1

    # Compare expanded XML names, independent of serializer namespace prefixes.
    def canonical(node):
        return (
            node.tag,
            tuple(sorted(node.attrib.items())),
            node.text or "",
            tuple(canonical(child) for child in node),
        )

    assert Counter(
        canonical(omml(formula)) for _, formula in formulas(document)
    ) == Counter(canonical(node) for node in root.findall(".//m:oMath", NS))
    return {
        "verified_text_fragments": count,
        "all_formulas_structurally_identical": True,
    }


def run(output, all_themes=False):
    output.mkdir(parents=True, exist_ok=True)
    previous_data = store.DATA
    reports = {}
    try:
        with tempfile.TemporaryDirectory(
            prefix="ctrltea-render-examples-"
        ) as temporary:
            store.DATA = Path(temporary) / "data"
            store.init()
            for name in ("control", "statistics"):
                restored = bundles.import_course(
                    (store.ROOT / f"examples/projects/{name}-project.zip").read_bytes()
                )
                lid = store.all_rows(
                    "SELECT id FROM lectures WHERE course_id=?",
                    (restored["course_id"],),
                )[0]["id"]
                before = store.lecture(lid)["document"]
                raw = store.one("SELECT doc,revision FROM lectures WHERE id=?", (lid,))
                for theme in PALETTES if all_themes else [store.lecture(lid)["theme"]]:
                    store.set_theme(lid, theme)
                    report = export_lecture(lid)
                    assert (
                        before == store.lecture(lid)["document"]
                    ), "Export modified the lecture"
                    assert raw == store.one(
                        "SELECT doc,revision FROM lectures WHERE id=?", (lid,)
                    )
                    folder = store.DATA / "exports" / report["export_id"]
                    report.update(
                        verify_content(
                            LectureDocument.model_validate(before),
                            folder / "lecture.docx",
                        )
                    )
                    basename = f"{name}-{theme}" if all_themes else name
                    for extension in ("docx", "pdf"):
                        shutil.copyfile(
                            folder / f"lecture.{extension}",
                            output / f"{basename}.{extension}",
                        )
                    report["content_unchanged"] = True
                    report["document_sha256"] = hashlib.sha256(
                        raw["doc"].encode()
                    ).hexdigest()
                    reports[basename] = report
                    print(
                        f"{basename}: {report['pages']} pages, {report['equations']} editable equations, {report['figures']} figures",
                        flush=True,
                    )
    finally:
        store.DATA = previous_data
    (output / "report.json").write_text(
        json.dumps(reports, ensure_ascii=False, indent=2)
    )
    return reports


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=store.ROOT / "examples/exports")
    parser.add_argument("--all-themes", action="store_true")
    args = parser.parse_args()
    run(args.output.resolve(), all_themes=args.all_themes)
