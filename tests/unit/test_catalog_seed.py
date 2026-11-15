import copy
import json
from pathlib import Path

from src.admin.seed_service import apply_seed, load_catalog, validate_catalog

CATALOG_PATH = Path(__file__).resolve().parents[2] / "seed" / "demo_catalog.json"


class InMemoryStore:
    """Base de datos falsa para probar sin AWS."""

    def __init__(self):
        self.tables = {}

    def _k(self, key):
        return tuple(sorted(key.items()))

    def get_item(self, table, key):
        item = self.tables.get(table, {}).get(self._k(key))
        return copy.deepcopy(item) if item else None

    def put_item(self, table, item):
        keys = {
            "t-operations": ["operation_id"],
            "t-machine-models": ["model_id"],
            "t-machines": ["machine_id"],
            "t-technicians": ["technician_id"],
            "t-parts": ["warehouse_id", "part_id"],
            "t-users": ["firebase_uid"],
        }
        base = table.split("af-test-")[-1]
        key = {k: item[k] for k in keys[base]}
        self.tables.setdefault(table, {})[self._k(key)] = copy.deepcopy(item)


def seed(catalog, store):
    return apply_seed(catalog, store, table_prefix="af-test-")


def test_catalog_is_valid():
    assert validate_catalog(load_catalog(CATALOG_PATH)) == []


def test_first_seed_creates_everything():
    report = seed(load_catalog(CATALOG_PATH), InMemoryStore())
    created = {t: r["created"] for t, r in report.items()}
    assert created == {
        "t-operations": 1,
        "t-machine-models": 4,
        "t-machines": 16,
        "t-technicians": 6,
        "t-parts": 18,
        "t-users": 5,
    }


def test_repeating_seed_changes_nothing():
    store, catalog = InMemoryStore(), load_catalog(CATALOG_PATH)
    seed(catalog, store)
    report = seed(catalog, store)
    assert all(r["created"] == 0 and r["updated"] == 0 for r in report.values())


def test_repeating_seed_preserves_operational_state():
    store, catalog = InMemoryStore(), load_catalog(CATALOG_PATH)
    seed(catalog, store)
    machine = store.get_item("af-test-t-machines", {"machine_id": "machine-001"})
    machine["status"] = "STOPPED"
    store.put_item("af-test-t-machines", machine)
    part = store.get_item(
        "af-test-t-parts", {"warehouse_id": "wh-central", "part_id": "turbocharger"}
    )
    part.update(reserved=1, available=0)
    store.put_item("af-test-t-parts", part)
    tech = store.get_item("af-test-t-technicians", {"technician_id": "tech-001"})
    tech.update(availability="BUSY", current_incident_id="inc-1")
    store.put_item("af-test-t-technicians", tech)

    seed(catalog, store)

    assert (
        store.get_item("af-test-t-machines", {"machine_id": "machine-001"})["status"]
        == "STOPPED"
    )
    p = store.get_item(
        "af-test-t-parts", {"warehouse_id": "wh-central", "part_id": "turbocharger"}
    )
    assert (p["reserved"], p["available"]) == (1, 0)
    t = store.get_item("af-test-t-technicians", {"technician_id": "tech-001"})
    assert (t["availability"], t["current_incident_id"]) == ("BUSY", "inc-1")


def test_catalog_change_updates_without_touching_state():
    store, catalog = InMemoryStore(), load_catalog(CATALOG_PATH)
    seed(catalog, store)
    machine = store.get_item("af-test-t-machines", {"machine_id": "machine-002"})
    machine["status"] = "STOPPED"
    store.put_item("af-test-t-machines", machine)

    changed = copy.deepcopy(catalog)
    changed["machines"][1]["name"] = "Excavadora renombrada"
    report = seed(changed, store)

    assert report["t-machines"]["updated"] == 1
    m = store.get_item("af-test-t-machines", {"machine_id": "machine-002"})
    assert m["name"] == "Excavadora renombrada" and m["status"] == "STOPPED"


def test_broken_reference_is_rejected():
    catalog = load_catalog(CATALOG_PATH)
    catalog["machines"][0]["model_id"] = "NO-EXISTE"
    assert validate_catalog(catalog) != []
    try:
        seed(catalog, InMemoryStore())
        assert False, "debió fallar"
    except ValueError:
        pass


def test_catalog_has_no_passwords():
    text = json.dumps(load_catalog(CATALOG_PATH)).lower()
    assert "password" not in text and "contraseña" not in text
