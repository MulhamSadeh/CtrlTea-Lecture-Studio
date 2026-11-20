"""One authoring contract, used by packets, offline validation and import.

Run the copy shipped in an authoring packet from the application's Python
installation: python validate_result.py result.json --schema schema.json --manifest manifest.json
No network, LLM or lecture mutation is involved in validation.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import re
import sys
import tempfile

from jsonschema import Draft202012Validator
from pydantic import ValidationError
from ctrltea.models import Block, LectureDocument

COMMON = {
    "id",
    "kind",
    "title",
    "text",
    "origin",
    "refs",
    "issue",
    "correction",
    "issue_resolved",
}
FIELDS = {
    "definition": {"text"},
    "rule": {"text"},
    "explanation": {"text"},
    "example": {"text"},
    "note": {"text"},
    "warning": {"text"},
    "equation": {"latex"},
    "exercise": {"problem", "givens", "steps", "result", "verbatim"},
    "list": {"items", "ordered"},
    "table": {"headers", "rows"},
    "figure": {"figure"},
}
REQUIRED = {
    "definition": ["text"],
    "rule": ["text"],
    "explanation": ["text"],
    "example": ["text"],
    "note": ["text"],
    "warning": ["text"],
    "equation": ["latex"],
    "exercise": ["problem"],
    "list": ["items"],
    "table": ["headers", "rows"],
    "figure": ["figure", "refs"],
}
FIELD_NAMES = {
    "sections": "الأقسام",
    "blocks": "العناصر",
    "title": "العنوان",
    "text": "النص",
    "kind": "نوع العنصر",
    "problem": "نص المسألة",
    "steps": "خطوات الحل",
    "result": "النتيجة",
    "latex": "المعادلة",
    "headers": "رؤوس الجدول",
    "rows": "صفوف الجدول",
    "items": "عناصر القائمة",
    "refs": "المراجع",
    "source_id": "المصدر",
    "page": "الصفحة",
    "figure": "مواصفات الرسم",
    "issue_resolved": "حالة المراجعة البشرية",
    "run_id": "مهمة التأليف",
}


class AuthoringValidationError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__(
            "لم تجتز نتيجة التأليف الفحص. "
            + "؛ ".join(x["message"] for x in errors[:3])
        )


def result_schema(run_id=None):
    definitions = copy.deepcopy(LectureDocument.model_json_schema()["$defs"])
    properties = definitions["Block"]["properties"]
    branches = []
    for kind, fields in FIELDS.items():
        allowed = COMMON | fields
        props = {k: copy.deepcopy(v) for k, v in properties.items() if k in allowed}
        props["kind"] = {"const": kind}
        # Review decisions belong to the human editor, never to the author.
        props["issue_resolved"] = {"const": False, "default": False}
        for required in REQUIRED[kind]:
            if props[required].get("type") == "string":
                props[required]["minLength"] = 1
                props[required]["pattern"] = r"\S"
        if kind == "list":
            props["items"]["minItems"] = 1
            props["items"]["items"]["minLength"] = 1
            props["items"]["items"]["pattern"] = r"\S"
        if kind == "figure":
            props["figure"] = {"$ref": "#/$defs/Figure"}
            props["refs"]["minItems"] = 1
        if kind == "table":
            props["headers"]["minItems"] = 1
        branches.append(
            {
                "type": "object",
                "additionalProperties": False,
                "properties": props,
                "required": ["id", "kind", *REQUIRED[kind]],
            }
        )
    definitions["Block"] = {"oneOf": branches}
    section = definitions["Section"]
    section["properties"].pop("palette", None)
    section["required"] = ["id", "title", "blocks"]
    section["properties"]["blocks"]["minItems"] = 1
    for key in ["id", "title"]:
        section["properties"][key]["minLength"] = 1
        section["properties"][key]["pattern"] = r"\S"
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Ctrl+Tea scientific author result",
        "type": "object",
        "additionalProperties": False,
        "required": ["run_id", "sections"],
        "properties": {
            "run_id": (
                {"const": run_id} if run_id else {"type": "string", "minLength": 1}
            ),
            "sections": {
                "type": "array",
                "minItems": 1,
                "items": {"$ref": "#/$defs/Section"},
            },
        },
        "$defs": definitions,
    }


def location(path):
    return (
        " / ".join(
            str(x + 1) if isinstance(x, int) else FIELD_NAMES.get(x, str(x))
            for x in path
        )
        or "الملف"
    )


def error_item(path, message):
    return {"path": list(path), "location": location(path), "message": message}


def compatibility_payload(payload):
    """Accept old normalized editor exports with irrelevant *empty defaults*.

    Never change a kind, move math, drop nonempty fields or clear review flags.
    The stored document and the original uploaded result are left untouched.
    """
    result = copy.deepcopy(payload)
    defaults = Block(kind="explanation", text="compatibility").model_dump()
    for section in (
        result.get("sections", [])
        if isinstance(result, dict) and isinstance(result.get("sections"), list)
        else []
    ):
        if not isinstance(section, dict):
            continue
        section.pop("palette", None)  # obsolete display metadata, not authored science
        for block in (
            section.get("blocks", []) if isinstance(section.get("blocks"), list) else []
        ):
            if not isinstance(block, dict) or block.get("kind") not in FIELDS:
                continue
            allowed = COMMON | FIELDS[block["kind"]]
            for key in list(block):
                if (
                    key not in allowed
                    and key in defaults
                    and block[key] == defaults[key]
                ):
                    del block[key]
    return result


def schema_errors(payload, schema):
    errors = []
    for error in Draft202012Validator(schema).iter_errors(payload):
        path = list(error.absolute_path)
        # Validate the branch selected by kind, avoiding an unreadable union of
        # errors for ten unrelated kinds.
        if (
            error.validator == "oneOf"
            and isinstance(error.instance, dict)
            and error.instance.get("kind") in FIELDS
        ):
            branch = next(
                x
                for x in schema["$defs"]["Block"]["oneOf"]
                if x["properties"]["kind"]["const"] == error.instance["kind"]
            )
            for detail in Draft202012Validator(
                dict(branch, **{"$defs": schema["$defs"]})
            ).iter_errors(error.instance):
                errors.append(friendly_error(detail, path + list(detail.path)))
        else:
            errors.append(friendly_error(error, path))
    return errors


def friendly_error(error, path):
    if error.validator == "additionalProperties":
        unknown = set(error.instance) - set(error.schema.get("properties", {}))
        message = "حقول غير مسموحة لهذا النوع: " + "، ".join(sorted(unknown))
    elif error.validator == "required":
        missing = set(error.validator_value) - set(error.instance)
        message = "حقول مطلوبة: " + "، ".join(
            FIELD_NAMES.get(k, k) for k in sorted(missing)
        )
    elif error.validator == "const" and path and path[-1] == "issue_resolved":
        message = "لا يحق للمؤلف اعتماد التصحيح بشريًا. اترك issue_resolved=false وراجعه في المحرر."
    elif error.validator in ("minLength", "minItems"):
        message = "هذا الحقل مطلوب ولا يمكن أن يكون فارغًا."
    elif error.validator == "type":
        message = "نوع البيانات غير صحيح؛ راجع الحقل في schema.json."
    elif error.validator in ("enum", "const", "oneOf"):
        message = "القيمة غير مسموحة في Schema أو لا تطابق مهمة التأليف."
    else:
        message = "الحقل لا يطابق قيود Schema: " + error.message[:160]
    return error_item(path, message)


def validate_result(
    payload, schema=None, manifest=None, *, compatibility=False, check_math=True
):
    schema = schema or result_schema(
        payload.get("run_id") if isinstance(payload, dict) else None
    )
    projected = (
        compatibility_payload(payload) if compatibility else copy.deepcopy(payload)
    )
    errors = schema_errors(projected, schema)
    if errors:
        raise AuthoringValidationError(errors)
    # These runtime validators also check row widths, paired plot data, node and
    # edge references, crop bounds, verbatim refs and unique section/block IDs.
    try:
        document = LectureDocument.model_validate({"sections": projected["sections"]})
    except ValidationError as exc:
        errors = [
            error_item(
                e["loc"],
                str(e["ctx"]["error"]) if e.get("ctx", {}).get("error") else e["msg"],
            )
            for e in exc.errors()
        ]
        raise AuthoringValidationError(errors) from exc
    if manifest:
        allowed = {x["section_id"] for x in manifest.get("tasks", [])}
        pages = {
            x["source_id"]: {p["page"] for p in x["pages"]}
            for x in manifest.get("sources", [])
        }
        for si, section in enumerate(document.sections):
            if allowed and "new" not in allowed and section.id not in allowed:
                errors.append(
                    error_item(
                        ["sections", si, "id"], "هذا القسم خارج نطاق مهمة التأليف."
                    )
                )
            for bi, block in enumerate(section.blocks):
                for ri, ref in enumerate(block.refs):
                    if (
                        ref.source_id not in pages
                        or ref.page not in pages[ref.source_id]
                    ):
                        errors.append(
                            error_item(
                                ["sections", si, "blocks", bi, "refs", ri],
                                "المرجع يشير إلى مصدر أو صفحة غير مدرجة في الحزمة.",
                            )
                        )
    for si, section in enumerate(document.sections):
        for bi, block in enumerate(section.blocks):
            if block.verbatim and block.problem not in [r.quote for r in block.refs]:
                errors.append(
                    error_item(
                        ["sections", si, "blocks", bi, "problem"],
                        "نص سؤال الكتاب لا يطابق المقتطف الحرفي. انسخه كما هو دون إعادة صياغة.",
                    )
                )
    if check_math:
        errors.extend(math_errors(document))
    if errors:
        raise AuthoringValidationError(errors)
    return document.sections


def math_errors(document):
    errors = []
    from ctrltea.mathml import formulas, omml, segments

    # Catch malformed inline delimiters before the regex can silently leave
    # them as ordinary text. Valid LaTeX itself is checked by the real OMML engine.
    for si, section in enumerate(document.sections):
        for bi, block in enumerate(section.blocks):
            values = [
                block.title,
                block.text,
                block.problem,
                block.givens,
                block.result,
                *block.steps,
                *block.items,
                *block.headers,
                *[v for row in block.rows for v in row],
            ]
            if block.figure:
                values.append(block.figure.caption)
            for value in values:
                for math, fragment in segments(value):
                    if not math and (
                        r"\(" in fragment
                        or r"\)" in fragment
                        or "$$" in fragment
                        or re.search(
                            r"\\(?:frac|int|delta|omega|sigma|sqrt)\b", fragment
                        )
                    ):
                        errors.append(
                            error_item(
                                ["sections", si, "blocks", bi],
                                "ترميز رياضي خارج معادلة أو محددات غير مغلقة؛ استخدم \\(…\\) للنص وكتلة equation للمعادلة المستقلة.",
                            )
                        )
    positions = {
        b.id: ["sections", si, "blocks", bi, "latex"]
        for si, section in enumerate(document.sections)
        for bi, b in enumerate(section.blocks)
    }
    for bid, latex in formulas(document):
        try:
            omml(latex)
        except (ValueError, OSError) as exc:
            item = error_item(
                positions[bid],
                "هذه الصيغة الرياضية لا تتحول إلى معادلة Word أصلية. صحّح LaTeX ثم أعد الفحص.",
            )
            item["diagnostic"] = str(exc)
            errors.append(item)
    return errors


def main():
    parser = argparse.ArgumentParser(description="فحص كامل لنتيجة التأليف قبل تسليمها")
    parser.add_argument("result", type=Path)
    parser.add_argument("--schema", type=Path, default=Path("schema.json"))
    parser.add_argument("--manifest", type=Path, default=Path("manifest.json"))
    args = parser.parse_args()
    try:
        payload = json.loads(args.result.read_text(encoding="utf-8"))
        schema = json.loads(args.schema.read_text(encoding="utf-8"))
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        from ctrltea import store

        previous_data = store.DATA
        with tempfile.TemporaryDirectory(prefix="ctrltea-author-check-") as temporary:
            try:
                store.DATA = Path(temporary)
                (store.DATA / "math").mkdir()
                sections = validate_result(payload, schema, manifest)
            finally:
                store.DATA = previous_data
    except AuthoringValidationError as exc:
        print(
            json.dumps(
                {"valid": False, "errors": exc.errors}, ensure_ascii=False, indent=2
            )
        )
        return 1
    except (ValueError, OSError) as exc:
        print(
            json.dumps(
                {"valid": False, "message": "لم يكتمل الفحص: " + str(exc)},
                ensure_ascii=False,
            )
        )
        return 2
    print(
        json.dumps(
            {
                "valid": True,
                "sections": len(sections),
                "blocks": sum(len(s.blocks) for s in sections),
                "schema_and_semantics": True,
                "native_word_math_checked": True,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
