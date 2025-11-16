import mysql.connector

# ✅ Direct DB configuration (fill with your actual credentials)
DB_CONFIG = {
    "host": "127.0.0.1",        # use 127.0.0.1 instead of localhost to avoid socket issues
    "port": 3306,
    "user": "root",             # or 'appuser' if you created a separate one
    "password": "785412", # put the SAME password that worked in test.py
    "database": "voting_system",
    "autocommit": True
}

def get_conn():
    """Establish and return a new DB connection."""
    return mysql.connector.connect(**DB_CONFIG)

def query_all(sql, params=None):
    """Execute a SELECT query and return all rows as dicts."""
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute(sql, params or ())
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def query_one(sql, params=None):
    """Return the first row (or None) from a SELECT query."""
    rows = query_all(sql, params)
    return rows[0] if rows else None

def execute(sql, params=None):
    """Execute an INSERT/UPDATE/DELETE query and return last inserted id if any."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(sql, params or ())
    lastid = cur.lastrowid
    conn.commit()
    cur.close()
    conn.close()
    return lastid

def get_next_id(table, id_col):
    """Return next id = MAX(id_col)+1, used when no AUTO_INCREMENT."""
    row = query_one(f"SELECT MAX({id_col}) AS m FROM {table}")
    m = row['m'] if row and row['m'] is not None else 0
    return int(m) + 1
