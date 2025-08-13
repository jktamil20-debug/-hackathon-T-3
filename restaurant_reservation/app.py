# app.py
from flask import Flask, request, render_template, redirect, url_for
from pymongo import MongoClient, errors
from bson import ObjectId
from datetime import datetime, timedelta
import pytz

app = Flask(__name__)

# MongoDB setup
client = MongoClient("mongodb+srv://jk:jeeva@data.pgbbi8p.mongodb.net/")  # Change to Atlas if needed
db = client['restaurant_db']
reservations = db['reservations']
tables = db['tables']

# Initialize tables (run once)
def init_tables():
    if tables.count_documents({}) == 0:
        tables.insert_many([
            {"table_id": 1, "seats": 2},
            {"table_id": 2, "seats": 2},
            {"table_id": 3, "seats": 4},
            {"table_id": 4, "seats": 4},
            {"table_id": 5, "seats": 6},
            {"table_id": 6, "seats": 6}
        ])
        print("✅ Tables initialized: 2x2, 2x4, 2x6 seaters")

init_tables()

# Generate 90-minute time slots from 10:00 to 22:00
def generate_time_slots():
    slots = []
    start = datetime.strptime("10:00", "%H:%M")
    end = datetime.strptime("22:00", "%H:%M")
    current = start
    while current <= end - timedelta(minutes=90):
        end_time = (current + timedelta(minutes=90)).strftime("%H:%M")
        slots.append({
            "value": current.strftime("%H:%M"),
            "label": f"{current.strftime('%H:%M')} – {end_time}"
        })
        current += timedelta(minutes=90)
    return slots

# Home Page - Make Reservation
@app.route("/", methods=["GET", "POST"])
def reserve():
    if request.method == "POST":
        name = request.form.get("name")
        date_str = request.form.get("date")
        time_str = request.form.get("time")
        party_size = int(request.form.get("party_size"))

        # Validate inputs
        if not name or not date_str or not time_str or party_size < 1 or party_size > 6:
            return render_template("index.html", error="Please fill all fields correctly.", slots=generate_time_slots())

        # Combine date and time into timezone-aware datetime
        naive_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        local_tz = pytz.timezone("America/New_York")  # Change to your timezone
        reservation_dt = local_tz.localize(naive_dt)
        end_dt = reservation_dt + timedelta(minutes=90)

        # Check for available tables
        all_tables = list(tables.find())
        booked_tables = list(reservations.find({
            "date": {"$lt": end_dt, "$gte": reservation_dt},
            "status": "confirmed"
        }))
        booked_table_ids = [r['table_id'] for r in booked_tables]

        # Find smallest available table that fits party
        suitable_tables = [
            t for t in all_tables
            if t['table_id'] not in booked_table_ids and t['seats'] >= party_size
        ]
        suitable_tables.sort(key=lambda x: x['seats'])

        if not suitable_tables:
            return render_template("index.html", error="❌ No available tables for this time and party size.", slots=generate_time_slots())

        assigned_table = suitable_tables[0]

        # Insert reservation
        try:
            result = reservations.insert_one({
                "name": name,
                "date": reservation_dt,
                "party_size": party_size,
                "table_id": assigned_table['table_id'],
                "status": "confirmed"
            })
            reservation_id = str(result.inserted_id)  # Convert ObjectId to string
            return redirect(url_for("confirm", reservation_id=reservation_id))
        except Exception as e:
            return render_template("index.html", error="❌ Reservation failed. Try again.", slots=generate_time_slots())

    return render_template("index.html", slots=generate_time_slots())


# Confirmation Page
@app.route("/confirm/<reservation_id>")
def confirm(reservation_id):
    try:
        res_id = ObjectId(reservation_id)
    except:
        return "Invalid reservation ID", 400

    reservation = reservations.find_one({"_id": res_id})
    if not reservation or reservation.get("status") != "confirmed":
        return "Reservation not found or canceled.", 404

    table = tables.find_one({"table_id": reservation['table_id']})
    reservation['end_time'] = (reservation['date'] + timedelta(minutes=90)).strftime("%H:%M")
    return render_template("confirm.html", res=reservation, table=table)


# Admin View - List All Reservations
@app.route("/admin")
def admin():
    res_list = list(reservations.find({"status": "confirmed"}))
    for r in res_list:
        r['_id'] = str(r['_id'])  # Convert ObjectId to string for template
        r['date_str'] = r['date'].strftime("%Y-%m-%d")
        r['time_str'] = r['date'].strftime("%H:%M")
        r['end_time'] = (r['date'] + timedelta(minutes=90)).strftime("%H:%M")
    return render_template("admin.html", reservations=res_list)


# Cancel Reservation
@app.route("/cancel/<reservation_id>")
def cancel(reservation_id):
    try:
        res_id = ObjectId(reservation_id)
    except:
        return "Invalid ID", 400

    result = reservations.update_one(
        {"_id": res_id, "status": "confirmed"},
        {"$set": {"status": "cancelled"}}
    )
    if result.matched_count == 0:
        return "Reservation not found or already canceled.", 404

    return redirect(url_for("admin"))


# Run the app
if __name__ == "__main__":
    print("👉 Open http://localhost:5000")
    app.run(debug=True)