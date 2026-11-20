---
name: ctrltea-lecture-authoring
description: Author or revise Arabic university handouts from Ctrl+Tea lecture packets, generate result.json for import, and preserve source fidelity and manual edits. Use for lecture production and scoped revisions.
---

# تأليف ملزمة Ctrl+Tea · AQ-04 v1.2.0

اعمل على حزمة واحدة ومهمة واحدة من manifest.json في كل نتيجة. افتح instructions.txt إن وجد؛ استعمل قواعد إصدار الحزمة عند اختلاف النسخ. راجع schema.json وblock-fields.json وschema-examples.json لفهم العقد الفعلي. الأمثلة أشكال تقنية. اقرأ current.json والمصادر المعتمدة في sources وتحقق بصريًا من originals عند الحاجة.

1. حدّد دور كل مصدر وأولويته وصفحاته المدرجة. النص المصحح مقدّم على OCR. احصر مفاهيم المصدر الأساسي وشروطه وأسئلته وأمثلته وخطواته. استخدم الداعم لتوضيحها، واحفظ طريقة الأستاذ ورموزه وحدود المحاضرة. عند نقص دليل أو تعارض اقرأ [أمانة المصادر](references/source-fidelity.md).
2. اكتب ملزمة عربية تصلح للدراسة الفردية. اشرح سبب الانتقال بين الخطوات، واحفظ الحسابات والأمثلة، واختر نوع الكتلة الدلالي المناسب. احذف الحوار والحشو بحسب السياق. عند تحويل تفريغ أو إعادة تنظيم الشرح اقرأ [التحرير الأكاديمي](references/academic-writing.md).
3. حمّل [الرياضيات](references/math-authoring.md) عند وجود علاقة أو شرط أو حساب أو جدول عددي في المصدر أو المطلوب، و[الرسوم](references/scientific-diagrams.md) عندما يحتاج الفهم شكلًا، وعند وجود مخطط تحكم مدعوم اقرأ [جوامع ومسارات التحكم](references/control-diagrams.md)، و[الجداول والكود](references/tables-code.md) عند وجود جدول أو VHDL. طبّق تصميم القالب في المولّد، واحفظ المحتوى العلمي في JSON.
4. لكل معلومة مصدرية أرفق refs مع source_id وpage ومقتطف حرفي من النص المعتمد. ميّز instructor_example وbook_question وadditional_exercise وفق حقول العقد، وorigin=clarification للتوضيح. سؤال الكتاب الحرفي يتطلب verbatim=true وproblem يطابق quote. سجّل المشكلة العلمية في issue والمقترح في correction واترك issue_resolved=false للمراجعة البشرية.
5. اقرأ [التحرير والاستيراد](references/editing-and-import.md) عند تعديل عمل قائم أو تعارض نسخ. حافظ على المعرّفات والكتل خارج التعديل. أخرج run_id وsections للمهمة المحددة؛ new إشارة إنشاء، فاختر معرفات فريدة. لا تعلن complete=true لقسم ناقص.
6. شغّل في بيئة التطبيق من مجلد الحزمة:
   `python validate_result.py result.json --schema schema.json --manifest manifest.json`
   اشترط رمز خروج 0 وvalid=true. راجع التغطية والمقتطفات واقرأ معاينة الاستيراد وتعارضاتها قبل اعتماد التغيير. سلّم result.json بالصيغة المطلوبة؛ سجل نتيجة التحقق خارج JSON. إذا تعذر التنفيذ اذكر الفحص المعلق صراحة.
