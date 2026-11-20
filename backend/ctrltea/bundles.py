from __future__ import annotations

import io
import json
import zipfile
from pathlib import PurePosixPath
from . import store
from .models import LectureDocument, uid
from .theme import DEFAULT_THEME, validate_theme


def export_course(cid, lecture_ids=None):
    # One read transaction keeps documents, OCR pages and their revision history
    # on the same snapshot while the extraction worker may still be running.
    with store.connect(snapshot=True) as db:
        db.execute("BEGIN")
        def rows(sql, args=()):
            return [dict(row) for row in db.execute(sql, args)]
        courses = rows("SELECT * FROM courses WHERE id=?", (cid,))
        if not courses:
            raise LookupError("المادة غير موجودة")
        course = courses[0]
        lectures = rows("SELECT * FROM lectures WHERE course_id=? ORDER BY updated DESC,id", (cid,))
        if lecture_ids is not None:
            chosen = set(lecture_ids)
            if not chosen or not chosen <= {lecture["id"] for lecture in lectures}:
                raise ValueError("اختر محاضرة أو أكثر من هذه المادة")
            lectures = [lecture for lecture in lectures if lecture["id"] in chosen]
        sources, pages, revisions, runs, tasks, source_aliases, run_aliases = [], [], [], [], [], [], []
        for lecture in lectures:
            args = (lecture["id"],)
            sources.extend(rows("SELECT * FROM sources WHERE lecture_id=?", args))
            revisions.extend(rows("SELECT * FROM revisions WHERE lecture_id=?", args))
            runs.extend(rows("SELECT * FROM author_runs WHERE lecture_id=?", args))
            source_aliases.extend(rows("SELECT * FROM source_aliases WHERE lecture_id=?", args))
            run_aliases.extend(rows("SELECT * FROM run_aliases WHERE lecture_id=?", args))
        for source in sources:
            pages.extend(rows("SELECT * FROM pages WHERE source_id=?", (source["id"],)))
        for run in runs:
            tasks.extend(rows("SELECT * FROM author_tasks WHERE run_id=?", (run["id"],)))
    manifest = {
        "format": "ctrltea-project", "version": 1,
        "scope": "course" if lecture_ids is None else "lectures", "created": store.now(),
        "course": course, "lectures": lectures, "sources": sources, "pages": pages,
        "revisions": revisions, "author_runs": runs, "author_tasks": tasks,
        "source_aliases": source_aliases, "run_aliases": run_aliases,
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("project.json", json.dumps(manifest, ensure_ascii=False))
        for source in sources:
            archive.write(store.DATA / source["path"], source["path"])
    return output.getvalue()


def import_course(data, lecture_ids=None, target_course_id=None, target_lecture_id=None, expected_revision=None):
    with open_bundle(data) as z:
        data = select_lectures(read_manifest(z), lecture_ids)
        if target_lecture_id:
            return append_lecture(z, data, target_lecture_id, expected_revision)
        lid_map = {l["id"]: uid() for l in data["lectures"]}
        sid_map = {s["id"]: uid() for s in data["sources"]}
        run_map = {r["id"]: uid() for r in data.get("author_runs", [])}
        cid = target_course_id or uid()
        c = store.one("SELECT * FROM courses WHERE id=?", (cid,)) if target_course_id else data["course"]
        written = []

        def remap_document(raw):
            doc = json.loads(raw)
            for section in doc["sections"]:
                for block in section["blocks"]:
                    for ref in block.get("refs", []):
                        if ref["source_id"] not in sid_map:
                            raise ValueError("المشروع يشير إلى مصدر مفقود")
                        ref["source_id"] = sid_map[ref["source_id"]]
            return json.dumps(doc, ensure_ascii=False)

        try:
            with store.connect() as db:
                if not target_course_id:
                    db.execute(
                        "INSERT INTO courses VALUES(?,?,?,?)",
                        (cid, c["name"], c.get("doctor", ""), store.now()),
                    )
                for l in data["lectures"]:
                    db.execute(
                        "INSERT INTO lectures(id,course_id,title,doc,revision,updated,theme) VALUES(?,?,?,?,?,?,?)",
                        (
                            lid_map[l["id"]],
                            cid,
                            l["title"],
                            document_for_course(remap_document(l["doc"]), c["name"]),
                            l["revision"],
                            store.now(),
                            l.get("theme", DEFAULT_THEME),
                        ),
                    )
                for s in data["sources"]:
                    old = s["path"]
                    suffix = PurePosixPath(old).suffix
                    if not old.startswith("sources/") or suffix not in (".txt", ".md", ".pdf", ".docx"):
                        raise ValueError("ملف مصدر غير صالح داخل المشروع")
                    relative = f'sources/{sid_map[s["id"]]}{suffix}'
                    path = store.DATA / relative
                    path.write_bytes(z.read(old))
                    written.append(path)
                    db.execute(
                        "INSERT INTO sources VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (
                            sid_map[s["id"]],
                            lid_map[s["lecture_id"]],
                            s["name"],
                            relative,
                            s["kind"],
                            s["priority"],
                            s["role"],
                            sid_map.get(s["linked_id"]),
                            s["digest"],
                            s["created"],
                        ),
                    )
                for src in data["sources"]:
                    db.execute(
                        "INSERT INTO source_aliases VALUES(?,?,?)",
                        (lid_map[src["lecture_id"]], src["id"], sid_map[src["id"]]),
                    )
                for alias in data.get("source_aliases", []):
                    db.execute(
                        "INSERT OR REPLACE INTO source_aliases VALUES(?,?,?)",
                        (
                            lid_map[alias["lecture_id"]],
                            alias["original_id"],
                            sid_map[alias["source_id"]],
                        ),
                    )
                for run in data.get("author_runs", []):
                    db.execute(
                        "INSERT INTO author_runs VALUES(?,?,?,?,?,?)",
                        (
                            run_map[run["id"]],
                            lid_map[run["lecture_id"]],
                            run["section_ids"],
                            run["status"],
                            run["created"],
                            remap_document(run["base_doc"]),
                        ),
                    )
                    db.execute(
                        "INSERT INTO run_aliases VALUES(?,?,?)",
                        (lid_map[run["lecture_id"]], run["id"], run_map[run["id"]]),
                    )
                for alias in data.get("run_aliases", []):
                    db.execute(
                        "INSERT OR REPLACE INTO run_aliases VALUES(?,?,?)",
                        (
                            lid_map[alias["lecture_id"]],
                            alias["original_id"],
                            run_map[alias["run_id"]],
                        ),
                    )
                for task in data.get("author_tasks", []):
                    db.execute(
                        "INSERT INTO author_tasks VALUES(?,?,?)",
                        (run_map[task["run_id"]], task["section_id"], task["status"]),
                    )
                for p in data["pages"]:
                    db.execute(
                        "INSERT INTO pages VALUES(?,?,?,?,?,?)",
                        (
                            sid_map[p["source_id"]],
                            p["number"],
                            p["raw"],
                            p["corrected"],
                            p["excluded"],
                            p["method"],
                        ),
                    )
                for r in data.get("revisions", []):
                    legacy = store.persistence.backend() == "postgres"
                    sql = "INSERT INTO revisions(id,lecture_id,revision,doc,created,reason" + (",is_legacy" if legacy else "") + ") VALUES(?,?,?,?,?,?" + (",1" if legacy else "") + ")"
                    db.execute(
                        sql,
                        (
                            uid(),
                            lid_map[r["lecture_id"]],
                            r["revision"],
                            remap_document(r["doc"]),
                            r["created"],
                            r["reason"],
                        ),
                    )
        except BaseException:
            for p in written:
                p.unlink(missing_ok=True)
            raise
    return {"course_id": cid, "lectures": len(lid_map), "sources": len(sid_map),
            "lecture_ids": list(lid_map.values()), "mode": "new_lectures"}


