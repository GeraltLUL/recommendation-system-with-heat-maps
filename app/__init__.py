import os
import json
from datetime import timedelta
from markupsafe import Markup
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager

# Use relative import for config
from .config import Config

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = 'auth.login' # Route name for the login page
# Optional: Add message and category for login_required redirect
login_manager.login_message = u"Please log in to access this page."
login_manager.login_message_category = "info"

# --- Custom Jinja Filters ---

def format_timedelta(value):
    """Formats a timedelta object into HH:MM:SS string."""
    if isinstance(value, timedelta):
        total_seconds = int(value.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02}:{minutes:02}:{seconds:02}"
    return value # Return original value if not a timedelta

def pretty_json(value):
    """Formats a dictionary or JSON string into pretty-printed HTML."""
    try:
        # If it's already a dict/list, dump it to JSON string first
        if isinstance(value, (dict, list)):
            json_str = json.dumps(value, indent=4, sort_keys=True, ensure_ascii=False)
        # If it's a string, assume it's JSON and load/dump to format
        elif isinstance(value, str):
            try:
                parsed = json.loads(value)
                json_str = json.dumps(parsed, indent=4, sort_keys=True, ensure_ascii=False)
            except json.JSONDecodeError:
                # If it's not valid JSON, escape and return as is
                from markupsafe import escape
                return escape(value)
        else:
            # If it's neither dict/list nor string, just convert to string
             from markupsafe import escape
             return escape(str(value))

        # Escape the formatted JSON string and wrap in <pre> for HTML display
        from markupsafe import escape
        escaped_json = escape(json_str)
        return Markup(f'<pre class="json-output"><code>{escaped_json}</code></pre>')
    except Exception:
        # Fallback for any unexpected errors
        from markupsafe import escape
        return escape(str(value))

# --------------------------


def create_app(config_class=Config):
    # Use __name__.split('.')[0] to get the package name ('app')
    # even if run directly or imported.
    app = Flask(__name__.split('.')[0], instance_relative_config=True)
    app.config.from_object(config_class)

    # Add Jinja extensions here
    app.jinja_env.add_extension('jinja2.ext.do')

    # Register custom Jinja filters
    app.jinja_env.filters['format_timedelta'] = format_timedelta
    app.jinja_env.filters['pretty_json'] = pretty_json

    # Ensure the instance folder exists (relative to workspace root)
    instance_path = os.path.join(app.root_path, '../instance')
    # Adjust instance path if it should be relative to app package
    # instance_path = app.instance_path
    try:
        os.makedirs(instance_path)
        app.instance_path = instance_path # Explicitly set instance path if needed
    except OSError:
        pass # Already exists

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # --- User Loader for Flask-Login ---
    # Import User model *inside* the factory to avoid potential circular imports
    # if models.py also imports 'app' or 'db'
    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        # Flask-Login stores the user ID as a string in the session
        # The User model's primary key is an integer
        try:
            return User.query.get(int(user_id))
        except (TypeError, ValueError):
            # Handle cases where user_id might not be a valid integer string
            return None
    # -----------------------------------

    # Register blueprints using relative imports
    from .routes import bp as main_bp
    app.register_blueprint(main_bp)

    # Example: Add API blueprint later
    from .api import bp as api_bp
    app.register_blueprint(api_bp)

    # Register Auth blueprint
    from .auth import bp as auth_bp
    # The url_prefix is defined within auth.py, no need to repeat here
    app.register_blueprint(auth_bp)

    # Register Admin blueprint
    from .admin import bp as admin_bp
    app.register_blueprint(admin_bp)

    # Register Database Viewer blueprint
    from .db_viewer import bp as db_viewer_bp
    app.register_blueprint(db_viewer_bp)

    # Register Reports blueprint
    from .reports import bp as reports_bp
    app.register_blueprint(reports_bp)

    @app.route('/hello')
    def hello():
        return 'Hello, World from GameFlow Package!'

    return app

# Import models here to make them available for Flask-Migrate
# but be cautious of circular imports if models import 'app' or 'db' directly
from . import models # noqa: F401 