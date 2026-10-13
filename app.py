from flask import (Flask,render_template,request,redirect,url_for,session,jsonify,flash)
from pymongo import MongoClient
from werkzeug.security import (generate_password_hash,check_password_hash)
from bson import ObjectId, Binary
from functools import wraps
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from collections import defaultdict
import base64


app = Flask(__name__)
app.secret_key = "qcgaul_secret_key" 

MONGODB_URI = "mongodb+srv://fdilaaa22:fadilamss08@cluster0.aakaikd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
client = MongoClient(MONGODB_URI)
db = client["qcgaul"]

# === Collections ===
collection = db["data"]
users_collection = db["users"]


# === Middleware ===
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("role") != "admin":
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)

    return decorated_function


def user_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("role") != "user":
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)

    return decorated_function


def ensure_default_admin():
    if users_collection.count_documents({"role": "admin"}) == 0:
        users_collection.insert_one({
            "name": "Administrator",
            "email": "admin@telkom.id",
            "role": "admin",
            "password": generate_password_hash("admin123"),
        })
       
# === Routes ===
@app.route("/")
def root():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        user = users_collection.find_one({"email": email})

        if user and check_password_hash(user["password"], password):
            session["user_id"] = str(user["_id"])
            session["name"] = user.get("name", "")
            session["email"] = user.get("email", "")
            session["role"] = user.get("role", "")
            return redirect(url_for("dashboard"))
        else:
            flash("Wrong Email / Password!", "error")
            return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/dashboard")
@login_required
def dashboard():
    today = datetime.now().date()
    h1_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    all_data = list(collection.find({"tanggal": h1_date}, {"_id": 0}))

    if not all_data:
        latest_data = collection.find(
            {"tanggal": {"$lt": str(today)}}, {"_id": 0}
        ).sort("tanggal", -1).limit(1)
        latest_date = None
        for d in latest_data:
            latest_date = d.get("tanggal")
        if latest_date:
            all_data = list(collection.find({"tanggal": latest_date}, {"_id": 0}))
            h1_date = latest_date

    # === Proses Hitung total tiket, redaman, scc, sto ===
    total_tiket = len(all_data)
    total_redaman = sum(
        1 for d in all_data if str(d.get("redaman", "")).strip().upper() == "YA"
    )
    total_scc = sum(
        1 for d in all_data if str(d.get("scc_not_passed", "")).strip().upper() == "YA"
    )
    total_sto = len({
        d.get("sto", "").strip().upper()
        for d in all_data if d.get("sto")
    })

    # === Data untuk grafik jumlah tiket per STO ===
    sto_count = {}
    for d in all_data:
        sto = d.get("sto", "").strip().upper()
        sto_count[sto] = sto_count.get(sto, 0) + 1

    # === Data untuk grafik SCC & Redaman ===
    scc_per_tanggal = {}
    redaman_per_tanggal = {}
    for d in all_data:
        tgl = datetime.strptime(d["tanggal"], "%Y-%m-%d").strftime("%Y-%m-%d")
        if str(d.get("scc_not_passed", "")).strip().upper() == "YA":
            scc_per_tanggal[tgl] = scc_per_tanggal.get(tgl, 0) + 1
        if str(d.get("redaman", "")).strip().upper() == "YA":
            redaman_per_tanggal[tgl] = redaman_per_tanggal.get(tgl, 0) + 1

    tanggal_labels = sorted(list({*scc_per_tanggal.keys(), *redaman_per_tanggal.keys()}))
    scc_values = [scc_per_tanggal.get(tgl, 0) for tgl in tanggal_labels]
    redaman_values = [redaman_per_tanggal.get(tgl, 0) for tgl in tanggal_labels]

    # === Data untuk grafik jumlah tiket (per tanggal) ===
    jumlah_tiket_chart = {h1_date: total_tiket}

    min_doc = collection.find_one(sort=[("tanggal", 1)])
    max_doc = collection.find_one(sort=[("tanggal", -1)])
    min_date = min_doc["tanggal"] if min_doc else datetime.now().strftime("%Y-%m-%d")
    max_date = max_doc["tanggal"] if max_doc else datetime.now().strftime("%Y-%m-%d")

    return render_template(
        "dashboard.html",
        total_tiket=total_tiket,
        total_redaman=total_redaman,
        total_scc=total_scc,
        total_sto=total_sto,
        sto_labels=list(sto_count.keys()),
        sto_values=list(sto_count.values()),
        jumlah_tiket_labels=list(jumlah_tiket_chart.keys()),
        jumlah_tiket_values=list(jumlah_tiket_chart.values()),
        tanggal_labels=tanggal_labels,
        scc_values=scc_values,
        redaman_values=redaman_values,
        min_date=min_date,
        max_date=max_date,
        role=session.get("role"),
        name=session.get("name"),
        email=session.get("email"),
    )


