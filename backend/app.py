from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from calendar import monthrange

from flask import Flask, jsonify, request
from flask_cors import CORS

from database import ensure_units_for_property, get_connection, init_db

app = Flask(__name__)
CORS(app)

init_db()

LEASE_SELECT = """
    SELECT
        leases.id,
        leases.property_id,
        leases.unit_id,
        leases.tenant_id,
        leases.start_date,
        leases.end_date,
        leases.monthly_rent,
        leases.due_day,
        tenants.name AS tenant_name,
        properties.address AS property_address,
        properties.city AS property_city,
        units.unit_label AS unit_label
    FROM leases
    JOIN tenants ON tenants.id = leases.tenant_id
    JOIN properties ON properties.id = leases.property_id
    JOIN units ON units.id = leases.unit_id
"""


# -----------------------------
# HELPERS
# -----------------------------

def parse_iso_date(value, field_name):
    if not value or not isinstance(value, str):
        raise ValueError(f"{field_name} is required")
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid date (YYYY-MM-DD)") from exc


def lease_status(start, end, today=None):
    today = today or date.today()
    if today < start:
        return "upcoming", False
    if today > end:
        return "expired", False
    return "active", (end - today).days <= 30


def serialize_lease(row, today=None):
    start = date.fromisoformat(row["start_date"])
    end = date.fromisoformat(row["end_date"])
    status, expiring_soon = lease_status(start, end, today)
    return {
        "id": row["id"],
        "property_id": row["property_id"],
        "unit_id": row["unit_id"],
        "tenant_id": row["tenant_id"],
        "tenant_name": row["tenant_name"],
        "property_address": row["property_address"],
        "property_city": row["property_city"],
        "unit_label": row["unit_label"],
        "start_date": row["start_date"],
        "end_date": row["end_date"],
        "monthly_rent": row["monthly_rent"],
        "due_day": row["due_day"],
        "status": status,
        "expiring_soon": expiring_soon,
    }


def units_by_property(conn):
    grouped = {}
    rows = conn.execute(
        "SELECT * FROM units ORDER BY property_id, id"
    ).fetchall()
    for row in rows:
        grouped.setdefault(row["property_id"], []).append(dict(row))
    return grouped


def fetch_lease(conn, lease_id):
    return conn.execute(
        LEASE_SELECT + " WHERE leases.id = ?",
        (lease_id,),
    ).fetchone()


def parse_lease_payload(data, conn, lease_id=None):
    if not isinstance(data, dict):
        return None, ("Invalid request data", 400)

    try:
        property_id = int(data.get("property_id"))
        unit_id = int(data.get("unit_id"))
        tenant_id = int(data.get("tenant_id"))
    except (TypeError, ValueError):
        return None, ("Property, unit, and tenant are required", 400)

    try:
        start = parse_iso_date(data.get("start_date"), "Start date")
        end = parse_iso_date(data.get("end_date"), "End date")
    except ValueError as exc:
        return None, (str(exc), 400)

    if end < start:
        return None, ("End date must be on or after the start date", 400)

    try:
        monthly_rent = float(data.get("monthly_rent"))
    except (TypeError, ValueError):
        return None, ("Monthly rent must be a number", 400)

    if monthly_rent <= 0:
        return None, ("Monthly rent must be greater than 0", 400)

    try:
        due_day = int(data.get("due_day", 1))
    except (TypeError, ValueError):
        return None, ("Due day must be a number", 400)

    if due_day < 1 or due_day > 28:
        return None, ("Due day must be between 1 and 28", 400)

    property_row = conn.execute(
        "SELECT id FROM properties WHERE id = ?",
        (property_id,),
    ).fetchone()
    if not property_row:
        return None, ("Property not found", 404)

    tenant_row = conn.execute(
        "SELECT id FROM tenants WHERE id = ?",
        (tenant_id,),
    ).fetchone()
    if not tenant_row:
        return None, ("Tenant not found", 404)

    unit_row = conn.execute(
        "SELECT id, property_id FROM units WHERE id = ?",
        (unit_id,),
    ).fetchone()
    if not unit_row:
        return None, ("Unit not found", 404)
    if unit_row["property_id"] != property_id:
        return None, ("Unit does not belong to the selected property", 400)

    overlap = conn.execute(
        """
        SELECT id FROM leases
        WHERE unit_id = ?
          AND (? IS NULL OR id != ?)
          AND date(start_date) <= date(?)
          AND date(end_date) >= date(?)
        """,
        (unit_id, lease_id, lease_id, end.isoformat(), start.isoformat()),
    ).fetchone()
    if overlap:
        return None, ("This unit already has a lease that overlaps these dates", 409)

    return {
        "property_id": property_id,
        "unit_id": unit_id,
        "tenant_id": tenant_id,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "monthly_rent": monthly_rent,
        "due_day": due_day,
    }, None


