from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import current_user, login_required
# No changes needed here for imports as they don't reference 'app' directly

# This blueprint can hold general web routes (like homepage, dashboard)
# API specific routes will be in a separate blueprint
# Auth routes in another, Admin routes in another

bp = Blueprint('main', __name__)

@bp.route('/')
@bp.route('/index')
def index():
    # Render the main index page
    return render_template('index.html')

# Example of a protected route
@bp.route('/dashboard')
@login_required # Requires user to be logged in
def dashboard():
    # Basic role check example (can be refined with decorators later)
    if not current_user.is_authenticated or (not current_user.has_role('Analyst') and not current_user.has_role('Administrator')):
        flash('You do not have permission to access the dashboard.', 'warning')
        return redirect(url_for('main.index'))

    # Render the dashboard template
    return render_template('dashboard.html')

# Add other general web routes here 