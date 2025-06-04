from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file
import pymysql
import os
from datetime import datetime
import qrcode
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import io

app = Flask(__name__)
# Set static folder ke dalam voucher-kurban/static
app.static_folder = os.path.join(os.path.dirname(__file__), 'static')
app.config['UPLOAD_FOLDER'] = os.path.join(app.static_folder, 'uploads')
app.config['BARCODE_FOLDER'] = os.path.join(app.static_folder, 'barcodes')
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data.db')

# Pastikan direktori yang dibutuhkan sudah ada
for dir in [app.config['UPLOAD_FOLDER'], app.config['BARCODE_FOLDER']]:
    if not os.path.exists(dir):
        os.makedirs(dir)

# Ganti koneksi SQLite ke MySQL
def get_db_connection():
    return pymysql.connect(
        host='localhost',
        user='root',  # ganti sesuai user MySQL Anda
        password='',  # ganti sesuai password MySQL Anda
        database='voucher_kurban',
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    # Drop existing tables if they exist
    c.execute('DROP TABLE IF EXISTS pendaftar')
    c.execute('DROP TABLE IF EXISTS kuota')
    # Create tables
    c.execute('''
        CREATE TABLE pendaftar (
            id INTEGER PRIMARY KEY AUTO_INCREMENT,
            nama TEXT NOT NULL,
            alamat TEXT NOT NULL,
            no_hp TEXT NOT NULL,
            foto TEXT,
            barcode TEXT,
            kode_qr TEXT,
            tanggal_daftar DATETIME,
            status VARCHAR(20) DEFAULT 'belum_diambil',
            tipe_kuota VARCHAR(20) DEFAULT 'lokal'
        )
    ''')
    c.execute('''
        CREATE TABLE kuota (
            id INTEGER PRIMARY KEY AUTO_INCREMENT,
            tipe VARCHAR(20) NOT NULL UNIQUE,
            jumlah INTEGER NOT NULL,
            terpakai INTEGER DEFAULT 0
        )
    ''')
    # Inisialisasi kuota hanya jika belum ada
    c.execute('SELECT COUNT(*) as jumlah FROM kuota WHERE tipe = %s', ('lokal',))
    row = c.fetchone()
    if row and row['jumlah'] == 0:
        c.execute('INSERT INTO kuota (tipe, jumlah) VALUES (%s, %s)', ('lokal', 100))
    c.execute('SELECT COUNT(*) as jumlah FROM kuota WHERE tipe = %s', ('luar',))
    row = c.fetchone()
    if row and row['jumlah'] == 0:
        c.execute('INSERT INTO kuota (tipe, jumlah) VALUES (%s, %s)', ('luar', 50))
    conn.commit()
    conn.close()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    conn = get_db_connection()
    c = conn.cursor()
    # Hitung jumlah voucher lokal dan luar yang sudah terisi data
    c.execute('SELECT COUNT(*) as jumlah FROM pendaftar WHERE tipe_kuota = "lokal" AND nama != ""')
    total_lokal = c.fetchone()['jumlah']
    c.execute('SELECT COUNT(*) as jumlah FROM pendaftar WHERE tipe_kuota = "luar" AND nama != ""')
    total_luar = c.fetchone()['jumlah']
    # Hitung jumlah voucher yang belum diambil (sudah ada data, status belum_diambil)
    c.execute('SELECT COUNT(*) as jumlah FROM pendaftar WHERE status = "belum_diambil" AND nama != ""')
    belum_diambil = c.fetchone()['jumlah']
    c.execute('SELECT COUNT(*) as jumlah FROM pendaftar WHERE status = "sudah_diambil" AND nama != ""')
    sudah_diambil = c.fetchone()['jumlah']
    conn.close()
    return render_template('dashboard.html', 
                         total_lokal=total_lokal,
                         total_luar=total_luar,
                         belum_diambil=belum_diambil,
                         sudah_diambil=sudah_diambil)

@app.route('/update_status/<int:id>', methods=['POST'])
def update_status(id):
    status = request.form.get('status')
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('UPDATE pendaftar SET status = %s WHERE id = %s', (status, id))
    conn.commit()
    conn.close()
    return redirect(url_for('verifikasi'))

@app.route('/daftar', methods=['GET', 'POST'])
def daftar():
    if request.method == 'POST':
        nama = request.form['nama']
        alamat = request.form['alamat']
        no_hp = request.form['no_hp']
        tipe_kuota = request.form['tipe_kuota']
        foto = request.files.get('foto')  # gunakan .get agar tidak error jika tidak ada
        conn = get_db_connection()
        c = conn.cursor()
        # Cari barcode kosong yang tersedia untuk tipe_kuota ini
        c.execute('SELECT id, barcode, kode_qr FROM pendaftar WHERE nama = "" AND alamat = "" AND no_hp = "" AND tipe_kuota = %s LIMIT 1', (tipe_kuota,))
        kosong = c.fetchone()
        if not kosong:
            conn.close()
            return "Tidak ada barcode kosong untuk kuota ini!", 400
        barcode_filename = kosong['barcode']
        kode_qr = kosong['kode_qr']
        pendaftar_id = kosong['id']
        # Simpan foto
        filename = ''
        if foto and foto.filename:
            filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{foto.filename}"
            foto.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        # Update data ke barcode kosong, pastikan kode_qr tidak diubah
        c.execute('''
            UPDATE pendaftar SET nama=%s, alamat=%s, no_hp=%s, foto=%s, tanggal_daftar=%s WHERE id=%s
        ''', (nama, alamat, no_hp, filename, datetime.now(), pendaftar_id))
        # Update kuota terpakai
        c.execute('UPDATE kuota SET terpakai = terpakai + 1 WHERE tipe = %s', (tipe_kuota,))
        conn.commit()
        conn.close()
        return redirect(url_for('verifikasi'))
    else:
        # Ambil jumlah barcode kosong untuk info
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('SELECT tipe_kuota, COUNT(*) FROM pendaftar WHERE nama = "" AND alamat = "" AND no_hp = "" GROUP BY tipe_kuota')
        kosong_kuota = {row[0]: row[1] for row in c.fetchall()}
        conn.close()
        return render_template('index.html', kosong_kuota=kosong_kuota)

@app.route('/verifikasi')
def verifikasi():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM pendaftar ORDER BY tanggal_daftar DESC')
    pendaftar = c.fetchall()
    conn.close()
    return render_template('verifikasi.html', pendaftar=pendaftar)

@app.route('/belum_diambil')
def belum_diambil():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM pendaftar WHERE status = "belum_diambil" ORDER BY tanggal_daftar DESC')
    pendaftar = c.fetchall()
    conn.close()
    return render_template('verifikasi.html', pendaftar=pendaftar, view_type="belum_diambil")

@app.route('/sudah_diambil')
def sudah_diambil():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM pendaftar WHERE status = "sudah_diambil" ORDER BY tanggal_daftar DESC')
    pendaftar = c.fetchall()
    conn.close()
    return render_template('verifikasi.html', pendaftar=pendaftar, view_type="sudah_diambil")

@app.route('/scan')
def scan():
    return render_template('scan.html')

@app.route('/verify_qr/<kode>', methods=['GET', 'POST'])
def verify_qr(kode):
    # kode = string kode QR, bisa dengan atau tanpa .png
    kode_qr = kode.replace('.png', '')
    if request.method == 'GET':
        conn = get_db_connection()
        c = conn.cursor()
        # Cek hanya berdasarkan kode_qr
        c.execute('SELECT * FROM pendaftar WHERE kode_qr = %s', (kode_qr,))
        data = c.fetchone()
        conn.close()
        if not data or not data['nama'] or not data['alamat'] or not data['no_hp']:
            return jsonify({'success': False, 'message': 'QR code kosong, tidak valid'}), 400
        return jsonify({
            'success': True,
            'data': {
                'nama': data['nama'],
                'alamat': data['alamat'],
                'no_hp': data['no_hp'],
                'tipe_kuota': data['tipe_kuota'],
                'status': data['status'],
                'foto': data['foto']
            }
        })
    else:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('SELECT status FROM pendaftar WHERE kode_qr = %s', (kode_qr,))
        data = c.fetchone()
        if not data or data['status'] == 'sudah_diambil':
            conn.close()
            return jsonify({'success': False, 'message': 'Voucher sudah diambil atau tidak ditemukan.'}), 400
        c.execute('UPDATE pendaftar SET status = %s WHERE kode_qr = %s', ('sudah_diambil', kode_qr))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Status voucher berhasil diubah!', 'data': {'status': 'sudah_diambil'}})

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_pendaftar(id):
    conn = get_db_connection()
    c = conn.cursor()
    if request.method == 'POST':
        nama = request.form['nama']
        alamat = request.form['alamat']
        no_hp = request.form['no_hp']
        tipe_kuota = request.form['tipe_kuota']
        c.execute('UPDATE pendaftar SET nama = %s, alamat = %s, no_hp = %s, tipe_kuota = %s WHERE id = %s',
                  (nama, alamat, no_hp, tipe_kuota, id))
        conn.commit()
        conn.close()
        return redirect(url_for('verifikasi'))
    else:
        c.execute('SELECT * FROM pendaftar WHERE id = %s', (id,))
        pendaftar = c.fetchone()
        conn.close()
        return render_template('edit.html', pendaftar=pendaftar)

@app.route('/delete/<int:id>', methods=['POST'])
def delete_pendaftar(id):
    conn = get_db_connection()
    c = conn.cursor()
    # Hapus file foto jika ada
    c.execute('SELECT foto, barcode FROM pendaftar WHERE id = %s', (id,))
    row = c.fetchone()
    if row:
        foto = row['foto']
        barcode = row['barcode']
        if foto:
            foto_path = os.path.join(app.config['UPLOAD_FOLDER'], foto)
            if os.path.exists(foto_path):
                os.remove(foto_path)
        if barcode:
            barcode_path = os.path.join(app.config['BARCODE_FOLDER'], barcode)
            if os.path.exists(barcode_path):
                os.remove(barcode_path)
    c.execute('DELETE FROM pendaftar WHERE id = %s', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('verifikasi'))

@app.route('/generate_qr', methods=['POST'])
def generate_qr():
    tipe = request.form.get('tipe')
    jumlah = int(request.form.get('jumlah'))
    # Konfigurasi kode QR
    tahun = '25'  # 2025
    kode_masjid = 'AIK'  # Kode masjid untuk kode QR
    lokasi = 'RW04RT07'  # Kode lokasi untuk kode QR
    jenis = 'L' if tipe == 'lokal' else 'U'
    # Untuk deskripsi di voucher
    nama_masjid = 'Al-ikhlas'
    alamat_masjid = 'Jl. Rks. Bitung 21, Kebonwaru, Batununggal, Bandung 40272'
    conn = get_db_connection()
    c = conn.cursor()
    # Cari nomor urut terakhir untuk tipe dan lokasi ini
    c.execute('''
        SELECT kode_qr FROM pendaftar WHERE kode_qr LIKE %s ORDER BY id DESC LIMIT 1
    ''', (f'KUR{tahun}-{kode_masjid}-{lokasi}-{jenis}-%',))
    last = c.fetchone()
    if last and last['kode_qr']:
        try:
            last_num = int(last['kode_qr'].split('-')[-1])
        except Exception:
            last_num = 0
    else:
        last_num = 0
    for i in range(1, jumlah+1):
        nomor_urut = str(last_num + i).zfill(4)
        kode_qr = f"KUR{tahun}-{kode_masjid}-{lokasi}-{jenis}-{nomor_urut}"
        # Generate QR code image
        qr = qrcode.QRCode(version=1, box_size=14, border=2)
        qr.add_data(kode_qr)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGBA')
        # Load background
        bg_path = os.path.join(app.static_folder, 'assets', 'voucher_bg.png')
        if os.path.exists(bg_path):
            ticket = Image.open(bg_path).convert('RGBA')
            width, height = ticket.size
        else:
            width, height = 1300, 480
            ticket = Image.new('RGBA', (width, height), 'white')
        draw = ImageDraw.Draw(ticket)
        # --- RAPIHKAN PENATAAN QR CODE DAN BLOK TEKS ---
        qr_size = 340  # Sedikit lebih kecil agar proporsional
        qr_img = qr_img.resize((qr_size, qr_size))
        margin_top = int(height * 0.10)
        margin_bottom = int(height * 0.10)
        area_height = height - margin_top - margin_bottom
        # QR code di kiri, vertikal tengah area
        qr_x = int(width * 0.06)
        qr_y = margin_top + (area_height - qr_size) // 2
        ticket.paste(qr_img, (qr_x, qr_y), qr_img)
        # Teks deskripsi
        try:
            font_title = ImageFont.truetype('arialbd.ttf', 60)
            font_code = ImageFont.truetype('arial.ttf', 44)
            font_small = ImageFont.truetype('arial.ttf', 32)
        except:
            font_title = font_code = font_small = None
        import textwrap
        alamat_lines = textwrap.wrap(alamat_masjid, width=38)
        text_lines = [
            ("Voucher Kurban 2025", font_title),
            (f"Kode: {kode_qr}", font_code),
            (f"Masjid: {nama_masjid}", font_small),
        ]
        for i, line in enumerate(alamat_lines):
            text_lines.append((f"Alamat: {line}" if i == 0 else line, font_small))
        text_lines += [
            (f"Tipe: {'Lokal' if jenis=='L' else 'Luar'}", font_small),
            (f"No. Urut: {nomor_urut}", font_small)
        ]
        # Hitung tinggi blok teks
        text_heights = []
        text_widths = []
        for line, font in text_lines:
            if font:
                bbox = draw.textbbox((0,0), line, font=font)
                height_text = bbox[3] - bbox[1]
                width_text = bbox[2] - bbox[0]
            else:
                height_text = 40
                width_text = 400
            text_heights.append(height_text)
            text_widths.append(width_text)
        total_text_height = sum(text_heights) + 18 * (len(text_lines)-1)
        max_text_width = max(text_widths)
        # Posisi blok teks di kanan QR, vertikal tengah area
        text_x = qr_x + qr_size + int(width * 0.05)
        text_block_width = int(width * 0.60)
        text_start_y = margin_top + (area_height - total_text_height) // 2
        # Overlay semi-transparan di belakang blok teks
        overlay_width = max_text_width + 60
        overlay_height = total_text_height + 40
        overlay_x = text_x - 30
        overlay_y = text_start_y - 20
        overlay = Image.new('RGBA', (overlay_width, overlay_height), (0, 0, 0, int(255 * 0.45)))
        ticket.alpha_composite(overlay, (overlay_x, overlay_y))
        # Tulis teks di atas overlay
        y = text_start_y
        for idx, (line, font) in enumerate(text_lines):
            draw.text((text_x, y), line, fill="white", font=font)
            y += text_heights[idx] + 18
        # Garis putus-putus (tanda potong) jika tidak ada background
        if not os.path.exists(bg_path):
            for x in range(8, width-8, 30):
                draw.line([(x, height-35), (x+16, height-35)], fill="gray", width=3)
            draw.rectangle([(0, 0), (width-1, height-1)], outline="black", width=8)
        # Simpan file tiket
        barcode_filename = f"{kode_qr}.png"
        barcode_path = os.path.join(app.config['BARCODE_FOLDER'], barcode_filename)
        ticket.convert('RGB').save(barcode_path)
        c.execute('''
            INSERT INTO pendaftar (nama, alamat, no_hp, foto, kode_qr, barcode, tanggal_daftar, tipe_kuota)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ''', ('', '', '', '', kode_qr, barcode_filename, datetime.now(), tipe))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/print_all_voucher')
def print_all_voucher():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT barcode FROM pendaftar WHERE barcode IS NOT NULL AND barcode != "" ORDER BY id')
    barcodes = [row['barcode'] for row in c.fetchall()]
    conn.close()

    buffer = io.BytesIO()
    c_pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    cols, rows = 2, 4  # 2 kolom x 4 baris per halaman
    margin_x, margin_y = 30, 30
    voucher_w = (width - 2 * margin_x) / cols
    voucher_h = (height - 2 * margin_y) / rows

    for idx, barcode in enumerate(barcodes):
        col = idx % cols
        row = (idx // cols) % rows
        if idx > 0 and idx % (cols * rows) == 0:
            c_pdf.showPage()
        x = margin_x + col * voucher_w
        y = height - margin_y - (row + 1) * voucher_h
        img_path = os.path.join(app.config['BARCODE_FOLDER'], barcode)
        if os.path.exists(img_path):
            c_pdf.drawImage(ImageReader(img_path), x, y, voucher_w-10, voucher_h-10, preserveAspectRatio=True, anchor='c')
    c_pdf.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="semua_voucher.pdf", mimetype='application/pdf')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
