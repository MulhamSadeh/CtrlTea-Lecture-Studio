from __future__ import annotations

import io
import copy
import json
import zipfile
from pathlib import Path
from . import store
from .models import LectureDocument, uid
from .sources import source_warnings
from .author_validation import (
    result_schema,
    validate_result,
    compatibility_payload,
    AuthoringValidationError,
)

SKILL_DIR = Path(__file__).parent / "skills" / "ctrltea-lecture-authoring"
# Manual packets and discoverable clients consume the same versioned rules.
INSTRUCTIONS = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8").split("\n---\n", 1)[1].lstrip()


def packet(lid, section_ids=None):
    lecture = store.lecture(lid)
    doc = LectureDocument.model_validate(lecture["document"])
    selected = (
        [s for s in doc.sections if s.id in section_ids]
        if section_ids
        else [s for s in doc.sections if not s.complete]
    )
    if doc.sections and not selected:
        raise ValueError("كل الأقسام مكتملة. أعد فتح قسم أو اختره صراحة لإعادة تأليفه.")
    run = uid()
    tasks = [s.id for s in selected] or ["new"]
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("instructions.txt", INSTRUCTIONS)
        for reference in sorted((SKILL_DIR / "references").glob("*.md")):
            z.write(reference, f"references/{reference.name}")
        z.write(SKILL_DIR / "scripts/check_math.py", "scripts/check_math.py")
        schema = result_schema(run)
        z.writestr("schema.json", json.dumps(schema, ensure_ascii=False, indent=2))
        z.writestr(
            "validate_result.py",
            (store.ROOT / "backend/ctrltea/author_validation.py").read_bytes(),
        )
        from .author_validation import FIELDS, COMMON, REQUIRED

        fields = {
            kind: {
                "allowed": sorted(COMMON | specific),
                "required": ["id", "kind", *REQUIRED[kind]],
            }
            for kind, specific in FIELDS.items()
        }
        z.writestr(
            "block-fields.json", json.dumps(fields, ensure_ascii=False, indent=2)
        )
        context = compatibility_payload({"sections": lecture["document"]["sections"]})
        for section in context["sections"]:
            for block in section["blocks"]:
                block.pop("issue_resolved", None)
        z.writestr(
            "current.json",
            json.dumps(
                dict(title=doc.title, course=doc.course, sections=context["sections"]),
                ensure_ascii=False,
                indent=2,
            ),
        )
        manifest = {
            "run_id": run,
            "lecture": doc.title,
            "base_revision": lecture["revision"],
            "tasks": [
                {"section_id": s.id, "title": s.title, "status": "pending"}
                for s in selected
            ]
            or [{"section_id": "new", "title": doc.title, "status": "pending"}],
            "sources": [],
        }
        sources = store.all_rows(
            "SELECT * FROM sources WHERE lecture_id=? ORDER BY priority", (lid,)
        )
        for s in sources:
            pages = store.all_rows(
                "SELECT * FROM pages WHERE source_id=? ORDER BY number", (s["id"],)
            )
            included = []
            for p in pages:
                if p["excluded"]:
                    continue
                txt = p["corrected"] if p["corrected"] is not None else p["raw"]
                if not txt.strip():
                    continue
                filename = f'sources/{s["id"]}/page-{p["number"]:04}.txt'
                z.writestr(filename, txt)
                included.append(
                    {
                        "page": p["number"],
                        "file": filename,
                        "corrected": p["corrected"] is not None,
                    }
                )
            z.write(store.DATA / s["path"], f'originals/{s["id"]}/{s["name"]}')
            manifest["sources"].append(
                {
                    "source_id": s["id"],
                    "name": s["name"],
                    "priority": s["priority"],
                    "role": s["role"],
                    "linked_id": s["linked_id"],
                    "pages": included,
                }
            )
        if not any(s["pages"] for s in manifest["sources"]):
            raise ValueError(
                "لا يوجد نص معتمد للتأليف. استخرج النص أو ارفع تفريغًا أولًا."
            )
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        first_source = next(s for s in manifest["sources"] if s["pages"])
        reference = {
            "source_id": first_source["source_id"],
            "page": first_source["pages"][0]["page"],
        }
        examples = [
            {
                "id": "shape-equation",
                "kind": "equation",
                "latex": r"\frac{a}{b}",
                "refs": [reference],
            },
            {
                "id": "shape-exercise",
                "kind": "exercise",
                "problem": "نص المسألة من المصدر",
                "steps": ["خطوة من المصدر"],
                "result": "النتيجة",
                "refs": [reference],
            },
            {
                "id": "shape-list",
                "kind": "list",
                "items": ["العنصر الأول من المصدر", "العنصر الثاني من المصدر"],
                "ordered": False,
                "refs": [reference],
            },
        ]
        # Validate the examples with the exact contract before shipping them.
        example_result = {
            "run_id": run,
            "sections": [
                {
                    "id": selected[0].id if selected else "section-1",
                    "title": "أشكال بنيوية فقط — ليست مادة علمية",
                    "blocks": examples,
                }
            ],
        }
        validate_result(example_result, schema, manifest)
        z.writestr(
            "schema-examples.json",
            json.dumps(example_result, ensure_ascii=False, indent=2),
        )
        z.writestr(
            "README.txt",
            "افتح instructions.txt أولًا. أمثلة schema-examples.json تبين البنية فقط وليست محتوى للتأليف.\nشغّل validate_result.py من بيئة التطبيق التي تتضمن ctrltea وjsonschema وPandoc. لا يحتاج الفحص إلى نموذج أو اتصال شبكي.\n",
        )
    with store.connect() as db:
        db.execute(
            "INSERT INTO author_runs VALUES(?,?,?,?,?,?)",
            (
                run,
                lid,
                json.dumps(tasks),
                "pending",
                store.now(),
                json.dumps(lecture["document"], ensure_ascii=False),
            ),
        )
        for sid in tasks:
            db.execute(
                "INSERT INTO author_tasks(run_id,section_id) VALUES(?,?)", (run, sid)
            )
    return run, output.getvalue()