MAX_BUNDLE = 220 * 1024 * 1024


def open_bundle(content):
    if not content or len(content) > MAX_BUNDLE:
        raise ValueError('حزمة البيانات فارغة أو أكبر من 220 ميغابايت')
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as error:
        raise ValueError('حزمة ZIP غير صالحة أو غير مكتملة') from error
    try:
        names = archive.namelist()
        if len(names) != len(set(names)) or len(names) > 20000:
            raise ValueError('الحزمة تتضمن مسارات مكررة أو عدد ملفات يتجاوز الحد المسموح')
        if sum(info.file_size for info in archive.infolist()) > 700 * 1024 * 1024:
            raise ValueError('محتويات الحزمة بعد فك الضغط أكبر من 700 ميغابايت')
        for name in names:
            path = PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
                raise ValueError('مسار غير صالح داخل حزمة البيانات')
        if 'project.json' not in names:
            raise ValueError('هذا الملف ليس حزمة بيانات Ctrl+Tea؛ اختر الحزمة المصدرة من تبادل البيانات')
        return archive
    except BaseException:
        archive.close()
        raise


def read_manifest(archive):
    import hashlib
    from pydantic import ValidationError
    try:
        if archive.getinfo('project.json').file_size > 80 * 1024 * 1024:
            raise ValueError('بيانات الحزمة أكبر من الحد المسموح')
        data = json.loads(archive.read('project.json'))
        if not isinstance(data, dict) or data.get('format') != 'ctrltea-project' or data.get('version') != 1:
            raise ValueError('صيغة حزمة البيانات غير مدعومة')
        if not isinstance(data['course']['name'], str):
            raise ValueError('اسم المادة غير صالح')
        for name in ('lectures','sources','pages'):
            if not isinstance(data[name], list):
                raise ValueError('بنية بيانات الحزمة غير صحيحة')
        for name in ('revisions','author_runs','author_tasks','source_aliases','run_aliases'):
            data.setdefault(name, [])
            if not isinstance(data[name], list):
                raise ValueError('بنية سجل الحزمة غير صحيحة')
        def identifiers(rows):
            ids = [row['id'] for row in rows]
            if any(not isinstance(value, str) or not value for value in ids) or len(ids) != len(set(ids)):
                raise ValueError('معرّفات مفقودة أو مكررة داخل الحزمة')
            return set(ids)
        lids, sids, runs = (identifiers(data[name]) for name in ('lectures','sources','author_runs'))
        owner = {source['id']:source['lecture_id'] for source in data['sources']}
        def document(raw, lid):
            doc = LectureDocument.model_validate_json(raw)
            if any(owner.get(ref.source_id) != lid for section in doc.sections for block in section.blocks for ref in block.refs):
                raise ValueError('المحاضرة تشير إلى مصدر مفقود أو إلى مصدر محاضرة أخرى')
        for lecture in data['lectures']:
            document(lecture['doc'], lecture['id'])
            validate_theme(lecture.get('theme', DEFAULT_THEME))
            if not isinstance(lecture['revision'], int) or lecture['revision'] < 0:
                raise ValueError('رقم نسخة المحاضرة غير صالح')
        for source in data['sources']:
            path = source['path']
            if source['lecture_id'] not in lids or not isinstance(path, str) or not path.startswith('sources/'):
                raise ValueError('ارتباط مصدر غير صالح داخل الحزمة')
            suffix = PurePosixPath(path).suffix
            if suffix not in ('.txt','.md','.pdf','.docx') or path not in archive.namelist():
                raise ValueError('ملف مصدر مفقود أو غير مدعوم: ' + source.get('name', ''))
            if hashlib.sha256(archive.read(path)).hexdigest() != source['digest']:
                raise ValueError('محتوى ملف المصدر لا يطابق الحزمة: ' + source.get('name', ''))
            if source.get('linked_id') and owner.get(source['linked_id']) != source['lecture_id']:
                raise ValueError('تفريغ مرتبط بمصدر مفقود أو غير تابع للمحاضرة')
        pages = set()
        for page in data['pages']:
            key = (page['source_id'], page['number'])
            if key in pages or key[0] not in sids or not isinstance(key[1], int) or key[1] < 1:
                raise ValueError('صفحات مكررة أو مرجع صفحة غير صالح')
            pages.add(key)
        for row in data['revisions']:
            if row['lecture_id'] not in lids:
                raise ValueError('سجل تعديل مرتبط بمحاضرة مفقودة')
            document(row['doc'], row['lecture_id'])
        run_owner = {run['id']:run['lecture_id'] for run in data['author_runs']}
        for run in data['author_runs']:
            if run['lecture_id'] not in lids:
                raise ValueError('مهمة تأليف مرتبطة بمحاضرة مفقودة')
            document(run['base_doc'], run['lecture_id'])
        if any(task['run_id'] not in runs for task in data['author_tasks']):
            raise ValueError('مهمة قسم مرتبطة بتأليف مفقود')
        for alias in data['source_aliases']:
            if alias['lecture_id'] not in lids or owner.get(alias['source_id']) != alias['lecture_id']:
                raise ValueError('ربط معرّف مصدر غير صالح')
        for alias in data['run_aliases']:
            if alias['lecture_id'] not in lids or run_owner.get(alias['run_id']) != alias['lecture_id']:
                raise ValueError('ربط معرّف تأليف غير صالح')
        return data
    except (KeyError, TypeError, ValidationError, json.JSONDecodeError, UnicodeDecodeError, zipfile.BadZipFile) as error:
        raise ValueError('بيانات الحزمة غير مكتملة أو غير صالحة؛ أعد تصديرها من الجهاز المرسل') from error


