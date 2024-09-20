#!/usr/bin/env python3
import json
import os
import base64
import requests
from datetime import datetime

# Function to convert an image to base64
def image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

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
def append_prompt_org_file(prompt_index, source_file, prompt_data, result_image_paths):
    # Extract required data for the org file
    prompt_title = prompt_data["prompt"]
    sd_model_checkpoint = prompt_data["override_settings"]["sd_model_checkpoint"]

    # Create a valid file name by replacing spaces and special characters
    org_file_name = f"_index.org"
    org_file_path = os.path.join(f"content", org_file_name)

    # Prepare the content of the org file
    images_list = '\n'.join([f'[[file:{image_path}]]' for image_path in result_image_paths])

    org_content = f"""

* prompt_{prompt_index} {prompt_title[:50]} :@{sd_model_checkpoint}:

[[file:{source_file}]]

{images_list}

#+begin_src json
{prompt_data}
#+end_src

    """
    # TODO Show controlnets

    # Write the content to the Org-mode file
    with open(org_file_path, "a") as org_file:
        org_file.write(org_content.strip())

    print(f"Org file saved to: {org_file_path}")

create_org_file()

# Load JSON data from list.json
with open('prompt.json', 'r') as file:
    data = json.load(file)

# Extract the prompts from the JSON array
prompts = data["prompts"]

# Set the API URL
api_url = 'http://127.0.0.1:7860/sdapi/v1/txt2img'

# Get today's date in the format YYYYMMDD
date_today = datetime.now().strftime('%Y%m%d')

# Ensure the base directory for saving images exists
base_dir = './assets/img/results/'
os.makedirs(base_dir, exist_ok=True)

# Load and list all files in the source_files directory
source_files_dir = './assets/img/source_files/'
source_files = [os.path.join(source_files_dir, file) for file in os.listdir(source_files_dir) if os.path.isfile(os.path.join(source_files_dir, file))]

# Check if there are fewer source files than prompts
if len(source_files) < len(prompts):
    raise ValueError(f"Not enough source files ({len(source_files)}) for the number of prompts ({len(prompts)}).")

# Iterate through the prompts and corresponding source files, and make the POST request
for prompt_index, prompt_data in enumerate(prompts):
    # List to keep paths of the saved images
    result_image_paths = []

    # For each prompt, use multiple source files
    for source_file in source_files:

        # Get the basename of the source file (without extension)
        source_basename = os.path.basename(source_file).split('.')[0]

        # Set the image path where the result will be saved, using the source file basename
        image_dir = os.path.join(base_dir, f"prompt_{prompt_index}")
        os.makedirs(image_dir, exist_ok=True)
        image_path = os.path.join(image_dir, f"result_{prompt_index}_{source_basename}.png")

        # Check if the image already exists, if yes, skip the HTTP POST request
        if os.path.exists(image_path):
            print(f"Image already exists: {image_path}. Skipping POST request.")
            result_image_paths.append(image_path)
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
            print(f"Image saved to: {image_path}")
        else:
            print(f"Failed to get image for title {title}. HTTP Status Code: {response.status_code}")

    # Create an Org-mode file with the list of result images
    append_prompt_org_file(prompt_index, source_file, prompt_data, result_image_paths)
