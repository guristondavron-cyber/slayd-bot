import os
import sqlite3
from typing import Dict, Any, List, Optional, Tuple

DB_PATH = os.path.join(os.path.dirname(__file__), "bot_database.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Barcha jadvallarni va sozlamalarni yaratadi / yangilaydi."""
    conn = get_connection()
    cursor = conn.cursor()

    # Foydalanuvchilar jadvali
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        first_name TEXT,
        username TEXT,
        slides_left INTEGER DEFAULT 3,
        is_vip INTEGER DEFAULT 0,
        referred_by INTEGER,
        referrals_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Agar eski bazada is_vip ustuni bo'lmasa qo'shish
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN is_vip INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    # Sozlamalar jadvali
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    # Taqdimotlar statistikasi jadvali
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

    # Qo'shimcha adminlar jadvali (2-admin va boshqalar)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS admin_users (
        user_id INTEGER PRIMARY KEY,
        added_by INTEGER,
        note TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Promokodlar jadvali
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS promocodes (
        code TEXT PRIMARY KEY,
        bonus_slides INTEGER,
        activations_left INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Ishlatilgan promokodlar (har bir user faqat 1 marta ishlata oladi)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS used_promocodes (
        user_id INTEGER,
        code TEXT,
        used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(user_id, code)
    )
    """)

    # Standart sozlamalar
    default_settings = {
        "required_channel": "",          # Majburiy kanal username
        "initial_slides_limit": "3",     # Boshlang'ich limit
        "referral_reward": "2",          # Referal bonusi
        "payment_info": "💳 Karta raqam: 8600 0000 0000 0000\nEgasi: Admin\nTo'lov qilgach chekni adminga yuboring.",
    }

    for key, val in default_settings.items():
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, val))

    conn.commit()
    conn.close()


def get_setting(key: str, default: str = "") -> str:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()


# ------------------ ADMINLAR BOSHQARUVI ------------------
def add_admin(user_id: int, added_by: int = 0, note: str = "") -> bool:
    """Yangi admin qo'shish."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR REPLACE INTO admin_users (user_id, added_by, note) VALUES (?, ?, ?)",
            (user_id, added_by, note),
        )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def remove_admin(user_id: int) -> bool:
    """Adminni ro'yxatdan o'chirish."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM admin_users WHERE user_id = ?", (user_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def get_all_admins() -> List[Dict[str, Any]]:
    """Barcha adminlarni olish."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM admin_users")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def is_user_admin(user_id: int, config_admin_id: str = "") -> bool:
    """Foydalanuvchi asosiy yoki 2-admin ekanligini tekshiradi."""
    uid_str = str(user_id)
    if config_admin_id and uid_str == config_admin_id:
        return True
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM admin_users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return bool(row)


# ------------------ FOYDALANUVCHILAR VA LIMITLAR ------------------
def get_or_create_user(
    user_id: int,
    first_name: str = "",
    username: str = "",
    referrer_id: Optional[int] = None,
) -> Tuple[Dict[str, Any], Optional[int], int]:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()

    rewarded_referrer_id = None
    reward_amount = 0

    if row:
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

    initial_limit = int(get_setting("initial_slides_limit", "3"))
    valid_referrer = None

    if referrer_id and referrer_id != user_id:
        cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (referrer_id,))
        if cursor.fetchone():
            valid_referrer = referrer_id

    cursor.execute(
        """
        INSERT INTO users (user_id, first_name, username, slides_left, is_vip, referred_by, referrals_count)
        VALUES (?, ?, ?, ?, 0, ?, 0)
        """,
        (user_id, first_name, username, initial_limit, valid_referrer),
    )

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
    if is_admin:
        return True
    user = get_user(user_id)
    if not user:
        return False
    if user.get("is_vip", 0) == 1:
        return True
    return user["slides_left"] > 0


def use_slide(user_id: int, is_admin: bool = False):
    if is_admin:
        return
    user = get_user(user_id)
    if user and user.get("is_vip", 0) == 1:
        return  # VIP foydalanuvchilar limitidan ayirilmaydi
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET slides_left = MAX(0, slides_left - 1) WHERE user_id = ?",
        (user_id,),
    )
    conn.commit()
    conn.close()


def add_slides_to_user(user_id: int, count: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET slides_left = slides_left + ? WHERE user_id = ?",
        (count, user_id),
    )
    conn.commit()
    conn.close()


def set_user_vip(user_id: int, is_vip: bool = True):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET is_vip = ? WHERE user_id = ?",
        (1 if is_vip else 0, user_id),
    )
    conn.commit()
    conn.close()


# ------------------ PROMOKODLAR BOSHQARUVI ------------------
def create_promocode(code: str, bonus_slides: int, activations: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        clean_code = code.strip().upper()
        cursor.execute(
            "INSERT OR REPLACE INTO promocodes (code, bonus_slides, activations_left) VALUES (?, ?, ?)",
            (clean_code, bonus_slides, activations),
        )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def use_promocode(user_id: int, code: str) -> Tuple[bool, str, int]:
    """
    Promokodni ishlatish.
    Qaytaradi: (success: bool, message: str, bonus_added: int)
    """
    clean_code = code.strip().upper()
    conn = get_connection()
    cursor = conn.cursor()

    # Avval ishlatilganmi tekshirish
    cursor.execute("SELECT * FROM used_promocodes WHERE user_id = ? AND code = ?", (user_id, clean_code))
    if cursor.fetchone():
        conn.close()
        return False, "Siz ushbu promokodni avval ishlatgansiz!", 0

    # Promokod mavjudligi va sonini tekshirish
    cursor.execute("SELECT * FROM promocodes WHERE code = ?", (clean_code,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False, "Bunday promokod topilmadi!", 0

    if row["activations_left"] <= 0:
        conn.close()
        return False, "Ushbu promokodning faollashtirish limiti tugagan!", 0

    bonus = row["bonus_slides"]

    # Aktivatsiyani kamaytirish va foydalanuvchiga bonus berish
    cursor.execute("UPDATE promocodes SET activations_left = activations_left - 1 WHERE code = ?", (clean_code,))
    cursor.execute("INSERT INTO used_promocodes (user_id, code) VALUES (?, ?)", (user_id, clean_code))
    cursor.execute("UPDATE users SET slides_left = slides_left + ? WHERE user_id = ?", (bonus, user_id))

    conn.commit()
    conn.close()
    return True, f"🎉 Tabriklaymiz! Hisobingizga +{bonus} ta bepul slayd qo'shildi.", bonus


def get_all_promocodes() -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM promocodes ORDER BY created_at DESC LIMIT 10")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def record_presentation(user_id: int, topic: str, theme: str, slide_count: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO presentations (user_id, topic, theme, slide_count) VALUES (?, ?, ?, ?)",
        (user_id, topic, theme, slide_count),
    )
    conn.commit()
    conn.close()


def get_all_user_ids() -> List[int]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    rows = cursor.fetchall()
    conn.close()
    return [r["user_id"] for r in rows]


def get_global_stats() -> Dict[str, Any]:
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

    cursor.execute("SELECT COUNT(*) as cnt FROM admin_users")
    total_subadmins = cursor.fetchone()["cnt"]

    conn.close()
    return {
        "total_users": total_users,
        "today_users": today_users,
        "total_presentations": total_presentations,
        "today_presentations": today_presentations,
        "total_referrals": total_referrals,
        "total_subadmins": total_subadmins,
    }


init_db()
