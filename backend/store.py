import os
from typing import Any, Dict, List, Optional

TRANSLATIONS_TABLE = os.environ.get("TRANSLATIONS_TABLE", "translations").strip() or "translations"


def _get_table():
    import boto3
    return boto3.resource("dynamodb").Table(TRANSLATIONS_TABLE)


def get(id: str) -> Optional[Dict[str, Any]]:
    try:
        r = _get_table().get_item(Key={"id": id})
        return r.get("Item")
    except Exception:
        return None


def put(record: Dict[str, Any]) -> None:
    _get_table().put_item(Item=record)


def delete(id: str) -> None:
    _get_table().delete_item(Key={"id": id})


def list_by_user(user_id: str) -> List[Dict[str, Any]]:
    try:
        from boto3.dynamodb.conditions import Attr

        tbl = _get_table()
        filt = Attr("user_id").eq(user_id)
        r = tbl.scan(FilterExpression=filt)
        items = list(r.get("Items", []))
        while "LastEvaluatedKey" in r:
            r = tbl.scan(ExclusiveStartKey=r["LastEvaluatedKey"], FilterExpression=filt)
            items.extend(r.get("Items", []))
        return items
    except Exception:
        return []
