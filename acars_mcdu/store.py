import json
import sqlite3
import time

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL, channel INTEGER, freq REAL, level REAL, err INTEGER,
  mode TEXT, label TEXT, block_id TEXT, ack TEXT, tail TEXT,
  msgno TEXT, flight TEXT, text TEXT, raw TEXT
);
CREATE INDEX IF NOT EXISTS idx_msg_ts ON messages(ts);
CREATE INDEX IF NOT EXISTS idx_msg_tail ON messages(tail);
CREATE TABLE IF NOT EXISTS ac_cache (reg TEXT PRIMARY KEY, ts REAL, data TEXT);
CREATE TABLE IF NOT EXISTS route_cache (callsign TEXT PRIMARY KEY, ts REAL, data TEXT);
"""


class Store:
    def __init__(self, path=None):
        self.db = sqlite3.connect(path or config.DB_PATH)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()

    def add_message(self, m):
        cur = self.db.execute(
            "INSERT INTO messages (ts,channel,freq,level,err,mode,label,block_id,"
            "ack,tail,msgno,flight,text,raw) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                m.get("timestamp") or time.time(),
                m.get("channel"),
                m.get("freq"),
                m.get("level"),
                m.get("error"),
                str(m.get("mode") or ""),
                str(m.get("label") or ""),
                str(m.get("block_id") or ""),
                str(m.get("ack") or ""),
                (m.get("tail") or "").strip().lstrip("."),
                str(m.get("msgno") or ""),
                (m.get("flight") or "").strip(),
                m.get("text") or "",
                json.dumps(m),
            ),
        )
        self.db.commit()
        return cur.lastrowid

    def get(self, mid):
        r = self.db.execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()
        return dict(r) if r else None

    def recent(self, limit=200, tail=None):
        if tail:
            q = "SELECT * FROM messages WHERE tail=? ORDER BY ts DESC LIMIT ?"
            rows = self.db.execute(q, (tail, limit)).fetchall()
        else:
            q = "SELECT * FROM messages ORDER BY ts DESC LIMIT ?"
            rows = self.db.execute(q, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def count(self):
        return self.db.execute("SELECT COUNT(*) c FROM messages").fetchone()["c"]

    def cache_get(self, table, key):
        col = "reg" if table == "ac_cache" else "callsign"
        r = self.db.execute(
            f"SELECT data FROM {table} WHERE {col}=?", (key,)
        ).fetchone()
        return json.loads(r["data"]) if r else None

    def cache_put(self, table, key, data):
        col = "reg" if table == "ac_cache" else "callsign"
        self.db.execute(
            f"INSERT OR REPLACE INTO {table} ({col},ts,data) VALUES (?,?,?)",
            (key, time.time(), json.dumps(data)),
        )
        self.db.commit()
