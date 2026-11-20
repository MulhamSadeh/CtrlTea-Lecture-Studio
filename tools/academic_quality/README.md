# CtrlTea deterministic validators — AQ06 1.0.0

طبقة محلية مستقلة، للقراءة والفحص فقط. نجاح أي فحص لا يثبت الصحة العلمية الشاملة. لا تعديل للمحاضرة، لا اتصال بنموذج، ولا اعتماد بشري آلي.

## تشغيل

Python 3.10+، والتبعيات في requirements.txt. تستعمل فحوص التطبيق بيئة AQ04 المثبتة وتبعياتها؛ تثبيت هذه الحزمة وحدها لا يثبت التطبيق. LibreOffice وPandoc اختياريان بحسب نوع الفحص. غياب التبعية المطلوبة يعيد unverified حيث أمكن؛ لا يصنف نجاحًا.

```sh
python -m pip install -r requirements.txt
python validate.py lecture.docx --meta metadata.json --preview previews --output review.json --app-root /path/to/ctrltea-studio
python validate.py lecture.pdf --meta metadata.json --output pdf-report.json
python validate.py fixtures/math.json --app-root /path/to/ctrltea-studio --output math-report.json
python validate.py existing-review.json --mode review --output integrity.json
```

عند وجود الحزمة داخل المشروع في tools/academic_quality يكتشف موضع backend تلقائيًا. الحزمة المنفردة تحتاج --app-root عند طلب مدققات التطبيق. متغير البيئة AQ06_APP_ROOT يحدد مسار التطبيق للاختبارات.

الاكتشاف يعتمد ترويسة PDF ومحتويات ZIP/Word وترويسات الصور وجذر JSON. الأوضاع: diagram, docx, pdf, structured, math, review, score, code. VHDL يكتشف بالامتداد ثم يجرد التعريفات دون تشغيله. `--checks` يحدد مجموعات الأوضاع المطلوبة، وليس كل دالة داخل المجموعة. المجموعة غير المعروفة تظهر unverified ولا تختفي. مسار --output يجب أن يكون جديدًا، ويتولد بجانبه ملف .json.md موجز. exit 1 يعني وجود fail، وexit 0 يعني عدم وجود fail، **ولا يعني اكتمال التحقق**؛ راجع unverified وwarning دائمًا.

Python API:

```python
from ctrltea_validators import validate, attach_evidence
report = validate('lecture.pdf', meta={'expected_pages': 5})
# attach_evidence(old_review, report) requires exactly the same document hash.
```

## بيانات جانبية مستقلة عن schema المحاضرة

```json
{
  "provenance": "generated",
  "expected_omml": 14,
  "expected_pages": 8,
  "images": {"word/media/image1.png": "source_crop"},
  "tables": {"0": [["x", "value"], ["x", "1"]]},
  "code_blocks": [{"id": "demo", "start": "ENTITY split_demo IS", "end": "END rtl;"}],
  "docx": "/absolute/path/matching.docx"
}
```

قيم المنشأ: generated/reconstructed/source_crop/photograph/unrelated/unknown. التصنيف تصريح مقدم من المحرر وليس استنتاجًا من اللون. قصاصات الأصل معفاة من **فحص نمط التوليد فقط**، ولا تصبح صحيحة علميًا بذلك. جدول images يستعمل أسماء ZIP الفعلية، وكل أصل SVG وPNG بديل يفحص منفصلًا. قارن نتائج الأصول ولا تعد المشكلة ذاتها خطأين علميين مستقلين.

اختياريًا: sources قائمة {id,path,sha256,pages,exact_excerpt} للتحقق من وجود الملف والبصمة وصفحات PDF ومقتطف حرفي من TXT/MD. المسارات صريحة محلية؛ لا جلب URLs. source_pages قائمة صفوف source_id,number,raw,corrected,excluded كما في المصدر الفعال للتطبيق؛ تستخدم لتشغيل source_warnings في عملية مؤقتة دون قاعدة بيانات حية. manifest المقدم يمرر لمدقق result.json. expected_control عقد ControlDiagram مرجعي صريح يقارن بالهيكل الفعلي؛ المقارنة لا تستخرج التوصيلات من صورة.

