from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user, login_required
from werkzeug.security import check_password_hash

from .models import User
from . import db

# Use a more specific name like 'auth_bp' if 'bp' is used elsewhere
bp = Blueprint('auth', __name__, url_prefix='/auth')

@bp.route('/login', methods=['GET', 'POST'])
def login():
    # If user is already logged in, redirect to main page
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        # Input field name is still 'username' in the form, but user can enter username or email
        login_identifier = request.form.get('username') 
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False

        if not login_identifier or not password:
            # Updated flash message
            flash('Username/Email and password are required.', 'warning') 
            return redirect(url_for('auth.login'))

        # Try finding user by username (case-insensitive)
        user = User.query.filter(User.username.ilike(login_identifier)).first()

        # If not found by username, try finding by email (case-insensitive)
        if not user:
            user = User.query.filter(User.email.ilike(login_identifier)).first()

        # Check if user exists (found by either method) and password is correct
        if not user or not user.check_password(password):
            # Updated flash message to be more general
            flash('Invalid credentials.', 'danger') 
            return redirect(url_for('auth.login'))

        # Log the user in
        login_user(user, remember=remember)
        flash(f'Welcome back, {user.username}!', 'success')

        # Redirect to the page user tried to access, or dashboard
        next_page = request.args.get('next')
        if not next_page or not next_page.startswith('/'): # Security check
            next_page = url_for('main.dashboard')
        return redirect(next_page)

    # Render the login form for GET requests
    return render_template('auth/login.html')

@bp.route('/logout')
@login_required # User must be logged in to log out
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('main.index'))

# Add registration route later if needed
# @bp.route('/register', methods=['GET', 'POST']) 