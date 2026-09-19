import datetime
import os
import sqlite3
from typing import Dict, Any, List, Optional, Tuple

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

IS_POSTGRES = bool(DATABASE_URL and DATABASE_URL.startswith("postgresql://"))

if IS_POSTGRES:
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
    except ImportError:
        IS_POSTGRES = False

DB_PATH = os.path.join(os.path.dirname(__file__), "bot_database.db")


class DBConnection:
    """SQLite va PostgreSQL uchun umumiy ulanish va kursor boshqaruvi."""

    def __init__(self):
        self.is_postgres = IS_POSTGRES
        if self.is_postgres:
            self.conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        else:
            self.conn = sqlite3.connect(DB_PATH)
            self.conn.row_factory = sqlite3.Row

    def cursor(self):
        return DBCursor(self.conn.cursor(), self.is_postgres)

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()


class DBCursor:
    def __init__(self, raw_cursor, is_postgres: bool):
        self.cursor = raw_cursor
        self.is_postgres = is_postgres

    def execute(self, sql: str, params: Optional[Tuple[Any, ...]] = None):
        if self.is_postgres:
            sql = sql.replace("?", "%s")
        if params is not None:
            return self.cursor.execute(sql, params)
        return self.cursor.execute(sql)

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    @property
    def rowcount(self):
        return self.cursor.rowcount


def get_connection() -> DBConnection:
    return DBConnection()


