import os
import sqlite3
from typing import Dict, Any, List, Optional, Tuple

DB_PATH = os.path.join(os.path.dirname(__file__), "bot_database.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Barcha jadvallarni va standart sozlamalarni yaratadi."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        first_name TEXT,
        username TEXT,
        slides_left INTEGER DEFAULT 3,
        referred_by INTEGER,
        referrals_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS presentations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        topic TEXT,
        theme TEXT,
        slide_count INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Standart sozlamalarni kiritish (agar mavjud bo'lmasa)
    default_settings = {
        "required_channel": "",          # Masalan: @kanalingiz yoki bo'sh
        "initial_slides_limit": "3",     # Yangi foydalanuvchiga beriladigan slaydlar soni
        "referral_reward": "2",          # Do'stini taklif qilgani uchun beriladigan bonus
        "admin_ids": "",                 # Bot adminlari ID lari
    }

    for key, val in default_settings.items():
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, val))

    conn.commit()
    conn.close()


def get_setting(key: str, default: str = "") -> str:
    """Sozlamani olish."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    """Sozlamani o'zgartirish."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()


def get_or_create_user(
    user_id: int,
    first_name: str = "",
    username: str = "",
    referrer_id: Optional[int] = None,
) -> Tuple[Dict[str, Any], Optional[int], int]:
    """
    Foydalanuvchini olish yoki yangi yaratish.
    Qaytaradi: (user_dict, rewarded_referrer_id, reward_amount)
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()

    rewarded_referrer_id = None
    reward_amount = 0

    if row:
        # Ma'lumotlarni yangilash (ism yoki username o'zgargan bo'lishi mumkin)
        cursor.execute(
            "UPDATE users SET first_name = ?, username = ? WHERE user_id = ?",
            (first_name, username, user_id),
        )
        conn.commit()
        user_dict = dict(row)
        user_dict["first_name"] = first_name
        user_dict["username"] = username
        conn.close()
        return user_dict, None, 0

    # Yangi foydalanuvchi yaratish
    initial_limit = int(get_setting("initial_slides_limit", "3"))
    valid_referrer = None

    if referrer_id and referrer_id != user_id:
        cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (referrer_id,))
        if cursor.fetchone():
            valid_referrer = referrer_id

    cursor.execute(
        """
        INSERT INTO users (user_id, first_name, username, slides_left, referred_by, referrals_count)
        VALUES (?, ?, ?, ?, ?, 0)
        """,
        (user_id, first_name, username, initial_limit, valid_referrer),
    )

    # Agar do'sti taklif qilgan bo'lsa, taklif qiluvchiga bonus berish
    if valid_referrer:
        bonus = int(get_setting("referral_reward", "2"))
        cursor.execute(
            """
            UPDATE users 
            SET slides_left = slides_left + ?, referrals_count = referrals_count + 1 
            WHERE user_id = ?
            """,
            (bonus, valid_referrer),
        )
        rewarded_referrer_id = valid_referrer
        reward_amount = bonus

    conn.commit()

    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    new_row = cursor.fetchone()
    conn.close()
    return dict(new_row), rewarded_referrer_id, reward_amount


def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def has_slides_left(user_id: int, is_admin: bool = False) -> bool:
    """Foydalanuvchida slayd yaratish uchun limit borligini tekshiradi."""
    if is_admin:
        return True
    user = get_user(user_id)
    return bool(user and user["slides_left"] > 0)


def use_slide(user_id: int, is_admin: bool = False):
    """Foydalanuvchi limitidan bitta ayirish."""
    if is_admin:
        return
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET slides_left = MAX(0, slides_left - 1) WHERE user_id = ?",
        (user_id,),
    )
    conn.commit()
    conn.close()


def add_slides_to_user(user_id: int, count: int):
    """Foydalanuvchiga qo'shimcha slayd limiti qo'shish."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET slides_left = slides_left + ? WHERE user_id = ?",
        (count, user_id),
    )
    conn.commit()
    conn.close()


def record_presentation(user_id: int, topic: str, theme: str, slide_count: int):
    """Yaratilgan taqdimotni statistikaga yozish."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO presentations (user_id, topic, theme, slide_count) VALUES (?, ?, ?, ?)",
        (user_id, topic, theme, slide_count),
    )
    conn.commit()
    conn.close()


def get_all_user_ids() -> List[int]:
    """Rassilka uchun barcha foydalanuvchilar ID larini olish."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    rows = cursor.fetchall()
    conn.close()
    return [r["user_id"] for r in rows]


def get_global_stats() -> Dict[str, Any]:
    """Admin paneli uchun to'liq statistika."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as cnt FROM users")
    total_users = cursor.fetchone()["cnt"]

    cursor.execute("SELECT COUNT(*) as cnt FROM users WHERE DATE(created_at) = DATE('now')")
    today_users = cursor.fetchone()["cnt"]

    cursor.execute("SELECT COUNT(*) as cnt FROM presentations")
    total_presentations = cursor.fetchone()["cnt"]

    cursor.execute("SELECT COUNT(*) as cnt FROM presentations WHERE DATE(created_at) = DATE('now')")
    today_presentations = cursor.fetchone()["cnt"]

    cursor.execute("SELECT SUM(referrals_count) as cnt FROM users")
    row_ref = cursor.fetchone()
    total_referrals = row_ref["cnt"] if row_ref["cnt"] else 0

    conn.close()
    return {
        "total_users": total_users,
        "today_users": today_users,
        "total_presentations": total_presentations,
        "today_presentations": today_presentations,
        "total_referrals": total_referrals,
    }


# Dastur ishga tushganda bazani tayyorlash
init_db()
