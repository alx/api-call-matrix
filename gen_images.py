#!/usr/bin/env python3
import json
import os
from datetime import datetime

import webuiapi
from webuiapi import raw_b64_img

import PIL
from PIL import Image, PngImagePlugin

# Config data
config_filepath = 'config.json'

def process_prompt(
        api,
        prompt_data,
        output_dir,
):

    config = load_config()

    if "sources_root" not in config:
        raise KeyError(f"❌ sources_root not found in config file: {config_filepath}")

    if "placeholder" not in config:
        raise KeyError(f"❌ placeholder not found in config file: {config_filepath}")

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

        # move the source file to PIL Image
        source_image = Image.open(source_file)

        controlnet_units = []
        for control in prompt_data["alwayson_scripts"]["ControlNet"]["args"]:

            # replace placeholder in prompt_data controlnets
            if "image" in control:
                control["image"] = raw_b64_img(source_image)

            controlnet_units.append(control)

        prompt_data["controlnet_units"] = controlnet_units

        if "reactor" in prompt_data:
            # include ReActor extension parameters in prompt_data
            reactor = webuiapi.ReActor(
                img=source_image,
                source_faces_index = "0,1,2,3", #2 Comma separated face number(s) from swap-source image
                faces_index = "0,1,2,3", #3 Comma separated face number(s) for target image (result)
                upscaler_name =  "None",# None, # "R-ESRGAN 4x+", #8 Upscaler (type 'None' if doesn't need), see full list here: http://127.0.0.1:7860/sdapi/v1/script-info -> reactor -> sec.8
                swap_in_source = True,
                console_logging_level = 2, #13 Console Log Level (0 - min, 1 - med or 2 - max)
                codeFormer_weight = 1,
                target_hash_check = True,
                mask_face = False,
            )
            prompt_data["alwayson_scripts"]["reactor"] = {
                "args": reactor.to_dict()
            }

        try:

            print(f"▶     source - [{source_index + 1}/{len(source_files)}] - {source_basename}")

            #####
            #
            #
            # a1111 api request
            #
            #
            #####
            use_async = False
            response = api.post_and_get_api_result(
                f"{api.baseurl}/txt2img",
                prompt_data,
                use_async
            )

            # Save the image
            response.image.save(image_path)

            # Save the result as json
            if config["save_json"]:

                json_path = os.path.join(
                    output_dir,
                    f"{source_basename}.json"
                )

                with open(json_path, "w") as f:
                    json.dump(response.json, f)

        except RuntimeError:
            print(api.baseurl)
            print(f"❌ response {response.status_code}")
            print(f"❌ {image_path}")


def process_sd_run(
        api,
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

        if "is_reactor" in sd_run \
            and sd_run["is_reactor"]:

            # TODO explain parameter
            prompt_data["restore_faces"] = False
            prompt_data["reactor"] = True

        print(f"▶   prompt - [{prompt_index + 1}/{len(prompts)}] - {prompt_data['slug_id']}")
        process_prompt(
            api,
            prompt_data,
            output_dir
        )

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

        api = webuiapi.WebUIApi(**config["api"])

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
                api,
                sd_run,
                enabled_prompts,
                config["positive"],
                config["negative"],
            )

if __name__ == "__main__":
    main()
