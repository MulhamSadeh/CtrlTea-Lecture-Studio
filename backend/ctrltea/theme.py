"""Document typography and measured artwork from control-original.pdf.

Ctrl+Tea Study Notes combines framed semantic blocks with flowing explanations.
Its academic hierarchy draws on mousse-notes 2.0.1, reimplemented in native Word.
One palette belongs to the lecture metadata, never to authored scientific content.
Cover artwork keeps its original colors independently of the lecture palette.
"""

from typing import Literal
from dataclasses import dataclass
import hashlib

ThemeName = Literal["cinnamon", "honey", "olive"]
DEFAULT_THEME: ThemeName = "cinnamon"

# Identity typography is retained for the approved cover/footer. Content body
# and heading typography are selected separately below.
AR_BODY = "Noto Naskh Arabic"
AR_HEADING = "Noto Sans Arabic"
EN_BODY = "Source Serif 4"
EN_HEADING = "Source Sans 3"
MATH = "Latin Modern Math"
MATH_SIZE = 14
INK = "#3D2D25"
PALETTES = {
    "cinnamon": ("#8B3F25", "#C77A45", "#F6E1D3"),
    "honey": ("#9B6B0C", "#F4C84E", "#FEF2D6"),
    "olive": ("#556B2F", "#8FA86B", "#E9F0D7"),
}
THEME_LABELS = {
    "cinnamon": ("Cinnamon", "القرفة"),
    "honey": ("Honey", "العسل"),
    "olive": ("Olive", "الزيتوني"),
}
FOOTER_POLICY = (
    "ثيم واحد محفوظ لكل محاضرة؛ فوتر ثابت لجميع صفحات المحتوى، والغلاف بألوانه الأصلية."
)


@dataclass(frozen=True)
class AcademicTypography:
    arabic: str
    latin: str
    arabic_size: float
    latin_size: float
    leading: float


# Candidates compared on identical real lecture excerpts; sizes follow each
# font's metrics. Cairo is selected for the current content-only update.
MODERN_ACADEMIC = AcademicTypography(
    "Noto Sans Arabic", "Source Sans 3", 13.0, 12.5, 24
)
CLASSICAL_TEXTBOOK = AcademicTypography(
    "Noto Naskh Arabic", "Source Serif 4", 15.5, 13.5, 25
)
STUDY_CAIRO = AcademicTypography("Cairo", "Cairo", 13.5, 13.0, 25)
CONTENT_HEADING = "Cairo"
ACADEMIC_TYPOGRAPHY = STUDY_CAIRO


def validate_theme(value):
    if not isinstance(value, str) or value not in PALETTES:
        raise ValueError("لون المحاضرة غير صالح؛ اختر القرفة أو العسل أو الزيتوني")
    return value


def design_settings():
    """The dashboard and document renderer share this single color definition."""
    return {
        "default_theme": DEFAULT_THEME,
        "themes": [
            dict(
                id=key,
                name=THEME_LABELS[key][0],
                label=THEME_LABELS[key][1],
                dark=colors[0],
                medium=colors[1],
                light=colors[2],
            )
            for key, colors in PALETTES.items()
        ],
        "fonts": dict(
            ar_body=ACADEMIC_TYPOGRAPHY.arabic,
            ar_heading=CONTENT_HEADING,
            en_body=ACADEMIC_TYPOGRAPHY.latin,
            en_heading=CONTENT_HEADING,
            math=MATH,
        ),
    }


def paper_tint(color, strength):
    """Keep a palette color's hue while reducing large areas of printed ink."""
    rgb = [int(color.lstrip("#")[i:i+2], 16) for i in (0, 2, 4)]
    return "#" + "".join(f"{round(255 + strength * (c - 255)):02X}" for c in rgb)


def academic_box_style(kind, dark, light):
    """One restrained box hierarchy, derived only from the lecture palette."""
    emphasis = kind in {"rule", "warning"}
    fill_strength = {"definition": .40, "rule": .55, "warning": .40,
                     "note": .22, "exercise": .28, "result": .65}.get(kind, 0)
    return dict(
        fill=paper_tint(light, fill_strength),
        border=dark if emphasis else paper_tint(dark, .65),
        weight=6 if emphasis else 4,
        vertical_padding=100 if kind in {"note", "result"} else 150,
        horizontal_padding=220,
    )


def footer_art(theme):
    """Recolor only the original footer backgrounds, retaining its mark geometry.

    The neutral transparent wordmark was extracted from the reference at its
    original pixel size. Rasterization is on demand, not three shipped templates.
    """
    import base64
    from .runtime import svg_png
    from . import store

    validate_theme(theme)
    dark, medium, _ = PALETTES[theme]
    mark = store.ROOT / "assets/original/footer-mark.png"
    key = hashlib.sha256(
        mark.read_bytes() + (dark + medium + "footer-v1").encode()
    ).hexdigest()
    path = store.DATA / "figures" / f"footer-{key}.png"
    if not path.exists():
        encoded = base64.b64encode(mark.read_bytes()).decode()
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="2016" height="144" viewBox="0 0 2016 144">
        <path fill="{dark}" d="M0 0h1008v144H0z"/>
        <path fill="{medium}" d="M1008 0h1008v144H1008z"/>
        <image x="1434" y="30" width="156" height="86" href="data:image/png;base64,{encoded}"/>
        </svg>"""
        # Atomic replacement also permits parallel preview/export processes.
        data = svg_png(svg.encode())
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(dir=path.parent, suffix=".png", delete=False) as tmp:
            tmp.write(data)
            temporary = tmp.name
        from pathlib import Path

        Path(temporary).replace(path)
    return path
