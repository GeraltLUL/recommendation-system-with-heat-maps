from app import db
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
import datetime


roles_users = db.Table('roles_users',
    db.Column('user_id', db.Integer(), db.ForeignKey('user.id')),
    db.Column('role_id', db.Integer(), db.ForeignKey('role.id'))
)

class Role(db.Model):
    id = db.Column(db.Integer(), primary_key=True)
    name = db.Column(db.String(80), unique=True)
    description = db.Column(db.String(255))

    
    def __str__(self):
        return self.name

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(256)) 
    active = db.Column(db.Boolean(), default=True)
    
    roles = db.relationship('Role', secondary=roles_users,
                            backref=db.backref('users', lazy='dynamic'))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def has_role(self, role_name):
        return any(role.name == role_name for role in self.roles)

    def __repr__(self):
        return f'<User {self.username}>'


class GameEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(100), index=True)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.datetime.utcnow)
    session_id = db.Column(db.String(100), index=True) 
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) 
    level_id = db.Column(db.String(100), nullable=True) 
    position_x = db.Column(db.Float, nullable=True) 
    position_y = db.Column(db.Float, nullable=True)
    position_z = db.Column(db.Float, nullable=True)
    event_data = db.Column(db.JSON) 

    def __repr__(self):
        return f'<GameEvent {self.id} ({self.event_type})>'



