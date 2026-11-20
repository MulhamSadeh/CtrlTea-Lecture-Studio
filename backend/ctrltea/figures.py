from __future__ import annotations

import ast
import base64
import hashlib
import math
import re
from lxml import etree
from html import escape
from pathlib import Path

import fitz
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import os

if os.name != "nt":
    os.environ.setdefault("FONTCONFIG_FILE", str(Path(__file__).resolve().parents[2] / "assets/fonts.conf"))
from .runtime import IS_WINDOWS, svg_png
from . import store
from .models import Block
from .text_layout import direction_runs
from matplotlib import font_manager

for _font in (store.ROOT / "assets/fonts").glob("*.ttf"):
    font_manager.fontManager.addfont(str(_font))

from .theme import PALETTES, CONTENT_HEADING, validate_theme

FUNCTIONS = {
    "sin": np.sin,
    "cos": np.cos,
    "tan": np.tan,
    "exp": np.exp,
    "sqrt": np.sqrt,
    "log": np.log,
    "abs": np.abs,
    "step": lambda x: np.where(x >= 0, 1.0, 0.0),
}


def evaluate(expression, x):
    """Evaluate a deliberately small numeric language; never eval model code."""
    tree = ast.parse(expression.replace("^", "**"), mode="eval")
    if sum(1 for _ in ast.walk(tree)) > 100:
        raise ValueError("الدالة طويلة جدًا")

    def walk(n):
        if isinstance(n, ast.Expression):
            return walk(n.body)
        if (
            isinstance(n, ast.Constant)
            and type(n.value) in (float, int)
            and abs(n.value) <= 1e6
        ):
            return n.value
        if isinstance(n, ast.Name) and n.id in ("x", "t", "pi", "e"):
            return {"x": x, "t": x, "pi": np.pi, "e": np.e}[n.id]
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.UAdd, ast.USub)):
            return walk(n.operand) * (-1 if isinstance(n.op, ast.USub) else 1)
        if isinstance(n, ast.BinOp) and isinstance(
            n.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)
        ):
            a, b = walk(n.left), walk(n.right)
            if isinstance(n.op, ast.Pow):
                if not np.isscalar(b) or abs(b) > 50:
                    raise ValueError("أس غير مدعوم؛ استخدم قيمة ثابتة بين -50 و50")
                return np.power(a, b)
            if isinstance(n.op, ast.Add):
                return a + b
            if isinstance(n.op, ast.Sub):
                return a - b
            if isinstance(n.op, ast.Mult):
                return a * b
            return a / b
        if (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id in FUNCTIONS
            and len(n.args) == 1
            and not n.keywords
        ):
            return FUNCTIONS[n.func.id](walk(n.args[0]))
        raise ValueError("الدالة تحتوي تعبيرًا غير مدعوم")

    with np.errstate(all="ignore"):
        y = np.asarray(walk(tree), dtype=float)
    y = np.broadcast_to(y, x.shape)
    if not np.isfinite(y).any():
        raise ValueError("لا توجد قيم حقيقية منتهية ضمن مجال الرسم")
    return np.where(np.isfinite(y), y, np.nan)


