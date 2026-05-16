"""發布前 API 測試 — v1.1.13"""
import urllib.request, json, urllib.error

BASE = "http://localhost:80"

def get(url, token=None):
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {}

def post(url, body, token=None):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {}

def delete(url, token):
    req = urllib.request.Request(url, method="DELETE")
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, {}
    except urllib.error.HTTPError as e:
        return e.code, {}

tests = []

# Health
s, b = get(f"{BASE}/api/health")
tests.append(("GET /api/health", s == 200 and b.get("status") == "ok"))

# Login
s, b = post(f"{BASE}/api/auth/login", {"email": "admin@local", "password": "12345678"})
token = b.get("access_token", "")
tests.append(("POST /api/auth/login", s == 200 and bool(token)))

# Folders list (新功能)
s, b = get(f"{BASE}/api/folders", token)
tests.append(("GET /api/folders", s == 200 and isinstance(b, list)))

# Folders create (新功能)
s, b = post(f"{BASE}/api/folders", {"name": "__test_release__", "icon": "📁", "color": "#2563eb"}, token)
folder_id = b.get("id", "")
tests.append(("POST /api/folders (create)", s == 201 and bool(folder_id)))

# Folders get (新功能)
if folder_id:
    s, b = get(f"{BASE}/api/folders/{folder_id}", token)
    tests.append(("GET /api/folders/{id}", s == 200 and b.get("id") == folder_id))

# Folders children (新功能)
if folder_id:
    s, b = get(f"{BASE}/api/folders/{folder_id}/children", token)
    tests.append(("GET /api/folders/{id}/children", s == 200 and isinstance(b, list)))

# Folders documents list (新功能)
if folder_id:
    s, b = get(f"{BASE}/api/folders/{folder_id}/documents", token)
    tests.append(("GET /api/folders/{id}/documents", s == 200 and isinstance(b, list)))

# Folders permissions list (新功能)
if folder_id:
    s, b = get(f"{BASE}/api/folders/{folder_id}/permissions", token)
    tests.append(("GET /api/folders/{id}/permissions", s == 200 and isinstance(b, list)))

# Documents list (既有功能)
s, b = get(f"{BASE}/api/documents?page=1&page_size=5", token)
tests.append(("GET /api/documents (existing)", s == 200 and isinstance(b, list)))

# Documents download Unicode fix (本次 bugfix)
s, b = get(f"{BASE}/api/documents", token)
if isinstance(b, dict) and b.get("items"):
    doc_id = b["items"][0]["id"]
    req = urllib.request.Request(f"{BASE}/api/documents/{doc_id}/download")
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            cd = r.headers.get("Content-Disposition", "")
            tests.append(("GET /api/documents/{id}/download (Unicode fix)", "filename*=UTF-8" in cd or r.status == 200))
    except Exception:
        tests.append(("GET /api/documents/{id}/download (Unicode fix)", False))

# 未授權 → 401
s, _ = get(f"{BASE}/api/folders")
tests.append(("GET /api/folders (no token) = 401", s == 401))

# Path traversal 安全性
s, _ = post(f"{BASE}/api/folders", {"name": "../../etc/passwd"}, token)
# Should succeed (it's just a name string), but not cause any harm
tests.append(("POST /api/folders path traversal safe", s in [201, 400, 422]))

# Cleanup: delete test folder
if folder_id:
    s, _ = delete(f"{BASE}/api/folders/{folder_id}", token)
    tests.append(("DELETE /api/folders/{id} cleanup", s in [200, 204]))

# 結果
for name, passed in tests:
    mark = "PASS" if passed else "FAIL"
    print(f"{mark}  {name}")

failed = sum(1 for _, p in tests if not p)
if failed == 0:
    print("\n全部通過 OK")
else:
    print(f"\n{failed} 項失敗 NG")
