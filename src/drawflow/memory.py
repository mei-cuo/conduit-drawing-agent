"""Project-isolated long-term conventions, written only by accepted reviews."""

import sqlite3
from datetime import datetime, timezone

from .config import identifier


class ProjectMemory:
    def __init__(self, path):
        self.path = path
        with self.connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS memories (
                project TEXT NOT NULL, key TEXT NOT NULL, content TEXT NOT NULL,
                kind TEXT NOT NULL, run_id TEXT NOT NULL, reviewer TEXT NOT NULL,
                updated_at TEXT NOT NULL, PRIMARY KEY(project, key))""")

    def connect(self):
        return sqlite3.connect(self.path, timeout=30)

    def remember(self, project, proposals, run_id, reviewer):
        identifier(project)
        if not reviewer.strip():
            raise ValueError("记忆写入需要复核人")
        with self.connect() as conn:
            for item in proposals:
                conn.execute(
                    """INSERT INTO memories VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(project,key) DO UPDATE SET content=excluded.content,
                    kind=excluded.kind,run_id=excluded.run_id,reviewer=excluded.reviewer,
                    updated_at=excluded.updated_at""",
                    (
                        project,
                        item.key,
                        item.content,
                        item.kind,
                        run_id,
                        reviewer,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )

    def recall(self, project, query="", limit=8):
        identifier(project)
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM memories WHERE project=? ORDER BY updated_at DESC",
                    (project,),
                )
            ]
        if query:
            rows.sort(
                key=lambda row: sum(token in row["content"] for token in query.split()),
                reverse=True,
            )
        return rows[:limit]
