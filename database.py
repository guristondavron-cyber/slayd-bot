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
            self.conn.autocommit = True
        else:
            self.conn = sqlite3.connect(DB_PATH)
            self.conn.row_factory = sqlite3.Row

    def cursor(self):
        return DBCursor(self.conn.cursor(), self.is_postgres)

    def commit(self):
        if not self.is_postgres:
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
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            conn.commit()
        except Exception:
            if hasattr(conn.conn, "rollback"):
                conn.conn.rollback()

        try:
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_reminder_sent TIMESTAMP")
            conn.commit()
        except Exception:
            if hasattr(conn.conn, "rollback"):
                conn.conn.rollback()

        try:
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_number TEXT")
            conn.commit()
        except Exception:
            if hasattr(conn.conn, "rollback"):
                conn.conn.rollback()

        try:
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_lucky_spin TIMESTAMP")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS extra_spins INT DEFAULT 0")
            conn.commit()
        except Exception:
            if hasattr(conn.conn, "rollback"):
                conn.conn.rollback()

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
        CREATE TABLE IF NOT EXISTS referral_events (
            id SERIAL PRIMARY KEY,
            referrer_id BIGINT NOT NULL,
            referred_id BIGINT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        try:
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_re_referrer ON referral_events (referrer_id, created_at)")
            cursor.execute("""
            INSERT INTO referral_events (referrer_id, referred_id, created_at)
            SELECT referred_by, user_id, created_at FROM users 
            WHERE referred_by IS NOT NULL
            ON CONFLICT (referred_id) DO NOTHING;
            """)
            conn.commit()
        except Exception:
            if hasattr(conn.conn, "rollback"):
                conn.conn.rollback()

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
            cursor.execute("ALTER TABLE presentations ADD COLUMN IF NOT EXISTS content_json TEXT")
            conn.commit()
        except Exception:
            if hasattr(conn.conn, "rollback"):
                conn.conn.rollback()

        try:
            cursor.execute("ALTER TABLE presentations ADD COLUMN IF NOT EXISTS author_name TEXT")
            conn.commit()
        except Exception:
            if hasattr(conn.conn, "rollback"):
                conn.conn.rollback()

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
        CREATE TABLE IF NOT EXISTS sponsor_channels (
            id SERIAL PRIMARY KEY,
            channel_id TEXT NOT NULL UNIQUE,
            channel_title TEXT NOT NULL,
            channel_username TEXT NOT NULL,
            channel_url TEXT,
            is_active INT DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            provider TEXT NOT NULL,
            amount INT NOT NULL,
            slides_count INT NOT NULL,
            status TEXT DEFAULT 'pending',
            external_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            paid_at TIMESTAMP
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

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS quiz_duels (
            duel_id TEXT PRIMARY KEY,
            creator_id BIGINT NOT NULL,
            opponent_id BIGINT,
            category TEXT,
            questions_json TEXT NOT NULL,
            creator_score INT DEFAULT 0,
            opponent_score INT DEFAULT 0,
            status TEXT DEFAULT 'waiting',
            winner_id BIGINT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

        try:
            cursor.execute("ALTER TABLE users ADD COLUMN phone_number TEXT")
        except Exception:
            pass

        try:
            cursor.execute("ALTER TABLE users ADD COLUMN last_lucky_spin TIMESTAMP")
        except Exception:
            pass

        try:
            cursor.execute("ALTER TABLE users ADD COLUMN extra_spins INTEGER DEFAULT 0")
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
        CREATE TABLE IF NOT EXISTS referral_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER NOT NULL,
            referred_id INTEGER NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        try:
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_re_referrer ON referral_events (referrer_id, created_at)")
            cursor.execute("""
            INSERT OR IGNORE INTO referral_events (referrer_id, referred_id, created_at)
            SELECT referred_by, user_id, created_at FROM users 
            WHERE referred_by IS NOT NULL;
            """)
        except Exception:
            pass

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
        CREATE TABLE IF NOT EXISTS sponsor_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT NOT NULL UNIQUE,
            channel_title TEXT NOT NULL,
            channel_username TEXT NOT NULL,
            channel_url TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            amount INTEGER NOT NULL,
            slides_count INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            external_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            paid_at TIMESTAMP
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

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS quiz_duels (
            duel_id TEXT PRIMARY KEY,
            creator_id INTEGER NOT NULL,
            opponent_id INTEGER,
            category TEXT,
            questions_json TEXT NOT NULL,
            creator_score INTEGER DEFAULT 0,
            opponent_score INTEGER DEFAULT 0,
            status TEXT DEFAULT 'waiting',
            winner_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

    try:
        sync_referral_counts()
    except Exception:
        pass



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
        user_dict = dict(row)
        user_dict["first_name"] = first_name
        user_dict["username"] = username

        # Agar foydalanuvchi avval kirgan bo'lsa-yu, lekin referred_by bo'lmasa va referal havola bilan kirsa
        if user_dict.get("referred_by") is None and referrer_id and referrer_id != user_id and referrer_id > 1000:
            cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (referrer_id,))
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO users (user_id, first_name, username, slides_left, is_vip, referrals_count) VALUES (?, 'Foydalanuvchi', '', 3, 0, 0)",
                    (referrer_id,),
                )
            cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (referrer_id,))
            if cursor.fetchone():
                valid_referrer = referrer_id
                bonus = int(get_setting("referral_reward", "2"))
                cursor.execute(
                    "UPDATE users SET referred_by = ? WHERE user_id = ? AND referred_by IS NULL",
                    (valid_referrer, user_id),
                )
                cursor.execute(
                    """
                    UPDATE users 
                    SET slides_left = slides_left + ?, referrals_count = referrals_count + 1, extra_spins = COALESCE(extra_spins, 0) + 1 
                    WHERE user_id = ?
                    """,
                    (bonus, valid_referrer),
                )
                try:
                    if IS_POSTGRES:
                        cursor.execute(
                            "INSERT INTO referral_events (referrer_id, referred_id) VALUES (?, ?) ON CONFLICT (referred_id) DO NOTHING",
                            (valid_referrer, user_id),
                        )
                    else:
                        cursor.execute(
                            "INSERT OR IGNORE INTO referral_events (referrer_id, referred_id) VALUES (?, ?)",
                            (valid_referrer, user_id),
                        )
                except Exception:
                    pass
                rewarded_referrer_id = valid_referrer
                reward_amount = bonus
                user_dict["referred_by"] = valid_referrer

        cursor.execute(
            "UPDATE users SET first_name = ?, username = ?, last_active = CURRENT_TIMESTAMP WHERE user_id = ?",
            (first_name, username, user_id),
        )
        conn.commit()
        conn.close()
        return user_dict, rewarded_referrer_id, reward_amount

    initial_limit = int(get_setting("initial_slides_limit", "3"))
    valid_referrer = None

    if referrer_id and referrer_id != user_id and referrer_id > 1000:
        cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (referrer_id,))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO users (user_id, first_name, username, slides_left, is_vip, referrals_count) VALUES (?, 'Foydalanuvchi', '', 3, 0, 0)",
                (referrer_id,),
            )
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
            SET slides_left = slides_left + ?, referrals_count = referrals_count + 1, extra_spins = COALESCE(extra_spins, 0) + 1 
            WHERE user_id = ?
            """,
            (bonus, valid_referrer),
        )
        try:
            if IS_POSTGRES:
                cursor.execute(
                    "INSERT INTO referral_events (referrer_id, referred_id) VALUES (?, ?) ON CONFLICT (referred_id) DO NOTHING",
                    (valid_referrer, user_id),
                )
            else:
                cursor.execute(
                    "INSERT OR IGNORE INTO referral_events (referrer_id, referred_id) VALUES (?, ?)",
                    (valid_referrer, user_id),
                )
        except Exception:
            pass
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


def set_user_phone(user_id: int, phone_number: str):
    """Foydalanuvchining tasdiqlangan telefon raqamini saqlaydi."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET phone_number = ? WHERE user_id = ?", (phone_number, user_id))
    conn.commit()
    conn.close()


