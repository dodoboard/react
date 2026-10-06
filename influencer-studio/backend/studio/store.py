"""Local persistence: SQLite metadata + PNG files under the data directory."""

from __future__ import annotations

import io
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from PIL import Image, ImageOps

MAX_UPLOAD_SIDE = 2048

_SCHEMA = """
CREATE TABLE IF NOT EXISTS characters (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    spec TEXT NOT NULL,
    portrait_id TEXT NOT NULL,
    reference_ids TEXT NOT NULL,
    lora TEXT NOT NULL DEFAULT '',
    lora_strength REAL NOT NULL DEFAULT 1.0,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS images (
    id TEXT PRIMARY KEY,
    character_id TEXT REFERENCES characters(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,          -- upload | candidate | reference | content
    caption TEXT NOT NULL DEFAULT '',
    prompt TEXT NOT NULL DEFAULT '',
    seed INTEGER,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS images_by_character ON images(character_id, created_at);
"""


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


class Store:
    def __init__(self, root: Path):
        self.images_dir = root / "images"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        # One connection shared by the event loop and FastAPI's threadpool: every access
        # goes through the lock, since sqlite3 connections are not safe for concurrent use.
        self._lock = threading.Lock()
        self._db = sqlite3.connect(root / "studio.db", check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.executescript(_SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def _read(self, sql: str, args: tuple | list = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._db.execute(sql, args).fetchall()

    def _write(self, *statements: tuple[str, tuple | list]) -> None:
        with self._lock:
            for sql, args in statements:
                self._db.execute(sql, args)
            self._db.commit()

    # ── images ──────────────────────────────────────────────────────────────
    def image_path(self, image_id: str) -> Path:
        return self.images_dir / f"{image_id}.png"

    def save_image(
        self,
        data: bytes,
        *,
        kind: str,
        caption: str = "",
        prompt: str = "",
        seed: int | None = None,
        character_id: str | None = None,
        normalize: bool = False,
    ) -> dict:
        img = Image.open(io.BytesIO(data))  # lazy: reads the header only
        image_id = _new_id()
        if normalize:  # user uploads: honor EXIF rotation, drop metadata, cap size, store as PNG
            img = ImageOps.exif_transpose(img).convert("RGB")
            img.thumbnail((MAX_UPLOAD_SIDE, MAX_UPLOAD_SIDE))
            img.save(self.image_path(image_id), format="PNG")
        else:  # ComfyUI output is already PNG
            self.image_path(image_id).write_bytes(data)
        self._write((
            "INSERT INTO images VALUES (?,?,?,?,?,?,?,?,?)",
            (image_id, character_id, kind, caption, prompt, seed, img.width, img.height, time.time()),
        ))
        return self.image(image_id)  # type: ignore[return-value]

    def image(self, image_id: str) -> dict | None:
        rows = self._read("SELECT * FROM images WHERE id = ?", (image_id,))
        return _image_row(rows[0]) if rows else None

    def images(self, character_id: str, kind: str | None = None) -> list[dict]:
        sql, args = "SELECT * FROM images WHERE character_id = ?", [character_id]
        if kind:
            sql, args = sql + " AND kind = ?", [*args, kind]
        return [_image_row(r) for r in self._read(sql + " ORDER BY created_at DESC", args)]

    def delete_image(self, image_id: str) -> None:
        self._write(("DELETE FROM images WHERE id = ?", (image_id,)))
        self.image_path(image_id).unlink(missing_ok=True)

    # ── characters ──────────────────────────────────────────────────────────
    def create_character(self, name: str, spec: dict, portrait_id: str) -> dict:
        character_id = _new_id()
        self._write(
            ("INSERT INTO characters (id, name, spec, portrait_id, reference_ids, created_at) VALUES (?,?,?,?,?,?)",
             (character_id, name, json.dumps(spec), portrait_id, json.dumps([portrait_id]), time.time())),
            ("UPDATE images SET character_id = ?, kind = 'reference' WHERE id = ?", (character_id, portrait_id)),
        )
        return self.character(character_id)  # type: ignore[return-value]

    def character(self, character_id: str) -> dict | None:
        rows = self._read("SELECT * FROM characters WHERE id = ?", (character_id,))
        return _character_row(rows[0]) if rows else None

    def characters(self) -> list[dict]:
        rows = self._read(
            "SELECT c.*, (SELECT COUNT(*) FROM images i WHERE i.character_id = c.id) AS image_count "
            "FROM characters c ORDER BY created_at DESC"
        )
        return [_character_row(r) | {"image_count": r["image_count"]} for r in rows]

    def update_character(
        self,
        character_id: str,
        *,
        name: str | None = None,
        reference_ids: list[str] | None = None,
        lora: str | None = None,
        lora_strength: float | None = None,
    ) -> None:
        changes = {
            "name": name,
            "reference_ids": json.dumps(reference_ids) if reference_ids is not None else None,
            "lora": lora,
            "lora_strength": lora_strength,
        }
        changes = {k: v for k, v in changes.items() if v is not None}
        if not changes:
            return
        self._write((
            f"UPDATE characters SET {', '.join(f'{k} = ?' for k in changes)} WHERE id = ?",
            (*changes.values(), character_id),
        ))

    def delete_character(self, character_id: str) -> None:
        image_ids = [r["id"] for r in self._read("SELECT id FROM images WHERE character_id = ?", (character_id,))]
        self._write(("DELETE FROM characters WHERE id = ?", (character_id,)))
        for image_id in image_ids:
            self.image_path(image_id).unlink(missing_ok=True)


def _image_row(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["url"] = f"/api/images/{d['id']}"
    return d


def _character_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "spec": json.loads(row["spec"]),
        "portrait_id": row["portrait_id"],
        "portrait_url": f"/api/images/{row['portrait_id']}",
        "reference_ids": json.loads(row["reference_ids"]),
        "lora": row["lora"],
        "lora_strength": row["lora_strength"],
        "created_at": row["created_at"],
    }
