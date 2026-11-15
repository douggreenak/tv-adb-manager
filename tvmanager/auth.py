"""Password auth with scrypt hashes and in-memory session tokens."""
import hashlib
import hmac
import json
import os
import secrets
import time

SESSION_TTL = 7 * 24 * 3600


def _hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1).hex()


class Auth:
    def __init__(self, data_dir, env_password=None, log=print):
        self.path = os.path.join(data_dir, "auth.json")
        self.sessions = {}
        self.fails = {}  # ip -> (count, first_ts)
        self.initial_password = None
        cfg = self._load()
        if env_password:
            self._set(env_password)
        elif not cfg:
            self.initial_password = secrets.token_urlsafe(12)
            self._set(self.initial_password)
            log("No password configured. Generated initial password: %s (change it in Settings)"
                % self.initial_password)

    def _load(self):
        try:
            with open(self.path) as f:
                return json.load(f)
        except Exception:
            return None

    def _set(self, password):
        salt = secrets.token_bytes(16)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"salt": salt.hex(), "hash": _hash(password, salt)}, f)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)

    def set_password(self, password):
        if len(password) < 8:
            raise ValueError("password must be at least 8 characters")
        self._set(password)
        self.sessions.clear()

    def check(self, password):
        cfg = self._load()
        if not cfg:
            return False
        return hmac.compare_digest(_hash(password, bytes.fromhex(cfg["salt"])), cfg["hash"])

    def throttled(self, ip):
        n, first = self.fails.get(ip, (0, 0))
        if time.time() - first > 300:
            self.fails.pop(ip, None)
            return False
        return n >= 8

    def login(self, ip, password):
        if self.throttled(ip):
            return None
        if self.check(password):
            self.fails.pop(ip, None)
            token = secrets.token_urlsafe(32)
            self.sessions[token] = time.time() + SESSION_TTL
            return token
        n, first = self.fails.get(ip, (0, time.time()))
        self.fails[ip] = (n + 1, first)
        return None

    def valid(self, token):
        exp = self.sessions.get(token)
        if not exp:
            return False
        if exp < time.time():
            self.sessions.pop(token, None)
            return False
        return True

    def logout(self, token):
        self.sessions.pop(token, None)
