from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from ctrltea import store


def test_atomic_sqlite_writers_preserve_history(client,lecture):
    _,row=lecture;gate=Barrier(2)
    def writer(title):
        document=dict(row['document']);document['title']=title
        gate.wait(timeout=5)
        try:return ('saved',store.save_document(row['id'],document,0)['document']['title'])
        except store.Conflict:return ('conflict',title)
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(writer,['A','B']))
    assert sorted(x[0] for x in results)==['conflict','saved']
    assert store.lecture(row['id'])['revision']==1
    assert len(store.all_rows('SELECT * FROM revisions WHERE lecture_id=?',(row['id'],)))==1
