import sqlite3

from studio.store import Store
from tests.media_fixtures import make_wav

# studio.db as created by the Motion release (before voice_id and clip meta)
OLD_SCHEMA = """
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
CREATE TABLE IF NOT EXISTS clips (
    id TEXT PRIMARY KEY,
    character_id TEXT REFERENCES characters(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,          -- driver | music (uploads) | dance | music_dance | motion
    ext TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    caption TEXT NOT NULL DEFAULT '',
    prompt TEXT NOT NULL DEFAULT '',
    seed INTEGER,
    width INTEGER NOT NULL DEFAULT 0,
    height INTEGER NOT NULL DEFAULT 0,
    fps REAL NOT NULL DEFAULT 0,
    duration REAL NOT NULL DEFAULT 0,
    has_audio INTEGER NOT NULL DEFAULT 0,
    source_image_id TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS clips_by_character ON clips(character_id, created_at);
"""


def test_old_database_is_migrated(tmp_path):
    db = sqlite3.connect(tmp_path / "studio.db")
    db.executescript(OLD_SCHEMA)
    db.execute("INSERT INTO clips (id, kind, ext, created_at) VALUES ('old', 'driver', 'mp4', 1)")
    db.commit()
    db.close()

    store = Store(tmp_path)
    assert store.clip("old")["meta"] == {}
    assert store.update_clip_meta("old", cues=[1], hd=None)["meta"] == {"cues": [1]}
    info = {"width": 0, "height": 0, "fps": 0, "duration": 1.0, "has_audio": True}
    clip = store.save_clip(make_wav(tmp_path / "a.wav", seconds=1, onset=0), kind="speech", ext="wav", info=info,
                           meta={"segments": [{"start": 0, "end": 1, "text": "Selam"}]})
    assert clip["meta"]["segments"][0]["text"] == "Selam"
    store.close()
    Store(tmp_path).close()  # reopening a migrated database is a no-op
