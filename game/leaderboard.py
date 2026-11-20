"""Local leaderboard (Ticket-04 part 3). Pure stdlib.

Entry: {name, score, nights_won (0-3), achieved_at (ISO 8601 with time zone, set by the caller/server), seed}.
Order: score descending; equal score -> earlier achieved_at first. Top 10 kept.
File: $DDL_LEADERBOARD, default ~/.dao-den-long/leaderboard.json  ->  {"entries": [...]}.
"""
import json
import os
import re
import tempfile
import threading
import unicodedata
from datetime import datetime, timezone

MAX_ENTRIES = 10
NAME_RE = re.compile(r"\w{3,12}")        # fullmatch; Unicode \w: letters (incl. Vietnamese), digits, "_"; no spaces
NAME_RULE = "name must be 3-12 characters: letters, digits or _ (no spaces)"
_LOCK = threading.Lock()


class LeaderboardError(ValueError):
    """Invalid entry (the server answers 400 with the message)."""


def default_path():
    return os.environ.get("DDL_LEADERBOARD") or os.path.join(
        os.path.expanduser("~"), ".dao-den-long", "leaderboard.json")


def clean_name(name):
    if not isinstance(name, str):
        raise LeaderboardError(NAME_RULE)
    n = unicodedata.normalize("NFC", name)
    if not NAME_RE.fullmatch(n):
        raise LeaderboardError(NAME_RULE)
    return n


def _int(v, what, lo, hi=None):
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if not isinstance(v, int) or isinstance(v, bool) or v < lo or (hi is not None and v > hi):
        rng = f"an integer >= {lo}" if hi is None else f"an integer {lo}-{hi}"
        raise LeaderboardError(f"{what} must be {rng}")
    return v


def validate(data, achieved_at=None):
    """Validate an incoming {name, score, nights_won, seed} -> a clean entry (with achieved_at)."""
    if not isinstance(data, dict):
        raise LeaderboardError("entry must be a JSON object")
    return {"name": clean_name(data.get("name")),
            "score": _int(data.get("score"), "score", 0),
            "nights_won": _int(data.get("nights_won"), "nights_won", 0, 3),
            "achieved_at": achieved_at or now_iso(),
            "seed": _int(data.get("seed"), "seed", 0) if data.get("seed") is not None else 0}


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


def _when(entry):
    """Sort key for achieved_at: aware datetime -> UTC timestamp; unparsable -> far future."""
    try:
        d = datetime.fromisoformat(str(entry.get("achieved_at", "")).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.astimezone()
        return d.timestamp()
    except (ValueError, OverflowError, OSError):
        return float("inf")


def ranked(entries):
    """Sort (score desc, earlier first; stable) and keep the top 10."""
    es = sorted((e for e in entries if isinstance(e, dict)), key=_when)    # earlier first ...
    es.sort(key=lambda e: -e.get("score", 0) if isinstance(e.get("score"), (int, float)) else 0)  # ... then score
    return es[:MAX_ENTRIES]


def load(path=None):
    """Entries from disk, in rank order. A missing or corrupt file counts as an empty board."""
    path = path or default_path()
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        return []
    entries = doc.get("entries") if isinstance(doc, dict) else doc
    if not isinstance(entries, list):
        return []
    return ranked(entries)


def save(entries, path=None):
    """Atomic write of {"entries": [...]}."""
    path = path or default_path()
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".lb-", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"entries": entries}, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def add(data, path=None, achieved_at=None):
    """Validate and insert an entry. Returns (entries, rank) with rank 1-based, or None if the entry
    did not make the top 10. Raises LeaderboardError for an invalid entry."""
    entry = validate(data, achieved_at)
    with _LOCK:
        entries = load(path)
        entries.append(entry)
        # the new entry is the latest, so on equal score it sorts after the existing ones
        entries = ranked(entries)
        rank = next((i + 1 for i, e in enumerate(entries) if e is entry), None)
        save(entries, path)
    return entries, rank