# -----------------------------
# HEALTH CHECK
# -----------------------------

@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "success",
        "message": "RentWise backend is running!"
    })


# -----------------------------
# PROPERTY MANAGEMENT
# -----------------------------

@app.route("/api/properties", methods=["GET"])
def get_properties():
    with get_connection() as conn:
        properties = conn.execute(
            "SELECT * FROM properties ORDER BY id DESC"
        ).fetchall()
        grouped_units = units_by_property(conn)

    result = []
    for property_row in properties:
        item = dict(property_row)
        item["unit_list"] = grouped_units.get(property_row["id"], [])
        result.append(item)

    return jsonify(result)


@app.route("/api/properties", methods=["POST"])
def add_property():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "Invalid request data"}), 400

    address = str(data.get("address") or "").strip()
    city = str(data.get("city") or "").strip()
    property_type = str(data.get("property_type") or "").strip()

    try:
        units = int(data.get("units", 1))
    except (ValueError, TypeError):
        return jsonify({"error": "Units must be a number"}), 400

    if not address or not city:
        return jsonify({
            "error": "Address and city are required"
        }), 400

    if units < 1:
        return jsonify({
            "error": "Units must be at least 1"
        }), 400

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO properties (address, city, property_type, units)
            VALUES (?, ?, ?, ?)
            """,
            (address, city, property_type, units)
        )
        property_id = cursor.lastrowid
        ensure_units_for_property(conn, property_id, units)

    return jsonify({
        "message": "Property added successfully!",
        "id": property_id
    }), 201


# -----------------------------
# TENANT MANAGEMENT
# -----------------------------

@app.route("/api/tenants", methods=["GET"])
def get_tenants():
    with get_connection() as conn:
        tenants = conn.execute(
            "SELECT * FROM tenants ORDER BY id DESC"
        ).fetchall()

    return jsonify([dict(tenant) for tenant in tenants])


@app.route("/api/tenants", methods=["POST"])
def add_tenant():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "Invalid request data"}), 400

    name = str(data.get("name") or "").strip()
    email = str(data.get("email") or "").strip()
    phone = str(data.get("phone") or "").strip()

    if not name:
        return jsonify({
            "error": "Tenant name is required"
        }), 400

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO tenants (name, email, phone)
            VALUES (?, ?, ?)
            """,
            (name, email, phone)
        )

        tenant_id = cursor.lastrowid

    return jsonify({
        "message": "Tenant added successfully!",
        "id": tenant_id
    }), 201


# -----------------------------
# PROPERTY AND TENANT EDITING
# -----------------------------