def is_user_phone_verified(user_id: int) -> bool:
    """Foydalanuvchi telefon raqami tasdiqlanganligini tekshiradi."""
    user = get_user(user_id)
    if not user:
        return False
    phone = user.get("phone_number")
    return bool(phone and len(str(phone).strip()) >= 7)


def get_user_phone(user_id: int) -> Optional[str]:
    """Foydalanuvchining telefon raqamini qaytaradi."""
    user = get_user(user_id)
    return user.get("phone_number") if user else None


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


def use_slides(user_id: int, count: int = 1, is_admin: bool = False):
    if is_admin:
        return
    user = get_user(user_id)
    if user and user.get("is_vip", 0) == 1:
        return
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET slides_left = CASE WHEN slides_left >= ? THEN slides_left - ? ELSE 0 END WHERE user_id = ?",
        (count, count, user_id),
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

    # Referallar hisobi (users, referral_events va referred_by orqali eng to'liqini olamiz)
    cursor.execute("SELECT COALESCE(SUM(referrals_count), 0) as cnt FROM users")
    row_ref = cursor.fetchone()
    c1 = row_ref["cnt"] if (row_ref and row_ref["cnt"]) else 0

    try:
        cursor.execute("SELECT COUNT(*) as cnt FROM referral_events")
        row_ev = cursor.fetchone()
        c2 = row_ev["cnt"] if (row_ev and row_ev["cnt"]) else 0
    except Exception:
        c2 = 0

    try:
        cursor.execute("SELECT COUNT(*) as cnt FROM users WHERE referred_by IS NOT NULL")
        row_rb = cursor.fetchone()
        c3 = row_rb["cnt"] if (row_rb and row_rb["cnt"]) else 0
    except Exception:
        c3 = 0

    total_referrals = max(c1, c2, c3)

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



