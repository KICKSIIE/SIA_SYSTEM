from flask import Blueprint

bp = Blueprint("admin", __name__, url_prefix="/admin")

# one file per owner, all routes are on the same blueprint
from . import people, items  # noqa: E402,F401