@app.route("/filter-data", methods=["POST"])
@login_required
def filter_data():
    start_date = request.json.get("start_date")
    end_date = request.json.get("end_date")

    if not start_date or not end_date:
        return jsonify({"status": "danger", "message": "Pilih kedua tanggal terlebih dahulu"}), 400

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    days_diff = (end_dt - start_dt).days + 1

    data_in_range = list(collection.find({
        "tanggal": {"$gte": start_date, "$lte": end_date}
    }, {"_id": 0}))

    if not data_in_range:
        return jsonify({"status": "danger", "message": "Tidak ada data untuk rentang tanggal tersebut"}), 404

    if days_diff > 365:
        mode = "year"
    elif days_diff > 30:
        mode = "month"
    else:
        mode = "day"

    # === Agregasi berdasarkan mode ===
    if mode == "day":
        labels = [(start_dt + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days_diff)]
        count_tiket = {tgl: 0 for tgl in labels}
        count_scc = {tgl: 0 for tgl in labels}
        count_redaman = {tgl: 0 for tgl in labels}
        sto_count = defaultdict(int)

        for d in data_in_range:
            try:
                tgl = datetime.strptime(d["tanggal"], "%Y-%m-%d").strftime("%Y-%m-%d")
            except Exception:
                continue

            if tgl not in count_tiket:
                continue

            count_tiket[tgl] += 1
            if str(d.get("scc_not_passed", "")).strip().upper() == "YA":
                count_scc[tgl] += 1
            if str(d.get("redaman", "")).strip().upper() == "YA":
                count_redaman[tgl] += 1
            sto_count[d.get("sto", "").strip().upper()] += 1

        result = {
            "mode": mode,
            "labels": labels,
            "jumlah_tiket": [count_tiket[tgl] for tgl in labels],
            "scc": [count_scc[tgl] for tgl in labels],
            "redaman": [count_redaman[tgl] for tgl in labels],
            "sto_labels": list(sto_count.keys()),
            "sto_values": list(sto_count.values()),
            "total_tiket": len(data_in_range),
            "total_redaman": sum(1 for d in data_in_range if str(d.get("redaman", "")).strip().upper() == "YA"),
            "total_scc": sum(1 for d in data_in_range if str(d.get("scc_not_passed", "")).strip().upper() == "YA"),
            "total_sto": len({d.get("sto", "").strip().upper() for d in data_in_range if d.get("sto")}),
        }

    elif mode == "month":
        count_tiket = defaultdict(int)
        count_scc = defaultdict(int)
        count_redaman = defaultdict(int)
        sto_count = defaultdict(int)

        for d in data_in_range:
            tgl = datetime.strptime(d["tanggal"], "%Y-%m-%d")
            key = f"{tgl.year}-{tgl.month:02d}"
            count_tiket[key] += 1
            if str(d.get("scc_not_passed", "")).strip().upper() == "YA":
                count_scc[key] += 1
            if str(d.get("redaman", "")).strip().upper() == "YA":
                count_redaman[key] += 1
            sto_count[d.get("sto", "").strip().upper()] += 1

        month_labels = sorted(count_tiket.keys())
        result = {
            "mode": mode,
            "labels": month_labels,
            "jumlah_tiket": [count_tiket[m] for m in month_labels],
            "scc": [count_scc[m] for m in month_labels],
            "redaman": [count_redaman[m] for m in month_labels],
            "sto_labels": list(sto_count.keys()),
            "sto_values": list(sto_count.values()),
            "total_tiket": len(data_in_range),
            "total_redaman": sum(1 for d in data_in_range if str(d.get("redaman", "")).strip().upper() == "YA"),
            "total_scc": sum(1 for d in data_in_range if str(d.get("scc_not_passed", "")).strip().upper() == "YA"),
            "total_sto": len({d.get("sto", "").strip().upper() for d in data_in_range if d.get("sto")}),
        }

    else:  # year
        count_tiket = defaultdict(int)
        count_scc = defaultdict(int)
        count_redaman = defaultdict(int)
        sto_count = defaultdict(int)

        for d in data_in_range:
            tgl = datetime.strptime(d["tanggal"], "%Y-%m-%d")
            key = str(tgl.year)
            count_tiket[key] += 1
            if str(d.get("scc_not_passed", "")).strip().upper() == "YA":
                count_scc[key] += 1
            if str(d.get("redaman", "")).strip().upper() == "YA":
                count_redaman[key] += 1
            sto_count[d.get("sto", "").strip().upper()] += 1

        year_labels = sorted(count_tiket.keys())
        result = {
            "mode": mode,
            "labels": year_labels,
            "jumlah_tiket": [count_tiket[y] for y in year_labels],
            "scc": [count_scc[y] for y in year_labels],
            "redaman": [count_redaman[y] for y in year_labels],
            "sto_labels": list(sto_count.keys()),
            "sto_values": list(sto_count.values()),
            "total_tiket": len(data_in_range),
            "total_redaman": sum(1 for d in data_in_range if str(d.get("redaman", "")).strip().upper() == "YA"),
            "total_scc": sum(1 for d in data_in_range if str(d.get("scc_not_passed", "")).strip().upper() == "YA"),
            "total_sto": len({d.get("sto", "").strip().upper() for d in data_in_range if d.get("sto")}),
        }

    result["status"] = "success"
    result["message"] = f"Data ditemukan untuk rentang {start_date} sampai {end_date}"
    return jsonify(result)

