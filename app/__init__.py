from flask import Flask, request, session, render_template

from .config import Config
from .extensions import db
from .roles import MENU, ROLE_LABELS


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)

    from .blueprints import auth, dashboard, requisition, inventory, purchasing, delivery, admin
    for module in (auth, dashboard, requisition, inventory, purchasing, delivery, admin):
        app.register_blueprint(module.bp)

    @app.context_processor
    def inject_layout():
        role = session.get("role")
        return {
            "current_role": role,
            "role_label": ROLE_LABELS.get(role, ""),
            "menu": MENU.get(role, []),
            "role_labels": ROLE_LABELS,
            "current_endpoint": request.endpoint,
        }

    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("403.html"), 403

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("404.html"), 404

    return app
