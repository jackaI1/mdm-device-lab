"""Set the Headwind admin password in the lab database, using Headwind's own hash scheme.

Headwind stores SHA1(MD5(password) + salt) and the login compares against it. The seeded
admin row uses a different value, so a fresh lab server cannot sign in until this runs.
Only for a throwaway lab: it writes to the PostgreSQL container from docker-compose.yml.

Usage: python scripts/set_lab_admin_password.py <password>
"""

from __future__ import annotations

import hashlib
import subprocess
import sys

PASS_SALT = "5YdSYHyg2U"  # from Headwind's PasswordUtil (hmdm-server, common module)


def headwind_hash(password: str) -> str:
    md5 = hashlib.md5(password.encode("utf-8")).hexdigest()
    return hashlib.sha1((md5 + PASS_SALT).encode("utf-8")).hexdigest()


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    value = headwind_hash(sys.argv[1])
    sql = f"UPDATE users SET password = '{value}' WHERE login = 'admin';"
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "hmdm", "-d", "hmdm", "-c", sql],
        check=False, capture_output=True, text=True)
    print(result.stdout.strip() or result.stderr.strip()[:300])
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
