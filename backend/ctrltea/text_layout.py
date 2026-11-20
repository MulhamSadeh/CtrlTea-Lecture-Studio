"""Presentation-only text segmentation shared by Word and vector labels."""

import re

ARABIC = re.compile(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff]")
LATIN = re.compile(r"[([\{]?[A-Za-z0-9][A-Za-z0-9 \t=+*/^_.:,;°Ωµ%−–—←→\[\](){}-]*")


def direction_runs(part):
    """Yield LTR phrases and uninterrupted Arabic/neutral shaping runs."""
    start = 0
    for match in LATIN.finditer(part):
        content = match.group().rstrip(" \t.,;:")
        for opening, closing in [("(", ")"), ("[", "]"), ("{", "}")]:
            while content.endswith(closing) and content.count(closing) > content.count(
                opening
            ):
                if re.fullmatch(r"\d+[.)]", content):
                    break
                content = content[:-1]
        while re.search(r"\s+[(\[{]$", content):
            opening = content[-1]
            closing = {"(": ")", "[": "]", "{": "}"}[opening]
            if content.count(opening) <= content.count(closing):
                break
            content = content[:-1].rstrip()
        if match.start() > start:
            yield False, part[start : match.start()]
        yield True, content
        start = match.start() + len(content)
    if start < len(part):
        yield False, part[start:]


def prose_parts(value):
    """Recognise existing explicit line lists; never infer a list from prose.

    Kept in the presentation layer so re-exporting old lectures changes no JSON.
    Only a sequence of two or more marked lines is treated as a legacy list.
    """
    lines = value.split("\n")
    pending = []
    i = 0
    pattern = re.compile(
        r"^\s*(?:(?P<bullet>[-*•])|(?P<number>\d+)[.)])\s+(?P<text>.+)$"
    )
    while i < len(lines):
        match = pattern.match(lines[i])
        group = []
        j = i
        if match:
            ordered = match.group("number") is not None
            first = int(match.group("number")) if ordered else 1
            while j < len(lines):
                item = pattern.match(lines[j])
                if not item or (item.group("number") is not None) != ordered:
                    break
                if ordered and int(item.group("number")) != first + len(group):
                    break
                group.append(item.group("text"))
                j += 1
        if len(group) >= 2:
            if pending:
                yield "prose", "\n".join(pending)
                pending = []
            yield ("ordered" if ordered else "bullet"), (first, group)
            i = j
        else:
            if not lines[i].strip() and pending:
                yield "prose", "\n".join(pending)
                pending = []
            elif lines[i].strip():
                pending.append(lines[i])
            i += 1
    if pending:
        yield "prose", "\n".join(pending)