def add_sponsor_channel(channel_id: str, channel_title: str, channel_username: str, channel_url: str) -> bool:
    """Yangi homiy kanal qo'shadi yoki yangilaydi."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO sponsor_channels (channel_id, channel_title, channel_username, channel_url, is_active)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT (channel_id) DO UPDATE SET
                channel_title = excluded.channel_title,
                channel_username = excluded.channel_username,
                channel_url = excluded.channel_url,
                is_active = 1
        """, (channel_id, channel_title, channel_username, channel_url))
        conn.commit()
        conn.close()
        return True
    except Exception:
        conn.close()
        return False


def get_active_sponsor_channels() -> List[Dict[str, Any]]:
    """Faol homiy kanallar ro'yxatini oladi."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sponsor_channels WHERE is_active = 1 ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows] if rows else []


def get_all_sponsor_channels() -> List[Dict[str, Any]]:
    """Barcha homiy kanallarni oladi."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sponsor_channels ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows] if rows else []


def delete_sponsor_channel(channel_id: str) -> bool:
    """Homiy kanalni o'chiradi."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sponsor_channels WHERE channel_id = ?", (channel_id,))
    conn.commit()
    conn.close()
    return True


def create_payment_order(user_id: int, provider: str, amount: int, slides_count: int, external_id: Optional[str] = None) -> int:
    """Click yoki Payme uchun yangi to'lov buyurtmasi yaratadi."""
    conn = get_connection()
    cursor = conn.cursor()
    if IS_POSTGRES:
        cursor.execute("""
            INSERT INTO payments (user_id, provider, amount, slides_count, status, external_id, created_at)
            VALUES (?, ?, ?, ?, 'pending', ?, CURRENT_TIMESTAMP)
            RETURNING id
        """, (user_id, provider, amount, slides_count, external_id))
        row = cursor.fetchone()
        order_id = row["id"] if row else 0
    else:
        cursor.execute("""
            INSERT INTO payments (user_id, provider, amount, slides_count, status, external_id, created_at)
            VALUES (?, ?, ?, ?, 'pending', ?, CURRENT_TIMESTAMP)
        """, (user_id, provider, amount, slides_count, external_id))
        order_id = cursor.cursor.lastrowid
    conn.commit()
    conn.close()
    return order_id


def complete_payment_order(order_id: int, external_id: Optional[str] = None) -> Tuple[bool, int, int]:
    """To'lov muvaffaqiyatli tasdiqlanganda 'paid' qiladi va balans qo'shadi."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM payments WHERE id = ? AND status = 'pending'", (order_id,))
    order = cursor.fetchone()
    if not order:
        conn.close()
        return False, 0, 0

    user_id = order["user_id"]
    slides = order["slides_count"]

    cursor.execute("""
        UPDATE payments SET status = 'paid', external_id = COALESCE(?, external_id), paid_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (external_id, order_id))

    cursor.execute("""
        UPDATE users SET slides_left = slides_left + ? WHERE user_id = ?
    """, (slides, user_id))
    conn.commit()
    conn.close()
    return True, user_id, slides