def label_vector(value, width, color, prefix, size=26):
    """Shape mixed Arabic/Latin with MuPDF's HarfBuzz HTML engine.

    Text becomes SVG paths, so both Word's SVG and Cairo's PNG fallback have the
    same joined glyphs. No reshaping/reversing source strings or font fallback.
    """
    css = f"""@font-face {{font-family:label;src:url(Cairo-Regular.ttf)}}
    body {{font-family:label;font-size:{size}pt;line-height:1.25;
    text-align:center;color:{color};margin:0;padding:0}}"""
    with fitz.open() as pdf:
        page = pdf.new_page(width=width, height=1000)
        rtl = bool(re.search(r"[\u0600-\u06ff]", value))
        shaped = "".join(
            (
                ('<span dir="ltr">\u2066' + escape(chunk) + "\u2069</span>")
                if ltr
                else escape(chunk)
            )
            for ltr, chunk in direction_runs(value)
        )
        spare, scale = page.insert_htmlbox(
            page.rect,
            '<div dir="' + ("rtl" if rtl else "ltr") + '">' + shaped + "</div>",
            css=css,
            archive=fitz.Archive(str(store.ROOT / "assets/fonts")),
            scale_low=1,
        )
        if spare < 0 or scale != 1:
            raise ValueError("تسمية الرسم طويلة جدًا؛ راجع مواصفات الرسم")
        height = max(size * 1.25, page.rect.height - spare)
        root = etree.fromstring(page.get_svg_image(text_as_path=True).encode())
    # SVG identifiers share one namespace, even inside nested svg elements.
    for node in root.iter():
        if node.get("id"):
            node.set("id", prefix + node.get("id"))
        for attr in list(node.attrib):
            value = node.get(attr)
            if attr.endswith("href") and value.startswith("#"):
                node.set(attr, "#" + prefix + value[1:])
            elif "url(#" in value:
                node.set(attr, value.replace("url(#", "url(#" + prefix))
    root.set("stroke", "none")
    root.set("height", str(height))
    root.set("viewBox", f"0 0 {width} {height}")
    return root, height


def diagram(spec, color, light):
    nodes = {n.id: n for n in spec.nodes}
    boxes, labels = {}, {}
    bounds = []
    for i, n in enumerate(spec.nodes):
        distance = min(
            (math.hypot(n.x - v.x, n.y - v.y) for v in spec.nodes if v.id != n.id),
            default=450,
        )
        if distance < 65:
            raise ValueError("العقد متقاربة؛ وسّع مسافة الرسم إلى 65 على الأقل")
        width = max(72, min(260, distance * 0.68))
        label, height = label_vector(n.label, width - 20, color, f"n{i}-")
        box_height = max(52, height + 20)
        boxes[n.id] = (width, box_height)
        labels[n.id] = label
        label.set("x", str(n.x - (width - 20) / 2))
        label.set(
            "y", str(n.y - height / 2 if spec.kind == "block_diagram" else n.y + 10)
        )
        bounds.append(
            (
                n.x - width / 2,
                n.y - box_height / 2,
                n.x + width / 2,
                n.y + box_height / 2 + (height if spec.kind == "circuit" else 0),
            )
        )
    xmin = min(v[0] for v in bounds) - 20
    ymin = min(v[1] for v in bounds) - 50
    xmax = max(v[2] for v in bounds) + 20
    ymax = max(v[3] for v in bounds) + 20
    width, height = xmax - xmin, ymax - ymin
    items = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="{xmin} {ymin} {width} {height}"><title>{escape(spec.kind)}</title><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8 Z" fill="{color}"/></marker></defs><g stroke="{color}" stroke-width="2" fill="none">'
    ]
    for edge in spec.edges:
        a, b = nodes[edge.start], nodes[edge.end]
        dx, dy = b.x - a.x, b.y - a.y
        distance = math.hypot(dx, dy)
        if distance < 65:
            raise ValueError("العقد متقاربة؛ وسّع مسافة الرسم إلى 65 على الأقل")
        if spec.kind == "block_diagram":
            # Edges attach to the rectangle boundary, including vertical connections.
            scale = min(
                boxes[a.id][0] / 2 / abs(dx) if dx else float("inf"),
                boxes[a.id][1] / 2 / abs(dy) if dy else float("inf"),
            )
            ax, ay = a.x + dx * scale, a.y + dy * scale
            bscale = min(
                boxes[b.id][0] / 2 / abs(dx) if dx else float("inf"),
                boxes[b.id][1] / 2 / abs(dy) if dy else float("inf"),
            )
            bx, by = b.x - dx * bscale, b.y - dy * bscale
            items.append(f'<path d="M{ax} {ay} L{bx} {by}" marker-end="url(#arrow)"/>')
        else:
            angle = math.degrees(math.atan2(dy, dx))
            center = distance / 2
            items.append(
                f'<g transform="translate({a.x} {a.y}) rotate({angle})"><path d="M0 0 H{center-23} M{center+23} 0 H{distance}"/>'
            )
            if edge.kind in ("wire", "arrow"):
                marker = ' marker-end="url(#arrow)"' if edge.kind == "arrow" else ""
                items.append(f'<path d="M{center-23} 0 H{center+23}"{marker}/>')
            elif edge.kind == "resistor":
                items.append(
                    f'<path d="M{center-23} 0 l5 -8 7 16 7 -16 7 16 7 -16 7 16 6 -8"/>'
                )
            elif edge.kind == "capacitor":
                items.append(
                    f'<path d="M{center-23} 0 H{center-5} M{center-5} -15 V15 M{center+5} -15 V15 M{center+5} 0 H{center+23}"/>'
                )
            elif edge.kind == "inductor":
                items.append(
                    f'<path d="M{center-23} 0 c0 -20 12 -20 12 0 c0 -20 12 -20 12 0 c0 -20 12 -20 12 0 c0 -20 10 -20 10 0"/>'
                )
            elif edge.kind == "voltage":
                items.append(
                    f'<circle cx="{center}" cy="0" r="23"/><path d="M{center-4} -9 h8 M{center} -13 v8 M{center-4} 10 h8"/>'
                )
            items.append("</g>")
        if edge.label:
            label, lh = label_vector(
                edge.label,
                max(140, min(300, distance * 0.7)),
                color,
                f"e{spec.edges.index(edge)}-",
                size=24,
            )
            label.set("x", str((a.x + b.x) / 2 - float(label.get("width")) / 2))
            label.set("y", str((a.y + b.y) / 2 - lh - 12))
            items.append(etree.tostring(label, encoding="unicode"))
    for n in spec.nodes:
        width, height = boxes[n.id]
        if spec.kind == "block_diagram":
            items.append(
                f'<rect x="{n.x-width/2}" y="{n.y-height/2}" width="{width}" height="{height}" rx="4" fill="{light}"/>'
            )
        else:
            items.append(f'<circle cx="{n.x}" cy="{n.y}" r="3" fill="{color}"/>')
        items.append(etree.tostring(labels[n.id], encoding="unicode"))
    return "".join(items) + "</g></svg>"


