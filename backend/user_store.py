import os
import uuid
from typing import Any, Dict, Optional

from auth_utils import hash_password, verify_password

USERS_TABLE = os.environ.get("USERS_TABLE", "users").strip() or "users"


def _get_table():
    import boto3
    return boto3.resource("dynamodb").Table(USERS_TABLE)


def create_user(email: str, name: str, password: str) -> Dict[str, Any]:
    email = email.strip().lower()
    user_id = str(uuid.uuid4())
    name = (name or "").strip() or email.split("@")[0]
    item = {
        "email": email,
        "user_id": user_id,
        "name": name,
        "password_hash": hash_password(password),
    }
    try:
        _get_table().put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(email)",
        )
    except Exception as e:
        err = getattr(e, "response", {}).get("Error", {}).get("Code", "")
        if err == "ConditionalCheckFailedException":
            raise ValueError("Email already registered")
        raise
    return item


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    try:
        r = _get_table().get_item(Key={"email": email.strip().lower()})
        return r.get("Item")
    except Exception:
        return None


def get_user(user_id: str) -> Optional[Dict[str, Any]]:
    try:
        tbl = _get_table()
        r = tbl.query(
            IndexName="user_id-index",
            KeyConditionExpression="user_id = :uid",
            ExpressionAttributeValues={":uid": user_id},
        )
        items = r.get("Items", [])
        while "LastEvaluatedKey" in r:
            r = tbl.query(
                IndexName="user_id-index",
                KeyConditionExpression="user_id = :uid",
                ExpressionAttributeValues={":uid": user_id},
                ExclusiveStartKey=r["LastEvaluatedKey"],
            )
            items.extend(r.get("Items", []))
        return items[0] if items else None
    except Exception:
        return None


def check_password(user: Dict[str, Any], password: str) -> bool:
    return verify_password(password, user["password_hash"])