def get_user_referral_stats(user_id: int) -> Dict[str, Any]:
    """Foydalanuvchining shaxsiy referal statistikasi va reyting o'rnini hisoblaydi."""
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Total count
    cursor.execute("SELECT referrals_count, slides_left FROM users WHERE user_id = ?", (user_id,))
    u_row = cursor.fetchone()
    total_refs = u_row["referrals_count"] if u_row and "referrals_count" in u_row.keys() else 0
    slides_left = u_row["slides_left"] if u_row and "slides_left" in u_row.keys() else 0

    # 2. Daily count (bugungi)
    if IS_POSTGRES:
        cursor.execute(
            "SELECT COUNT(*) as cnt FROM referral_events WHERE referrer_id = ? AND created_at >= CURRENT_DATE",
            (user_id,),
        )
    else:
        cursor.execute(
            "SELECT COUNT(*) as cnt FROM referral_events WHERE referrer_id = ? AND DATE(created_at) = DATE('now')",
            (user_id,),
        )
    d_row = cursor.fetchone()
    daily_refs = d_row["cnt"] if d_row else 0

    # 3. Weekly count (oxirgi 7 kun)
    if IS_POSTGRES:
        cursor.execute(
            "SELECT COUNT(*) as cnt FROM referral_events WHERE referrer_id = ? AND created_at >= CURRENT_DATE - INTERVAL '7 days'",
            (user_id,),
        )
    else:
        cursor.execute(
            "SELECT COUNT(*) as cnt FROM referral_events WHERE referrer_id = ? AND created_at >= datetime('now', '-7 days')",
            (user_id,),
        )
    w_row = cursor.fetchone()
    weekly_refs = w_row["cnt"] if w_row else 0

    # 4. Total rank:
    if total_refs > 0:
        cursor.execute("SELECT COUNT(*) as cnt FROM users WHERE referrals_count > ?", (total_refs,))
        row_rank = cursor.fetchone()
        t_cnt = row_rank["cnt"] if row_rank else 0
        rank_total = t_cnt + 1
    else:
        rank_total = "-"

    # 5. Daily rank:
    if daily_refs > 0:
        if IS_POSTGRES:
            cursor.execute(
                """
                SELECT COUNT(*) as cnt FROM (
                    SELECT referrer_id FROM referral_events 
                    WHERE created_at >= CURRENT_DATE 
                    GROUP BY referrer_id HAVING COUNT(*) > ?
                ) as sub
                """,
                (daily_refs,),
            )
        else:
            cursor.execute(
                """
                SELECT COUNT(*) as cnt FROM (
                    SELECT referrer_id FROM referral_events 
                    WHERE DATE(created_at) = DATE('now') 
                    GROUP BY referrer_id HAVING COUNT(*) > ?
                )
                """,
                (daily_refs,),
            )
        d_rank_res = cursor.fetchone()
        rank_daily = (d_rank_res["cnt"] if d_rank_res else 0) + 1
    else:
        rank_daily = "-"

    # 6. Weekly rank:
    if weekly_refs > 0:
        if IS_POSTGRES:
            cursor.execute(
                """
                SELECT COUNT(*) as cnt FROM (
                    SELECT referrer_id FROM referral_events 
                    WHERE created_at >= CURRENT_DATE - INTERVAL '7 days' 
                    GROUP BY referrer_id HAVING COUNT(*) > ?
                ) as sub
                """,
                (weekly_refs,),
            )
        else:
            cursor.execute(
                """
                SELECT COUNT(*) as cnt FROM (
                    SELECT referrer_id FROM referral_events 
                    WHERE created_at >= datetime('now', '-7 days') 
                    GROUP BY referrer_id HAVING COUNT(*) > ?
                )
                """,
                (weekly_refs,),
            )
        w_rank_res = cursor.fetchone()
        rank_weekly = (w_rank_res["cnt"] if w_rank_res else 0) + 1
    else:
        rank_weekly = "-"

    reward_per_ref = int(get_setting("referral_reward", "2"))
    bonus_earned = total_refs * reward_per_ref

    conn.close()
    return {
        "total_referrals": total_refs,
        "daily_referrals": daily_refs,
        "weekly_referrals": weekly_refs,
        "bonus_earned": bonus_earned,
        "rank_total": rank_total,
        "rank_daily": rank_daily,
        "rank_weekly": rank_weekly,
        "slides_left": slides_left,
        "reward_per_ref": reward_per_ref,
    }


