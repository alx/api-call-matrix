#!/usr/bin/env python3
import json
import os
import io
import itertools
import base64

import webuiapi
from webuiapi import b64_img, raw_b64_img

import PIL
from PIL import Image, PngImagePlugin

from flask import Flask, request, jsonify

app = Flask(__name__)

# Config data
config_filepath = 'config.json'

def process_interrogator(
        input_image
):
    config = load_config()
    api = load_api(config)
    use_async = False

    interrogator_config = config["api"]["interrogator"]
    interrogator_prompt = ""

    interrogator_params = {
        "image": b64_img(input_image),
        "clip_model_name": interrogator_config["clip_model_name"],
        "mode": interrogator_config["mode"]
    }

    interrogator_url = f'http://{interrogator_config["host"]}:{interrogator_config["port"]}/{interrogator_config["prompt_endpoint"]}'

    try:

        interrogator_response = api.post_and_get_api_result(
            interrogator_url,
            interrogator_params,
            use_async
        )

        # Check if an exception occured
        response_prompt = interrogator_response.json["prompt"]
        if "Exception" in response_prompt:
            raise RuntimeError

        else:

            # Get TOP results from prompt
            if "sliced_top_prompts" in interrogator_config:

                interrogator_prompt = ",".join(itertools.islice(
                    response_prompt.split(","),
                    interrogator_config["sliced_top_prompts"]
                ))

            else:

                interrogator_prompt = response_prompt

    except RuntimeError:
        print(f"❌ interrogator runtime error")

    return interrogator_prompt

def load_prompt_data(input_image):
    config = load_config()

    sd_run = [
        r for r in config["runs"]
        if r["enabled"]
    ][0]

    prompt = [
        p for p in config["prompts"]
        if p["enabled"]
    ][0]

    # populate prompt_data with sd_run
    prompt_data = sd_run["params"]
    prompt_data["prompt"] = ""
    prompt_data["negative_prompt"] = ""

    if "positive" in prompt:
        prompt_data["prompt"] = prompt["positive"]
    if "positive" in sd_run:
        prompt_data["prompt"] += sd_run["positive"]

    if "negative" in prompt:
        prompt_data["negative_prompt"] = prompt["negative"]
    if "negative" in sd_run:
        prompt_data["negative_prompt"] += sd_run["negative"]

    controlnet_units = []
    for control in prompt_data["alwayson_scripts"]["ControlNet"]["args"]:

        # replace placeholder in prompt_data controlnets
        if "image" in control:
            control["image"] = raw_b64_img(input_image)

        controlnet_units.append(control)

    prompt_data["controlnet_units"] = controlnet_units

    if "is_reactor" in sd_run \
        and sd_run["is_reactor"]:

        prompt_data["restore_faces"] = False

        # include ReActor extension parameters in prompt_data
        reactor = webuiapi.ReActor(
            img=input_image,
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

    if "interrogator" in config["api"]:

        interrogator_prompt = process_interrogator(input_image)

        prompt_data["prompt"] = ",".join([
            interrogator_prompt,
            prompt_data["prompt"]
        ])

    return prompt_data


def load_config():

    if not os.path.exists(config_filepath):
        raise OSError(f"❌ Config file not found: {config_filepath}")

    with open(config_filepath, 'r') as f:
        config = json.load(f)

    return config

def load_api(config):

    if "api" not in config:
        raise KeyError(f"❌ api not found in config file: {config_filepath}")

    if "a1111" not in config["api"]:
        raise KeyError(f"❌ a1111 not found in config file: {config_filepath}")

    return webuiapi.WebUIApi(**config["api"]["a1111"])

@app.route("/gen", methods=['POST'])
def gen_image():

    config = load_config()
    api = load_api(config)

    msg = base64.b64decode(request.json["image"])
    buf = io.BytesIO(msg)
    input_image = Image.open(buf)
    input_image.save("image.png")

    prompt_data = load_prompt_data(input_image)

    try:


        #####
        #
        #
        # a1111 api request
        #
        #
        #####
        response = api.post_and_get_api_result(
            f"{api.baseurl}/txt2img",
            prompt_data,
            False
        )
        print(response)

        return jsonify({
            "image": b64_img(response.images[0])
        })

    except RuntimeError:
        return 500

@app.route("/accept")
def publish_image():

    # get latest image
    # git add commit
    # git push
    # create url
    # return url
    return f"https://github.com/alx/onastick/public/{image}"
