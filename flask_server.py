import sys
sys.path.append("/usr/lib/python3/dist-packages")
from flask import Flask, send_from_directory

app = Flask(__name__)

@app.route('/')
def index():
    return send_from_directory('public', 'index.html')

@app.route('/<path:filename>')
def static_files(filename):
    # Prevent adding "index.html" to paths of HTML, CSS, JS, and image files
    if not filename.endswith(('.html', '.css', '.js','svg', '.jpg', '.png', '.gif')):
        filename += "/index.html"
    return send_from_directory('static/public', filename)

if __name__ == '__main__':
    app.run(debug=True)