def proposal(lid, payload):
    current = store.lecture(lid)
    payload = copy.deepcopy(payload)
    if not isinstance(payload, dict):
        raise AuthoringValidationError(
            [
                {
                    "path": [],
                    "location": "الملف",
                    "message": "يجب أن تكون النتيجة كائن JSON يحوي run_id وsections.",
                }
            ]
        )
    aliases = {
        r["original_id"]: r["source_id"]
        for r in store.all_rows(
            "SELECT * FROM source_aliases WHERE lecture_id=?", (lid,)
        )
    }
    run_id = payload.get("run_id")
    if "run_id" in payload and not isinstance(run_id, str):
        raise AuthoringValidationError(
            [
                {
                    "path": ["run_id"],
                    "location": "مهمة التأليف",
                    "message": "معرّف مهمة التأليف يجب أن يكون نصًا من manifest.json.",
                }
            ]
        )
    conflicts = []
    if run_id:
        resolved = store.all_rows(
            "SELECT * FROM author_runs WHERE id=? AND lecture_id=?", (run_id, lid)
        )
        if not resolved:
            alias = store.one(
                "SELECT run_id FROM run_aliases WHERE lecture_id=? AND original_id=?",
                (lid, run_id),
            )
            run_id = alias["run_id"]
            resolved = store.all_rows(
                "SELECT * FROM author_runs WHERE id=? AND lecture_id=?", (run_id, lid)
            )
        run = resolved[0]
        if set(payload) - {"run_id", "sections"}:
            raise ValueError("نتيجة التأليف الجزئية تقبل run_id وsections فقط")
        sections = validate_result(
            payload, result_schema(payload["run_id"]), compatibility=True
        )
        for section in sections:
            for block in section.blocks:
                for ref in block.refs:
                    ref.source_id = aliases.get(ref.source_id, ref.source_id)
        allowed = json.loads(run["section_ids"])
        if "new" not in allowed and any(s.id not in allowed for s in sections):
            raise ValueError("النتيجة تحتوي قسمًا خارج نطاق مهمة التأليف")
        baseline = {s["id"]: s for s in json.loads(run["base_doc"])["sections"]}
        existing = {s["id"]: s for s in current["document"]["sections"]}
        for s in sections:
            if s.id in existing and existing[s.id] != baseline.get(s.id):
                conflicts.append(s.id)
        replace = {s.id: s.model_dump() for s in sections}
        merged = [replace.pop(s["id"], s) for s in current["document"]["sections"]]
        merged.extend(replace.values())
        raw = dict(current["document"], sections=merged)
    else:
        raw = payload
        if current["document"]["sections"]:
            conflicts = ["full_document"]
    try:
        doc = LectureDocument.model_validate(raw)
    except Exception as error:
        from pydantic import ValidationError
        from .author_validation import error_item

        if isinstance(error, ValidationError):
            raise AuthoringValidationError(
                [
                    error_item(e["loc"], str(e.get("ctx", {}).get("error", e["msg"])))
                    for e in error.errors()
                ]
            ) from error
        raise
    if not run_id:
        from .author_validation import math_errors

        errors = math_errors(doc)
        if errors:
            raise AuthoringValidationError(errors)
        for section in doc.sections:
            for block in section.blocks:
                for ref in block.refs:
                    ref.source_id = aliases.get(ref.source_id, ref.source_id)
    # Bare legacy documents can still be imported, but an external file cannot
    # create a human approval. A byte-equivalent previously reviewed block is
    # preserved; full project backup/restore retains its own review metadata.
    from .author_validation import error_item

    approved = {
        b.id: b
        for section in LectureDocument.model_validate(current["document"]).sections
        for b in section.blocks
        if b.issue_resolved
    }
    review_errors = []
    for si, section in enumerate(doc.sections):
        for bi, block in enumerate(section.blocks):
            if block.issue_resolved and (
                block.id not in approved
                or block.model_dump() != approved[block.id].model_dump()
            ):
                review_errors.append(
                    error_item(
                        ["sections", si, "blocks", bi, "issue_resolved"],
                        "ملف التأليف لا ينشئ موافقة بشرية. اترك حالة المراجعة false، ثم اعتمد التصحيح من المحرر؛ لاستعادة مراجعات مشروع سابق استخدم استعادة المشروع.",
                    )
                )
    if review_errors:
        raise AuthoringValidationError(review_errors)
    checks = source_warnings(doc, lid)
    return {
        "document": doc.model_dump(),
        "revision": current["revision"],
        "run_id": run_id,
        "conflicts": conflicts,
        "checks": checks,
        "section_count": len(doc.sections),
    }


