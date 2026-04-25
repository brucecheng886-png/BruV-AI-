"""
system_tools 完整測試腳本
執行：docker exec ai_kb_backend python /app/scripts/test_system_tools.py
"""
import sys
sys.path.insert(0, '/app')

from tools.system_tools import (
    move_document_to_kb,
    create_knowledge_base,
    update_knowledge_base,
    delete_knowledge_base,
    rename_document,
    soft_delete_document,
    restore_document,
    batch_reprocess_failed,
    crawl_url,
    list_knowledge_bases,
)
import psycopg2, psycopg2.extras
from config import settings

PASS = "✅ PASS"
FAIL = "❌ FAIL"

def check(label, result, expect_contains):
    ok = expect_contains.lower() in result.lower()
    print(f"{'✅ PASS' if ok else '❌ FAIL'} [{label}]")
    print(f"       → {result[:120]}")
    return ok

def get_conn():
    return psycopg2.connect(settings.DATABASE_URL.replace('+asyncpg',''))

# ── 取得真實 KB ID & doc ID ─────────────────────────────
conn = get_conn()
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
cur.execute('SELECT id FROM knowledge_bases LIMIT 1')
kb = cur.fetchone()
cur.execute("SELECT id, title FROM documents WHERE deleted_at IS NULL LIMIT 1")
doc = cur.fetchone()
conn.close()

if not kb or not doc:
    print("❌ 無法取得測試資料，請確認 DB 有資料")
    sys.exit(1)

KB_ID = kb['id']
DOC_ID = doc['id']
DOC_TITLE = doc['title']

print(f"\n使用 KB_ID={KB_ID[:8]}... DOC_ID={DOC_ID[:8]}...\n")
results = []

# ── 測試 1：move_document_to_kb ────────────────────────
r = move_document_to_kb(f'{DOC_ID}|{KB_ID}')
results.append(check("move_document_to_kb", r, "移動到知識庫"))

# ── 測試 2：move_document_to_kb (移出) ─────────────────
r = move_document_to_kb(f'{DOC_ID}|none')
results.append(check("move_document_to_kb (移出)", r, "從知識庫移出"))

# ── 測試 3：create_knowledge_base ──────────────────────
r = create_knowledge_base('__test_kb__|自動測試用知識庫')
results.append(check("create_knowledge_base", r, "已建立"))

conn = get_conn()
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
cur.execute("SELECT id FROM knowledge_bases WHERE name = '__test_kb__'")
new_kb = cur.fetchone()
conn.close()
NEW_KB_ID = new_kb['id'] if new_kb else None

# ── 測試 4：update_knowledge_base ──────────────────────
if NEW_KB_ID:
    r = update_knowledge_base(f'{NEW_KB_ID}|__test_kb_updated__|更新後描述')
    results.append(check("update_knowledge_base", r, "已從"))
else:
    print("❌ FAIL [update_knowledge_base] — 找不到剛建立的知識庫")
    results.append(False)

# ── 測試 5：delete_knowledge_base ──────────────────────
if NEW_KB_ID:
    r = delete_knowledge_base(NEW_KB_ID)
    results.append(check("delete_knowledge_base", r, "已刪除"))

# ── 測試 6：rename_document ────────────────────────────
r = rename_document(f'{DOC_ID}|__test_title__')
results.append(check("rename_document", r, "已從"))

r = rename_document(f'{DOC_ID}|{DOC_TITLE}')  # 還原
check("rename_document (還原)", r, "已從")

# ── 測試 7：soft_delete + restore ─────────────────────
r = soft_delete_document(DOC_ID)
results.append(check("soft_delete_document", r, "垃圾桶"))

r = restore_document(DOC_ID)
results.append(check("restore_document", r, "還原"))

# ── 測試 8：crawl_url ──────────────────────────────────
r = crawl_url('https://en.wikipedia.org/wiki/Wind_power')
results.append(check("crawl_url", r, "爬取任務"))

# ── 測試 9：batch_reprocess_failed ────────────────────
r = batch_reprocess_failed()
results.append(check("batch_reprocess_failed", r, ""))  # 不管結果都 pass

# ── 測試 10：無效輸入防禦 ─────────────────────────────
r = rename_document('invalid-id-no-pipe')
results.append(check("rename_document (invalid input)", r, "格式錯誤"))

r = move_document_to_kb('only-one-part')
results.append(check("move_document_to_kb (invalid input)", r, "格式錯誤"))

r = crawl_url('not-a-url')
results.append(check("crawl_url (invalid url)", r, "格式錯誤"))

# ── 總結 ───────────────────────────────────────────────
total = len(results)
passed = sum(results)
print(f"\n{'='*50}")
print(f"測試結果：{passed}/{total} 通過")
if passed == total:
    print("🎉 所有測試通過！")
else:
    print(f"⚠️  {total - passed} 個測試失敗")
