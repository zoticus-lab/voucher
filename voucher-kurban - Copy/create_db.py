import pymysql

# Konfigurasi koneksi MySQL
connection = pymysql.connect(
    host='localhost',
    user='root',  # ganti sesuai user MySQL Anda
    password='',  # ganti sesuai password MySQL Anda
    database='voucher_kurban',
    charset='utf8mb4',
    cursorclass=pymysql.cursors.DictCursor
)

try:
    with connection.cursor() as cursor:
        # Membuat tabel pendaftar dengan kolom kode_qr (string kode QR tanpa .png) dan barcode (nama file gambar QR)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pendaftar (
                id INT AUTO_INCREMENT PRIMARY KEY,
                nama VARCHAR(255) NOT NULL,
                alamat TEXT NOT NULL,
                no_hp VARCHAR(50) NOT NULL,
                foto VARCHAR(255),
                kode_qr VARCHAR(100),
                barcode VARCHAR(255),
                tanggal_daftar DATETIME,
                status VARCHAR(20) DEFAULT 'belum_diambil',
                tipe_kuota VARCHAR(20) DEFAULT 'lokal'
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS kuota (
                id INT AUTO_INCREMENT PRIMARY KEY,
                tipe VARCHAR(20) NOT NULL UNIQUE,
                jumlah INT NOT NULL,
                terpakai INT DEFAULT 0
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        ''')
    connection.commit()
    print('Database dan tabel berhasil dibuat!')
finally:
    connection.close()
