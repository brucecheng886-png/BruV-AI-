
# test_perms2.ps1 - Permission system integration tests (ASCII-safe)
$BASE = "http://localhost"
$ADMIN_EMAIL = "admin@local"
$ADMIN_PW = "admin123456"
$RNG = Get-Random -Maximum 99999
$TEST_EMAIL = "testperm_$RNG@test.local"
$TEST_PW = "TestPerm2026!"
$INVITE_EMAIL = "invited_$RNG@test.local"
$INVITE_PW = "InviteReg2026!"

$passed = 0; $failed = 0

function Pass($msg) { Write-Host "  [PASS] $msg" -ForegroundColor Green; $script:passed++ }
function Fail($msg) { Write-Host "  [FAIL] $msg" -ForegroundColor Red;   $script:failed++ }
function Section($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function H { param($t) @{ "Authorization" = "Bearer $t"; "Content-Type" = "application/json" } }

function Req {
    param([string]$M="GET",[string]$P,[hashtable]$B=$null,[string]$T="",[int]$E=200)
    $h = @{ "Content-Type" = "application/json" }
    if ($T) { $h["Authorization"] = "Bearer $T" }
    $j = if ($B) { $B | ConvertTo-Json -Depth 5 } else { $null }
    try {
        return Invoke-RestMethod -Uri "$BASE$P" -Method $M -Headers $h -Body $j -ErrorAction Stop
    } catch {
        $code = $_.Exception.Response.StatusCode.value__
        if ($code -eq $E) { return $null }
        $detail = try { ($_.ErrorDetails.Message | ConvertFrom-Json).detail } catch { "" }
        throw "HTTP $code (expected $E) [$P]: $detail"
    }
}

# 0. Admin login
Section "0. Admin login"
$AT = ""
try {
    $r = Req -M POST -P "/api/auth/login" -B @{email=$ADMIN_EMAIL;password=$ADMIN_PW}
    $AT = $r.access_token
    Pass "Admin login OK (token len=$($AT.Length))"
} catch { Fail "Admin login FAILED: $_"; exit 1 }

# 1. User management CRUD
Section "1. User management CRUD"
$TEST_USER_ID = ""

try {
    $u = Req -M POST -P "/api/auth/users" -T $AT -B @{email=$TEST_EMAIL;password=$TEST_PW;role="user"} -E 201
    $TEST_USER_ID = $u.id
    Pass "Create user OK (id=$($TEST_USER_ID.Substring(0,8))...)"
} catch { Fail "Create user: $_" }

try {
    $users = Req -M GET -P "/api/auth/users" -T $AT
    if ($users.Count -ge 1) { Pass "List users OK: count=$($users.Count)" }
    else { Fail "List users: empty" }
} catch { Fail "List users: $_" }

if ($TEST_USER_ID) {
    try {
        Req -M PATCH -P "/api/auth/users/$TEST_USER_ID" -T $AT -B @{role="readonly"} | Out-Null
        $all = Req -M GET -P "/api/auth/users" -T $AT
        $u2 = $all | Where-Object { $_.id -eq $TEST_USER_ID }
        if ($u2.role -eq "readonly") { Pass "Update role -> readonly OK" }
        else { Fail "Update role: expected readonly, got $($u2.role)" }
    } catch { Fail "Update role: $_" }
}

$UT = ""
try {
    $r = Req -M POST -P "/api/auth/login" -B @{email=$TEST_EMAIL;password=$TEST_PW}
    $UT = $r.access_token
    Pass "Test user login OK"
} catch { Fail "Test user login: $_" }

# 2. Create KBs
Section "2. Create KBs (admin)"
$KB_A = ""; $KB_B = ""

try {
    $r = Req -M POST -P "/api/knowledge-bases" -T $AT -B @{name="TestKB-A-$RNG";description="perm test A";color="#FF0000"} -E 201
    $KB_A = $r.id
    Pass "Create KB-A OK (id=$($KB_A.Substring(0,8))...)"
} catch { Fail "Create KB-A: $_" }

try {
    $r = Req -M POST -P "/api/knowledge-bases" -T $AT -B @{name="TestKB-B-$RNG";description="perm test B";color="#0000FF"} -E 201
    $KB_B = $r.id
    Pass "Create KB-B OK (id=$($KB_B.Substring(0,8))...)"
} catch { Fail "Create KB-B: $_" }

# 3. KB access filtering
Section "3. KB access filtering"

if ($UT) {
    try {
        $kbs = Req -M GET -P "/api/knowledge-bases" -T $UT
        if ($kbs.Count -eq 0) { Pass "Non-admin sees 0 KBs initially (isolation OK)" }
        else { Fail "Non-admin should see 0 KBs, got $($kbs.Count)" }
    } catch { Fail "KB list (no perm): $_" }
}

if ($KB_A -and $TEST_USER_ID) {
    try {
        Req -M POST -P "/api/knowledge-bases/$KB_A/permissions" -T $AT -B @{user_id=$TEST_USER_ID;permission="read"} -E 201 | Out-Null
        Pass "Grant KB-A read to test user OK"
    } catch { Fail "Grant KB-A: $_" }
}

if ($UT -and $KB_A -and $KB_B) {
    try {
        $kbs = Req -M GET -P "/api/knowledge-bases" -T $UT
        $ids = $kbs | ForEach-Object { $_.id }
        if ($ids -contains $KB_A) { Pass "Test user sees KB-A (granted)" }
        else { Fail "Test user should see KB-A" }
        if ($ids -notcontains $KB_B) { Pass "Test user cannot see KB-B (isolated)" }
        else { Fail "Test user should NOT see KB-B" }
    } catch { Fail "KB filter test: $_" }
}

# 4. KB permission CRUD
Section "4. KB permission CRUD"

if ($KB_A) {
    try {
        $perms = Req -M GET -P "/api/knowledge-bases/$KB_A/permissions" -T $AT
        $found = $perms | Where-Object { $_.user_id -eq $TEST_USER_ID }
        if ($found) { Pass "List KB-A perms: found test user (permission=$($found.permission))" }
        else { Fail "List KB-A perms: test user not found" }
    } catch { Fail "List KB perms: $_" }
}

if ($KB_A -and $TEST_USER_ID) {
    try {
        Req -M POST -P "/api/knowledge-bases/$KB_A/permissions" -T $AT -B @{user_id=$TEST_USER_ID;permission="write"} -E 201 | Out-Null
        $perms = Req -M GET -P "/api/knowledge-bases/$KB_A/permissions" -T $AT
        $found = $perms | Where-Object { $_.user_id -eq $TEST_USER_ID }
        if ($found.permission -eq "write") { Pass "Upsert perm to write OK" }
        else { Fail "Upsert perm: expected write, got $($found.permission)" }
    } catch { Fail "Upsert perm: $_" }
}

if ($TEST_USER_ID) {
    try {
        $kbPerms = Req -M GET -P "/api/auth/users/$TEST_USER_ID/kb-permissions" -T $AT
        if ($kbPerms.Count -ge 1) { Pass "User KB perms endpoint: $($kbPerms.Count) entries" }
        else { Fail "User KB perms endpoint: empty" }
    } catch { Fail "User KB perms: $_" }
}

if ($KB_A -and $TEST_USER_ID -and $UT) {
    try {
        Req -M DELETE -P "/api/knowledge-bases/$KB_A/permissions/$TEST_USER_ID" -T $AT -E 204 | Out-Null
        $kbs = Req -M GET -P "/api/knowledge-bases" -T $UT
        if (($kbs | Where-Object { $_.id -eq $KB_A }).Count -eq 0) {
            Pass "After revoke: test user cannot see KB-A"
        } else {
            Fail "After revoke: test user still sees KB-A"
        }
    } catch { Fail "Revoke KB perm: $_" }
}

# 5. Invite mechanism
Section "5. Invite mechanism"
$invToken = ""; $invId = ""

try {
    $r = Req -M POST -P "/api/auth/invite" -T $AT -B @{email=$INVITE_EMAIL;role="user";expires_days=1} -E 201
    $invToken = $r.token
    $invId = $r.id
    Pass "Create invite token OK (first 16: $($invToken.Substring(0,16))...)"
} catch { Fail "Create invite: $_" }

try {
    $invites = Req -M GET -P "/api/auth/invites" -T $AT
    if ($invites.Count -ge 1) { Pass "List invites OK: count=$($invites.Count)" }
    else { Fail "List invites: empty" }
} catch { Fail "List invites: $_" }

if ($invToken) {
    try {
        $info = Req -M GET -P "/api/auth/invite/$invToken"
        if ($info.email -eq $INVITE_EMAIL -and $info.role -eq "user") {
            Pass "Public verify token OK: email=$($info.email) role=$($info.role)"
        } else {
            Fail "Public verify token returned wrong data: $($info | ConvertTo-Json -Compress)"
        }
    } catch { Fail "Public verify token: $_" }

    try {
        $r = Req -M POST -P "/api/auth/register-via-invite" -B @{token=$invToken;email=$INVITE_EMAIL;password=$INVITE_PW;display_name="Invited User"} -E 201
        Pass "Register via invite OK: $($r.email)"
    } catch { Fail "Register via invite: $_" }

    try {
        Req -M POST -P "/api/auth/register-via-invite" -B @{token=$invToken;email="another@test.local";password=$INVITE_PW} -E 409 | Out-Null
        Pass "Reuse used token -> 409 Conflict (correct)"
    } catch { Fail "Reuse used token should return 409: $_" }

    try {
        $invites2 = Req -M GET -P "/api/auth/invites" -T $AT
        $thisInv = $invites2 | Where-Object { $_.id -eq $invId }
        if ($thisInv.used_at) { Pass "Invite marked used_at after registration" }
        else { Fail "Invite used_at not set" }
    } catch { Fail "Check invite used_at: $_" }

    try {
        $r = Req -M POST -P "/api/auth/login" -B @{email=$INVITE_EMAIL;password=$INVITE_PW}
        Pass "Invited user can login (role=$($r.role))"
    } catch { Fail "Invited user login: $_" }
}

try {
    Req -M GET -P "/api/auth/invite/invalid_fake_token_xyz_$(Get-Random)" -E 404 | Out-Null
    Pass "Invalid token -> 404 (correct)"
} catch { Fail "Invalid token should return 404: $_" }

# 6. Disable account
Section "6. Disable account"

if ($TEST_USER_ID) {
    try {
        Req -M PATCH -P "/api/auth/users/$TEST_USER_ID" -T $AT -B @{is_active=$false} | Out-Null
        Pass "Disable test user OK"
    } catch { Fail "Disable user: $_" }

    try {
        Req -M POST -P "/api/auth/login" -B @{email=$TEST_EMAIL;password=$TEST_PW} -E 403 | Out-Null
        Pass "Disabled user login attempt -> 403 Forbidden (correct)"
    } catch { Fail "Disabled user should get 403: $_" }
}

# 7. Cleanup
Section "7. Cleanup"

if ($TEST_USER_ID) {
    try { Req -M DELETE -P "/api/auth/users/$TEST_USER_ID" -T $AT -E 204 | Out-Null; Pass "Delete test user" }
    catch { Fail "Delete test user: $_" }
}

try {
    $all3 = Req -M GET -P "/api/auth/users" -T $AT
    $inv2 = $all3 | Where-Object { $_.email -eq $INVITE_EMAIL }
    if ($inv2) {
        Req -M DELETE -P "/api/auth/users/$($inv2.id)" -T $AT -E 204 | Out-Null
        Pass "Delete invited user"
    }
} catch { Fail "Delete invited user: $_" }

foreach ($kbId in @($KB_A, $KB_B)) {
    if ($kbId) {
        try { Req -M DELETE -P "/api/knowledge-bases/$kbId" -T $AT -E 204 | Out-Null; Pass "Delete KB $($kbId.Substring(0,8))..." }
        catch { Fail "Delete KB: $_" }
    }
}

# Summary
Write-Host "`n" + ("=" * 50)
$total = $passed + $failed
$color = if ($failed -eq 0) { "Green" } else { "Yellow" }
Write-Host "  RESULT: PASS=$passed  FAIL=$failed  TOTAL=$total" -ForegroundColor $color
Write-Host ("=" * 50) + "`n"
if ($failed -gt 0) { exit 1 } else { exit 0 }