def render(block: Block, palette: str):
    validate_theme(palette)
    spec = block.figure
    if not spec:
        raise ValueError("مواصفات الرسم غير موجودة")
    # Source crops keep their original colors and share one cache entry across themes.
    color_key = "source" if spec.kind == "source_crop" else palette
    style_key = "v11-academic-layout" if spec.kind == "source_crop" else "v12-cairo-type"
    if spec.kind == "control_diagram":
        style_key = "aq04-control-v2"
    if IS_WINDOWS:
        style_key += "-windows-raster-v1"
    key = hashlib.sha256(
        (block.model_dump_json() + color_key + style_key).encode()
    ).hexdigest()
    svg = store.DATA / "figures" / f"{key}.svg"
    png = svg.with_suffix(".png")
    if svg.exists() and png.exists():
        return svg, png
    dark, medium, light = PALETTES[palette]
    if spec.kind == "control_diagram":
        from .control_diagrams import diagram as control_diagram
        svg.write_text(control_diagram(spec.control), encoding="utf-8")
    elif spec.kind in ("block_diagram", "circuit"):
        svg.write_text(diagram(spec, dark, light), encoding="utf-8")
    elif spec.kind == "source_crop":
        ref = block.refs[0]
        with fitz.open(store.source_path(ref.source_id)) as pdf:
            page = pdf[ref.page - 1]
            c = spec.crop or [0, 0, 1, 1]
            rect = fitz.Rect(
                c[0] * page.rect.width,
                c[1] * page.rect.height,
                c[2] * page.rect.width,
                c[3] * page.rect.height,
            )
            pix = page.get_pixmap(clip=rect, dpi=180)
        data = base64.b64encode(pix.tobytes("png")).decode()
        if IS_WINDOWS:
            png.write_bytes(pix.tobytes("png"))
        svg.write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{pix.width}" height="{pix.height}" viewBox="0 0 {pix.width} {pix.height}"><image width="100%" height="100%" xlink:href="data:image/png;base64,{data}"/></svg>', encoding="utf-8"
        )
    else:
        with plt.rc_context(
            {
                "font.family": CONTENT_HEADING,
                "svg.fonttype": "path",
                "font.size": 14,
                "axes.spines.top": False,
                "axes.spines.right": False,
            }
        ):
            fig, ax = plt.subplots(figsize=(7, 2.65), layout="constrained")
            try:
                ax.set_axisbelow(True)
                ax.grid(alpha=0.18, color=dark)
                ax.axhline(0, color="#555555", lw=0.7)
                ax.axvline(0, color="#555555", lw=0.7)

                def axis_label(value):
                    return (
                        "$" + value + "$"
                        if value.startswith("\\") and "$" not in value
                        else value
                    )

                ax.set_xlabel(axis_label(spec.xlabel))
                ax.set_ylabel(axis_label(spec.ylabel))
                x = np.linspace(spec.xmin, spec.xmax, 600)
                if spec.kind == "step":
                    ax.plot([spec.xmin, 0], [0, 0], color=dark, lw=2)
                    ax.plot([0, spec.xmax], [1, 1], color=dark, lw=2)
                    ax.plot(0, 0, "o", mfc="white", mec=dark)
                    ax.plot(0, 1, "o", color=dark)
                    ax.set_ylim(-0.2, 1.35)
                elif spec.kind == "ramp":
                    ax.plot(x, np.maximum(x, 0), color=dark, lw=2)
                elif spec.kind == "impulse":
                    ax.annotate(
                        "",
                        xy=(0, 1),
                        xytext=(0, 0),
                        arrowprops={"arrowstyle": "-|>", "color": dark, "lw": 2},
                    )
                    ax.text(0.08, 1, "unit area", color=dark)
                    ax.set_ylim(-0.15, 1.3)
                    ax.set_yticks([0])
                elif spec.kind in ("plot", "scatter"):
                    for i, s in enumerate(spec.series):
                        xx = x if s.expression else np.array(s.x)
                        yy = (
                            evaluate(s.expression, xx)
                            if s.expression
                            else np.array(s.y)
                        )
                        if spec.kind == "scatter":
                            ax.scatter(
                                xx,
                                yy,
                                label=s.label,
                                color=dark,
                                marker=["o", "s", "^", "x", "D", "v", "+", "P"][i],
                            )
                        else:
                            ax.plot(
                                xx,
                                yy,
                                label=s.label,
                                color=dark,
                                ls=s.style,
                                lw=1.8,
                                alpha=max(0.75, 1 - i * 0.035),
                                marker=[None, "o", "s", "^", "D", "v", "x", "+"][i],
                                markevery=max(1, len(xx) // 12),
                                markersize=4,
                            )
                    if any(s.label for s in spec.series):
                        ax.legend()
                elif spec.kind == "bar":
                    ax.bar(
                        spec.labels,
                        spec.values,
                        color=light,
                        edgecolor=dark,
                        hatch="//",
                    )
                elif spec.kind == "histogram":
                    ax.hist(spec.values, bins=spec.bins, color=light, edgecolor=dark)
                if spec.kind not in ("bar", "histogram", "scatter"):
                    ax.set_xlim(spec.xmin, spec.xmax)
                fig.savefig(svg, format="svg")
                if IS_WINDOWS:
                    # Agg honors Matplotlib transparency/hatching directly; do
                    # not reinterpret its SVG in a limited SVG rasterizer.
                    fig.savefig(png, format="png", dpi=1800 / fig.get_figwidth())
            finally:
                plt.close(fig)
    if not IS_WINDOWS or spec.kind in ("block_diagram", "circuit", "control_diagram"):
        png.write_bytes(svg_png(svg.read_bytes(), output_width=1800))
    return svg, png
