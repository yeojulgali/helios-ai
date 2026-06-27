import copy
from datetime import datetime, timezone

from config import DEFAULT_SETTINGS
from auth import get_supabase_client


def deep_merge(default: dict, saved: dict):
    result = copy.deepcopy(default)

    for key, value in saved.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value

    return result


def load_user_settings(user_id: str):
    client = get_supabase_client()

    response = (
        client
        .table("user_settings")
        .select("settings")
        .eq("user_id", user_id)
        .execute()
    )

    if response.data and len(response.data) > 0:
        saved_settings = response.data[0].get("settings", {})
        return deep_merge(DEFAULT_SETTINGS, saved_settings)

    settings = copy.deepcopy(DEFAULT_SETTINGS)
    save_user_settings(user_id, settings)

    return settings


def save_user_settings(user_id: str, settings: dict):
    client = get_supabase_client()

    now = datetime.now(timezone.utc).isoformat()

    payload = {
        "user_id": user_id,
        "settings": settings,
        "updated_at": now,
    }

    response = (
        client
        .table("user_settings")
        .upsert(payload)
        .execute()
    )

    return response