import os
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
# Assumes .env is in the parent directory of the 'app' package
basedir = os.path.abspath(os.path.dirname(__file__))
dotenv_path = os.path.join(basedir, '../../.env') # Go up two levels from app/config.py
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:
    # Fallback to checking in the project root if running differently
    dotenv_path = os.path.join(basedir, '../.env')
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'
    # Reference instance folder relative to the app package path
    instance_folder_path = os.path.join(basedir, '../instance')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(instance_folder_path, 'app.db') # Use instance folder
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Add other configurations like Redis URL if needed
    # REDIS_URL = os.environ.get('REDIS_URL') or 'redis://localhost:6379/0' 