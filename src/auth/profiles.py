"""Lectura del perfil del usuario en t-users (AUTH-02)."""

from __future__ import annotations


class DynamoProfileLoader:
    """Busca el perfil por firebase_uid. Devuelve None si no existe."""

    def __init__(self, table_name: str):
        import boto3  # disponible en el runtime de Lambda

        self._table = boto3.resource("dynamodb").Table(table_name)

    def __call__(self, uid: str) -> dict | None:
        return self._table.get_item(Key={"firebase_uid": uid}).get("Item")