@app.route("/available-dates")
@login_required
def available_dates():
    dates = collection.distinct("tanggal")
    dates = sorted([d for d in dates if d], key=lambda x: x)

    return jsonify({"dates": dates})


@app.route('/management_data')
@login_required
@user_only
def tabel_excel():
    page = int(request.args.get('page', 1))
    per_page = 50
    is_new = request.args.get('new', 'false').lower() == 'true'
    filter_date = request.args.get('date')
    view_all = request.args.get('view_all', 'false').lower() == 'true'
    search_query = request.args.get('search', '').strip()

    saved_dates = [d for d in collection.distinct("tanggal") if isinstance(d, str) and d.strip()]
    saved_dates.sort(reverse=True)

    paginated_data, total_items, total_pages, start, end = [], 0, 0, 0, 0

    # Kondisi import baru
    if is_new:
        return render_template(
            'management_data.html',
            saved_dates=saved_dates,
            all_data=[],
            total_items=0,
            total_pages=0,
            page=1,
            per_page=per_page,
            new_data=True,
            selected_date=None,
            view_all=False,
            start=0,
            end=0,
            role=session.get('role'),
            name=session.get('name'),
            email=session.get('email'),
            search_query=search_query
        )

    # Kalau user belum pilih filter_date, belum klik view_all, dan tidak search → jangan load data
    if not filter_date and not view_all and not search_query:
        return render_template(
            'management_data.html',
            saved_dates=saved_dates,
            all_data=[],
            total_items=0,
            total_pages=0,
            page=page,
            per_page=per_page,
            new_data=False,
            selected_date=None,
            view_all=False,
            start=0,
            end=0,
            role=session.get('role'),
            name=session.get('name'),
            email=session.get('email'),
            search_query=search_query
        )

    # Search server-side (prioritas utama)
    if search_query:
        query = {"$or": [
            {"no_tiket": {"$regex": search_query, "$options": "i"}},
            {"no_inet": {"$regex": search_query, "$options": "i"}},
            {"sto": {"$regex": search_query, "$options": "i"}},
            {"tanggal": {"$regex": search_query, "$options": "i"}}
        ]}
        total_items = collection.count_documents(query)
        total_pages = (total_items + per_page - 1) // per_page
        skip = (page - 1) * per_page
        paginated_data = list(
            collection.find(query)
            .sort([("tanggal", 1), ("_id", 1)])
            .skip(skip)
            .limit(per_page)
        )
        start, end = skip, min(skip + per_page, total_items)

    # Logika View All Data
    elif view_all:
        total_items = collection.count_documents({})
        total_pages = (total_items + per_page - 1) // per_page
        skip = (page - 1) * per_page
        paginated_data = list(
            collection.find()
            .sort([("tanggal", 1), ("_id", 1)])
            .skip(skip)
            .limit(per_page)
        )
        start, end = skip, min(skip + per_page, total_items)
        
    # Filter berdasarkan tanggal tertentu
    elif filter_date:
        query = {"tanggal": filter_date}
        total_items = collection.count_documents(query)
        total_pages = (total_items + per_page - 1) // per_page
        skip = (page - 1) * per_page
        paginated_data = list(
            collection.find(query)
            .sort([("_id", 1)])
            .skip(skip)
            .limit(per_page)
        )
        start, end = skip, min(skip + per_page, total_items)


    return render_template(
        'management_data.html',
        saved_dates=saved_dates,
        all_data=paginated_data,
        total_items=total_items,
        total_pages=total_pages,
        page=page,
        per_page=per_page,
        new_data=False,
        selected_date=filter_date,
        view_all=view_all,
        start=start,
        end=end,
        role=session.get('role'),
        name=session.get('name'),
        email=session.get('email'),
        search_query=search_query
    )


