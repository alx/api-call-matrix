
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
sd_params = config["sd_params"]

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

# Function to create an Org-mode file for each prompt result
def create_org_file():
    # Create a valid file name by replacing spaces and special characters
    org_file_name = f"_index.org"
    org_file_path = os.path.join(f"content", org_file_name)

    org_content = f"""
    """

    # Write the content to the Org-mode file
    with open(org_file_path, "w") as org_file:
        org_file.write(org_content.strip())


# Function to create an Org-mode file for each prompt result
def append_prompt_org_file(prompt_data, result_image_paths):
    # Extract required data for the org file
    prompt_title = prompt_data["prompt"]
    sd_model_checkpoint = prompt_data["override_settings"]["sd_model_checkpoint"]

    # Create a valid file name by replacing spaces and special characters
    org_file_name = f"_index.org"
    org_file_path = os.path.join(f"content", org_file_name)

    # Prepare the content of the org file
    image_paths = [image_path.replace("./static/", "") for image_path in result_image_paths]
    images_list = '\n'.join([f'[[{img_path}]]' for img_path in image_paths])

    controlnet_args = prompt_data["alwayson_scripts"]["ControlNet"]["args"];
    for control in controlnet_args:
        # clean base64 images
        control["image"] = base64_placeholder

    org_content = f"""

* {prompt_data['slug_id']}  :@{sd_model_checkpoint}:

{images_list}

#+BEGIN_SRC json
{json.dumps(prompt_data, indent=4)}
#+END_SRC

    """
    # TODO Show controlnets

    # Write the content to the Org-mode file
    with open(org_file_path, "a") as org_file:
        org_file.write(org_content.strip())

    print(f"Org file saved to: {org_file_path}")

create_org_file()

# For each sd params, use multiple params
for sd_param in sd_params:

    # Set the sd_param path where the result will be saved, using the source file basename
    sd_param_dir = os.path.join(base_dir, sd_param["params_slug_id"])
    os.makedirs(sd_param_dir, exist_ok=True)

    # Iterate through the prompts and corresponding source files, and make the POST request
    for prompt_index, prompt_data in enumerate(prompts):

        # populate prompt_data with sd_param
        prompt_data = prompt_data | sd_param["params"]
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

        # Create an Org-mode file with the list of result images
        append_prompt_org_file(prompt_data, result_image_paths)
