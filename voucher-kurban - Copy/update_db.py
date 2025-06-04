import sqlite3

def update_database():
    conn = sqlite3.connect('data.db')
    c = conn.cursor()
    
    # Check if columns exist before adding them
    c.execute("PRAGMA table_info(pendaftar)")
    columns = [column[1] for column in c.fetchall()]
    
    if 'status' not in columns:
        c.execute('ALTER TABLE pendaftar ADD COLUMN status TEXT DEFAULT "belum_diambil"')
    
    if 'tipe_kuota' not in columns:
        c.execute('ALTER TABLE pendaftar ADD COLUMN tipe_kuota TEXT DEFAULT "lokal"')
    
    # Create kuota table if it doesn't exist
    c.execute('''
        CREATE TABLE IF NOT EXISTS kuota (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipe TEXT NOT NULL,
            jumlah INTEGER NOT NULL,
            terpakai INTEGER DEFAULT 0
        )
    ''')
    
    # Initialize kuota if empty
    c.execute('SELECT COUNT(*) FROM kuota')
    if c.fetchone()[0] == 0:
        c.execute('INSERT INTO kuota (tipe, jumlah) VALUES (?, ?), (?, ?)', 
                 ('lokal', 100, 'luar', 50))
    
    conn.commit()
    conn.close()
    print("Database updated successfully!")

if __name__ == '__main__':
    update_database()