def get_top_referrers(period: str = "daily", limit: int = 10) -> List[Dict[str, Any]]:
    """
    Kunlik, haftalik yoki umumiy eng ko'p referal qo'shgan foydalanuvchilar ro'yxatini qaytaradi.
    period: 'daily' | 'weekly' | 'total'
    """
    conn = get_connection()
    cursor = conn.cursor()

    if period == "daily":
        if IS_POSTGRES:
            cursor.execute(
                """
                SELECT r.referrer_id as user_id, COUNT(*) as ref_count, u.first_name, u.username
                FROM referral_events r
                LEFT JOIN users u ON r.referrer_id = u.user_id
                WHERE r.created_at >= CURRENT_DATE
                GROUP BY r.referrer_id, u.first_name, u.username
                ORDER BY ref_count DESC, r.referrer_id ASC
                LIMIT ?
                """,
                (limit,),
            )
        else:
            cursor.execute(
                """
                SELECT r.referrer_id as user_id, COUNT(*) as ref_count, u.first_name, u.username
                FROM referral_events r
                LEFT JOIN users u ON r.referrer_id = u.user_id
                WHERE DATE(r.created_at) = DATE('now')
                GROUP BY r.referrer_id, u.first_name, u.username
                ORDER BY ref_count DESC, r.referrer_id ASC
                LIMIT ?
                """,
                (limit,),
            )
    elif period == "weekly":
        if IS_POSTGRES:
            cursor.execute(
                """
                SELECT r.referrer_id as user_id, COUNT(*) as ref_count, u.first_name, u.username
                FROM referral_events r
                LEFT JOIN users u ON r.referrer_id = u.user_id
                WHERE r.created_at >= CURRENT_DATE - INTERVAL '7 days'
                GROUP BY r.referrer_id, u.first_name, u.username
                ORDER BY ref_count DESC, r.referrer_id ASC
                LIMIT ?
                """,
                (limit,),
            )
        else:
            cursor.execute(
                """
                SELECT r.referrer_id as user_id, COUNT(*) as ref_count, u.first_name, u.username
                FROM referral_events r
                LEFT JOIN users u ON r.referrer_id = u.user_id
                WHERE r.created_at >= datetime('now', '-7 days')
                GROUP BY r.referrer_id, u.first_name, u.username
                ORDER BY ref_count DESC, r.referrer_id ASC
                LIMIT ?
                """,
                (limit,),
            )
    else:  # total
        cursor.execute(
            """
            SELECT user_id, referrals_count as ref_count, first_name, username
            FROM users
            WHERE referrals_count > 0
            ORDER BY referrals_count DESC, created_at ASC
            LIMIT ?
            """,
            (limit,),
        )

    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows] if rows else []