def _import_result(lid, payload, revision, allow_conflicts=False):
    preview = proposal(lid, payload)
    if preview["conflicts"] and not allow_conflicts:
        raise store.Conflict(
            "الاستيراد سيستبدل محتوى سبق تعديله. راجع المقارنة وأكد الاستبدال."
        )
    saved = store.save_document(
        lid, preview["document"], revision, "استيراد نتيجة التأليف"
    )
    if preview["run_id"]:
        imported = [s["id"] for s in payload["sections"]]
        with store.connect() as db:
            for sid in imported:
                db.execute(
                    "UPDATE author_tasks SET status='imported' WHERE run_id=? AND section_id=?",
                    (preview["run_id"], sid),
                )
            db.execute(
                "UPDATE author_tasks SET status='imported' WHERE run_id=? AND section_id='new'",
                (preview["run_id"],),
            )
            remaining = db.execute(
                "SELECT count(*) FROM author_tasks WHERE run_id=? AND status='pending'",
                (preview["run_id"],),
            ).fetchone()[0]
            db.execute(
                "UPDATE author_runs SET status=? WHERE id=?",
                ("partial" if remaining else "complete", preview["run_id"]),
            )
    return saved


def import_result(lid, payload, revision, allow_conflicts=False):
    with store.transaction():
        return _import_result(lid, payload, revision, allow_conflicts)
