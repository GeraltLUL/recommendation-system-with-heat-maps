import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
dotenv_path = os.path.join(basedir, '../.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'instance', 'app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False