## الرياضيات

fixtures/math.json يوضح عمليات row باستعمال check_math.py الأصلي، fraction بكسور دقيقة، feedback بإشارة + أو −، وidentity بالضرب التبادلي لكثيرات الحدود. substitution يقبل expression ذات numerator/denominator وقيمة value وexpected. معاملات كثيرات الحدود بترتيب القوى التصاعدي، أعداد صحيحة أو سلاسل كسور، حتى 64 معاملًا في العمليات الداخلية. لا eval ولا sympify لنص قادم من المحاضرة. التكافؤ محصور في توابع كسرية محددة المجال؛ المقامات الأصلية ومقام الحلقة يجب ألا تكون صفرًا. تحقق نقطة عددية لا يثبت هوية عامة. درجات المعادلات العامة وقيود الرموز خارج هذه الصيغة unverified.

## ما يثبته كل فحص

- النموذج/الهندسة: يعيد استخدام AQ04، بما فيه control_geometry والتحقق من المنافذ والتقاطعات؛ لا يثبت اختيار الفرع الصحيح من المصدر إلا بمقارنة مرجعية صريحة.
- math_render: نفس math_errors/OMML، مع cache مؤقت؛ لا يثبت الحساب. PDF math يعيد استخدام فحص tags والتوكنات والحبر من pdf_math، وليس بديلًا عن قراءة الاشتقاق.
- الصور: RGB=0 تمامًا لكل بكسل alpha>0؛ لون البكسلات الشفافة مهمل. لا سماحية رمادية خفية. خلفية معتمة أو مساحة بيضاء كبيرة تفشل؛ وجود قناة alpha وحده لا يكفي. فحص حافة شفافة بنسبة 95% قرينة خارجية موثقة، ولا يفسر الأشكال الداخلية علميًا. SVG يُصيّر في CairoSVG ضمن 1000×1000؛ CSS موروث وmarkers/use تُفحص في الناتج. الفلاتر والتدرجات والتحريك unverified. العناصر الدقيقة جدًا قد تفوت التصيير، ولا يوجد اعتماد عام لكل SVG.
- DOCX: OMML والجداول والروابط والعناوين والعلاقات ونسب الصور؛ الدمج المعقد واتجاه النص وتنسيق الكود تحتاج مراجعة بصرية. الفرق في نسبة الصورة فوق 2% warning وليس خطأً علميًا مؤكدًا.
- PDF: عدد الصفحات مقابل مرجع معتمد؛ كثافة الحبر المنخفضة warning فقط؛ انقسام كود بمعلمين صريحين warning. القص والأسهم المفقودة وتسميات غير مقروءة تحتاج مصادر وفحصًا بصريًا وتبقى unverified.

## الحماية والحدود

المحولات تعمل في عمليات مؤقتة بمهلة 45 ثانية وحد CPU/ذاكرة/حجم على POSIX. لا تنفذ أكواد المحاضرات، ولا VHDL المرفوع. التصيير بملف تعريف LibreOffice مؤقت ومهلة 60 ثانية؛ ملفات تحوي ماكرو أو كائنات مضمّنة أو مصادر خارجية غير الروابط لا تُصيّر. هذه حدود عملية وليست sandbox أمنيًا عامًا أو شهادة Windows. SVG لا يجلب مراجع خارجية؛ يسمح بترويسة DOCTYPE القياسية دون تحميلها، ويمنع entities/المجموعة الداخلية.

خطوط CairoSVG ونسخة LibreOffice تؤثر في العرض. حين يتعذر الفحص يذكر التقرير ذلك. ملفات الأدلة الأولى قد تحتوي إخفاقات التطوير؛ التقارير المسماة final وملفات JUnit النهائية هي مرجع التسليم.

## الاختبارات

```sh
AQ06_APP_ROOT=/path/to/ctrltea-studio python -m pytest tests -q
```

pytest مطلوب للتطوير فقط. vendor/ctrltea-lecture-reviewer نسخة AQ05 غير معدلة من الأرشيف المتحقق، مع عقده وحاسباته. لا تعني إضافتها إلى الحزمة استبدال المهارة الشخصية أو تغيير التقييمات السابقة.
