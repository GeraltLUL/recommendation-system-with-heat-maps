from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import current_user, login_required

bp = Blueprint('main', __name__)

@bp.route('/')
@bp.route('/index')
def index():
    if current_user.is_authenticated:
        return f"Hello, {current_user.username}! Role: {current_user.roles}"
    else:
        return "Welcome Guest! Please login."

@bp.route('/dashboard')
@login_required
def dashboard():
    return "This is the main dashboard (Protected)"