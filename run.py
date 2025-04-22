from app import create_app, db
from app.models import Role, roles_users, User
import click

app = create_app()

@app.cli.command("create-roles")
def create_roles_command():
    """Creates or updates the default Administrator and Analyst roles."""
    roles_to_create = {
        'Administrator': {'id': 1, 'description': 'Full system access'},
        'Analyst': {'id': 2, 'description': 'Can view analytics and reports'}
    }
    print("--- Running create-roles command ---")
    
    with app.app_context():
        for role_name, details in roles_to_create.items():
            target_id = details['id']
            description = details['description']
            print(f"\nProcessing role: {role_name} (ID: {target_id})")

            existing_role_by_id = db.session.get(Role, target_id)
            if existing_role_by_id and existing_role_by_id.name != role_name:
                print(f"  Warning: Role with ID {target_id} exists but has name '{existing_role_by_id.name}'. Deleting it.")
                try:
                    stmt = roles_users.delete().where(roles_users.c.role_id == target_id)
                    db.session.execute(stmt)
                    db.session.delete(existing_role_by_id)
                    db.session.commit()
                    print(f"  Existing role with ID {target_id} deleted.")
                except Exception as e:
                    db.session.rollback()
                    print(f"  Error deleting existing role with ID {target_id}: {e}")
                    continue

            existing_role_by_name = Role.query.filter_by(name=role_name).first()
            if existing_role_by_name and existing_role_by_name.id != target_id:
                print(f"  Warning: Role with name '{role_name}' exists but has ID {existing_role_by_name.id}. Deleting it.")
                try:
                    stmt = roles_users.delete().where(roles_users.c.role_id == existing_role_by_name.id)
                    db.session.execute(stmt)
                    db.session.delete(existing_role_by_name)
                    db.session.commit()
                    print(f"  Existing role '{role_name}' deleted.")
                except Exception as e:
                    db.session.rollback()
                    print(f"  Error deleting existing role '{role_name}': {e}")
                    continue

            final_role = db.session.get(Role, target_id)
            if not final_role:
                print(f"  Creating role '{role_name}' with ID {target_id}...")
                try:
                    new_role = Role(id=target_id, name=role_name, description=description)
                    db.session.add(new_role)
                    db.session.commit()
                    print(f"  Role '{role_name}' created successfully.")
                except Exception as e:
                    db.session.rollback()
                    print(f"  Error creating role '{role_name}' with ID {target_id}: {e}")
            elif final_role.name == role_name:
                 print(f"  Role '{role_name}' with ID {target_id} already exists correctly.")
            else:
                 print(f"  Error: ID {target_id} is occupied by role '{final_role.name}'. Cannot create '{role_name}'.")

    print("\n--- Role creation finished ---")

@app.cli.command("create-admin")
def create_admin_command():
    """Creates or updates the default admin user with Administrator role."""
    admin_username = 'adminLogin'
    admin_password = 'adminPassword'
    admin_email = 'admin@example.com'
    admin_role_name = 'Administrator'
    admin_role_id = 1

    print(f"--- Running create-admin command for user: {admin_username} ---")

    with app.app_context():
        admin_role = db.session.get(Role, admin_role_id)
        if not admin_role or admin_role.name != admin_role_name:
            print(f"Error: Role '{admin_role_name}' with ID {admin_role_id} not found or name mismatch.")
            print("Please run 'flask --app run create-roles' first.")
            return
        else:
             print(f"Found role: {admin_role.name} (ID: {admin_role.id})")

        admin_user = User.query.filter_by(username=admin_username).first()
        if not admin_user:
            print(f"Creating user: {admin_username}...")
            admin_user = User(username=admin_username, email=admin_email)
            admin_user.set_password(admin_password)
            admin_user.roles.append(admin_role)
            db.session.add(admin_user)
        else:
            print(f"User '{admin_username}' already exists. Updating password and checking role.")
            admin_user.set_password(admin_password)
            if admin_role not in admin_user.roles:
                print(f"Adding role '{admin_role_name}' to user '{admin_username}'.")
                admin_user.roles.append(admin_role)
            else:
                print(f"User already has role '{admin_role_name}'.")

        try:
            db.session.commit()
            print(f"User '{admin_username}' created/updated successfully with role '{admin_role_name}'.")
        except Exception as e:
            db.session.rollback()
            print(f"Error saving user changes: {e}")

    print("\n--- Admin user creation finished ---")

if __name__ == '__main__':
    
    
    app.run(debug=True, host='0.0.0.0', port=5000)