def init_db():
    """Barcha jadvallarni va sozlamalarni yaratadi / yangilaydi (SQLite yoki PostgreSQL)."""
    conn = get_connection()
    cursor = conn.cursor()

    if IS_POSTGRES:
        # PostgreSQL jadvallari (Doimiy bulutli baza uchun)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            slides_left INT DEFAULT 3,
            is_vip INT DEFAULT 0,
            referred_by BIGINT,
            referrals_count INT DEFAULT 0,
            last_daily_bonus TIMESTAMP,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_reminder_sent TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        try:
            cursor.execute("ALTER TABLE users ADD COLUMN last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        except Exception:
            pass

        try:
            cursor.execute("ALTER TABLE users ADD COLUMN last_reminder_sent TIMESTAMP")
        except Exception:
            pass

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS last_presentations (
            user_id BIGINT PRIMARY KEY,
            topic TEXT,
            theme TEXT,
            content_json TEXT,
            author_name TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS presentations (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            topic TEXT,
            theme TEXT,
            slide_count INT,
            content_json TEXT,
            author_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        try:
            cursor.execute("ALTER TABLE presentations ADD COLUMN content_json TEXT")
        except Exception:
            pass

        try:
            cursor.execute("ALTER TABLE presentations ADD COLUMN author_name TEXT")
        except Exception:
            pass

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin_users (
            user_id BIGINT PRIMARY KEY,
            added_by BIGINT,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS promocodes (
            code TEXT PRIMARY KEY,
            bonus_slides INT,
            activations_left INT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS used_promocodes (
            user_id BIGINT,
            code TEXT,
            used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(user_id, code)
        );
        """)

        default_settings = {
            "required_channel": "",
            "initial_slides_limit": "3",
            "referral_reward": "2",
            "payment_info": "💳 Karta raqam: 8600 0000 0000 0000\nEgasi: Admin\nTo'lov qilgach chekni adminga yuboring.",
            "card_holder": "",
        }

        for key, val in default_settings.items():
            cursor.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT (key) DO NOTHING",
                (key, val),
            )

    else:
        # SQLite jadvallari (Mahalliy kompyuter uchun)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            slides_left INTEGER DEFAULT 3,
            is_vip INTEGER DEFAULT 0,
            referred_by INTEGER,
            referrals_count INTEGER DEFAULT 0,
            last_daily_bonus TIMESTAMP,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_reminder_sent TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        try:
            cursor.execute("ALTER TABLE users ADD COLUMN is_vip INTEGER DEFAULT 0")
        except Exception:
            pass

        try:
            cursor.execute("ALTER TABLE users ADD COLUMN last_daily_bonus TIMESTAMP")
        except Exception:
            pass

        try:
            cursor.execute("ALTER TABLE users ADD COLUMN last_active TIMESTAMP")
        except Exception:
            pass

        try:
            cursor.execute("ALTER TABLE users ADD COLUMN last_reminder_sent TIMESTAMP")
        except Exception:
            pass

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS last_presentations (
            user_id INTEGER PRIMARY KEY,
            topic TEXT,
            theme TEXT,
            content_json TEXT,
            author_name TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS presentations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            topic TEXT,
            theme TEXT,
            slide_count INTEGER,
            content_json TEXT,
            author_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        try:
            cursor.execute("ALTER TABLE presentations ADD COLUMN content_json TEXT")
        except Exception:
            pass

        try:
            cursor.execute("ALTER TABLE presentations ADD COLUMN author_name TEXT")
        except Exception:
            pass

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin_users (
            user_id INTEGER PRIMARY KEY,
            added_by INTEGER,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS promocodes (
            code TEXT PRIMARY KEY,
            bonus_slides INTEGER,
            activations_left INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS used_promocodes (
            user_id INTEGER,
            code TEXT,
            used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(user_id, code)
        );
        """)

        default_settings = {
            "required_channel": "",
            "initial_slides_limit": "3",
            "referral_reward": "2",
            "payment_info": "💳 Karta raqam: 8600 0000 0000 0000\nEgasi: Admin\nTo'lov qilgach chekni adminga yuboring.",
            "card_holder": "",
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
    if IS_POSTGRES:
        cursor.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            (key, str(value)),
        )
    else:
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()


def get_formatted_payment_info() -> str:
    """To'lov ma'lumotlarini (karta raqami va egasining ism-familiyasi) chiroyli qilib qaytaradi."""
    payment_info = get_setting("payment_info", "").strip()
    card_holder = get_setting("card_holder", "").strip()

    if not payment_info:
        payment_info = "💳 Karta raqam: 8600 0000 0000 0000\nEgasi: Admin\nTo'lov qilgach chekni adminga yuboring."

    # Agar payment_info faqat 16 xonali raqamlar bo'lsa (masalan foydalanuvchi Neonda faqat raqam yozgan bo'lsa)
    clean_digits = payment_info.replace(" ", "").replace("-", "")
    if clean_digits.isdigit() and len(clean_digits) == 16:
        card_formatted = f"{clean_digits[:4]} {clean_digits[4:8]} {clean_digits[8:12]} {clean_digits[12:]}"
        formatted = f"💳 <b>Karta:</b> <code>{card_formatted}</code>"
        if card_holder:
            formatted += f"\n👤 <b>Karta egasi:</b> {card_holder}"
        return formatted

    # Agar alohida card_holder mavjud bo'lsa va payment_info ichida hali yozilmagan bo'lsa
    if card_holder and card_holder.lower() not in payment_info.lower():
        return f"{payment_info}\n👤 <b>Karta egasi:</b> {card_holder}"

    return payment_info


# ------------------ ADMINLAR BOSHQARUVI ------------------
def add_admin(user_id: int, added_by: int = 0, note: str = "") -> bool:
    """Yangi admin qo'shish."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        if IS_POSTGRES:
            cursor.execute(
                """
                INSERT INTO admin_users (user_id, added_by, note) VALUES (?, ?, ?)
                ON CONFLICT (user_id) DO UPDATE SET added_by = EXCLUDED.added_by, note = EXCLUDED.note
                """,
                (user_id, added_by, note),
            )
        else:
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
            "UPDATE users SET first_name = ?, username = ?, last_active = CURRENT_TIMESTAMP WHERE user_id = ?",
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
        INSERT INTO users (user_id, first_name, username, slides_left, is_vip, referred_by, referrals_count, last_active)
        VALUES (?, ?, ?, ?, 0, ?, 0, CURRENT_TIMESTAMP)
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


def touch_user_activity(user_id: int):
    """Foydalanuvchi faolligini yangilaydi (oxirgi faol bo'lgan vaqti)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def get_inactive_users(days_inactive: int = 3, limit: int = 50) -> List[Dict[str, Any]]:
    """3 kundan beri kirmagan va oxirgi 7 kunda eslatma olmagan foydalanuvchilarni qaytaradi."""
    conn = get_connection()
    cursor = conn.cursor()
    if IS_POSTGRES:
        sql = f"""
        SELECT user_id, first_name, username, slides_left, is_vip, last_active
        FROM users
        WHERE (last_active < NOW() - INTERVAL '{days_inactive} days' OR last_active IS NULL)
          AND (last_reminder_sent IS NULL OR last_reminder_sent < NOW() - INTERVAL '7 days')
        LIMIT ?
        """
    else:
        sql = f"""
        SELECT user_id, first_name, username, slides_left, is_vip, last_active
        FROM users
        WHERE (last_active < datetime('now', '-{days_inactive} days') OR last_active IS NULL)
          AND (last_reminder_sent IS NULL OR last_reminder_sent < datetime('now', '-7 days'))
        LIMIT ?
        """
    cursor.execute(sql, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows] if rows else []


def record_reminder_sent(user_id: int):
    """Foydalanuvchiga eslatma yuborilgan vaqtni saqlaydi."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_reminder_sent = CURRENT_TIMESTAMP WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def get_retargeting_stats() -> Dict[str, int]:
    """Retargeting uchun statistikani qaytaradi."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as total FROM users")
    total_row = cursor.fetchone()
    total = total_row["total"] if total_row else 0

    if IS_POSTGRES:
        cursor.execute("SELECT COUNT(*) as inactive FROM users WHERE (last_active < NOW() - INTERVAL '3 days' OR last_active IS NULL)")
    else:
        cursor.execute("SELECT COUNT(*) as inactive FROM users WHERE (last_active < datetime('now', '-3 days') OR last_active IS NULL)")
    inactive_row = cursor.fetchone()
    inactive = inactive_row["inactive"] if inactive_row else 0
    conn.close()
    return {"total": total, "inactive": inactive}


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
        "UPDATE users SET slides_left = CASE WHEN slides_left > 0 THEN slides_left - 1 ELSE 0 END WHERE user_id = ?",
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
        if IS_POSTGRES:
            cursor.execute(
                """
                INSERT INTO promocodes (code, bonus_slides, activations_left) VALUES (?, ?, ?)
                ON CONFLICT (code) DO UPDATE SET bonus_slides = EXCLUDED.bonus_slides, activations_left = EXCLUDED.activations_left
                """,
                (clean_code, bonus_slides, activations),
            )
        else:
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


def record_presentation(
    user_id: int,
    topic: str,
    theme: str,
    slide_count: int,
    content_json: Optional[str] = None,
    author_name: Optional[str] = None,
):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO presentations (user_id, topic, theme, slide_count, content_json, author_name) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, topic, theme, slide_count, content_json, author_name),
    )
    conn.commit()
    conn.close()


def get_user_presentations(user_id: int, limit: int = 5) -> List[Dict[str, Any]]:
    """Foydalanuvchining yaratgan oldingi taqdimotlari tarixini oladi."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, user_id, topic, theme, slide_count, content_json, author_name, created_at FROM presentations WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_presentation_by_id(presentation_id: int) -> Optional[Dict[str, Any]]:
    """ID bo'yicha taqdimot ma'lumotlarini olish."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, user_id, topic, theme, slide_count, content_json, author_name, created_at FROM presentations WHERE id = ?",
        (presentation_id,),
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


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

    if IS_POSTGRES:
        cursor.execute("SELECT COUNT(*) as cnt FROM users WHERE created_at >= CURRENT_DATE")
    else:
        cursor.execute("SELECT COUNT(*) as cnt FROM users WHERE DATE(created_at) = DATE('now')")
    today_users = cursor.fetchone()["cnt"]

    cursor.execute("SELECT COUNT(*) as cnt FROM presentations")
    total_presentations = cursor.fetchone()["cnt"]

    if IS_POSTGRES:
        cursor.execute("SELECT COUNT(*) as cnt FROM presentations WHERE created_at >= CURRENT_DATE")
    else:
        cursor.execute("SELECT COUNT(*) as cnt FROM presentations WHERE DATE(created_at) = DATE('now')")
    today_presentations = cursor.fetchone()["cnt"]

    cursor.execute("SELECT SUM(referrals_count) as cnt FROM users")
    row_ref = cursor.fetchone()
    total_referrals = row_ref["cnt"] if (row_ref and row_ref["cnt"]) else 0

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


def claim_daily_bonus(user_id: int) -> Tuple[bool, str, int, int]:
    """
    Foydalanuvchiga 24 soatda 1 marta +1 bepul slayd bonusi beradi.
    Qaytaradi: (muvaffaqiyatli: bool, xabar: str, joriy_balans: int, qolgan_soniya: int)
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT slides_left, is_vip, last_daily_bonus FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        return False, "Foydalanuvchi topilmadi!", 0, 0

    if user["is_vip"]:
        conn.close()
        return False, "Sizda allaqachon Cheksiz VIP tarif faol!", 9999, 0

    last_bonus = user["last_daily_bonus"]
    if last_bonus:
        last_dt = None
        if isinstance(last_bonus, str):
            try:
                last_dt = datetime.datetime.fromisoformat(last_bonus)
            except Exception:
                try:
                    last_dt = datetime.datetime.strptime(last_bonus, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    pass
        elif isinstance(last_bonus, datetime.datetime):
            last_dt = last_bonus

        if last_dt:
            if last_dt.tzinfo:
                last_dt = last_dt.replace(tzinfo=None)
            now = datetime.datetime.utcnow()
            diff = int((now - last_dt).total_seconds())
            if diff < 86400:
                remaining = 86400 - diff
                hours = remaining // 3600
                mins = (remaining % 3600) // 60
                conn.close()
                return False, f"⏳ <b>Kunlik bonus allaqachon olingan!</b>\n\nKeyingi bonusni <b>{hours} soat {mins} daqiqadan</b> keyin olishingiz mumkin.", user["slides_left"], remaining

    # Bonus berish
    cursor.execute("""
        UPDATE users 
        SET slides_left = slides_left + 1, last_daily_bonus = CURRENT_TIMESTAMP 
        WHERE user_id = ?
    """, (user_id,))
    conn.commit()

    cursor.execute("SELECT slides_left FROM users WHERE user_id = ?", (user_id,))
    new_bal = cursor.fetchone()["slides_left"]
    conn.close()
    return True, "🎉 <b>Tabriklaymiz!</b> Sizga bugungi kunlik <b>+1 bepul slayd</b> bonusi berildi!", new_bal, 0


def save_last_presentation(user_id: int, topic: str, theme: str, content_json: str, author_name: Optional[str] = None):
    """Foydalanuvchining oxirgi yaratilgan taqdimotini Quick Re-skin va PDF uchun saqlaydi."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO last_presentations (user_id, topic, theme, content_json, author_name, updated_at)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id) DO UPDATE SET
            topic = excluded.topic,
            theme = excluded.theme,
            content_json = excluded.content_json,
            author_name = excluded.author_name,
            updated_at = CURRENT_TIMESTAMP
    """, (user_id, topic, theme, content_json, author_name))
    conn.commit()
    conn.close()


def get_last_presentation(user_id: int) -> Optional[Dict[str, Any]]:
    """Foydalanuvchining oxirgi yaratilgan taqdimoti ma'lumotlarini oladi."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM last_presentations WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


init_db()

