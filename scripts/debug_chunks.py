import httpx, sys
sys.path.insert(0, '/app')
from tasks.document_tasks import _settings, _minio, _PARSERS, _parse_text, _sentence_window_chunks
s = _settings()
import psycopg2
pg = psycopg2.connect(host=s.POSTGRES_HOST, port=s.POSTGRES_PORT, database=s.POSTGRES_DB, user=s.POSTGRES_USER, password=s.POSTGRES_PASSWORD)
cur = pg.cursor()
cur.execute('SELECT file_path, file_type FROM documents WHERE id=%s', ('2d1bee01-b325-4db4-ac7c-c9faa91f32d9',))
row = cur.fetchone()
mc = _minio()
resp = mc.get_object(s.MINIO_BUCKET, row[0])
data = resp.read(); resp.close(); resp.release_conn()
pages = _PARSERS.get(row[1], _parse_text)(data)
chunks = []
for text, page in pages:
    chunks.extend(_sentence_window_chunks(text, page))
for i, c in enumerate(chunks):
    texts = [c['content']]
    r = httpx.post('http://host.docker.internal:11434/api/embed', json={'model':'bge-m3','input':texts}, timeout=30)
    content_preview = c['content'][:50]
    if r.status_code == 200:
        print(f'Chunk {i}: OK | {content_preview}')
    else:
        print(f'Chunk {i}: FAIL {r.text[:80]} | {content_preview}')
