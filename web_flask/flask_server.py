import json

# TODO fix: No module named 'request'
# (api-call-matrix) alx@slim:~/code/api-call-matrix$ python3 gen_gallery.py
# Traceback (most recent call last):
#   File "/home/alx/code/api-call-matrix/gen_gallery.py", line 4, in <module>
#     import requests
# ModuleNotFoundError: No module named 'requests'
#
# Probable cause: uv install
#
# Temp fix: append /usr/lib dist-packages
import sys
sys.path.append("/usr/lib/python3/dist-packages")

from flask import Flask, send_from_directory

app = Flask(__name__)
config_path = "config.json"

# Load JSON config from config.json
with open(config_path, 'r') as file:
    config = json.load(file)

@app.route('/')
def index():
    return send_from_directory('public', 'index.html')

@app.route('/<path:filename>')
def static_files(filename):
    # Prevent adding "index.html" to paths of HTML, CSS, JS, and image files
    if not filename.endswith(('.html', '.css', '.js','svg', '.jpg', '.png', '.gif')):
        filename += "/index.html"
    return send_from_directory('static/public', filename)

@app.route('/tags', methods=["POST"])
def tags():
    if request.method == "POST":
        params = request.get_json()

        if "prompt_slug_id" in params:
            prompt = [
                p for p in config["prompts"]
                if p["prompt_slug_id"] == params["prompt_slug_id"]
            ]
            if prompt:

                if "tags" not in prompt:
                    prompt["tags"] = []

                if (
                        params["prompt_action"] == "add_tag"
                        and "tag" in params["tags"]
                        and params["tag"] not in prompt["tags"]
                ):
                    prompt["tags"].append(params["tag"])

                if (
                        params["prompt_action"] == "replace_tag"
                        and "tag" in params["tags"]
                        and "replace_str" in params["replace_str"]
                ):
                    prompt["tags"] = [t for t in prompt["tags"]
                                      if params["replace_str"] not in t]
                    prompt["tags"].append(params["tag"])

        with open(config_path, "w") as f:
            json.dump(config, f)
    else:
        return 404

if __name__ == '__main__':
    app.run(debug=True)
