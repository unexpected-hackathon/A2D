"""SQLite 저장소. 한 프로세스에서 쓰므로 연결 하나와 잠금 하나로 처리한다.

표마다 조회에 쓰는 열만 따로 두고, 나머지는 data(JSON)에 담는다.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS counters (name TEXT PRIMARY KEY, value INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS domains (
  domain_id TEXT PRIMARY KEY, domain TEXT UNIQUE NOT NULL, data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assets (
  domain_id TEXT NOT NULL, host TEXT NOT NULL, asset_id TEXT NOT NULL,
  importance_manual INTEGER, PRIMARY KEY (domain_id, host)
);
CREATE TABLE IF NOT EXISTS finding_keys (
  domain_id TEXT NOT NULL, fkey TEXT NOT NULL, finding_id TEXT NOT NULL, PRIMARY KEY (domain_id, fkey)
);
CREATE TABLE IF NOT EXISTS scans (
  scan_id TEXT PRIMARY KEY, seq INTEGER NOT NULL, domain_id TEXT NOT NULL, status TEXT NOT NULL,
  data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS scans_domain ON scans (domain_id, seq);
CREATE TABLE IF NOT EXISTS scan_assets (
  scan_id TEXT NOT NULL, asset_id TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY (scan_id, asset_id)
);
CREATE TABLE IF NOT EXISTS findings (
  scan_id TEXT NOT NULL, finding_id TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY (scan_id, finding_id)
);
CREATE INDEX IF NOT EXISTS findings_id ON findings (finding_id);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT, scan_id TEXT NOT NULL, data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS audit_scan ON audit (scan_id, id);
CREATE TABLE IF NOT EXISTS reports (scan_id TEXT PRIMARY KEY, data TEXT NOT NULL);
"""


def _dump(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False)


