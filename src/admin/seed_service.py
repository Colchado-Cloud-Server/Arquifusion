"""Carga idempotente del catálogo demo (ADMIN-01 / RF-02).

Reglas:
- Lo que falta se CREA.
- Lo que ya existe se ACTUALIZA solo en campos de catálogo (nombre, zona, roles...).
- Los campos operativos (estado de máquinas, stock, disponibilidad de técnicos)
  se escriben la primera vez y NUNCA se pisan al repetir la carga.

Este módulo no conoce AWS: recibe un `store` con get_item/put_item. Más adelante
se le pasa un adaptador de DynamoDB; en las pruebas se usa uno en memoria.
"""

from __future__ import annotations

import json
from pathlib import Path

# sección del JSON -> tabla (sin prefijo af-<stage>-)
SECTIONS = [
    ("operations", "t-operations"),
    ("machine_models", "t-machine-models"),
    ("machines", "t-machines"),
    ("technicians", "t-technicians"),
    ("parts", "t-parts"),
    ("users", "t-users"),
]

KEYS = {
    "t-operations": ("operation_id",),
    "t-machine-models": ("model_id",),
    "t-machines": ("machine_id",),
    "t-technicians": ("technician_id",),
    "t-parts": ("warehouse_id", "part_id"),
    "t-users": ("firebase_uid",),
}

# Campos que cambian durante la operación: el seed no los pisa.
OPERATIONAL_FIELDS = {
    "t-machines": {"status", "hours_total", "hours_since_service", "last_position"},
    "t-technicians": {"availability", "current_incident_id"},
    "t-parts": {"on_hand", "reserved", "available"},
}


def load_catalog(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def validate_catalog(catalog: dict) -> list[str]:
    """Devuelve la lista de errores de referencias (vacía si todo cuadra)."""
    errors: list[str] = []
    zones = {z["zone_id"] for op in catalog["operations"] for z in op["zones"]}
    warehouses = {
        w["warehouse_id"] for op in catalog["operations"] for w in op["warehouses"]
    }
    operations = {op["operation_id"] for op in catalog["operations"]}
    models = {m["model_id"] for m in catalog["machine_models"]}
    parts = {p["part_id"] for p in catalog["parts"]}
    technicians = {t["technician_id"] for t in catalog["technicians"]}

    for m in catalog["machines"]:
        if m["model_id"] not in models:
            errors.append(f"{m['machine_id']}: modelo inexistente {m['model_id']}")
        if m["zone_id"] not in zones:
            errors.append(f"{m['machine_id']}: zona inexistente {m['zone_id']}")
        if m["operation_id"] not in operations:
            errors.append(
                f"{m['machine_id']}: operación inexistente {m['operation_id']}"
            )
    for t in catalog["technicians"]:
        if t["zone_id"] not in zones:
            errors.append(f"{t['technician_id']}: zona inexistente {t['zone_id']}")
    for p in catalog["parts"]:
        if p["warehouse_id"] not in warehouses:
            errors.append(f"{p['part_id']}: almacén inexistente {p['warehouse_id']}")
    for model in catalog["machine_models"]:
        for fam in model["anomaly_families"]:
            for pp in fam["parts"]:
                if pp["part_id"] not in parts:
                    errors.append(
                        f"{model['model_id']}/{fam['family']}: repuesto inexistente {pp['part_id']}"
                    )
    for u in catalog["users"]:
        tid = u.get("technician_id")
        if tid and tid not in technicians:
            errors.append(f"usuario {u['email']}: técnico inexistente {tid}")
        for op_id in u["roles"]:
            if op_id not in operations:
                errors.append(f"usuario {u['email']}: operación inexistente {op_id}")
    return errors


def _key_of(table: str, item: dict) -> dict:
    return {k: item[k] for k in KEYS[table]}


def apply_seed(catalog: dict, store, table_prefix: str = "") -> dict:
    """Carga el catálogo en `store`. Devuelve un reporte por tabla."""
    errors = validate_catalog(catalog)
    if errors:
        raise ValueError("Catálogo inválido: " + "; ".join(errors))

    report: dict[str, dict[str, int]] = {}
    for section, table in SECTIONS:
        counts = {"created": 0, "updated": 0, "unchanged": 0}
        operational = OPERATIONAL_FIELDS.get(table, set())
        for item in catalog[section]:
            name = table_prefix + table
            existing = store.get_item(name, _key_of(table, item))
            if existing is None:
                store.put_item(name, dict(item))
                counts["created"] += 1
                continue
            catalog_part = {k: v for k, v in item.items() if k not in operational}
            merged = {**existing, **catalog_part}
            if merged == existing:
                counts["unchanged"] += 1
            else:
                store.put_item(name, merged)
                counts["updated"] += 1
        report[table] = counts
    return report
