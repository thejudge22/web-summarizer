# ABOUTME: The Flask app entry point, initializing the app and registering routes.
# ABOUTME: Sets up the Flask application and registers the routes defined in routes.py.

from flask import Flask
from config import Config
from routes import app as application

# Initialize Flask app
app = application

if __name__ == '__main__':
    # This block is NOT used when running with Gunicorn/Docker CMD
    # It's only for direct execution like `python app.py`
    # Use a more secure secret key for development if needed
    # app.secret_key = 'dev_secret_key'
    app.run(host='0.0.0.0', port=5000, debug=True)