import importlib
import os
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path


class LeaseApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["RENTWISE_DB"] = str(Path(self.tmp.name) / "test.db")

        backend_dir = Path(__file__).parent
        if str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))

        import app as app_module
        import database

        importlib.reload(database)
        importlib.reload(app_module)
        self.client = app_module.app.test_client()
        self.seed()

    def tearDown(self):
        self.tmp.cleanup()

    def seed(self):
        property_res = self.client.post(
            "/api/properties",
            json={
                "address": "10 Test Street",
                "city": "Halifax",
                "property_type": "Apartment",
                "units": 2,
            },
        )
        self.assertEqual(property_res.status_code, 201)
        self.property_id = property_res.get_json()["id"]

        tenant_res = self.client.post(
            "/api/tenants",
            json={"name": "Sample Tenant", "email": "", "phone": ""},
        )
        self.assertEqual(tenant_res.status_code, 201)
        self.tenant_id = tenant_res.get_json()["id"]

        second_tenant = self.client.post(
            "/api/tenants",
            json={"name": "Second Tenant"},
        )
        self.second_tenant_id = second_tenant.get_json()["id"]

        properties = self.client.get("/api/properties").get_json()
        property_row = next(item for item in properties if item["id"] == self.property_id)
        self.assertEqual(len(property_row["unit_list"]), 2)
        self.unit_a = property_row["unit_list"][0]["id"]
        self.unit_b = property_row["unit_list"][1]["id"]

    def lease_payload(self, **overrides):
        today = date.today()
        payload = {
            "property_id": self.property_id,
            "unit_id": self.unit_a,
            "tenant_id": self.tenant_id,
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=60)).isoformat(),
            "monthly_rent": 1200,
            "due_day": 1,
        }
        payload.update(overrides)
        return payload

    def test_create_and_list_lease(self):
        response = self.client.post("/api/leases", json=self.lease_payload())
        self.assertEqual(response.status_code, 201)
        lease = response.get_json()["lease"]
        self.assertEqual(lease["tenant_name"], "Sample Tenant")
        self.assertEqual(lease["property_address"], "10 Test Street")
        self.assertEqual(lease["status"], "active")
        self.assertFalse(lease["expiring_soon"])

        listed = self.client.get("/api/leases").get_json()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["id"], lease["id"])

    def test_upcoming_and_expiring_status(self):
        today = date.today()
        upcoming = self.client.post(
            "/api/leases",
            json=self.lease_payload(
                start_date=(today + timedelta(days=10)).isoformat(),
                end_date=(today + timedelta(days=40)).isoformat(),
            ),
        ).get_json()["lease"]
        self.assertEqual(upcoming["status"], "upcoming")
        self.assertFalse(upcoming["expiring_soon"])

        expiring = self.client.post(
            "/api/leases",
            json=self.lease_payload(
                unit_id=self.unit_b,
                tenant_id=self.second_tenant_id,
                start_date=(today - timedelta(days=5)).isoformat(),
                end_date=(today + timedelta(days=15)).isoformat(),
            ),
        ).get_json()["lease"]
        self.assertEqual(expiring["status"], "active")
        self.assertTrue(expiring["expiring_soon"])

    def test_expired_status(self):
        today = date.today()
        expired = self.client.post(
            "/api/leases",
            json=self.lease_payload(
                start_date=(today - timedelta(days=90)).isoformat(),
                end_date=(today - timedelta(days=1)).isoformat(),
            ),
        ).get_json()["lease"]
        self.assertEqual(expired["status"], "expired")
        self.assertFalse(expired["expiring_soon"])

    def test_rejects_invalid_rent_due_day_and_dates(self):
        self.assertEqual(
            self.client.post("/api/leases", json=self.lease_payload(monthly_rent=0)).status_code,
            400,
        )
        self.assertEqual(
            self.client.post("/api/leases", json=self.lease_payload(due_day=29)).status_code,
            400,
        )
        self.assertEqual(
            self.client.post("/api/leases", json=self.lease_payload(due_day=0)).status_code,
            400,
        )
        today = date.today()
        self.assertEqual(
            self.client.post(
                "/api/leases",
                json=self.lease_payload(
                    start_date=today.isoformat(),
                    end_date=(today - timedelta(days=1)).isoformat(),
                ),
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                "/api/leases",
                json=self.lease_payload(start_date="not-a-date"),
            ).status_code,
            400,
        )

    def test_rejects_overlapping_leases_on_same_unit(self):
        today = date.today()
        first = self.client.post("/api/leases", json=self.lease_payload())
        self.assertEqual(first.status_code, 201)

        overlap = self.client.post(
            "/api/leases",
            json=self.lease_payload(
                tenant_id=self.second_tenant_id,
                start_date=(today + timedelta(days=10)).isoformat(),
                end_date=(today + timedelta(days=80)).isoformat(),
            ),
        )
        self.assertEqual(overlap.status_code, 409)

        other_unit = self.client.post(
            "/api/leases",
            json=self.lease_payload(
                unit_id=self.unit_b,
                tenant_id=self.second_tenant_id,
            ),
        )
        self.assertEqual(other_unit.status_code, 201)

    def test_update_and_delete_lease(self):
        created = self.client.post("/api/leases", json=self.lease_payload())
        lease_id = created.get_json()["lease"]["id"]

        updated = self.client.put(
            f"/api/leases/{lease_id}",
            json=self.lease_payload(monthly_rent=1500.5, due_day=15),
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.get_json()["lease"]["monthly_rent"], 1500.5)
        self.assertEqual(updated.get_json()["lease"]["due_day"], 15)

        deleted = self.client.delete(f"/api/leases/{lease_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get("/api/leases").get_json(), [])
        self.assertEqual(self.client.delete(f"/api/leases/{lease_id}").status_code, 404)

    def test_existing_property_and_tenant_endpoints_still_work(self):
        properties = self.client.get("/api/properties")
        tenants = self.client.get("/api/tenants")
        health = self.client.get("/api/health")
        self.assertEqual(properties.status_code, 200)
        self.assertEqual(tenants.status_code, 200)
        self.assertEqual(health.status_code, 200)
        self.assertIn("units", properties.get_json()[0])
        self.assertEqual(tenants.get_json()[0]["name"], "Second Tenant")


if __name__ == "__main__":
    unittest.main()