@app.route("/api/properties/<int:property_id>", methods=["PUT", "DELETE"])
def manage_property(property_id):
    with get_connection() as conn:
        existing = conn.execute("SELECT * FROM properties WHERE id=?", (property_id,)).fetchone()
        if existing is None:
            return jsonify({"error": "Property not found"}), 404
        if request.method == "DELETE":
            if conn.execute("SELECT 1 FROM leases WHERE property_id=? LIMIT 1", (property_id,)).fetchone():
                return jsonify({"error": "This property has leases; remove the leases first"}), 409
            conn.execute("DELETE FROM units WHERE property_id=?", (property_id,))
            conn.execute("DELETE FROM properties WHERE id=?", (property_id,))
            return jsonify({"message": "Property deleted"})
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "Invalid request data"}), 400
        address = str(data.get("address") or "").strip()
        city = str(data.get("city") or "").strip()
        kind = str(data.get("property_type") or "").strip()
        try:
            units = int(data.get("units", 1))
        except (ValueError, TypeError):
            return jsonify({"error": "Units must be a number"}), 400
        if not address or not city or units < 1:
            return jsonify({"error": "Address, city and a positive unit count are required"}), 400
        last_unit = conn.execute("SELECT MAX(CAST(SUBSTR(unit_label, 6) AS INTEGER)) FROM units WHERE property_id=?", (property_id,)).fetchone()[0] or 0
        if units < last_unit:
            occupied = conn.execute("SELECT 1 FROM leases JOIN units ON units.id=leases.unit_id WHERE units.property_id=? AND CAST(SUBSTR(units.unit_label, 6) AS INTEGER)>? LIMIT 1", (property_id, units)).fetchone()
            if occupied:
                return jsonify({"error": "Cannot remove units that have leases"}), 409
            conn.execute("DELETE FROM units WHERE property_id=? AND CAST(SUBSTR(unit_label, 6) AS INTEGER)>?", (property_id, units))
        conn.execute("UPDATE properties SET address=?, city=?, property_type=?, units=? WHERE id=?", (address, city, kind, units, property_id))
        ensure_units_for_property(conn, property_id, units)
        return jsonify({"message": "Property updated"})


