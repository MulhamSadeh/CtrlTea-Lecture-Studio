راجع UPDATE_GUIDE_AR.md لتحديثات الاتجاه والمعادلات والتخطيط واستيراد Word. لم تُشغّل اختبارات على هذا التحديث.

# تشغيل Ctrl+Tea على Windows

هذه حزمة تشغيل معدّلة لـ **Windows 10/11 — x64**، وليست ملف EXE مستقلًا. تحتاج الإنترنت عند التثبيت الأول. الواجهة المبنية والخطوط مرفقة، ولا تحتاج تثبيت Node.js أو Nix.

## أول تشغيل

1. فك ZIP كاملًا في مجلد تملك صلاحية الكتابة فيه، مثل `Documents\CtrlTea`. لا تشغّله من داخل الأرشيف أو من `Program Files`.
2. انقر مرتين على **Install-Windows.cmd**. يجهّز Python 3.12 وبيئة `.venv` ومكتبات التطبيق، ويثبت البرامج الناقصة بواسطة WinGet: Pandoc وLibreOffice الكامل وTesseract. قد يطلب Windows موافقة صلاحيات لتثبيت هذه البرامج.
3. يحمّل ملفات OCR العربية والإنكليزية من مشروع Tesseract الرسمي إلى `.tools\tessdata`، ويثبت الخطوط المرفقة للمستخدم الحالي. لا يغيّر إعداد Execution Policy العام للجهاز.
4. ينفّذ فحصًا فعليًا للخطوط وOCR وتصدير DOCX وPDF بمعادلات أصلية. عند نجاحه افتح **Start-Windows.cmd**؛ يفتح المتصفح بعد جاهزية الخادم على `http://127.0.0.1:8765`.
5. أبقِ نافذة التشغيل مفتوحة. لإيقاف الخادم استخدم `Ctrl+C` ثم أغلقها. في المرات التالية يكفي `Start-Windows.cmd`.

للتشخيص افتح **Check-Windows.cmd**. التقرير في `output\windows-check\report.json`، ومعه `Native_Math_Check.docx` وPDF للفحص البصري على جهازك. فشل الفحص يوقف إعلان نجاح التثبيت ويعرض السبب؛ لا يستبدل المعادلات بصور.

## تحديث مشروع قائم

أغلق البرنامج واحتفظ بنسخة احتياطية من `data`، ثم انقل مجلد `data` إلى مجلد النسخة الجديدة أو حدّث ملفات البرنامج مع الإبقاء عليه. لا تنقل `.venv` من Linux إلى Windows؛ كل نظام يحتاج بيئته. شغّل التثبيت مرة على ويندوز، ثم أعد التصدير من الداشبورد. لا تحتاج إعادة التأليف. يمكن نقل أعمال الفريق بالطريقة المعتادة: تصدير المشروع واستعادته.

## إذا لم يتوفر WinGet

ثبّت **App Installer** من Microsoft Store، ثم أعد فتح `Install-Windows.cmd`. أو ثبّت Python 3.12 x64 وPandoc وLibreOffice الكامل وTesseract يدويًا من مصادرهم الرسمية، ثم أعد تشغيل ملف التثبيت. الخطأ في تثبيت أحد البرامج يظهر باسمه؛ لا تُحذف بيانات المحاضرات.

المراجع الرسمية:

- Python: https://www.python.org/downloads/windows/
- Pandoc: https://pandoc.org/installing.html
- LibreOffice: https://www.libreoffice.org/download/download-libreoffice/
- Tesseract لويندوز: https://github.com/UB-Mannheim/tesseract/wiki
- نماذج اللغات: https://github.com/tesseract-ocr/tessdata_fast/tree/4.1.0

## مسارات مخصصة — عند الحاجة فقط

يكتشف التطبيق الأدوات من PATH ومن المجلدات المعتادة في Program Files وLocalAppData. عند التثبيت في مكان مختلف يمكن تحديد ملف البرنامج نفسه بمتغير بيئة، مثل PowerShell:

```powershell
$env:CTRLTEA_LIBREOFFICE = 'D:\Apps\LibreOffice\program\soffice.com'
$env:CTRLTEA_PANDOC = 'D:\Apps\Pandoc\pandoc.exe'
$env:CTRLTEA_TESSERACT = 'D:\Apps\Tesseract-OCR\tesseract.exe'
.\.venv\Scripts\python.exe scripts\start.py --open-browser
```

لملفات اللغات المخصصة استعمل `CTRLTEA_TESSDATA_DIR` لمجلد يحوي `ara.traineddata` و`eng.traineddata`. ولمنفذ مختلف: `.\.venv\Scripts\python.exe scripts\start.py --port 8766 --open-browser`.

## ما تغير وما بقي

- اكتشاف مسارات البرامج واستدعاء `soffice.com` المناسب للعمليات الطرفية على ويندوز.
- التعامل الصريح مع UTF-8 في تقارير التصدير وOCR وSVG؛ تدعم المسارات فراغات وأسماء عربية.
- على Windows تُحفظ صور المخططات مباشرة من Matplotlib للمحافظة على الشفافية وأنماط الخطوط. وتُصيّر صور الرسومات البسيطة وخلفية الفوتر عبر PyMuPDF الموجود أصلًا، وتُحفظ صور المصادر كما هي؛ لا حاجة لمكتبات Cairo الخارجية. الرسم العلمي الأصلي يظل SVG داخل DOCX. لينكس يظل يستخدم CairoSVG.
- المعادلات تظل LaTeX في البيانات وOMML أصلية قابلة للتعديل في Word. لا تتحول إلى صور. لم تتغير البيانات العلمية أو Schema أو الألوان أو الغلاف أو قاعدة البيانات.
- ملفات Windows الإضافية لا تستبدل طريقة تشغيل Linux أو NixOS.

## حدود الاختبار

أُجريت اختبارات الانحدار في بيئة Linux، مع اختبارات مسارات Windows وعرض SVG البديل، وتحقّق توافر حزم Python الثنائية لـWindows x64/Python 3.12. فُحص تركيب PowerShell آليًا. **لم يتوفر جهاز Windows أو Microsoft Word**، لذلك لا ندّعي اختبار WinGet أو سجل الخطوط أو تثبيت النظام فعليًا، ولا تطابق صفحات Microsoft Word. الفحص المرفق يختبر هذه الاعتماديات ومسار LibreOffice على جهازك قبل الاستخدام؛ راجع PDF الناتج أيضًا. يبقى PDF التطبيق مرجع الطباعة.
