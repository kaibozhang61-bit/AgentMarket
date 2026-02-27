from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.conditions import Attr

from app.core.config import get_settings


def _to_python(obj: Any) -> Any:
    """Recursively convert DynamoDB Decimal to int / float."""
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    if isinstance(obj, dict):
        return {k: _to_python(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_python(i) for i in obj]
    return obj


class BaseDAO:
    def __init__(self) -> None:
        settings = get_settings()
        dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
        self._table = dynamodb.Table(settings.dynamodb_table_name)

    def _clean(self, item: dict[str, Any]) -> dict[str, Any]:
        return _to_python(item)

    def _build_update_expr(
        self, fields: dict[str, Any]
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        """
        Build a SET UpdateExpression from a flat dict of {field: value}.
        All field names are aliased to avoid DynamoDB reserved-word collisions.

        Returns (expression, ExpressionAttributeNames, ExpressionAttributeValues).
        """
        parts: list[str] = []
        names: dict[str, str] = {}
        values: dict[str, Any] = {}

        for i, (key, val) in enumerate(fields.items()):
            n = f"#f{i}"
            v = f":v{i}"
            names[n] = key
            values[v] = val
            parts.append(f"{n} = {v}")

        return "SET " + ", ".join(parts), names, values

    def _item_exists_condition(self) -> Attr:
        return Attr("PK").exists()

    def _item_not_exists_condition(self) -> Attr:
        return Attr("PK").not_exists()