@app.route("/api/tenants/<int:tenant_id>", methods=["PUT", "DELETE"])
def manage_tenant(tenant_id):
    with get_connection() as conn:
        if conn.execute("SELECT id FROM tenants WHERE id=?", (tenant_id,)).fetchone() is None:
            return jsonify({"error": "Tenant not found"}), 404
        if request.method == "DELETE":
            if conn.execute("SELECT 1 FROM leases WHERE tenant_id=? LIMIT 1", (tenant_id,)).fetchone():
                return jsonify({"error": "This tenant has leases; remove the leases first"}), 409
            conn.execute("DELETE FROM tenants WHERE id=?", (tenant_id,))
            return jsonify({"message": "Tenant deleted"})
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "Invalid request data"}), 400
        name = str(data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Tenant name is required"}), 400
        conn.execute("UPDATE tenants SET name=?,email=?,phone=? WHERE id=?", (name, str(data.get("email") or "").strip(), str(data.get("phone") or "").strip(), tenant_id))
        return jsonify({"message": "Tenant updated"})


def parse_month(raw):
    if not isinstance(raw, str) or len(raw) != 7 or raw[4] != "-":
        raise ValueError("Month must use YYYY-MM")
    try:
        year, month = map(int, raw.split("-"))
        first = date(year, month, 1)
    except (ValueError, TypeError) as exc:
        raise ValueError("Month must use YYYY-MM") from exc
    if first.strftime("%Y-%m") != raw:
        raise ValueError("Month must use YYYY-MM")
    return first, date(year, month, monthrange(year, month)[1])


def money_cents(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("Amount must be a valid number")
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount <= 0 or amount.as_tuple().exponent < -2:
            raise ValueError
        cents = int((amount * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    except (ValueError, InvalidOperation, TypeError, OverflowError) as exc:
        raise ValueError("Amount must be positive with at most 2 decimal places") from exc
    if cents > 100000000000:
        raise ValueError("Amount is too large")
    return cents


def cents_to_money(cents):
    return round(cents / 100, 2)


def payment_records(conn, month=None, lease_id=None, include_voided=False):
    where = []
    params = []
    if month:
        where.append('payments.payment_month = ?')
        params.append(month)
    if lease_id is not None:
        where.append('payments.lease_id = ?')
        params.append(lease_id)
    if not include_voided:
        where.append('payments.voided_at IS NULL')
    clause = (' WHERE ' + ' AND '.join(where)) if where else ''
    rows = conn.execute("""
        SELECT payments.id, payments.lease_id, payments.payment_month,
               payments.amount_paid, payments.payment_date, payments.voided_at,
               payments.void_reason, tenants.name AS tenant,
               properties.address AS property, units.unit_label AS unit
        FROM payments JOIN leases ON leases.id=payments.lease_id
        JOIN tenants ON tenants.id=leases.tenant_id
        JOIN properties ON properties.id=leases.property_id
        JOIN units ON units.id=leases.unit_id
    """ + clause + " ORDER BY payments.payment_date DESC, payments.id DESC", params).fetchall()
    return [{**dict(row), 'amount_paid': cents_to_money(int(Decimal(str(row['amount_paid'])) * 100))} for row in rows]


def month_overview(conn, month, today=None):
    first, last = parse_month(month)
    today = today or date.today()
    leases = conn.execute(LEASE_SELECT + " WHERE date(leases.start_date)<=date(?) AND date(leases.end_date)>=date(?) ORDER BY leases.id", (last.isoformat(), first.isoformat())).fetchall()
    payments = conn.execute("""
        SELECT lease_id, amount_paid FROM payments
        WHERE payment_month=? AND voided_at IS NULL
    """, (month,)).fetchall()
    totals = {}
    for p in payments:
        totals[p['lease_id']] = totals.get(p['lease_id'], 0) + int((Decimal(str(p['amount_paid'])) * 100).quantize(Decimal('1')))
    records = []
    for lease in leases:
        due_date = date(first.year, first.month, lease['due_day'])
        expected = int((Decimal(str(lease['monthly_rent'])) * 100).quantize(Decimal('1')))
        paid = totals.get(lease['id'], 0)
        balance = max(expected - paid, 0)
        overdue = balance > 0 and today > due_date
        if balance == 0:
            status = 'Paid'
        elif overdue:
            status = 'Overdue'
        elif paid > 0:
            status = 'Partially Paid'
        else:
            status = 'Pending'
        records.append({'lease_id': lease['id'], 'tenant': lease['tenant_name'], 'property': lease['property_address'], 'unit': lease['unit_label'], 'month': month, 'due_date': due_date.isoformat(), 'monthly_rent': cents_to_money(expected), 'amount_paid': cents_to_money(paid), 'outstanding': cents_to_money(balance), 'status': status, 'overdue': overdue, 'partial': 0 < paid < expected})
    return {'month': month, 'expected_total': cents_to_money(sum(int(round(r['monthly_rent']*100)) for r in records)), 'collected_total': cents_to_money(sum(int(round(r['amount_paid']*100)) for r in records)), 'outstanding_total': cents_to_money(sum(int(round(r['outstanding']*100)) for r in records)), 'overdue_total': cents_to_money(sum(int(round(r['outstanding']*100)) for r in records if r['overdue'])), 'leases': records}


@app.route('/api/rent-overview', methods=['GET'])
def rent_overview():
    month = request.args.get('month', date.today().strftime('%Y-%m'))
    try:
        with get_connection() as conn:
            result = month_overview(conn, month)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify(result)


@app.route('/api/payments', methods=['GET'])
def get_payments():
    month = request.args.get('month')
    lease_id = request.args.get('lease_id')
    if month:
        try:
            parse_month(month)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
    if lease_id is not None:
        try:
            lease_id = int(lease_id)
        except ValueError:
            return jsonify({'error': 'Invalid lease ID'}), 400
    with get_connection() as conn:
        records = payment_records(conn, month=month, lease_id=lease_id, include_voided=request.args.get('include_voided') == 'true')
    return jsonify(records)


@app.route('/api/payments', methods=['POST'])
def record_payment():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Invalid request data'}), 400
    try:
        lease_id = int(data.get('lease_id'))
        month = data.get('payment_month')
        first, last = parse_month(month)
        payment_date = parse_iso_date(data.get('payment_date'), 'Payment date')
        amount = money_cents(data.get('amount_paid'))
    except (ValueError, TypeError) as exc:
        return jsonify({'error': str(exc)}), 400
    with get_connection() as conn:
        # Reserve a write lock while checking and inserting to prevent double-posting races.
        conn.execute('BEGIN IMMEDIATE')
        lease = fetch_lease(conn, lease_id)
        if lease is None:
            return jsonify({'error': 'Lease not found'}), 404
        if date.fromisoformat(lease['start_date']) > last or date.fromisoformat(lease['end_date']) < first:
            return jsonify({'error': 'No rent due for this lease in the selected month'}), 400
        overview = month_overview(conn, month)
        row = next(r for r in overview['leases'] if r['lease_id'] == lease_id)
        outstanding = int((Decimal(str(row['outstanding'])) * 100).quantize(Decimal('1')))
        if amount > outstanding:
            return jsonify({'error': 'Payment exceeds the outstanding monthly rent'}), 400
        cursor = conn.execute('INSERT INTO payments (lease_id, payment_month, amount_paid, payment_date) VALUES (?, ?, ?, ?)', (lease_id, month, cents_to_money(amount), payment_date.isoformat()))
        payment_id = cursor.lastrowid
    return jsonify({'message': 'Payment recorded', 'id': payment_id}), 201


@app.route('/api/payments/<int:payment_id>/void', methods=['POST'])
def void_payment(payment_id):
    data = request.get_json(silent=True) or {}
    reason = str(data.get('reason') or 'Entry correction').strip()[:300]
    with get_connection() as conn:
        row = conn.execute('SELECT id, voided_at FROM payments WHERE id=?', (payment_id,)).fetchone()
        if not row:
            return jsonify({'error': 'Payment not found'}), 404
        if row['voided_at']:
            return jsonify({'error': 'Payment already voided'}), 409
        conn.execute('UPDATE payments SET voided_at=?, void_reason=? WHERE id=?', (datetime.now(timezone.utc).isoformat(), reason, payment_id))
    return jsonify({'message': 'Payment voided; original entry retained in history'})


# -----------------------------
# LEASE MANAGEMENT
# -----------------------------

@app.route("/api/leases", methods=["GET"])
def get_leases():
    with get_connection() as conn:
        leases = conn.execute(
            LEASE_SELECT + " ORDER BY leases.id DESC"
        ).fetchall()

    return jsonify([serialize_lease(lease) for lease in leases])


@app.route("/api/leases", methods=["POST"])
def add_lease():
    data = request.get_json(silent=True)

    with get_connection() as conn:
        payload, error = parse_lease_payload(data, conn)
        if error:
            message, status_code = error
            return jsonify({"error": message}), status_code

        cursor = conn.execute(
            """
            INSERT INTO leases (
                property_id, unit_id, tenant_id,
                start_date, end_date, monthly_rent, due_day
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["property_id"],
                payload["unit_id"],
                payload["tenant_id"],
                payload["start_date"],
                payload["end_date"],
                payload["monthly_rent"],
                payload["due_day"],
            ),
        )
        lease = fetch_lease(conn, cursor.lastrowid)

    return jsonify({
        "message": "Lease added successfully!",
        "lease": serialize_lease(lease),
    }), 201


@app.route("/api/leases/<int:lease_id>", methods=["PUT"])
def update_lease(lease_id):
    data = request.get_json(silent=True)

    with get_connection() as conn:
        existing = fetch_lease(conn, lease_id)
        if not existing:
            return jsonify({"error": "Lease not found"}), 404

        payload, error = parse_lease_payload(data, conn, lease_id=lease_id)
        if error:
            message, status_code = error
            return jsonify({"error": message}), status_code

        conn.execute(
            """
            UPDATE leases
            SET property_id = ?,
                unit_id = ?,
                tenant_id = ?,
                start_date = ?,
                end_date = ?,
                monthly_rent = ?,
                due_day = ?
            WHERE id = ?
            """,
            (
                payload["property_id"],
                payload["unit_id"],
                payload["tenant_id"],
                payload["start_date"],
                payload["end_date"],
                payload["monthly_rent"],
                payload["due_day"],
                lease_id,
            ),
        )
        lease = fetch_lease(conn, lease_id)

    return jsonify({
        "message": "Lease updated successfully!",
        "lease": serialize_lease(lease),
    })


@app.route("/api/leases/<int:lease_id>", methods=["DELETE"])
def delete_lease(lease_id):
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM leases WHERE id = ?",
            (lease_id,),
        ).fetchone()
        if not existing:
            return jsonify({"error": "Lease not found"}), 404

        if conn.execute("SELECT id FROM payments WHERE lease_id = ? LIMIT 1", (lease_id,)).fetchone():
            return jsonify({"error": "Lease has payment history and cannot be deleted"}), 409
        conn.execute("DELETE FROM leases WHERE id = ?", (lease_id,))

    return jsonify({"message": "Lease deleted successfully!"})


# -----------------------------
# RUN FLASK SERVER
# -----------------------------

if __name__ == "__main__":
    app.run(debug=True, port=5000)
