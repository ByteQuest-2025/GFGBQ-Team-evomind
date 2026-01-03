def get_db_connection():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            gender TEXT CHECK(gender IN ('Male','Female','Other')),
            age INTEGER,
            medical_history TEXT,                
            allergies TEXT,                      
            family_history TEXT,                 
            lifestyle TEXT,
            blood_group TEXT,
            blacklisted INTEGER NOT NULL DEFAULT 1
        );
    """)
    conn.commit()
    conn.close()
