from flask import Blueprint, render_template, redirect, url_for, flash, abort, request, jsonify
from flask_login import login_required, current_user
from functools import wraps
from sqlalchemy import asc, desc, func, exc

from .models import User, Role, roles_users
from . import db

# Decorator to require Administrator role
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.has_role('Administrator'):
            flash("You do not have permission to access this page.", "danger")
            # Redirect to dashboard or index page instead of aborting with 403
            # depending on desired user experience
            return redirect(url_for('main.dashboard')) 
            # Or: abort(403) # Forbidden
        return f(*args, **kwargs)
    return decorated_function

# Decorator to require Administrator OR Analyst role
def analyst_or_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Import login_manager here if not available globally or pass it somehow
        # For now, assume login_manager is accessible
        from . import login_manager 
        
        if not current_user.is_authenticated:
            # Redirect to login if not authenticated
            return login_manager.unauthorized()
        if not (current_user.has_role('Administrator') or current_user.has_role('Analyst')):
            flash("You do not have permission to access this page.", "danger")
            # Redirect non-admins/analysts (e.g., to dashboard)
            return redirect(url_for('main.dashboard')) 
        return f(*args, **kwargs)
    return decorated_function

bp = Blueprint('admin', __name__, url_prefix='/admin')

@bp.route('/users')
@login_required
@admin_required
def user_management():
    """Displays the user management page with sorting."""
    # Sorting parameters
    sort_by = request.args.get('sort_by', 'id') # Default sort by id
    order = request.args.get('order', 'asc') # Default order asc

    # Base query
    query = User.query

    # Determine sort column and direction
    order_func = asc if order == 'asc' else desc

    if sort_by == 'username':
        query = query.order_by(order_func(User.username))
    elif sort_by == 'email':
        query = query.order_by(order_func(User.email))
    elif sort_by == 'roles':
        query = query.outerjoin(User.roles).group_by(User.id).order_by(order_func(func.min(Role.name)))
    else: # Default to sorting by id
        sort_by = 'id'
        query = query.order_by(order_func(User.id))

    # Apply sorting
    users = query.all()

    # Fetch all roles for the edit form dropdown/checkboxes
    all_roles = Role.query.order_by(Role.name).all()

    # Pass sorting info to template for link generation
    return render_template(
        'admin/user_management.html',
        users=users,
        all_roles=all_roles, # Pass roles to template
        current_sort_by=sort_by,
        current_order=order
    )

@bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    """Deletes a user."""
    if user_id == current_user.id:
        flash("You cannot delete your own account.", "danger")
        return redirect(url_for('admin.user_management'))

    user_to_delete = db.session.get(User, user_id)
    if not user_to_delete:
        flash("User not found.", "warning")
        return redirect(url_for('admin.user_management'))

    try:
        # Clear associations before deleting user
        user_to_delete.roles = [] 
        db.session.commit() # Commit clearing roles
        
        db.session.delete(user_to_delete)
        db.session.commit()
        flash(f"User '{user_to_delete.username}' has been deleted.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting user: {e}", "danger")

    return redirect(url_for('admin.user_management'))

# --- Routes for Edit Functionality ---

@bp.route('/users/<int:user_id>/data')
@login_required
@admin_required
def get_user_data(user_id):
    """Returns user data as JSON for the edit modal."""
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Assuming only one role, get its ID or None
    user_role_id = user.roles[0].id if user.roles else None
    
    user_data = {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'role_id': user_role_id # Return single role ID
    }
    return jsonify(user_data)

@bp.route('/users/<int:user_id>/update', methods=['POST'])
@login_required
@admin_required
def update_user(user_id):
    """Updates user data based on JSON payload (expects single role_id)."""
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid data'}), 400

    new_username = data.get('username', '').strip()
    new_email = data.get('email', '').strip()
    new_role_id_str = data.get('role_id') # Expecting a single role ID string/number
    new_password = data.get('password')

    if not new_username or not new_email:
        return jsonify({'error': 'Username and Email cannot be empty'}), 400
        
    # Validate role ID
    new_role_id = None
    if new_role_id_str is not None:
        try:
            new_role_id = int(new_role_id_str)
        except ValueError:
             return jsonify({'error': 'Invalid Role ID format.'}), 400
    else: # Role is required
        return jsonify({'error': 'A role must be selected.'}), 400

    # Fetch the selected role object
    selected_role = db.session.get(Role, new_role_id)
    if not selected_role:
        return jsonify({'error': 'Selected role not found.'}), 400
    
    # Check uniqueness constraints
    if User.query.filter(User.username == new_username, User.id != user_id).first():
        return jsonify({'error': 'Username already taken'}), 400
    if User.query.filter(User.email == new_email, User.id != user_id).first():
         return jsonify({'error': 'Email already taken'}), 400

    user.username = new_username
    user.email = new_email

    if new_password:
        user.set_password(new_password)

    # Update roles - ensure admin cannot remove their own admin role
    is_self = (user_id == current_user.id)
    current_admin_role_id = 1 # Administrator ID

    if is_self and user.has_role('Administrator') and selected_role.id != current_admin_role_id:
        # Trying to change own role from Admin to something else - prevent
        # Return an error or flash message (flash won't show on AJAX, return error)
         return jsonify({'error': 'You cannot change your own role from Administrator.'}), 403 # Forbidden
    else:
        # Assign the single selected role
        user.roles = [selected_role] 
    
    try:
        db.session.commit()
        return jsonify({'message': f'User {user.username} updated successfully.'}) 
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Database error: {e}'}), 500

# --- Route for Creating New User (via Modal/JSON) ---
@bp.route('/users/create', methods=['POST'])
@login_required
@admin_required
def create_user():
    """Handles creating a new user from JSON data (expects single role_id)."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid data'}), 400

    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password')
    role_id_str = data.get('role_id') # Expect single role ID

    # --- Validation --- 
    if not username or not email or not password:
        return jsonify({'error': 'Username, Email, and Password are required.'}), 400
        
    if User.query.filter(User.username == username).first():
        return jsonify({'error': 'Username already exists.'}), 400

    if User.query.filter(User.email == email).first():
        return jsonify({'error': 'Email already registered.'}), 400

    # Validate role ID
    role_id = None
    if role_id_str is not None:
         try:
            role_id = int(role_id_str)
         except ValueError:
            return jsonify({'error': 'Invalid role ID format.'}), 400
    else:
        return jsonify({'error': 'A role must be selected.'}), 400
        
    # Fetch the selected role object
    selected_role = db.session.get(Role, role_id)
    if not selected_role:
        return jsonify({'error': 'Selected role not found.'}), 400

    # --- Create User --- 
    try:
        new_user = User(username=username, email=email)
        new_user.set_password(password)
        new_user.roles = [selected_role] # Assign the single role
        
        db.session.add(new_user)
        db.session.commit()
        return jsonify({'message': f"User '{username}' created successfully!"}), 201

    except exc.IntegrityError as e:
        db.session.rollback()
        return jsonify({'error': f'Database error: Could not add user. {e}'}), 500
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'An unexpected error occurred: {e}'}), 500

# Removed the old add_user route

# Add routes for adding/editing users later
# Example:
# @bp.route('/users/add', methods=['GET', 'POST'])
# @login_required
# @admin_required
# def add_user():
#     # Logic to add a new user
#     pass 