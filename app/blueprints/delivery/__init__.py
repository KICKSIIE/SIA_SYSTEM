from flask import Blueprint

bp = Blueprint("delivery", __name__, url_prefix="/delivery")

# one file per owner, all routes are on the same blueprint
from . import transfers, shop_receiving, supplier_receiving  # noqa: E402,F401