# Update nomor tiket → kolom 'no'
@app.route('/update-no', methods=['POST'])
def update_no():
    data = request.get_json()
    updates = data.get('updates', [])

    for item in updates:
        no_tiket, new_no = item.get('no_tiket'), item.get('no')
        if no_tiket and new_no:
            collection.update_one(
                {'no_tiket': no_tiket},
                {'$set': {'no': new_no}}
            )

    return jsonify({'message': 'Nomor berhasil diperbarui'}), 200


@app.route('/save-data', methods=['POST'])
def save_data():
    try:
        payload = request.get_json()
        data = payload.get("data", [])

        if not data:
            return jsonify({"message": "Tidak ada data yang dikirim."}), 400

        tanggal_import = data[0].get("tanggal")
        if not tanggal_import:
            return jsonify({"message": "Tanggal tidak ditemukan dalam data."}), 400
        
        exists = collection.count_documents({"tanggal": tanggal_import}) > 0
        if exists:
            return jsonify({"message": f"Data untuk tanggal {tanggal_import} sudah ada."}), 409

        collection.insert_many(data)
        return jsonify({"message": "Data berhasil disimpan ke MongoDB!"}), 201

    except Exception as e:
        return jsonify({"message": f"Gagal menyimpan data: {str(e)}"}), 500


@app.route('/check-date-exists', methods=['POST'])
def check_date_exists():
    data = request.get_json()
    tanggal = data.get('tanggal') if data else None

    if not tanggal:
        return jsonify({'exists': False, 'message': 'Tanggal tidak dikirim'}), 400

    exists = collection.count_documents({'tanggal': tanggal}) > 0

    if exists:
        return jsonify({'exists': True, 'message': f'Data untuk tanggal {tanggal} sudah ada'}), 200
    else:
        return jsonify({'exists': False, 'message': f'Tidak ada data untuk tanggal {tanggal}'}), 404
@app.route('/fix-none-tanggal', methods=['POST'])
def fix_none_tanggal():
    try:
        data = request.get_json()
        tanggal_pengganti = data.get("tanggal")

        if not tanggal_pengganti:
            return jsonify({"message": "Tanggal pengganti wajib dikirim."}), 400

        # Update semua data yang tanggalnya None atau kosong
        result = collection.update_many(
            {"$or": [{"tanggal": None}, {"tanggal": ""}]},
            {"$set": {"tanggal": tanggal_pengganti}}
        )

        return jsonify({
            "message": f"{result.modified_count} data berhasil diperbaiki ke tanggal {tanggal_pengganti}"
        }), 200

    except Exception as e:
        return jsonify({"message": f"Error: {str(e)}"}), 500


@app.route("/management_user")
@login_required
@admin_required
def management_user():
    return render_template("management_user.html",
                           role=session.get('role'),
                           name=session.get('name'),
                           email=session.get('email'))

@app.context_processor
def inject_user_role():
    return {
        'user_role': session.get('role'),
        'user_name': session.get('name'),
        'user_email': session.get('email')
    }


@app.route('/get_users')
@admin_required
def get_users():
    users = []
    for u in users_collection.find():
        users.append({
            'name': u.get('name'),
            'email': u.get('email'),
            'role': u.get('role')
        })
    return jsonify(users)


@app.route('/add_user', methods=['POST'])
@login_required
@admin_required
def add_user():
    data = request.get_json()
    name = data.get('name')
    email = data.get('email')
    role = data.get('role')
    password = data.get('password', 'admin123')

    # Cek jika role = admin, tolak
    if role == 'admin':
        return jsonify({'message': 'Tidak dapat menambahkan admin baru'}), 403

   
    if users_collection.find_one({'email': email}):
        return jsonify({'message': 'Email sudah digunakan'}), 409

    hashed_password = generate_password_hash(password)
    users_collection.insert_one({
        'name': name,
        'email': email,
        'role': 'user',
        'password': hashed_password
    })
    return jsonify({'message': 'User berhasil ditambahkan'}), 200


@app.route('/delete_user/<email>', methods=['DELETE'])
@login_required
@admin_required
def delete_user(email):
    result = users_collection.delete_one({'email': email})
    if result.deleted_count:
        return jsonify({'message': 'User berhasil dihapus'}), 200
    return jsonify({'message': 'User tidak ditemukan'}), 404