class Store:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)
        self._lock = threading.RLock()

    # ------------------------------------------------------------ 공통

    def _q(self, sql: str, args: tuple = ()) -> list[tuple]:
        with self._lock:
            return self._db.execute(sql, args).fetchall()

    def next_seq(self, name: str) -> int:
        with self._lock:
            self._db.execute(
                "INSERT INTO counters (name, value) VALUES (?, 1) "
                "ON CONFLICT(name) DO UPDATE SET value = value + 1",
                (name,),
            )
            return self._db.execute("SELECT value FROM counters WHERE name = ?", (name,)).fetchone()[0]

    # ------------------------------------------------------------ 도메인

    def create_domain(self, domain: str, data: dict) -> dict:
        with self._lock:
            row = self._q("SELECT data FROM domains WHERE domain = ?", (domain,))
            if row:
                return json.loads(row[0][0])
            domain_id = f"DOM-{self.next_seq('domain')}"
            data = {"domain_id": domain_id, "domain": domain, **data}
            self._db.execute("INSERT INTO domains VALUES (?, ?, ?)", (domain_id, domain, _dump(data)))
            return {**data, "_created": True}

    def get_domain(self, domain_id: str) -> dict | None:
        row = self._q("SELECT data FROM domains WHERE domain_id = ?", (domain_id,))
        return json.loads(row[0][0]) if row else None

    def list_domains(self) -> list[dict]:
        return [json.loads(r[0]) for r in self._q("SELECT data FROM domains ORDER BY rowid")]

    def save_domain(self, data: dict) -> None:
        self._q("UPDATE domains SET data = ? WHERE domain_id = ?", (_dump(data), data["domain_id"]))

    # ------------------------------------------------------------ 자산 ID (점검이 바뀌어도 유지)

    def asset_id_for(self, domain_id: str, host: str) -> str:
        with self._lock:
            row = self._q("SELECT asset_id FROM assets WHERE domain_id = ? AND host = ?", (domain_id, host))
            if row:
                return row[0][0]
            n = self.next_seq(f"asset:{domain_id}")
            asset_id = f"A-{n:03d}"
            self._db.execute(
                "INSERT INTO assets (domain_id, host, asset_id) VALUES (?, ?, ?)", (domain_id, host, asset_id)
            )
            return asset_id

    def manual_importance(self, domain_id: str) -> dict[str, int]:
        rows = self._q(
            "SELECT asset_id, importance_manual FROM assets WHERE domain_id = ? AND importance_manual IS NOT NULL",
            (domain_id,),
        )
        return {a: v for a, v in rows}

    def set_manual_importance(self, domain_id: str, asset_id: str, value: int) -> bool:
        with self._lock:
            cur = self._db.execute(
                "UPDATE assets SET importance_manual = ? WHERE domain_id = ? AND asset_id = ?",
                (value, domain_id, asset_id),
            )
            return cur.rowcount > 0

    # ------------------------------------------------------------ 발견 ID (같은 자산·항목·위치면 유지)

    def finding_id_for(self, domain_id: str, fkey: str) -> str:
        with self._lock:
            row = self._q("SELECT finding_id FROM finding_keys WHERE domain_id = ? AND fkey = ?", (domain_id, fkey))
            if row:
                return row[0][0]
            finding_id = f"F-{self.next_seq('finding'):04d}"
            self._db.execute("INSERT INTO finding_keys VALUES (?, ?, ?)", (domain_id, fkey, finding_id))
            return finding_id

    # ------------------------------------------------------------ 점검

    def create_scan(self, domain_id: str, data: dict) -> dict:
        with self._lock:
            seq = self.next_seq("scan")
            scan_id = f"S-{seq:04d}"
            data = {"scan_id": scan_id, "domain_id": domain_id, **data}
            self._db.execute(
                "INSERT INTO scans VALUES (?, ?, ?, ?, ?)", (scan_id, seq, domain_id, data["status"], _dump(data))
            )
            return data

    def get_scan(self, scan_id: str) -> dict | None:
        row = self._q("SELECT data FROM scans WHERE scan_id = ?", (scan_id,))
        return json.loads(row[0][0]) if row else None

    def save_scan(self, data: dict) -> None:
        self._q("UPDATE scans SET status = ?, data = ? WHERE scan_id = ?", (data["status"], _dump(data), data["scan_id"]))

    def scans_for(self, domain_id: str, statuses: tuple[str, ...] | None = None) -> list[dict]:
        rows = self._q("SELECT data, status FROM scans WHERE domain_id = ? ORDER BY seq", (domain_id,))
        return [json.loads(d) for d, s in rows if statuses is None or s in statuses]

    def running_scans(self) -> list[dict]:
        rows = self._q(
            "SELECT data FROM scans WHERE status NOT IN ('done', 'stopped', 'failed') ORDER BY seq"
        )
        return [json.loads(r[0]) for r in rows]

    # ------------------------------------------------------------ 점검 결과

    def put_scan_assets(self, scan_id: str, assets: list[dict]) -> None:
        with self._lock:
            self._db.execute("DELETE FROM scan_assets WHERE scan_id = ?", (scan_id,))
            self._db.executemany(
                "INSERT INTO scan_assets VALUES (?, ?, ?)", [(scan_id, a["asset_id"], _dump(a)) for a in assets]
            )

    def scan_assets(self, scan_id: str) -> list[dict]:
        rows = self._q("SELECT data FROM scan_assets WHERE scan_id = ? ORDER BY asset_id", (scan_id,))
        return [json.loads(r[0]) for r in rows]

    def put_findings(self, scan_id: str, findings: list[dict]) -> None:
        with self._lock:
            self._db.execute("DELETE FROM findings WHERE scan_id = ?", (scan_id,))
            self._db.executemany(
                "INSERT INTO findings VALUES (?, ?, ?)", [(scan_id, f["finding_id"], _dump(f)) for f in findings]
            )

    def findings(self, scan_id: str) -> list[dict]:
        rows = self._q("SELECT data FROM findings WHERE scan_id = ?", (scan_id,))
        return [json.loads(r[0]) for r in rows]

    def latest_finding(self, finding_id: str) -> dict | None:
        rows = self._q(
            "SELECT f.data FROM findings f JOIN scans s ON s.scan_id = f.scan_id "
            "WHERE f.finding_id = ? ORDER BY s.seq DESC LIMIT 1",
            (finding_id,),
        )
        return json.loads(rows[0][0]) if rows else None

    def add_audit(self, scan_id: str, entry: dict) -> None:
        self._q("INSERT INTO audit (scan_id, data) VALUES (?, ?)", (scan_id, _dump(entry)))

    def audit(self, scan_id: str) -> list[dict]:
        return [json.loads(r[0]) for r in self._q("SELECT data FROM audit WHERE scan_id = ? ORDER BY id", (scan_id,))]

    def put_report(self, scan_id: str, report: dict) -> None:
        self._q("INSERT OR REPLACE INTO reports VALUES (?, ?)", (scan_id, _dump(report)))

    def get_report(self, scan_id: str) -> dict | None:
        row = self._q("SELECT data FROM reports WHERE scan_id = ?", (scan_id,))
        return json.loads(row[0][0]) if row else None
