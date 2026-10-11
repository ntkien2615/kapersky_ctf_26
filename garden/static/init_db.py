import os
import sqlite3

DB_PATH = os.environ.get('DATABASE_PATH', 'shogi.db')

def get_db_connection():
    return sqlite3.connect(DB_PATH)

def init_database():
    if os.path.exists(DB_PATH):
        print("Database already exists, skipping initialization.")
        return

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        print("Creating database tables...")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS game_moves (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                move TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_game_moves_user_id ON game_moves (user_id);
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_game_moves_created_at ON game_moves (created_at);
        """)

        cur.execute("""
            INSERT INTO game_moves (user_id, move, created_at)
            SELECT 'admin', 'kaspersky{test}', datetime('now')
            WHERE NOT EXISTS (
                SELECT 1 FROM game_moves WHERE user_id = 'admin'
            )
        """)

        conn.commit()
        print("Database tables created successfully!")
    finally:
        conn.close()

if __name__ == "__main__":
    init_database()
