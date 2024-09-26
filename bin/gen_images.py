#!/usr/bin/env python3
import json
import os
import base64
from datetime import datetime

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

# SD runs
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

# Function to convert an image to base64
def image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

# For each sd params, use multiple params
for sd_run in sd_runs:

    # Set the sd_run path where the result will be saved, using the source file basename
    sd_run_dir = os.path.join(base_dir, sd_run["run_slug_id"])
    os.makedirs(sd_run_dir, exist_ok=True)

    # Iterate through the prompts and corresponding source files, and make the POST request
    for prompt_index, prompt_data in enumerate(prompts):

        # populate prompt_data with sd_run
        prompt_data = prompt_data | sd_run["params"]
        prompt_data["prompt"] = prompt_data["positive"]

        if "append_prompt" in sd_run["params"]:
            prompt_data["prompt"] += sd_run["params"]["append_prompt"]

        prompt_data["negative_prompt"] = prompt_data["negative"]

        image_dir = os.path.join(sd_run_dir, prompt_data["slug_id"])
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

            # Check if the image already exists, if yes, skip the HTTP POST request
            is_forced = "force" in prompt_data and prompt_data["force"]
            if not is_forced and os.path.exists(image_path):
                print(f"Image already exists: {image_path}. Skipping POST request.")
                continue

            # Convert the source file to base64
            base64_image = image_to_base64(source_file)

            # Include the base64 image in the prompt data (assuming ControlNet uses "image" field)
            for control in prompt_data["alwayson_scripts"]["ControlNet"]["args"]:
                control["image"] = base64_image  # Update the "image" field with the base64 content

            response = requests.post(api_url, json=prompt_data)

            # If the request was successful
            if response.status_code == 200:
                response_data = response.json()
                base64_img = response_data.get("images")[0]  # Assuming the API response has "image" key with base64 data

                # Save the image as PNG
                with open(image_path, "wb") as img_file:
                    img_file.write(base64.b64decode(base64_img))

                # Save the result as json
                with open(json_path, "w") as json_file:
                    response_data.get("images")[0] = base64_placeholder
                    json.dump(response_data, json_file)

                print(f"Image saved to: {image_path}")
            else:
                print(f"Failed to get image for title {title}. HTTP Status Code: {response.status_code}")