def select_lectures(data, lecture_ids):
    if lecture_ids is None:
        return data
    selected = set(lecture_ids)
    if not selected or not selected <= {lecture['id'] for lecture in data['lectures']}:
        raise ValueError('اختر محاضرة أو أكثر موجودة في الحزمة')
    result = dict(data)
    for name in ('lectures','sources','revisions','author_runs','source_aliases','run_aliases'):
        result[name] = [row for row in data[name] if row['id' if name == 'lectures' else 'lecture_id'] in selected]
    sources = {source['id'] for source in result['sources']}
    runs = {run['id'] for run in result['author_runs']}
    result['pages'] = [row for row in data['pages'] if row['source_id'] in sources]
    result['author_tasks'] = [row for row in data['author_tasks'] if row['run_id'] in runs]
    return result


def document_for_course(raw, name):
    document = json.loads(raw)
    document['course'] = name
    return json.dumps(document, ensure_ascii=False)


def preview_bundle(content):
    with open_bundle(content) as archive:
        data = read_manifest(archive)
    lectures = []
    for lecture in data['lectures']:
        document = json.loads(lecture['doc'])
        lectures.append({'id':lecture['id'], 'title':lecture['title'], 'revision':lecture['revision'],
                         'sections':len(document['sections']),
                         'sources':sum(source['lecture_id'] == lecture['id'] for source in data['sources'])})
    return {'course':{'name':data['course']['name'], 'doctor':data['course'].get('doctor','')},
            'lectures':lectures, 'sources':len(data['sources']), 'scope':data.get('scope','course')}


