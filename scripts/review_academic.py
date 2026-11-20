"""Compose an annotated, vector PDF comparison from actual lecture exports."""

from pathlib import Path
import argparse
from html import escape
import json

import fitz

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "assets/fonts"
CSS = """@font-face{font-family:ar;src:url(NotoSansArabic-Regular.ttf)}
@font-face{font-family:en;src:url(SourceSans3-Regular.ttf)}
body{font-family:ar,en;font-size:11pt;line-height:1.55;margin:0;color:#3d2d25}
b{color:#8b3f25} table{border-collapse:collapse;width:100%}td,th{border:1px solid #c77a45;padding:9pt;text-align:right}th{background:#f6e1d3}
"""


def arabic(page, rect, html, size=11):
    spare, scale = page.insert_htmlbox(
        rect,
        '<div dir="rtl">' + html + "</div>",
        css=CSS.replace("font-size:11pt", f"font-size:{size}pt"),
        archive=fitz.Archive(str(FONTS)),
        scale_low=1,
    )
    assert spare >= 0 and scale == 1, "Review annotation does not fit"


def report(output):
    output.parent.mkdir(parents=True, exist_ok=True)
    before = fitz.open(ROOT / "examples/references/CtrlTea_Lecture-before.pdf")
    modern = fitz.open(ROOT / "examples/academic-exports/Style_A_Modern.pdf")
    after = fitz.open(ROOT / "examples/academic-exports/CtrlTea_Lecture_Academic.pdf")
    evidence = json.loads((ROOT / "docs/academic-verification.json").read_text())
    result = fitz.open()
    width, height = fitz.paper_size("a3-l")

    def new_page(title, subtitle):
        p = result.new_page(width=width, height=height)
        p.draw_rect(p.rect, color=None, fill=(0.982, 0.974, 0.958))
        p.insert_font(fontname="ct-title", fontfile=str(FONTS / "SourceSans3-Bold.ttf"))
        p.insert_text(
            (30, 33), title, fontname="ct-title", fontsize=21, color=(0.30, 0.18, 0.12)
        )
        arabic(p, fitz.Rect(30, 43, width - 30, 91), subtitle)
        p.insert_text(
            (30, height - 10),
            f"Ctrl+Tea | Academic review | {len(result)}",
            fontname="ct-title",
            fontsize=9,
            color=(0.4, 0.35, 0.3),
        )
        return p

    def panel(p, source, index, rect, label, clip=None):
        p.insert_text(
            (rect.x0, rect.y0 + 14),
            label,
            fontname="ct-title",
            fontsize=13,
            color=(0.54, 0.25, 0.15),
        )
        box = fitz.Rect(rect.x0, rect.y0 + 23, rect.x1, rect.y1)
        p.show_pdf_page(box, source, index, clip=clip)

    left = fitz.Rect(30, 94, width / 2 - 15, height - 27)
    right = fitz.Rect(width / 2 + 15, 94, width - 30, height - 27)
    for title, subtitle, pa, pb in [
        (
            "01 | Font comparison — mixed prose and lists",
            "المصدر البنيوي نفسه للنمطين. كلاهما بعد إصلاح المحاذاة؛ اختير B لتوازن المتن مع الرياضيات والطابع الكتابي.",
            1,
            1,
        ),
        (
            "02 | Font comparison — rule, derivatives and diagram",
            "تظهر الفروق الطباعية على المعادلة والصندوق والتسميات. تغير الخط يعيد توزيع السطور دون تغيير النص أو مواصفات الرسم.",
            3,
            3,
        ),
        (
            "03 | Font comparison — worked solution",
            "الحل يستخدم ترقيم Word حقيقيًا، مع فصل السؤال والخطوات والنتيجة. لا توجد بادئات من نوع «مثال: مثال».",
            8,
            8,
        ),
    ]:
        p = new_page(title, subtitle)
        panel(p, modern, pa, left, "A · Noto Sans Arabic / Source Sans 3")
        panel(p, after, pb, right, "B · Noto Naskh Arabic / Source Serif 4")
    p = new_page(
        "04 | Before / after — Arabic spacing",
        "يسارًا PDF المرفق قبل الإصلاح، ويمينًا الناتج الجديد. أزيل التبرير المسبب للاستطالة، وتحولت أسطر التعداد إلى عناصر أصلية دون إعادة صياغة المحتوى.",
    )
    panel(p, before, 1, left, "Before · supplied PDF · page 2")
    panel(p, after, 1, right, "After · application PDF · page 2")
    p = new_page(
        "05 | Before / after — scientific diagram",
        "قُصت مساحة الرسم الفارغة حسابيًا من حدود عناصره، وشُكلت تسمياته العربية والإنكليزية كمسارات SVG. العقد والتوصيلات والمعادلات محفوظة.",
    )
    panel(p, before, 3, left, "Before · supplied PDF · page 4")
    panel(p, after, 3, right, "After · application PDF · page 4")
    p = new_page(
        "06 | Before / after — exercise pagination",
        "المقتطفان يسارًا من الصفحتين 9 و10 في الملف المرفق؛ الحل الجديد كامل في الصفحة 9. انتقلت علامة الختام إلى نهاية المحتوى بدل إنشاء صفحة إضافية.",
    )
    panel(
        p,
        before,
        8,
        fitz.Rect(30, 94, width / 2 - 15, 430),
        "Before · page 9, lower part",
        fitz.Rect(0, 480, 595, 799),
    )
    panel(
        p,
        before,
        9,
        fitz.Rect(30, 448, width / 2 - 15, 725),
        "Before · page 10, upper part",
        fitz.Rect(0, 0, 595, 220),
    )
    panel(p, after, 8, right, "After · page 9")
    p = new_page(
        "07 | Cover retained",
        "الشعار والشخصية والشريط والفوتر وهندسة الغلاف محفوظة. أثبت الفحص تطابق الغلاف والفوتر بكسليًا مع إعادة التصدير المحلية السابقة، دون تغيير هويتهما.",
    )
    panel(p, before, 0, left, "Before · supplied cover")
    panel(p, after, 0, right, "After · cover")
    p = new_page(
        "08 | Verification and limits",
        "هذه نتائج تنفيذ وفحص فعلية. لا تمثل اختبارات XML وحدها مراجعة علمية أو اختبار Microsoft Word.",
    )
    rows = [
        ("المحاضرة الحالية", "9 صفحات؛ 82 معادلة Word أصلية؛ 5 كتل رسومات"),
        (
            "حفظ المحتوى",
            "140 مقطع نص متحقق؛ جميع أشجار OMML متطابقة؛ JSON لم يُكتب أثناء التصدير",
        ),
        (
            "الوحدات والتكامل",
            f'{evidence["tests_passed"]} اختبارًا ناجحًا؛ يشمل الجداول والصندوق والتمرين الطويلين ومنع صفحة الخاتمة المنفردة',
        ),
        (
            "المسار من React",
            "9 حالات ثيم وتصدير لثلاث محاضرات؛ حفظ واستعادة وإعادة تشغيل الخادم؛ دون أخطاء JavaScript",
        ),
        (
            "حزمة التأليف",
            "تعليمات واحدة، Schema لكل نوع، مدقق مستقل؛ أخطاء واضحة قبل أي استيراد",
        ),
        (
            "عينة التأليف الحقيقية",
            "22 كتلة، 3 أقسام، 30 معادلة ورسمان؛ اجتازت الفحص بعد مراجعة واحدة من المؤلف",
        ),
        (
            "مصدر العينة",
            "مقتطف 32:15–35:30 من التفريغ الحقيقي؛ ألّفه النموذج الحالي، لا OpenCode",
        ),
        (
            "حدود الفحص",
            "LibreOffice وChromium متاحان؛ Microsoft Word وOpenCode وNixOS غير مختبرة في هذه البيئة",
        ),
    ]
    html = (
        "<table><tr><th>الفحص</th><th>النتيجة</th></tr>"
        + "".join(
            "<tr><td>" + escape(a) + "</td><td>" + escape(b) + "</td></tr>"
            for a, b in rows
        )
        + "</table><p>بقيت مشكلة تعريف نبضة ديراك في عينة التأليف قيد المراجعة ولم تعتمد بشريًا. الملزمة الحالية لم تُعد كتابتها؛ الفاحص البنيوي لا يثبت صحة جميع الادعاءات العلمية. التفاصيل وإعادة الفحص في docs/ACADEMIC_REVIEW_AR.md داخل المشروع.</p>"
    )
    arabic(p, fitz.Rect(60, 112, width - 60, height - 60), html, 13)
    result.set_metadata(
        {
            "title": "Ctrl+Tea — Academic Typography Review",
            "author": "Ctrl+Tea",
            "subject": "Actual before/after comparison and validation",
        }
    )
    result.save(output, garbage=4, deflate=True)
    # This is a rendered document comparison, not a browser screenshot.
    result[3].get_pixmap(dpi=110).save(output.with_name("Before_After_Arabic.png"))
    print(output, len(result))
    for d in [before, modern, after, result]:
        d.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=ROOT / "docs/Academic_Typography_Review.pdf"
    )
    report(parser.parse_args().output)
