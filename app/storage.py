"""File I/O helpers with thread-safe locks for portfolio and profile."""

import copy
import json
import os
import stat
import tempfile
import threading

from app import config

_portfolio_lock = threading.Lock()
_profile_lock = threading.Lock()


def _atomic_write_json(path: str, data):
    """Write JSON atomically: temp file + rename. Sets 0600 permissions."""
    dir_name = os.path.dirname(path)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)  # 0600
        os.rename(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def read_portfolio() -> list[dict]:
    with _portfolio_lock:
        if not os.path.exists(config.PORTFOLIO_PATH):
            return []
        with open(config.PORTFOLIO_PATH, "r") as f:
            return json.load(f)


def write_portfolio(data: list[dict]):
    with _portfolio_lock:
        _atomic_write_json(config.PORTFOLIO_PATH, data)


def read_profile() -> dict:
    """Return saved profile merged over defaults (so new fields always exist).

    Merge is 2 levels deep so saved profiles missing newly-added keys
    (e.g. `min_ror` inside a strategy_defaults entry) fall back to defaults.
    """
    with _profile_lock:
        profile = copy.deepcopy(config.DEFAULT_PROFILE)
        if os.path.exists(config.PROFILE_PATH):
            with open(config.PROFILE_PATH, "r") as f:
                saved = json.load(f)
            for key in profile:
                if key in saved and isinstance(profile[key], dict) and isinstance(saved[key], dict):
                    for sub_key, sub_val in saved[key].items():
                        if isinstance(sub_val, dict) and isinstance(profile[key].get(sub_key), dict):
                            profile[key][sub_key] = {**profile[key][sub_key], **sub_val}
                        else:
                            profile[key][sub_key] = sub_val
                elif key in saved:
                    profile[key] = saved[key]
        return profile


def write_profile(data: dict):
    with _profile_lock:
        _atomic_write_json(config.PROFILE_PATH, data)
