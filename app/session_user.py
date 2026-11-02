"""Who is logged in, and which location they may see.

TEMPORARY: until the real login exists, the dev role picker fills the session
(see auth.dev_role). When the real login is built, only the place that fills
the session changes. Everything else keeps using current_user().
"""
from flask import session

MANAGER_ROLES = ("shop_manager", "warehouse_manager")


def current_user():
    return {"id": session.get("user_id"), "role": session.get("role"),
            "location_id": session.get("location_id"), "name": session.get("user_name")}


def scope_location(user):
    """None = may see every location (owner). Otherwise the user's own location id."""
    return None if user["role"] == "owner" else user["location_id"]
