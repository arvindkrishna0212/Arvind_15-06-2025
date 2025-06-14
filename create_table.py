import psycopg2
from typing import Dict

def create_tables(db_params: Dict[str, str]) -> None:
    conn = None
    try:
        conn = psycopg2.connect(**db_params)
        cursor = conn.cursor()

        # Create tables
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS store_status (
                id SERIAL PRIMARY KEY,
                store_id VARCHAR(50),
                timestamp_utc TIMESTAMP WITH TIME ZONE,
                status VARCHAR(10)
            );
            CREATE TABLE IF NOT EXISTS menu_hours (
                id SERIAL PRIMARY KEY,
                store_id VARCHAR(50),
                day_of_week INTEGER,
                start_time_local TIME,
                end_time_local TIME
            );
            CREATE TABLE IF NOT EXISTS timezones (
                store_id VARCHAR(50) PRIMARY KEY,
                timezone_str VARCHAR(50)
            );
            CREATE TABLE IF NOT EXISTS reports (
                report_id VARCHAR(50) PRIMARY KEY,
                status VARCHAR(20),
                created_at TIMESTAMP WITH TIME ZONE,
                completed_at TIMESTAMP WITH TIME ZONE,
                report_path TEXT,
                store_id TEXT
            );
        """)

        # Create indexes for performance
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_store_status_store_id ON store_status (store_id);
            CREATE INDEX IF NOT EXISTS idx_store_status_timestamp ON store_status (timestamp_utc);
            CREATE INDEX IF NOT EXISTS idx_menu_hours_store_id ON menu_hours (store_id);
        """)

        conn.commit()
        print("Database tables and indexes created successfully.")
    except Exception as e:
        print(f"Error creating tables: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            cursor.close()
            conn.close()

if __name__ == '__main__':
    db_params = {
        'dbname': 'loop',
        'user': 'postgres',
        'password': 'password',
        'host': 'localhost',
        'port': '5432'
    }
    create_tables(db_params)