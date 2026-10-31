from flask_sqlalchemy import SQLAlchemy

# The database tables are created with database/schema.sql.
# Models are not written yet: you can generate them from the schema later
# (for example with sqlacodegen) or query with plain SQL through db.session.
db = SQLAlchemy()
