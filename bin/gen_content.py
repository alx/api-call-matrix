
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

# Config data
config_filepath = 'config.json'

def content_path(filename="_index.html"):

    config = load_config()

    return os.path.join(config["content_root"], filename)

# Function to create an content file
def init_content():

    index_content = (
    )

    # Write the content to the content file
    with open(content_path(), "w+") as f:
        f.writelines(index_content)

def sd_run_to_content(sd_run):

    config = load_config()

    if "base64_placeholder" not in config:
        raise KeyError(f"❌ base64_placeholder not found in config file: {config_filepath}")

    if "save_json" not in config:
        raise KeyError(f"❌ save_json not found in config file: {config_filepath}")

    slug = sd_run['slug_id']
    sd_params = sd_run["params"]
    sd_model_checkpoint = sd_params["override_settings"]["sd_model_checkpoint"]

    categories = [sd_model_checkpoint]

    controlnet_args = sd_params["alwayson_scripts"]["ControlNet"]["args"];
    for control_index, control_data in enumerate(controlnet_args):
        categories.append(control_data['module'])

        if config["save_json"]:
            # replace base64 image by placeholder
            sd_params["alwayson_scripts"]["ControlNet"]["args"][control_index] = \
                config["base64_placeholder"]

    badges = "</span><span class='badge text-bg-secondary'>".join(categories)

    content = f'<h1>{slug} <span class="badge text-bg-secondary">{badges}</span></h1>'

    if config["save_json"]:
        content += (
            f'<p class="d-inline-flex gap-1">'
            f'<a class="btn btn-primary" data-bs-toggle="collapse" href="#collapseExample" role="button" aria-expanded="false" aria-controls="collapse">'
            f'SD Params'
            f'</a>'
            f'<div class="collapse" id="collapseExample">'
            f'<pre><code>'
            f'{json.dumps(sd_params, indent=4)}'
            f'</code></pre></div>'
        )

    for prompt in sd_run["prompts"]:
        content += prompt

    return content

# Function to create an content file for each prompt result
def prompt_to_content(prompt_data, result_output_paths):

    config = load_config()

    if "base64_placeholder" not in config:
        raise KeyError(f"❌ base64_placeholder not found in config file: {config_filepath}")

    # Extract required data
    prompt_title = prompt_data["prompt"]

    # Prepare the content of the org file
    image_paths = [
        image_path.replace("./static/", "")
        for image_path in result_output_paths
    ]

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

    content = (
        f'<h2>{prompt_data["slug_id"]}</h2>'
        f'<div class="pswp-gallery pswp-gallery--single-column list-group list-group-horizontal">'
        f'{images_list}'
        f'</div>'
    )

    return content

def process_prompt(prompt_data, output_dir):

    config = load_config()

    if "sources_root" not in config:
        raise KeyError(f"❌ sources_root not found in config file: {config_filepath}")

    if not os.path.exists(config["sources_root"]):
        raise OSError(f"❌ Sources root folder not found: {config['sources_root']}")

    # Load and list all files in the source_files directory
    source_files = [
        os.path.join(config["sources_root"], f)
        for f in os.listdir(config["sources_root"])
        if os.path.isfile(os.path.join(config["sources_root"], f))
    ]

    # Check if there are source files
    if len(source_files) == 0:
        raise ValueError(f"❌ Not enough source files ({len(source_files)}).")

    # List to keep paths of the saved images
    result_output_paths = []

    # For each prompt, use multiple source files
    for source_file in source_files:

        # Get the basename of the source file (without extension)
        source_basename = os.path.basename(source_file).split('.')[0]

        # Set the image path where the result will be saved,
        # using the source file basename
        output_path = os.path.join(output_dir, f"{source_basename}.png")

        # check if output file exists
        # before to insert it in results
        if os.path.exists(output_path):
            result_output_paths.append(output_path)

    # Create content with the list of result images
    return prompt_to_content(prompt_data, result_output_paths)

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

    sd_run["prompts"] = []

    # Iterate through the prompts and corresponding source files, and make the POST request
    for prompt_index, prompt_data in enumerate(prompts):

        # Do not process this prompt if excluded from sd_run params
        if (
                "limit_slug_prompts" in sd_run
                and prompt_data["slug_id"] not in sd_run["limit_slug_prompts"]
        ):
            continue;

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
            prompt_data["prompt"] += sd_run["negative"]
        if len(top_level_negative) > 0:
            prompt_data["prompt"] += top_level_negative

        # create output folder
        output_dir = os.path.join(sd_param_dir, prompt_data["slug_id"])
        os.makedirs(output_dir, exist_ok=True)

        prompt_content = process_prompt(prompt_data, output_dir)

        if len(prompt_content) > 0:
            sd_run["prompts"].append(prompt_content)

    content = sd_run_to_content(sd_run)

    return content

def load_config():

    if not os.path.exists(config_filepath):
        raise OSError(f"❌ Config file not found: {config_filepath}")

    with open(config_filepath, 'r') as f:
        config = json.load(f)

    return config

def main():

    config = load_config()
    content = ""

    if "runs" not in config:
        raise KeyError(f"❌ runs not found in config file: {config_filepath}")

    elif "prompts" not in config:
        raise KeyError(f"❌ prompts not found in config file: {config_filepath}")

    elif "save_content" not in config:
        raise KeyError(f"❌ save_content not found in config file: {config_filepath}")

    else:

        enabled_runs = [
            r for r in config["runs"]
            if r["enabled"]
        ]

        enabled_prompts = [
            p for p in config["prompts"]
            if p["enabled"]
        ]

        # Start runs
        for sd_run in enabled_runs:

            content = process_sd_run(
                sd_run,
                enabled_prompts,
                config["positive"],
                config["negative"],
            )

    if "save_content" and len(content) > 0:

        if "content_root" not in config:
            raise KeyError(f"❌ content_root not found in config file: {config_filepath}")

        # Write the content to the content file
        with open(content_path(), "w+") as f:
            f.writelines(content)

        print("✔ gen_content DONE")

if __name__ == "__main__":
    main()