def append_lecture(archive, data, lid, expected_revision):
    """Append scientific sections and sources; preserve the destination history."""
    if len(data['lectures']) != 1:
        raise ValueError('اختر محاضرة واحدة لإضافة أقسامها إلى محاضرة موجودة')
    if expected_revision is None:
        raise ValueError('أعد اختيار المحاضرة الوجهة لتحديث رقم نسختها')
    sid_map = {source['id']:uid() for source in data['sources']}
    incoming = json.loads(data['lectures'][0]['doc'])
    id_map = {}
    for section in incoming['sections']:
        for node in [section, *section['blocks']]:
            previous = node['id']
            node['id'] = id_map[previous] = uid()
        for block in section['blocks']:
            for ref in block.get('refs', []):
                ref['source_id'] = sid_map[ref['source_id']]
    layout = {id_map[key]:value for key,value in incoming.get('settings',{}).get('layout',{}).items() if key in id_map}
    written = []
    try:
        with store.transaction() as db:
            suffix = ' FOR UPDATE' if store.persistence.backend() == 'postgres' else ''
            row = db.execute('SELECT * FROM lectures WHERE id=?' + suffix, (lid,)).fetchone()
            if row is None:
                raise LookupError('المحاضرة الوجهة غير موجودة')
            if row['revision'] != expected_revision:
                raise store.Conflict('تغيرت المحاضرة الوجهة؛ أعد اختيارها قبل استيراد الأقسام')
            document = json.loads(row['doc'])
            document['sections'].extend(incoming['sections'])
            document.setdefault('settings',{}).setdefault('layout',{}).update(layout)
            LectureDocument.model_validate(document)
            for source in data['sources']:
                relative = f'sources/{sid_map[source["id"]]}{PurePosixPath(source["path"]).suffix}'
                path = store.DATA / relative
                path.write_bytes(archive.read(source['path']))
                written.append(path)
                db.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (sid_map[source['id']], lid, source['name'], relative, source['kind'], source['priority'],
                     source['role'], sid_map.get(source.get('linked_id')), source['digest'], source['created']))
                # Existing packet aliases on the destination must keep their meaning.
                db.execute('INSERT OR IGNORE INTO source_aliases VALUES(?,?,?)', (lid,source['id'],sid_map[source['id']]))
            for page in data['pages']:
                db.execute('INSERT INTO pages VALUES(?,?,?,?,?,?)',
                    (sid_map[page['source_id']],page['number'],page['raw'],page['corrected'],page['excluded'],page['method']))
            db.execute('INSERT INTO revisions VALUES(?,?,?,?,?,?)',
                       (uid(),lid,row['revision'],row['doc'],store.now(),'إضافة أقسام من حزمة بيانات'))
            db.execute('UPDATE lectures SET doc=?,revision=revision+1,updated=? WHERE id=? AND revision=?',
                       (json.dumps(document,ensure_ascii=False),store.now(),lid,expected_revision))
            cid = row['course_id']
    except BaseException:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    return {'course_id':cid,'lecture_ids':[lid],'lectures':1,'sources':len(sid_map),'mode':'append_sections',
            'sections_added':len(incoming['sections'])}
