"""Import editable Word content into the studio's semantic blocks.

Formatting is intentionally restyled by the studio. Unsupported objects are
reported before the user adds the parsed sections to the lecture.
"""
import io
import json
import subprocess
import tempfile
import zipfile
from pathlib import Path
from .models import Section, Block
from .runtime import find_binary, tool_environment


def parse(data, name):
    if len(data) > 40 * 1024 * 1024:
        raise ValueError('ملف Word أكبر من 40 ميغابايت')
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as package:
            if 'word/document.xml' not in package.namelist():
                raise ValueError('الملف ليس مستند DOCX')
            if sum(info.file_size for info in package.infolist()) > 200 * 1024 * 1024:
                raise ValueError('محتوى DOCX بعد فك الضغط أكبر من الحد المسموح')
            xml = package.read('word/document.xml')
    except zipfile.BadZipFile as error:
        raise ValueError('ملف DOCX غير صالح أو غير مكتمل') from error
    warnings = []
    if b'<w:ins' in xml or b'<w:del' in xml:
        warnings.append('يتضمن الملف تعقب تغييرات؛ يعرض الاستيراد النص بعد قبول التغييرات. راجع الأصل قبل الإضافة.')
    with tempfile.TemporaryDirectory(prefix='ctrltea-word-') as directory:
        target = Path(directory) / 'input.docx'
        target.write_bytes(data)
        result = subprocess.run([find_binary('pandoc'), str(target), '--from=docx', '--to=json', '--track-changes=accept'],
                                capture_output=True, env=tool_environment(), timeout=90)
    if result.returncode:
        raise ValueError('تعذر استيراد Word: ' + result.stderr.decode(errors='replace')[-500:])
    ast = json.loads(result.stdout)
    if result.stderr.strip():
        warnings.append(result.stderr.decode(errors='replace')[-700:])
    sections = [Section(title=Path(name).stem)]

    def inline(items):
        chunks = []
        for item in items:
            kind, value = item['t'], item.get('c')
            if kind == 'Str': chunks.append(value)
            elif kind in ('Space', 'SoftBreak'): chunks.append(' ')
            elif kind == 'LineBreak': chunks.append('\n')
            elif kind == 'Math': chunks.append('\\(' + value[1] + '\\)')
            elif kind == 'Code': chunks.append(value[1])
            elif kind in ('Emph','Strong','Strikeout','Underline','SmallCaps','Superscript','Subscript'):
                chunks.append(inline(value))
            elif kind in ('Span','Link'): chunks.append(inline(value[1]))
            elif kind == 'Quoted': chunks.append('«' + inline(value[1]) + '»')
            elif kind == 'Image':
                warnings.append('صورة أو معادلة مصوّرة موجودة في الأصل لم تتحول إلى عنصر قابل للتحرير. أضفها من المصدر بعد الاستيراد.')
                chunks.append('[صورة في ملف Word الأصلي: ' + (inline(value[1]) or 'دون وصف') + ']')
            elif kind == 'Note':
                chunks.append(' (' + block_text(value) + ')')
            elif kind not in ('RawInline',):
                warnings.append('عنصر نصي يحتاج مراجعة: ' + kind)
        return ''.join(chunks)

    def block_text(blocks):
        return '\n'.join(inline(v.get('c', [])) for v in blocks if v['t'] in ('Para','Plain'))

    def add(block):
        sections[-1].blocks.append(block)

    def consume(blocks):
        for item in blocks:
            kind, value = item['t'], item.get('c')
            if kind == 'Header':
                title = inline(value[2])
                if not sections[-1].blocks and sections[-1].title == Path(name).stem:
                    sections[-1].title = title
                else:
                    sections.append(Section(title=title))
            elif kind in ('Para','Plain'):
                if len(value) == 1 and value[0]['t'] == 'Math' and value[0]['c'][0]['t'] == 'DisplayMath':
                    add(Block(kind='equation', latex=value[0]['c'][1]))
                else:
                    text = inline(value)
                    if text.strip(): add(Block(kind='explanation', text=text))
            elif kind in ('BulletList','OrderedList'):
                entries = value if kind == 'BulletList' else value[1]
                text = [block_text(entry) for entry in entries]
                if any(v.strip() for v in text):
                    add(Block(kind='list', items=[v for v in text if v.strip()], ordered=kind=='OrderedList'))
            elif kind == 'Table':
                # Pandoc 1.22+ Table: attr, caption, colspecs, head, bodies, foot.
                if len(value) != 6:
                    warnings.append('جدول بإصدار غير مدعوم؛ راجع ملف Word الأصلي.')
                    continue
                def row_cells(row):
                    row_values = []
                    for cell in row[1]:
                        if cell[2] != 1 or cell[3] != 1:
                            warnings.append('يتضمن الجدول خلايا مدمجة؛ راجع توزيعها بعد الاستيراد.')
                        row_values.append(block_text(cell[4]))
                        row_values.extend([''] * max(0, cell[3] - 1))
                    return row_values
                headers = [row_cells(row) for row in value[3][1]]
                rows = []
                for body in value[4]:
                    rows.extend(row_cells(row) for row in body[2] + body[3])
                rows.extend(row_cells(row) for row in value[5][1])
                if headers:
                    head = headers[0]
                    rows = headers[1:] + rows
                elif rows:
                    width = max(map(len, rows))
                    head = ['عمود ' + str(i + 1) for i in range(width)]
                    warnings.append('جدول دون صف رأس صريح؛ أضيفت أسماء أعمدة قابلة للتعديل مع الاحتفاظ بجميع صفوفه.')
                else:
                    continue
                width = max([len(head)] + [len(row) for row in rows])
                head += [''] * (width-len(head))
                rows = [row + [''] * (width-len(row)) for row in rows]
                add(Block(kind='table', headers=head, rows=rows))
            elif kind in ('Div','BlockQuote'):
                consume(value[1] if kind == 'Div' else value)
            elif kind == 'CodeBlock': add(Block(kind='example', text=value[1]))
            elif kind == 'HorizontalRule': pass
            else: warnings.append('عنصر يحتاج مراجعة في الأصل: ' + kind)
    consume(ast['blocks'])
    sections = [section for section in sections if section.blocks]
    if not sections:
        raise ValueError('لم يوجد نص أو جدول أو معادلة قابلة للاستيراد في هذا الملف')
    source_text = '\n\n'.join(section.title + '\n' + '\n'.join(
        b.text or b.latex or '\n'.join(b.items) or '\n'.join('\t'.join(row) for row in [b.headers,*b.rows])
        for b in section.blocks) for section in sections)
    return {'sections':[section.model_dump() for section in sections],
            'warnings':list(dict.fromkeys(warnings)), 'source_text':source_text}
