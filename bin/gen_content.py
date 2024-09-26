
#!/usr/bin/env python3
import json
import os
import base64
from datetime import datetime

#
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
import requests

# Load JSON config from config.json
with open('config.json', 'r') as file:
    config = json.load(file)

# Extract the prompts from the JSON array
prompts = config["prompts"]

# SD params
sd_runs = config["runs"]

# Set the API URL
api_url = 'http://127.0.0.1:7860/sdapi/v1/txt2img'

# Get today's date in the format YYYYMMDD
date_today = datetime.now().strftime('%Y%m%d')

# Ensure the base directory for saving images exists
base_dir = './static/img/results/'
os.makedirs(base_dir, exist_ok=True)

# Load and list all files in the source_files directory
source_files_dir = './static/img/source_files/'
source_files = [os.path.join(source_files_dir, file) for file in os.listdir(source_files_dir) if os.path.isfile(os.path.join(source_files_dir, file))]

# Check if there are source files
if len(source_files) == 0:
    raise ValueError(f"Not enough source files ({len(source_files)}).")

base64_placeholder = "base64_img_placeholder"

index_filename = f"_index.html"
index_path = os.path.join(f"content", index_filename)

# Function to create an content file
def init_content():

    index_content = (
    )

    # Write the content to the content file
    with open(index_path, "w+") as f:
        f.writelines(index_content)

def append_run_to_content(run_data):

    slug = run_data['run_slug_id']
    sd_params = run_data["params"]
    sd_model_checkpoint = sd_params["override_settings"]["sd_model_checkpoint"]

    categories = [
        sd_model_checkpoint
    ]

    controlnet_args = sd_params["alwayson_scripts"]["ControlNet"]["args"];
    for control in controlnet_args:
        categories.append(control['module'])
        # clean base64 images
        control["image"] = base64_placeholder

    badges = "</span><span class='badge text-bg-secondary'>".join(categories)

    content = (
        f'<h1>{slug} <span class="badge text-bg-secondary">{badges}</span></h1>'
        f'<p class="d-inline-flex gap-1">'
        f'<a class="btn btn-primary" data-bs-toggle="collapse" href="#collapseExample" role="button" aria-expanded="false" aria-controls="collapse">'
        f'SD Params'
        f'</a>'
        f'<div class="collapse" id="collapseExample">'
        f'<pre><code>'
        f'{json.dumps(sd_params, indent=4)}'
        f'</code></pre></div>'
    )

    # Write the content to the content file
    with open(index_path, "a+") as f:
        f.writelines(content)

# Function to create an content file for each prompt result
def append_prompt_to_content(prompt_data, result_image_paths):

    # Extract required data
    prompt_title = prompt_data["prompt"]

    # Prepare the content of the org file
    image_paths = [image_path.replace("./static/", "") for image_path in result_image_paths]
    images_list = '\n'.join(
        [(
            f'<a href={img_path} '
            f'class="text-decoration-none shadow-none p-2" '
            f'data-pswp-width="{prompt_data["width"]}" '
            f'data-pswp-height="{prompt_data["height"]}" '
            f'target="_blank">'
            f'<img src="{img_path}" alt="{os.path.basename(img_path)}">'
            f'</a>'
            ) for img_path in image_paths]

    )

    controlnet_args = prompt_data["alwayson_scripts"]["ControlNet"]["args"];
    for control in controlnet_args:
        # clean base64 images
        control["image"] = base64_placeholder

    content = (
        f'<h2>{prompt_data["slug_id"]}</h2>'
        f'<div class="pswp-gallery pswp-gallery--single-column list-group list-group-horizontal">'
        f'{images_list}'
        f'</div>'
    )

    # Write the content to the Org-mode file
    with open(index_path, "a+") as f:
        f.writelines(content)

# init content
init_content()

# For each sd params, use multiple params
for sd_run in sd_runs:

    # Set the sd_run path where the result will be saved, using the source file basename
    sd_param_dir = os.path.join(base_dir, sd_run["run_slug_id"])
    os.makedirs(sd_param_dir, exist_ok=True)

    append_run_to_content(sd_run)

    # Iterate through the prompts and corresponding source files, and make the POST request
    for prompt_index, prompt_data in enumerate(prompts):

        if (
                "limit_slug_prompts" in sd_run
                and prompt_data["slug_id"] not in sd_run["limit_slug_prompts"]
        ):
            continue;

        # merge prompt_data with sd_run
        prompt_data = prompt_data | sd_run["params"]
        prompt_data["prompt"] = prompt_data["positive"]
        prompt_data["negative_prompt"] = prompt_data["negative"]

        image_dir = os.path.join(sd_param_dir, prompt_data["slug_id"])
        os.makedirs(image_dir, exist_ok=True)

        # Save the request as json
        json_path = os.path.join(image_dir, f"prompt_data.json")
        with open(json_path, "w") as json_file:
            json.dump(prompt_data, json_file)

        # List to keep paths of the saved images
        result_image_paths = []

        # For each prompt, use multiple source files
        for source_file in source_files:

            # Get the basename of the source file (without extension)
            source_basename = os.path.basename(source_file).split('.')[0]

            # Set the image path where the result will be saved, using the source file basename
            image_path = os.path.join(image_dir, f"{source_basename}.png")
            json_path = os.path.join(image_dir, f"{source_basename}.json")

            result_image_paths.append(image_path)

        # Create content with the list of result images
        append_prompt_to_content(prompt_data, result_image_paths)
