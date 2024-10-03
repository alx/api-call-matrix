
#!/usr/bin/env python3
import json
import os
from datetime import datetime
import jinja2

# Config data
config_filepath = 'config.json'

# Templates
env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(searchpath="./templates/"),
    autoescape=jinja2.select_autoescape()
)

template_sdrun = env.get_template("sdrun.html")
template_prompt = env.get_template("prompt.html")

####
####

def content_path(filename="_index.html"):

    config = load_config()

    return os.path.join(config["content_root"], filename)

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

        if (
                config["save_json"]
                and "image" in control_data
        ):
            # replace base64 image by placeholder
            control_data["image"] = config["base64_placeholder"]

    content = template_sdrun.render({
        "slug": sd_run["slug_id"],
        "badges": categories,
        "save_json": config["save_json"],
        "sd_params": json.dumps(sd_params, sort_keys=False, indent=2)
    })

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

    img_list = []
    for img_path in image_paths:
        json_path = img_path.replace(".png", ".json")
        img_list.append({
            "basename": os.path.basename(img_path),
            "path": img_path,
            "json_path": img_path.replace(".png", ".json"),
            "width": prompt_data["width"],
            "height": prompt_data["height"]
        })

    return template_prompt.render({
        "slug": prompt_data["slug_id"],
        "img_list": img_list
    })

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

        print(f"✔ gen_content - prompt - {prompt_data['slug_id']}")

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

            print(f"✔ gen_content - sd_run - {sd_run['slug_id']}")

            content += process_sd_run(
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

        print(f"✔ gen_content DONE")

if __name__ == "__main__":
    main()
