import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("RENTWISE_DB", Path(__file__).parent / "rentwise.db"))


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _column_names(conn, table_name):
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table_name})")]


def ensure_units_for_property(conn, property_id, unit_count):
    """Create missing Unit 1..N rows for a property without deleting existing units."""
    if unit_count < 1:
        unit_count = 1

    existing = conn.execute(
        "SELECT unit_label FROM units WHERE property_id = ?",
        (property_id,),
    ).fetchall()
    existing_labels = {row["unit_label"] for row in existing}

    for index in range(1, unit_count + 1):
        label = f"Unit {index}"
        if label not in existing_labels:
            conn.execute(
                "INSERT INTO units (property_id, unit_label) VALUES (?, ?)",
                (property_id, label),
            )


def _migrate_schema(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS units (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            property_id INTEGER NOT NULL,
            unit_label TEXT NOT NULL,
            FOREIGN KEY (property_id) REFERENCES properties(id),
            UNIQUE (property_id, unit_label)
        )
        """
    )

    # Add reversible payment corrections without discarding historical records.
    payment_columns = _column_names(conn, "payments")
    if "voided_at" not in payment_columns:
        conn.execute("ALTER TABLE payments ADD COLUMN voided_at TEXT")
    if "void_reason" not in payment_columns:
        conn.execute("ALTER TABLE payments ADD COLUMN void_reason TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_payments_lease_month ON payments(lease_id, payment_month)")

    lease_columns = _column_names(conn, "leases")
    if "unit_id" not in lease_columns:
        lease_count = conn.execute("SELECT COUNT(*) FROM leases").fetchone()[0]
        if lease_count == 0:
            conn.execute("DROP TABLE IF EXISTS leases")
            conn.execute(
                """
                CREATE TABLE leases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    property_id INTEGER NOT NULL,
                    unit_id INTEGER NOT NULL,
                    tenant_id INTEGER NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    monthly_rent REAL NOT NULL,
                    due_day INTEGER NOT NULL DEFAULT 1,
                    FOREIGN KEY (property_id) REFERENCES properties(id),
                    FOREIGN KEY (unit_id) REFERENCES units(id),
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
                )
                """
            )
        else:
            conn.execute(
                "ALTER TABLE leases ADD COLUMN unit_id INTEGER REFERENCES units(id)"
            )

    properties = conn.execute("SELECT id, units FROM properties").fetchall()
    for property_row in properties:
        ensure_units_for_property(conn, property_row["id"], property_row["units"])


def init_db():
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS properties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address TEXT NOT NULL,
                city TEXT NOT NULL,
                property_type TEXT,
                units INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS tenants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT,
                phone TEXT
            );

            CREATE TABLE IF NOT EXISTS leases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                property_id INTEGER NOT NULL,
                tenant_id INTEGER NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                monthly_rent REAL NOT NULL,
                due_day INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (property_id) REFERENCES properties(id),
                FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            );

            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lease_id INTEGER NOT NULL,
                payment_month TEXT NOT NULL,
                amount_paid REAL NOT NULL DEFAULT 0,
                payment_date TEXT,
                FOREIGN KEY (lease_id) REFERENCES leases(id)
            );
            """
        )
        _migrate_schema(conn)


if __name__ == "__main__":
    init_db()
    print("RentWise database initialized successfully!")
