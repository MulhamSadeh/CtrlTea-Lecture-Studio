"""Thirty-day recoverable deletion. Original file bytes are retained privately."""
import json
from fastapi import APIRouter,Request,HTTPException
from . import store,accounts,persistence
from .models import uid
router=APIRouter()


def capture(kind,identifier):
    if not accounts.enabled():return
    with store.transaction() as db:
        # Serialize the recoverable snapshot with saves and child mutations.
        # No long conversion work runs while these short deletion locks live.
        if kind=='course':
            db.execute('SELECT id FROM courses WHERE id=? FOR UPDATE',(identifier,)).fetchall()
            db.execute('SELECT id FROM lectures WHERE course_id=? ORDER BY id FOR UPDATE',(identifier,)).fetchall()
        elif kind=='lecture':
            db.execute('SELECT id FROM lectures WHERE id=? FOR UPDATE',(identifier,)).fetchall()
        else:
            db.execute('SELECT id FROM sources WHERE id=? FOR UPDATE',(identifier,)).fetchall()
        snapshot={}
        if kind=='course':
            snapshot['courses']=store.all_rows('SELECT * FROM courses WHERE id=?',(identifier,))
            lectures=store.all_rows('SELECT * FROM lectures WHERE course_id=?',(identifier,))
        elif kind=='lecture':lectures=store.all_rows('SELECT * FROM lectures WHERE id=?',(identifier,))
        else:lectures=[]
        if kind in ('course','lecture'):
            snapshot['lectures']=lectures
            for lecture in lectures:
                lid=lecture['id']
                for table in ('sources','revisions','author_runs','jobs','source_aliases','run_aliases'):
                    snapshot.setdefault(table,[]).extend(store.all_rows('SELECT * FROM '+table+' WHERE lecture_id=? FOR UPDATE',(lid,)))
                snapshot.setdefault('private_assets',[]).extend(store.all_rows('SELECT id,lecture_id,kind,relative_path,sha256,bytes FROM private_assets WHERE lecture_id=?',(lid,)))
                snapshot.setdefault('import_provenance',[]).extend(store.all_rows('SELECT lecture_id,provenance FROM import_provenance WHERE lecture_id=?',(lid,)))
        else:
            snapshot['sources']=store.all_rows('SELECT * FROM sources WHERE id=?',(identifier,))
            snapshot['source_aliases']=store.all_rows('SELECT * FROM source_aliases WHERE source_id=?',(identifier,))
        for source in snapshot.get('sources',[]):snapshot.setdefault('pages',[]).extend(store.all_rows('SELECT * FROM pages WHERE source_id=? FOR UPDATE',(source['id'],)))
        for run in snapshot.get('author_runs',[]):snapshot.setdefault('author_tasks',[]).extend(store.all_rows('SELECT * FROM author_tasks WHERE run_id=?',(run['id'],)))
        who=accounts.actor.get()
        db.execute('INSERT INTO trash_records(id,kind,resource_id,deleted_by,snapshot) VALUES(?,?,?,?,?)',(uid(),kind,identifier,who['id'] if who else None,json.dumps(snapshot,ensure_ascii=False)))


@router.get('/api/trash')
def trash_list():
    return store.all_rows('SELECT id,kind,resource_id,created_at,expires_at,restored_at FROM trash_records ORDER BY created_at DESC LIMIT 100')


@router.post('/api/trash/{tid}/restore')
def trash_restore(tid:str):
    import psycopg
    try:return restore(tid)
    except psycopg.IntegrityError:
        raise HTTPException(409,"تعارضت معرّفات أو علاقات المورد؛ استعد المورد الأب أولًا دون استبدال البيانات الحالية")


def restore(tid):
    with store.transaction() as db:
        row=db.execute('SELECT snapshot,expires_at,restored_at FROM trash_records WHERE id=? FOR UPDATE',(tid,)).fetchone()
        if not row or row['restored_at'] or row['expires_at']<=accounts.now():raise HTTPException(409,'انتهت مهلة الاستعادة أو أُنجزت مسبقًا')
        snapshot=json.loads(row['snapshot'])
        for table in ('courses','lectures','sources','pages','revisions','author_runs','author_tasks','source_aliases','run_aliases','jobs','private_assets','import_provenance'):
            for record in snapshot.get(table,[]):
                record['workspace_id']=persistence.workspace_id()
                if table=='revisions':record['is_legacy']=1
                if table=='jobs' and record['status'] in ('queued','running'):
                    record['status']='failed';record['error']=json.dumps({'message':'استُعيدت المهمة؛ أعد تشغيلها صراحةً'})
                columns=list(record)
                db.execute('INSERT INTO '+table+'('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',tuple(record[c] for c in columns))
        db.execute('UPDATE trash_records SET restored_at=now() WHERE id=?',(tid,))
    return {'message':'استُعيد المورد بمعرّفاته الأصلية؛ راجع السجل قبل متابعة العمل.'}
