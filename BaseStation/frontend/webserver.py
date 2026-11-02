from flask import Flask, render_template
from datetime import datetime
import time
import threading
import redis
import json

from flask_sse import sse

app = Flask(__name__)

# Configure Redis backend for Flask-SSE
# Server sent events will be triggered by station.py
app.config["REDIS_URL"] = "redis://localhost:6379/0"
app.register_blueprint(sse, url_prefix='/stream')

redis_client = redis.Redis(host='localhost', port=6379, db=0)


# Main Dashboard page
@app.route("/")
def dashboard():
    return render_template('dashboard.html')

# Run the app for local testing
if __name__ == '__main__':
    app.run(threaded=True, debug=True, port=5000)