def sync_referral_counts():
    """Barcha foydalanuvchilarning referallari sonini qayta to'liq tekshirib, sinxronlaydi."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # 1. users jadvalidagi referred_by orqali referral_events ni to'ldirish
        if IS_POSTGRES:
            cursor.execute("""
                INSERT INTO referral_events (referrer_id, referred_id, created_at)
                SELECT referred_by, user_id, created_at FROM users 
                WHERE referred_by IS NOT NULL
                ON CONFLICT (referred_id) DO NOTHING
            """)
        else:
            cursor.execute("""
                INSERT OR IGNORE INTO referral_events (referrer_id, referred_id, created_at)
                SELECT referred_by, user_id, created_at FROM users 
                WHERE referred_by IS NOT NULL
            """)

        # 2. referral_events dagi haqiqiy sonlarni users.referrals_count ga sinxronlash
        cursor.execute("""
            UPDATE users SET referrals_count = (
                SELECT COUNT(*) FROM referral_events WHERE referral_events.referrer_id = users.user_id
            ) WHERE user_id IN (SELECT DISTINCT referrer_id FROM referral_events)
        """)

        # 3. Agar referral_events jadvali bo'sh bo'lsa, referred_by orqali hisoblash (fallback)
        cursor.execute("""
            UPDATE users SET referrals_count = (
                SELECT COUNT(*) FROM users u2 WHERE u2.referred_by = users.user_id
            ) WHERE referrals_count = 0 AND user_id IN (
                SELECT DISTINCT referred_by FROM users WHERE referred_by IS NOT NULL
            )
        """)

        conn.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"sync_referral_counts error: {e}", exc_info=True)
        try:
            conn.conn.rollback()
        except Exception:
            pass
    finally:
        conn.close()


def get_all_referrers_admin(limit: int = 50) -> List[Dict[str, Any]]:
    """Admin uchun referallari bor barcha foydalanuvchilar ro'yxati (ikkala manbadan)."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Avval sinxronlaymiz
        sync_referral_counts()
    except Exception:
        pass

    # Birlamchi: referrals_count ustuni (sinxronlangandan keyin)
    # Ikkilamchi: referred_by orqali to'g'ridan-to'g'ri hisoblash (agar sinxronlash ishlamasa)
    cursor.execute("""
        SELECT 
            u.user_id,
            u.first_name,
            u.username,
            u.slides_left,
            u.is_vip,
            u.phone_number,
            u.created_at,
            COALESCE(u.referrals_count, 0) as referrals_count,
            (SELECT COUNT(*) FROM users u2 WHERE u2.referred_by = u.user_id) as referred_by_count
        FROM users u
        WHERE COALESCE(u.referrals_count, 0) > 0 
           OR u.user_id IN (SELECT DISTINCT referred_by FROM users WHERE referred_by IS NOT NULL)
           OR u.user_id IN (SELECT DISTINCT referrer_id FROM referral_events)
        ORDER BY CASE 
            WHEN COALESCE(u.referrals_count, 0) > 0 THEN COALESCE(u.referrals_count, 0)
            ELSE (SELECT COUNT(*) FROM users u2 WHERE u2.referred_by = u.user_id)
        END DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        return []
    result = []
    for r in rows:
        d = dict(r)
        # Eng kattasini olamiz: sinxronlangan yoki referred_by orqali hisoblangan
        rc = max(d.get("referrals_count", 0), d.get("referred_by_count", 0))
        d["referrals_count"] = rc
        result.append(d)
    # 0 bo'lganlarni olib tashlaymiz
    result = [r for r in result if r["referrals_count"] > 0]
    result.sort(key=lambda x: x["referrals_count"], reverse=True)
    return result


def get_user_admin_info(user_id: int) -> Optional[Dict[str, Any]]:
    """Admin bitta foydalanuvchini to'liq tekshirishi uchun ma'lumot."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    res = dict(row)

    # Foydalanuvchini kim taklif qilgani
    if res.get("referred_by"):
        cursor.execute("SELECT user_id, first_name, username FROM users WHERE user_id = ?", (res["referred_by"],))
        ref_by_row = cursor.fetchone()
        res["referrer_info"] = dict(ref_by_row) if ref_by_row else None
    else:
        res["referrer_info"] = None

    # Ushbu foydalanuvchi taklif qilgan so'nggi do'stlar
    cursor.execute("""
        SELECT user_id, first_name, username, created_at 
        FROM users 
        WHERE referred_by = ? 
        ORDER BY created_at DESC 
        LIMIT 10
    """, (user_id,))
    res["invited_users"] = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return res


# ------------------ OMAD G'ILDIRAGI (LUCKY WHEEL) ------------------
import random

LUCKY_WHEEL_PRIZES = [
    {"id": "s1", "type": "slides", "amount": 1, "label": "🎁 +1 ta bepul slayd", "weight": 35, "icon": "🎁"},
    {"id": "s2", "type": "slides", "amount": 2, "label": "⚡️ +2 ta bepul slayd", "weight": 25, "icon": "⚡️"},
    {"id": "s3", "type": "slides", "amount": 3, "label": "🚀 +3 ta bepul slayd", "weight": 15, "icon": "🚀"},
    {"id": "s5", "type": "slides", "amount": 5, "label": "💎 Jackpot: +5 ta slayd", "weight": 10, "icon": "💎"},
    {"id": "essay", "type": "essay_bonus", "amount": 3, "label": "📝 1 ta Mustaqil Ish (+3 slayd)", "weight": 10, "icon": "📝"},
    {"id": "vip", "type": "vip", "amount": 1, "label": "👑 24 soatlik VIP Cheksiz rejim", "weight": 5, "icon": "👑"},
]


def can_spin_lucky_wheel(user_id: int) -> Tuple[bool, int, str, int]:
    """
    Foydalanuvchi Omad G'ildiragini aylantira oladimi?
    Qaytaradi: (mumkinmi: bool, qolgan_soniya: int, izoh: str, mavjud_extra_spins: int)
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT last_lucky_spin, extra_spins FROM users WHERE user_id = ?", (user_id,))
    u = cursor.fetchone()
    conn.close()
    if not u:
        return True, 0, "Kunlik bepul aylantirish mavjud!", 0

    extra = u["extra_spins"] if ("extra_spins" in u.keys() and u["extra_spins"]) else 0
    if extra > 0:
        return True, 0, f"Sizda {extra} ta qo'shimcha navbatsiz imkoniyat bor!", extra

    last_spin = u["last_lucky_spin"] if ("last_lucky_spin" in u.keys() and u["last_lucky_spin"]) else None
    if not last_spin:
        return True, 0, "Kunlik bepul aylantirish mavjud!", 0

    if isinstance(last_spin, str):
        try:
            last_dt = datetime.datetime.fromisoformat(last_spin.replace(" ", "T"))
        except Exception:
            last_dt = datetime.datetime.now() - datetime.timedelta(days=2)
    elif isinstance(last_spin, datetime.datetime):
        last_dt = last_spin
    else:
        last_dt = datetime.datetime.now() - datetime.timedelta(days=2)

    diff = (datetime.datetime.now() - last_dt).total_seconds()
    cooldown = 24 * 3600
    if diff >= cooldown:
        return True, 0, "Kunlik bepul aylantirish mavjud!", 0

    rem = int(cooldown - diff)
    return False, rem, "Bugungi bepul imkoniyatdan foydalandingiz.", 0


def execute_lucky_spin(user_id: int) -> Tuple[bool, Dict[str, Any], str]:
    """Omad g'ildiragini aylantiradi va yutuqni balansga qo'shadi."""
    can, rem, msg, extra = can_spin_lucky_wheel(user_id)
    if not can:
        h = rem // 3600
        m = (rem % 3600) // 60
        return False, {}, f"⏳ Keyingi bepul aylantirishgacha: <b>{h} soat {m} daqiqa</b> qoldi.\n\n💡 <i>Do'stingizni taklif qiling va har bir do'stingiz uchun +1 ta navbatsiz aylantirish imkoniyatini oling!</i>"

    weights = [p["weight"] for p in LUCKY_WHEEL_PRIZES]
    won_prize = random.choices(LUCKY_WHEEL_PRIZES, weights=weights, k=1)[0].copy()

    conn = get_connection()
    cursor = conn.cursor()

    if extra > 0:
        cursor.execute("UPDATE users SET extra_spins = CASE WHEN extra_spins > 0 THEN extra_spins - 1 ELSE 0 END WHERE user_id = ?", (user_id,))
    else:
        cursor.execute("UPDATE users SET last_lucky_spin = CURRENT_TIMESTAMP WHERE user_id = ?", (user_id,))

    if won_prize["type"] in ("slides", "essay_bonus"):
        cursor.execute("UPDATE users SET slides_left = slides_left + ? WHERE user_id = ?", (won_prize["amount"], user_id))
    elif won_prize["type"] == "vip":
        cursor.execute("UPDATE users SET is_vip = 1 WHERE user_id = ?", (user_id,))

    conn.commit()

    cursor.execute("SELECT slides_left, is_vip, extra_spins FROM users WHERE user_id = ?", (user_id,))
    updated_u = cursor.fetchone()
    conn.close()

    won_prize["new_balance"] = updated_u["slides_left"] if updated_u else 0
    won_prize["is_vip"] = updated_u["is_vip"] if updated_u else 0
    won_prize["remaining_extra"] = updated_u["extra_spins"] if updated_u else 0
    return True, won_prize, "Yutuq hisobingizga muvaffaqiyatli qo'shildi!"


# ------------------ HAFTALIK SOVRINLI TURNIR ------------------
def get_tournament_info(user_id: int) -> Dict[str, Any]:
    """Haftalik turnir holati, sovrinlar va qolgan vaqt."""
    now = datetime.datetime.now()
    days_until_sunday = (6 - now.weekday()) % 7
    end_of_week = (now + datetime.timedelta(days=days_until_sunday)).replace(
        hour=23, minute=59, second=59, microsecond=0
    )
    if end_of_week < now:
        end_of_week += datetime.timedelta(days=7)
    delta = end_of_week - now
    days = delta.days
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60

    top_weekly = get_top_referrers(period="weekly", limit=10)
    user_stats = get_user_referral_stats(user_id)

    return {
        "remaining_days": days,
        "remaining_hours": hours,
        "remaining_minutes": minutes,
        "top_weekly": top_weekly,
        "user_weekly_refs": user_stats["weekly_referrals"],
        "user_weekly_rank": user_stats["rank_weekly"],
        "total_refs": user_stats["total_referrals"],
    }


def award_tournament_winners() -> List[Dict[str, Any]]:
    """Haftalik turnirning TOP-3 g'oliblariga avtomatik sovrinlarni topshiradi."""
    top_weekly = get_top_referrers(period="weekly", limit=3)
    if not top_weekly:
        return []

    conn = get_connection()
    cursor = conn.cursor()
    awarded = []

    for idx, winner in enumerate(top_weekly, start=1):
        uid = winner["user_id"]
        if idx == 1:
            prize_name = "👑 1 Oylik VIP Cheksiz + 50 ta slayd"
            cursor.execute("UPDATE users SET is_vip = 1, slides_left = slides_left + 50 WHERE user_id = ?", (uid,))
        elif idx == 2:
            prize_name = "💎 15 Kunlik VIP Cheksiz + 30 ta slayd"
            cursor.execute("UPDATE users SET is_vip = 1, slides_left = slides_left + 30 WHERE user_id = ?", (uid,))
        elif idx == 3:
            prize_name = "⚡️ 7 Kunlik VIP Cheksiz + 15 ta slayd"
            cursor.execute("UPDATE users SET is_vip = 1, slides_left = slides_left + 15 WHERE user_id = ?", (uid,))
        else:
            prize_name = "🎁 +5 ta bepul slayd"
            cursor.execute("UPDATE users SET slides_left = slides_left + 5 WHERE user_id = ?", (uid,))

        awarded.append({
            "place": idx,
            "user_id": uid,
            "first_name": winner.get("first_name", "Foydalanuvchi"),
            "username": winner.get("username", ""),
            "prize": prize_name,
            "ref_count": winner.get("ref_count", 0),
        })

    conn.commit()
    conn.close()
    return awarded


# ------------------ BILIMLAR JANGI (QUIZ DUELS) ------------------
def create_quiz_duel(duel_id: str, creator_id: int, category: str, questions_json: str):
    """Yangi viktorina duelini yaratadi."""
    conn = get_connection()
    cursor = conn.cursor()
    if IS_POSTGRES:
        cursor.execute("""
            INSERT INTO quiz_duels (duel_id, creator_id, category, questions_json, status)
            VALUES (?, ?, ?, ?, 'waiting')
            ON CONFLICT (duel_id) DO UPDATE SET questions_json = EXCLUDED.questions_json
        """, (duel_id, creator_id, category, questions_json))
    else:
        cursor.execute("""
            INSERT OR REPLACE INTO quiz_duels (duel_id, creator_id, category, questions_json, status)
            VALUES (?, ?, ?, ?, 'waiting')
        """, (duel_id, creator_id, category, questions_json))
    conn.commit()
    conn.close()


def get_quiz_duel(duel_id: str) -> Optional[Dict[str, Any]]:
    """Duel ma'lumotlarini ID bo'yicha oladi."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM quiz_duels WHERE duel_id = ?", (duel_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def update_creator_duel_score(duel_id: str, score: int):
    """Duel yaratuvchisining to'plagan ballini yozadi."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE quiz_duels SET creator_score = ?, status = 'waiting' WHERE duel_id = ?", (score, duel_id))
    conn.commit()
    conn.close()


def finish_quiz_duel(duel_id: str, opponent_id: int, opponent_score: int, winner_id: Optional[int]):
    """Duelni yakunlab, raqib balli va g'olibni qayd etadi."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE quiz_duels 
        SET opponent_id = ?, opponent_score = ?, winner_id = ?, status = 'finished'
        WHERE duel_id = ?
    """, (opponent_id, opponent_score, winner_id, duel_id))
    conn.commit()
    conn.close()


def get_user_duel_stats(user_id: int) -> Dict[str, int]:
    """Foydalanuvchining duel statistikasini qaytaradi."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) as wins FROM quiz_duels WHERE winner_id = ? AND status = 'finished'", (user_id,))
        row_w = cursor.fetchone()
        wins = row_w["wins"] if row_w else 0

        cursor.execute("""
            SELECT COUNT(*) as losses FROM quiz_duels 
            WHERE (creator_id = ? OR opponent_id = ?) AND status = 'finished' AND winner_id IS NOT NULL AND winner_id != ?
        """, (user_id, user_id, user_id))
        row_l = cursor.fetchone()
        losses = row_l["losses"] if row_l else 0
    except Exception:
        wins, losses = 0, 0
    finally:
        conn.close()

    return {
        "wins": wins,
        "losses": losses,
        "total_duels": wins + losses
    }

