import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.config import BASE_DIR

DB_PATH = BASE_DIR / "knowledge_base.db"

_local = threading.local()

def get_connection() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(str(DB_PATH))
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS kb_categories (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            parent_id   INTEGER REFERENCES kb_categories(id),
            description TEXT    DEFAULT '',
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS kb_articles (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            title             TEXT    NOT NULL,
            content           TEXT    DEFAULT '',
            status            TEXT    NOT NULL DEFAULT 'published'
                                    CHECK (status IN ('published','draft','archived')),
            category_id       INTEGER REFERENCES kb_categories(id),
            author_name       TEXT    DEFAULT 'المؤلف',
            total_views       INTEGER NOT NULL DEFAULT 0,
            helpful_votes     INTEGER NOT NULL DEFAULT 0,
            not_helpful_votes INTEGER NOT NULL DEFAULT 0,
            feedback_count    INTEGER NOT NULL DEFAULT 0,
            latest_activity   TEXT,
            created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at        TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS kb_comments (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id  INTEGER NOT NULL REFERENCES kb_articles(id),
            user_name   TEXT    DEFAULT 'مستخدم',
            body        TEXT    NOT NULL,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS kb_activity (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id  INTEGER NOT NULL REFERENCES kb_articles(id),
            description TEXT    NOT NULL,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.commit()


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row) if row else None


def rows_to_list(rows) -> list:
    return [dict(r) for r in rows]


def insert_activity(article_id: int, description: str):
    conn = get_connection()
    ts = now()
    conn.execute(
        "INSERT INTO kb_activity (article_id, description, created_at) VALUES (?, ?, ?)",
        (article_id, description, ts),
    )
    conn.execute(
        "UPDATE kb_articles SET latest_activity = ? WHERE id = ?",
        (ts, article_id),
    )
    conn.commit()


# ── Categories ──────────────────────────────────────────────────────────

def get_all_categories() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM kb_categories ORDER BY name").fetchall()
    return rows_to_list(rows)


def create_category(name: str, parent_id: int | None = None, description: str = "") -> dict:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO kb_categories (name, parent_id, description) VALUES (?, ?, ?)",
        (name, parent_id, description),
    )
    conn.commit()
    return get_category(cur.lastrowid)


def get_category(cat_id: int) -> dict | None:
    conn = get_connection()
    return row_to_dict(conn.execute("SELECT * FROM kb_categories WHERE id = ?", (cat_id,)).fetchone())


def delete_category(cat_id: int) -> bool:
    conn = get_connection()
    cat = get_category(cat_id)
    if not cat:
        return False
    child_ids = [
        r["id"] for r in
        conn.execute("SELECT id FROM kb_categories WHERE parent_id = ?", (cat_id,)).fetchall()
    ]
    for cid in child_ids:
        delete_category(cid)
    article_ids = conn.execute(
        "SELECT id FROM kb_articles WHERE category_id = ?", (cat_id,)
    ).fetchall()
    for row in article_ids:
        delete_article(row["id"])
    conn.execute("DELETE FROM kb_categories WHERE id = ?", (cat_id,))
    conn.commit()
    return True


# ── Articles ────────────────────────────────────────────────────────────

def get_article(article_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM kb_articles WHERE id = ?", (article_id,)).fetchone()
    if not row:
        return None
    article = dict(row)
    cat = get_category(article["category_id"]) if article["category_id"] else None
    article["category"] = {"id": cat["id"], "name": cat["name"]} if cat else None
    article["author"] = {"id": 0, "name": article["author_name"]}
    article["last_edited_by"] = article["author"]
    article["last_edited_at"] = article["updated_at"]
    return article


def list_articles(
    page: int = 1,
    per_page: int = 20,
    category_id: int | None = None,
    search: str | None = None,
) -> tuple[list[dict], dict]:
    conn = get_connection()
    conditions = []
    params = []

    if category_id:
        conditions.append("category_id = ?")
        params.append(category_id)
    if search:
        conditions.append("(title LIKE ? OR content LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    count_row = conn.execute(f"SELECT count(*) AS cnt FROM kb_articles {where}", params).fetchone()
    total = count_row["cnt"]

    offset = (page - 1) * per_page
    rows = conn.execute(
        f"SELECT * FROM kb_articles {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?",
        params + [per_page, offset],
    ).fetchall()

    articles = rows_to_list(rows)
    for a in articles:
        cat = get_category(a["category_id"]) if a["category_id"] else None
        a["category"] = {"id": cat["id"], "name": cat["name"]} if cat else None
        a["author"] = {"id": 0, "name": a["author_name"]}
        a["last_edited_by"] = a["author"]
        a["last_edited_at"] = a["updated_at"]

    meta = {
        "page": page,
        "per_page": per_page,
        "total": total,
        "last_page": max(1, (total + per_page - 1) // per_page),
    }
    return articles, meta


def create_article(
    title: str,
    content: str = "",
    status: str = "published",
    category_id: int | None = None,
    author_name: str = "المؤلف",
) -> dict:
    conn = get_connection()
    ts = now()
    cur = conn.execute(
        """INSERT INTO kb_articles
           (title, content, status, category_id, author_name, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (title, content, status, category_id, author_name, ts, ts),
    )
    article_id = cur.lastrowid
    insert_activity(article_id, f"تم إنشاء المقال '{title}' بواسطة {author_name}")
    conn.commit()
    return get_article(article_id)


def update_article(article_id: int, data: dict) -> dict | None:
    conn = get_connection()
    existing = get_article(article_id)
    if not existing:
        return None

    allowed = {"title", "content", "status", "category_id", "author_name"}
    updates = {k: v for k, v in data.items() if k in allowed and v is not None}
    if not updates:
        return existing

    updates["updated_at"] = now()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [article_id]
    conn.execute(f"UPDATE kb_articles SET {set_clause} WHERE id = ?", values)

    insert_activity(article_id, f"تم تحديث المقال '{existing['title']}'")
    conn.commit()
    return get_article(article_id)


def delete_article(article_id: int) -> bool:
    conn = get_connection()
    cur = conn.execute("DELETE FROM kb_articles WHERE id = ?", (article_id,))
    conn.execute("DELETE FROM kb_comments WHERE article_id = ?", (article_id,))
    conn.execute("DELETE FROM kb_activity WHERE article_id = ?", (article_id,))
    conn.commit()
    return cur.rowcount > 0


def increment_views(article_id: int):
    conn = get_connection()
    conn.execute("UPDATE kb_articles SET total_views = total_views + 1 WHERE id = ?", (article_id,))
    conn.commit()


def vote_article(article_id: int, helpful: bool) -> dict | None:
    conn = get_connection()
    col = "helpful_votes" if helpful else "not_helpful_votes"
    conn.execute(f"UPDATE kb_articles SET {col} = {col} + 1 WHERE id = ?", (article_id,))
    conn.commit()
    return get_article(article_id)


# ── Tree ────────────────────────────────────────────────────────────────

def build_tree() -> list[dict]:
    conn = get_connection()
    categories = rows_to_list(conn.execute("SELECT * FROM kb_categories ORDER BY name").fetchall())
    articles = rows_to_list(
        conn.execute(
            "SELECT id, title, category_id FROM kb_articles WHERE status = 'published' ORDER BY updated_at DESC"
        ).fetchall()
    )

    cat_map: dict[int, dict] = {}
    for c in categories:
        c["children"] = []
        c["articles"] = []
        c["articles_count"] = 0
        cat_map[c["id"]] = c

    roots = []
    for c in categories:
        if c["parent_id"] and c["parent_id"] in cat_map:
            cat_map[c["parent_id"]]["children"].append(c)
        else:
            roots.append(c)

    for a in articles:
        cat_id = a["category_id"]
        if cat_id and cat_id in cat_map:
            cat_map[cat_id]["articles"].append({"id": a["id"], "title": a["title"]})
            cat_map[cat_id]["articles_count"] += 1

    return roots


# ── Comments ────────────────────────────────────────────────────────────

def get_comments(article_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM kb_comments WHERE article_id = ? ORDER BY created_at ASC",
        (article_id,),
    ).fetchall()
    result = rows_to_list(rows)
    for r in result:
        r["user"] = {"name": r["user_name"]}
    return result


def add_comment(article_id: int, body: str, user_name: str = "مستخدم") -> dict:
    conn = get_connection()
    ts = now()
    cur = conn.execute(
        "INSERT INTO kb_comments (article_id, user_name, body, created_at) VALUES (?, ?, ?, ?)",
        (article_id, user_name, body, ts),
    )
    comment_id = cur.lastrowid
    insert_activity(article_id, f"تمت إضافة تعليق بواسطة {user_name}")
    conn.commit()
    row = conn.execute("SELECT * FROM kb_comments WHERE id = ?", (comment_id,)).fetchone()
    d = dict(row)
    d["user"] = {"name": d["user_name"]}
    return d


# ── Activity ────────────────────────────────────────────────────────────

def get_activity(article_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM kb_activity WHERE article_id = ? ORDER BY created_at DESC",
        (article_id,),
    ).fetchall()
    return rows_to_list(rows)


# ── Tickets (stub) ─────────────────────────────────────────────────────

def get_tickets(article_id: int, page: int = 1, per_page: int = 20) -> tuple[list, dict]:
    meta = {"page": page, "per_page": per_page, "total": 0, "last_page": 1}
    return [], meta


# ── Create initial category ────────────────────────────────────────────

def ensure_root_category():
    conn = get_connection()
    row = conn.execute("SELECT id FROM kb_categories WHERE parent_id IS NULL LIMIT 1").fetchone()
    if row:
        root_id = row["id"]
    else:
        cur = conn.execute(
            "INSERT INTO kb_categories (name, description) VALUES (?, ?)",
            ("قاعدة المعرفة", "المقالات المرفوعة"),
        )
        conn.commit()
        root_id = cur.lastrowid

    faq = conn.execute("SELECT id FROM kb_categories WHERE name = 'FAQ' LIMIT 1").fetchone()
    if not faq:
        conn.execute(
            "INSERT INTO kb_categories (name, parent_id, description) VALUES (?, ?, ?)",
            ("FAQ", root_id, "أسئلة وأجوبة المحادثات المباشرة"),
        )
        conn.commit()

    return root_id


def get_faq_category_id() -> int | None:
    conn = get_connection()
    row = conn.execute("SELECT id FROM kb_categories WHERE name = 'FAQ' LIMIT 1").fetchone()
    return row["id"] if row else None
