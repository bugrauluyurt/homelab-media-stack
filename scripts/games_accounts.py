"""Accounts for SFTPGo, the read-only games download page.

Used by configure-sftpgo.py (your account) and add-viewer.py (everyone else's).
"""
import base64
import sys
import time
import urllib.error
import urllib.request

from stack_env import ENV, http

URL = "http://127.0.0.1:8090"
ADMIN_ALLOW = ["127.0.0.0/8", "172.16.0.0/12"]

# Read-only on purpose; no 2FA, since a lost phone would lock a viewer out.
ACCOUNT = {"status": 1, "home_dir": "/srv/games", "permissions": {"/": ["list", "download"]},
           "filters": {"denied_protocols": ["FTP", "DAV"],
                       "web_client": ["write-disabled", "shares-disabled", "shares-without-password-disabled", "mfa-disabled"]}}


def basic(user, password):
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()}


def request(path, headers, body=None, method=None):
    return http(URL + path, body, method, headers, timeout=30)


def wait_ready():
    for _ in range(30):
        try:
            urllib.request.urlopen(f"{URL}/healthz", timeout=5)
            return
        except OSError:
            time.sleep(2)

    sys.exit("SFTPGo is not answering")


def admin():
    token = request("/api/v2/token", basic(ENV["SFTPGO_ADMIN_USER"], ENV["SFTPGO_ADMIN_PASSWORD"]))["access_token"]
    return {"Authorization": f"Bearer {token}"}


def lock_admin(auth):
    me = request(f"/api/v2/admins/{ENV['SFTPGO_ADMIN_USER']}", auth)

    if me.get("filters", {}).get("allow_list") == ADMIN_ALLOW:
        return False

    me.setdefault("filters", {})["allow_list"] = ADMIN_ALLOW
    request(f"/api/v2/admins/{ENV['SFTPGO_ADMIN_USER']}", auth, me, "PUT")
    return True


def users(auth):
    return {u["username"]: u for u in request("/api/v2/users?limit=500", auth)}


def ensure(name, password=None):
    """Create the account (needs a password) or re-apply the read-only settings.
    Returns '+' when something changed, '=' otherwise."""
    wait_ready()

    auth = admin()
    existing = users(auth).get(name)

    if existing is None:
        if password is None:
            raise ValueError("a password is needed to create the account")

        request("/api/v2/users", auth, {"username": name, "password": password, **ACCOUNT})
        return "+"

    current = {k: existing.get(k) for k in ("status", "home_dir", "permissions")}
    current["filters"] = {k: existing.get("filters", {}).get(k) for k in ACCOUNT["filters"]}

    if current == ACCOUNT and password is None:
        return "="

    request(f"/api/v2/users/{name}", auth, {**existing, **ACCOUNT, "filters": {**existing.get("filters", {}), **ACCOUNT["filters"]},
                                            **({"password": password} if password else {})}, "PUT")
    return "+"


def exists(name):
    wait_ready()
    return name in users(admin())


def login_works(name, password):
    try:
        return urllib.request.urlopen(urllib.request.Request(f"{URL}/api/v2/user/token", headers=basic(name, password)),
                                      timeout=10).status == 200
    except (urllib.error.HTTPError, OSError):
        return False
