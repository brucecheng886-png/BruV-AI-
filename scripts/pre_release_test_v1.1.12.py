"""
Pre-release API test script for v1.1.12 (RBAC + Invite System)
All-ASCII output to avoid encoding issues.
"""
import requests
import sys

BASE = "http://localhost:80"
H_JSON = {"Content-Type": "application/json"}


def login(email, password):
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": email, "password": password},
                      headers=H_JSON, timeout=10)
    if r.status_code != 200:
        return None
    return r.json().get("access_token")


def auth_header(token):
    return {"Authorization": f"Bearer {token}", **H_JSON}


def no_auth_header():
    return H_JSON


tests = []


def T(name, passed, extra=""):
    status = "[PASS]" if passed else "[FAIL]"
    msg = f"{status}  {name}"
    if extra:
        msg += f"  ({extra})"
    tests.append((name, passed))
    print(msg)


# ── Login ──────────────────────────────────────────────────────────────────
admin_token = login("admin@local", "admin123456")
T("Admin login", admin_token is not None)
if not admin_token:
    print("ABORT: cannot get admin token")
    sys.exit(1)

AH = auth_header(admin_token)

# ── Create test user ───────────────────────────────────────────────────────
r = requests.post(f"{BASE}/api/auth/users",
                  json={"email": "rbac_test@test.com", "password": "TestPass123!",
                        "display_name": "RBAC Test User", "role": "user"},
                  headers=AH, timeout=10)
T("Create test user", r.status_code in (200, 201), f"status={r.status_code}")
test_user_id = r.json().get("id") if r.status_code in (200, 201) else None

# ── Create test KB ─────────────────────────────────────────────────────────
r = requests.post(f"{BASE}/api/knowledge-bases",
                  json={"name": "rbac_test_kb", "description": "RBAC test"},
                  headers=AH, timeout=10)
T("Create test KB", r.status_code in (200, 201), f"status={r.status_code}")
test_kb_id = r.json().get("id") if r.status_code in (200, 201) else None

# ── Non-admin sees 0 KBs before permission ─────────────────────────────────
if test_user_id:
    user_token = login("rbac_test@test.com", "TestPass123!")
    T("Test user login", user_token is not None)
    if user_token:
        UH = auth_header(user_token)
        r = requests.get(f"{BASE}/api/knowledge-bases", headers=UH, timeout=10)
        kbs = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        T("Non-admin sees 0 KBs before perm grant", len(kbs) == 0,
          f"found {len(kbs)}")
    else:
        user_token = None
        T("Test user login", False)

# ── KB permission CRUD ─────────────────────────────────────────────────────
if test_kb_id and test_user_id:
    # list (empty)
    r = requests.get(f"{BASE}/api/knowledge-bases/{test_kb_id}/permissions",
                     headers=AH, timeout=10)
    T("List KB permissions (empty)", r.status_code == 200 and isinstance(r.json(), list))

    # grant
    r = requests.post(f"{BASE}/api/knowledge-bases/{test_kb_id}/permissions",
                      json={"user_id": test_user_id, "permission": "read"},
                      headers=AH, timeout=10)
    T("Grant KB permission", r.status_code in (200, 201), f"status={r.status_code}")

    # list (now 1)
    r = requests.get(f"{BASE}/api/knowledge-bases/{test_kb_id}/permissions",
                     headers=AH, timeout=10)
    perms = r.json()
    T("List KB permissions (1 entry)", r.status_code == 200 and len(perms) == 1,
      f"count={len(perms) if isinstance(perms, list) else '?'}")

    # non-admin now sees that KB
    if 'user_token' in dir() and user_token:
        UH = auth_header(user_token)
        r = requests.get(f"{BASE}/api/knowledge-bases", headers=UH, timeout=10)
        kbs = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        T("Non-admin sees 1 KB after perm grant", len(kbs) == 1,
          f"found {len(kbs)}")

    # revoke
    r = requests.delete(
        f"{BASE}/api/knowledge-bases/{test_kb_id}/permissions/{test_user_id}",
        headers=AH, timeout=10)
    T("Revoke KB permission", r.status_code in (200, 204))

