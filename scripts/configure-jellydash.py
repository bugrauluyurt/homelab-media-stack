#!/usr/bin/env python3
"""Configure JellyDash: its own Jellyfin API key, the admin login and its Downloads page.

Runs: by hand, after configure-sabnzbd.py.
Changes: Jellyfin API key; .env; docker compose up -d jellydash, which recreates it when the key
  changed; JellyDash's database through docker exec.
Idempotent: yes.

The key is stored in .env as JELLYDASH_JELLYFIN_API_KEY, and the
container is recreated when it changes.
"""
import json
import secrets
import subprocess
import sys
import time
import urllib.request

from stack_env import ENV, REPO, require_service, set_env, http, jellyfin_headers

require_service("jellydash")

JELLYFIN = "http://127.0.0.1:8096"
AUTH = jellyfin_headers()
APP = "JellyDash"
DB = "/var/www/html/var/data/jellydash.sqlite"

user, password = ENV["JELLYDASH_USER"], ENV["JELLYDASH_PASSWORD"]

# JellyDash refuses passwords under 8 characters, but login only verifies the stored hash.
SET_HASH = r"""
$pw = rtrim(stream_get_contents(STDIN), "\n");
$db = new PDO('sqlite:' . $argv[1]);
$db->exec('PRAGMA busy_timeout = 5000');
$row = $db->prepare('SELECT password FROM users WHERE username = ?');
$row->execute([$argv[2]]);
$hash = $row->fetchColumn();
if ($hash === false) { fwrite(STDERR, "no such user\n"); exit(1); }
if (password_verify($pw, $hash)) { echo "same"; exit(0); }
$db->prepare('UPDATE users SET password = ? WHERE username = ?')->execute([password_hash($pw, PASSWORD_DEFAULT), $argv[2]]);
echo "updated";
"""


# Through JellyDash's own ConnectionRepository, so its validation still applies.
DOWNLOAD_CLIENTS = r"""
define('ROOT_DIR', '/var/www/html');
require ROOT_DIR . '/vendor/autoload.php';
require ROOT_DIR . '/utils/@constants.php';
Dotenv\Dotenv::createImmutable(ROOT_DIR)->safeLoad();
use Mk\Framework\Config;
use Mk\Framework\Integrations\{Connection, ConnectionRepository};
define('DATABASE_NAME', Config::get('DB_NAME', 'framework'));
define('DATABASE_HOST', Config::get('DB_HOST', 'localhost'));
define('DATABASE_PORT', Config::get('DB_PORT'));
define('DATABASE_DRIVER_DIBI', Config::get('DB_DRIVER', 'mysqli'));
define('DATABASE_USERNAME', Config::get('DB_USER', 'root'));
define('DATABASE_PASSWORD', Config::get('DB_PASS', ''));
$repo = new ConnectionRepository();
foreach (json_decode(stream_get_contents(STDIN), true) as $w) {
    $c = $repo->find($w['id']);
    if ($c && $c->name === $w['name'] && $c->url === $w['url'] && $c->username === $w['username']
        && $c->enabled && $c->hasSecret && $repo->credentials($c)['secret'] === $w['secret']) {
        echo "  = Downloads: {$w['name']}\n";
        continue;
    }
    $repo->save(new Connection(id: $w['id'], provider: $w['provider'], name: $w['name'], url: $w['url'],
                               username: $w['username']), $w['secret'], $c?->revision);
    echo "  + Downloads: {$w['name']} ({$w['url']})\n";
}
"""

CLIENTS = [
    {"id": "stack-qbittorrent", "provider": "qbittorrent", "name": "qBittorrent", "url": f"http://gluetun:{ENV['QBIT_PORT']}",
     "username": "jellydash", "secret": "not-needed-on-the-docker-network"},
    {"id": "stack-sabnzbd", "provider": "sabnzbd", "name": "SABnzbd", "url": "http://sabnzbd:8080",
     "username": "", "secret": ENV["SABNZBD_API_KEY"]},
]


def jellyfin(path, method="GET"):
    return http(JELLYFIN + path, method=method, headers=AUTH, timeout=30)


def api_key():
    key = next((k["AccessToken"] for k in jellyfin("/Auth/Keys")["Items"] if k["AppName"] == APP), None)
    if key:
        return key, False

    jellyfin(f"/Auth/Keys?App={APP}", "POST")
    return next(k["AccessToken"] for k in jellyfin("/Auth/Keys")["Items"] if k["AppName"] == APP), True


def jellydash(*args, **kw):
    return subprocess.run(["docker", "exec", "-u", "www-data", "-w", "/var/www/html", *kw.pop("opts", []),
                           "jellydash", *args], capture_output=True, text=True, **kw)


key, created = api_key()
if ENV.get("JELLYDASH_JELLYFIN_API_KEY") == key:
    print(f"  = Jellyfin API key '{APP}' in .env")
else:
    set_env("JELLYDASH_JELLYFIN_API_KEY", key)
    print(f"  + {'created' if created else 'stored'} Jellyfin API key '{APP}' in .env")

up = subprocess.run(["docker", "compose", "up", "-d", "jellydash"], cwd=REPO, check=True,
                    capture_output=True, text=True)
for _ in range(40):
    try:
        urllib.request.urlopen("http://127.0.0.1:3004/healthz.php", timeout=5)
        break
    except OSError:
        time.sleep(3)
else:
    sys.exit("JellyDash did not come up")

if "Recreate" in up.stderr:
    print("  + recreated JellyDash with the key")

out = jellydash("php", "bin/console.php", "user:ensure", user, secrets.token_urlsafe(18))
if "Created user" in out.stdout:
    print(f"  + created JellyDash admin '{user}'")

result = jellydash("php", "-r", SET_HASH, DB, user, input=f"{password}\n", opts=["-i"])
if result.returncode != 0:
    sys.exit(f"setting the JellyDash password failed: {result.stderr.strip()}")

print(f"  = JellyDash login '{user}' matches .env" if result.stdout == "same"
      else f"  + JellyDash password for '{user}' set from .env")

clients = jellydash("php", "-r", DOWNLOAD_CLIENTS, input=json.dumps(CLIENTS), opts=["-i"])
if clients.returncode != 0:
    sys.exit(f"adding JellyDash download clients failed: {clients.stderr.strip()}")

print(clients.stdout, end="")
