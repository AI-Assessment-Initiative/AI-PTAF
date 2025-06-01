from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import logging # Add logging import
import os # For log directory

db = SQLAlchemy()

def setup_logging(app):
    # Create logs directory if it doesn't exist
    log_dir = os.path.join(app.root_path, '..', 'logs') # Place logs dir one level above ptplatform package
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_file_path = os.path.join(log_dir, 'ptaf_platform.log')

    # Basic configuration for logging to a file and console
    logging.basicConfig(
        level=logging.INFO, # Set default logging level
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file_path), # Log to a file
            logging.StreamHandler()             # Log to console
        ]
    )
    # You can also configure specific loggers, e.g., for SQLAlchemy or Werkzeug
    # logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
    # logging.getLogger('werkzeug').setLevel(logging.INFO) # For request logs

def create_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ptaf_platform.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    # It's good practice to set a secret key for flash messages, even in dev
    app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev_secret_key_please_change')


    setup_logging(app) # Call logging setup
    app.logger.info("PTAF Platform application starting up...")


    db.init_app(app)

    from .views import main_blueprint
    app.register_blueprint(main_blueprint)

    from .models import TestEnvironment, Agent, TestRun, Finding

    with app.app_context():
        db.create_all()
        app.logger.info("Database tables checked/created.")

    return app
