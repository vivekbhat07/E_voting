# test_connect_mysqlconn.py
import mysql.connector

HOST = "127.0.0.1"
USER = "root"
PASSWORD = "785412"
DB = "voting_system"

try:
    conn = mysql.connector.connect(host=HOST, user=USER, password=PASSWORD, database=DB)
    print("Connected OK (mysql-connector).")
    conn.close()
except Exception as e:
    print("Connection failed:", e)