@app.route('/edit_user/<email>', methods=['PUT'])
@login_required
@admin_required
def edit_user(email):
    data = request.get_json()
    new_name = data.get('name')
    new_password = data.get('password')

    user = users_collection.find_one({'email': email})
    if not user:
        return jsonify({'message': 'User tidak ditemukan'}), 404

    update_fields = {'name': new_name}
    update_fields['role'] = user['role']

    if new_password:
        update_fields['password'] = generate_password_hash(new_password)

    result = users_collection.update_one({'email': email}, {'$set': update_fields})

    if result.modified_count > 0:
        return jsonify({'message': 'User berhasil diperbarui'}), 200
    return jsonify({'message': 'Tidak ada perubahan data'}), 200


@app.route('/profile')
@login_required
def profile():
    user = users_collection.find_one({'_id': ObjectId(session.get('user_id'))})

    photo_binary = user.get('photo')
    if photo_binary:
        photo_url = f"data:image/png;base64,{base64.b64encode(photo_binary).decode('utf-8')}"
    else:
         photo_url = url_for('static', filename='images/profile.png')

    user_data = {
        'name': user.get('name', ''),
        'email': user.get('email', ''),
        'position': user.get('position', ''),
        'phone': user.get('phone', ''),
        'photo': photo_url
    }
    active_tab = request.args.get('tab', 'info')
    return render_template('profile.html', user=user_data, name=user_data['name'], active_tab=active_tab)


@app.route('/update_profile', methods=['POST'])
@login_required
def update_profile():
    user_id = session.get('user_id')
    if not user_id:
        flash("Session berakhir. Silakan login ulang.", "danger")
        return redirect(url_for('login'))

    user = users_collection.find_one({'_id': ObjectId(user_id)})
    if not user:
        flash("User tidak ditemukan.", "danger")
        return redirect(url_for('login'))

    updated_data = {
        'name': request.form.get('fullname'),
        'email': request.form.get('email'),
        'phone': request.form.get('phone'),
        'position': request.form.get('position')
    }

    photo = request.files.get('photo')
    if photo and photo.filename != '':
        filename = secure_filename(photo.filename)

        photo.seek(0, 2)
        file_size = photo.tell()
        photo.seek(0)

        if file_size > 500 * 1024:
            flash("Ukuran foto terlalu besar. Maksimal 500KB.", "danger")
            return redirect(url_for('profile'))

        photo_data = photo.read()
        updated_data['photo'] = Binary(photo_data)

    users_collection.update_one({'_id': ObjectId(user_id)}, {'$set': updated_data})

    flash("Profile berhasil diperbarui.", "success")
    return redirect(url_for('profile'))


@app.template_filter('b64encode')
def b64encode_filter(data):
    return base64.b64encode(data).decode('utf-8')


@app.context_processor
def inject_user():
    if 'user_id' in session:
        user = users_collection.find_one({'_id': ObjectId(session['user_id'])})
        if user:
            if user.get('photo'):
                photo_url = f"data:image/png;base64,{base64.b64encode(user['photo']).decode('utf-8')}"
            else:
                photo_url = url_for('static', filename='images/profile.png')

            user_data = {
                'name': user.get('name', ''),
                'email': user.get('email', ''),
                'role': user.get('role', ''),
                'photo': photo_url
            }
            return dict(user=user_data)
    return dict(user=None)


@app.route('/change_password', methods=['POST'])
@login_required
def change_password():
    user_id = session.get('user_id')
    user = users_collection.find_one({'_id': ObjectId(user_id)})

    current = request.form['current']
    new = request.form['new']
    confirm = request.form['confirm']

    if not user or not check_password_hash(user['password'], current):
        flash('Password lama salah.', 'danger')
        return redirect(url_for('profile', tab='password'))

    if new != confirm:
        flash('Konfirmasi password tidak cocok.', 'danger')
        return redirect(url_for('profile', tab='password'))

    if check_password_hash(user['password'], new):
        flash('Password baru tidak boleh sama dengan password lama.', 'warning')
        return redirect(url_for('profile', tab='password'))

    hashed_password = generate_password_hash(new)
    users_collection.update_one(
        {'_id': ObjectId(user_id)},
        {'$set': {'password': hashed_password}}
    )

    flash('Password berhasil diperbarui.', 'success')
    return redirect(url_for('profile', tab='password'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# === Run App ===
if __name__ == '__main__':
    app.run(debug=True)