# ── User KB permissions endpoint ────────────────────────────────────────────
if test_user_id:
    r = requests.get(f"{BASE}/api/auth/users/{test_user_id}/kb-permissions",
                     headers=AH, timeout=10)
    T("GET user KB permissions", r.status_code == 200 and isinstance(r.json(), list))

# ── Invite CRUD ────────────────────────────────────────────────────────────
r = requests.post(f"{BASE}/api/auth/invite",
                  json={"email": "newbie@test.com", "role": "user",
                        "expires_hours": 24},
                  headers=AH, timeout=10)
T("Create invite token", r.status_code in (200, 201), f"status={r.status_code}")
invite_token = r.json().get("token") if r.status_code in (200, 201) else None
invite_id = r.json().get("id") if r.status_code in (200, 201) else None

if invite_token:
    # verify
    r = requests.get(f"{BASE}/api/auth/invite/{invite_token}",
                     headers=no_auth_header(), timeout=10)
    T("Verify invite token (public)", r.status_code == 200 and r.json().get("valid") is True)

    # register via invite
    r = requests.post(f"{BASE}/api/auth/register-via-invite",
                      json={"token": invite_token, "email": "newbie@test.com",
                            "password": "NewPass123!", "display_name": "New User"},
                      headers=no_auth_header(), timeout=10)
    T("Register via invite", r.status_code in (200, 201), f"status={r.status_code}")
    newbie_id = r.json().get("id") if r.status_code in (200, 201) else None

    # reuse rejected
    r = requests.post(f"{BASE}/api/auth/register-via-invite",
                      json={"token": invite_token, "email": "newbie2@test.com",
                            "password": "NewPass123!", "display_name": "New User2"},
                      headers=no_auth_header(), timeout=10)
    T("Reuse invite rejected (400/422)", r.status_code in (400, 409, 422),
      f"status={r.status_code}")

# ── List invites ────────────────────────────────────────────────────────────
r = requests.get(f"{BASE}/api/auth/invites", headers=AH, timeout=10)
T("List invites", r.status_code == 200 and isinstance(r.json(), list))

# ── Security: unauthenticated → 401 ────────────────────────────────────────
r = requests.get(f"{BASE}/api/knowledge-bases", headers=no_auth_header(), timeout=10)
T("Unauthenticated KB list → 401", r.status_code == 401,
  f"status={r.status_code}")

r = requests.post(f"{BASE}/api/auth/invite",
                  json={"email": "x@x.com", "role": "user", "expires_hours": 1},
                  headers=no_auth_header(), timeout=10)
T("Unauthenticated invite create → 401", r.status_code == 401,
  f"status={r.status_code}")

# ── Security: non-admin → 403 for admin endpoints ──────────────────────────
if 'user_token' in dir() and user_token:
    UH = auth_header(user_token)
    r = requests.get(f"{BASE}/api/auth/invites", headers=UH, timeout=10)
    T("Non-admin list invites → 403", r.status_code == 403,
      f"status={r.status_code}")
    if test_kb_id:
        r = requests.get(f"{BASE}/api/knowledge-bases/{test_kb_id}/permissions",
                         headers=UH, timeout=10)
        T("Non-admin list KB perms → 403", r.status_code == 403,
          f"status={r.status_code}")

# ── Cleanup ─────────────────────────────────────────────────────────────────
if test_kb_id:
    requests.delete(f"{BASE}/api/knowledge-bases/{test_kb_id}", headers=AH, timeout=10)
if test_user_id:
    requests.delete(f"{BASE}/api/auth/users/{test_user_id}", headers=AH, timeout=10)
if 'newbie_id' in dir() and newbie_id:
    requests.delete(f"{BASE}/api/auth/users/{newbie_id}", headers=AH, timeout=10)
if invite_id:
    requests.delete(f"{BASE}/api/auth/invites/{invite_id}", headers=AH, timeout=10)

# ── Summary ─────────────────────────────────────────────────────────────────
total = len(tests)
failed = sum(1 for _, p in tests if not p)
passed = total - failed
print(f"\n{'='*50}")
print(f"Result: {passed}/{total} PASS  {failed} FAIL")
print("ALL PASS [OK]" if failed == 0 else f"{failed} FAILED [ERROR]")
sys.exit(0 if failed == 0 else 1)
