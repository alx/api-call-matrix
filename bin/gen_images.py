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

# Config data
config_filepath = 'config.json'

def image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def process_prompt(
        prompt_data,
        output_dir,
):

    config = load_config()

    if "api_url" not in config:
        raise KeyError(f"❌ api_url not found in config file: {config_filepath}")

    if "sources_root" not in config:
        raise KeyError(f"❌ sources_root not found in config file: {config_filepath}")

    if "base64_placeholder" not in config:
        raise KeyError(f"❌ base64_placeholder not found in config file: {config_filepath}")

    if "save_json" not in config:
        raise KeyError(f"❌ save_json not found in config file: {config_filepath}")

    if config["save_json"]:
        # Save the request as json
        json_path = os.path.join(output_dir, f"prompt_data.json")
        with open(json_path, "w") as f:
            json.dump(prompt_data, f)

    # Load and list all files in the source_root directory
    source_files = [
        os.path.join(config["sources_root"], f)
        for f in os.listdir(config["sources_root"])
        if os.path.isfile(os.path.join(config["sources_root"], f))
    ]

    # Check if there are source files
    if len(source_files) == 0:
        raise ValueError(f"❌ Not enough source files ({len(source_files)}).")

    for source_index, source_file in enumerate(source_files):

        # Get the basename of the source file (without extension)
        source_basename = os.path.basename(source_file).split('.')[0]

        # Set the image path where the result will be saved
        # using the source file basename
        image_path = os.path.join(output_dir, f"{source_basename}.png")

        # Check if the image already exists
        # if yes: skip the HTTP POST request
        if os.path.exists(image_path):
            print(f"▶     source - [{source_index + 1}/{len(source_files)}] - {source_basename} - exists")
            continue

        # Convert the source file to base64
        base64_image = image_to_base64(source_file)

        # Include the base64 image in the prompt data
        # assuming ControlNet uses "image" field
        for control in prompt_data["alwayson_scripts"]["ControlNet"]["args"]:
            control["image"] = base64_image

        try:

            print(f"▶     source - [{source_index + 1}/{len(source_files)}] - {source_basename}")

            # a1111 api request
            response = requests.post(
                config["api_url"],
                json=prompt_data
            )

            # If the request was successful
            if response.status_code == 200:
                response_data = response.json()

                # Assuming the API response has "image" key with base64 data
                base64_img = response_data.get("images")[0]

                # Save the image as PNG
                with open(image_path, "wb") as img_file:
                    img_file.write(base64.b64decode(base64_img))

                # Save the result as json
                if config["save_json"]:

                    json_path = os.path.join(
                        output_dir,
                        f"{source_basename}.json"
                    )

                    with open(json_path, "w") as json_file:
                        response_data.get("images")[0] = config["base64_placeholder"]
                        json.dump(response_data, json_file)

            else:
                print(f"❌ requests.post {response.status_code}")
                print(f"❌ {image_path}")

        except requests.exceptions.ConnectionError:
            print(f"❌ check api_url access! {config['api_url']}")


def process_sd_run(
        sd_run,
        prompts,
        top_level_positive="",
        top_level_negative="",
):

    config = load_config()

    if "results_root" not in config:
        raise KeyError(f"❌ results_root not found in config file: {config_filepath}")


    # Set the sd_run path where the result will be saved,
    # using the sd_run slug id
    sd_param_dir = os.path.join(config["results_root"], sd_run["slug_id"])
    os.makedirs(sd_param_dir, exist_ok=True)

    # Iterate through the prompts and corresponding source files, and make the POST request
    for prompt_index, prompt_data in enumerate(prompts):

        # populate prompt_data with sd_run
        prompt_data = prompt_data | sd_run["params"]
        prompt_data["prompt"] = ""
        prompt_data["negative_prompt"] = ""

        if "positive" in prompt_data:
            prompt_data["prompt"] = prompt_data["positive"]
        if "positive" in sd_run:
            prompt_data["prompt"] += sd_run["positive"]
        if len(top_level_positive) > 0:
            prompt_data["prompt"] += top_level_positive

        if "negative" in prompt_data:
            prompt_data["negative_prompt"] = prompt_data["negative"]
        if "negative" in sd_run:
            prompt_data["negative_prompt"] += sd_run["negative"]
        if len(top_level_negative) > 0:
            prompt_data["negative_prompt"] += top_level_negative

        # create output folder
        output_dir = os.path.join(sd_param_dir, prompt_data["slug_id"])
        os.makedirs(output_dir, exist_ok=True)

        print(f"▶   prompt - [{prompt_index + 1}/{len(prompts)}] - {prompt_data['slug_id']}")
        process_prompt(prompt_data, output_dir)

def load_config():

    if not os.path.exists(config_filepath):
        raise OSError(f"❌ Config file not found: {config_filepath}")

    with open(config_filepath, 'r') as f:
        config = json.load(f)

    return config

def main():

    config = load_config()

    if "runs" not in config:
        raise KeyError(f"❌ runs not found in config file: {config_filepath}")

    elif "prompts" not in config:
        raise KeyError(f"❌ prompts not found in config file: {config_filepath}")

    else:

        enabled_runs = [
            r for r in config["runs"]
            if r["enabled"]
        ]

        enabled_prompts = [
            p for p in config["prompts"]
            if p["enabled"]
        ]

        for sd_run_index, sd_run in enumerate(enabled_runs):

            print(f"▶ sd_run - [{sd_run_index + 1}/{len(enabled_runs)}] - {sd_run['slug_id']}")
            process_sd_run(
                sd_run,
                enabled_prompts,
                config["positive"],
                config["negative"],
            )

if __name__ == "__main__":
    main()
