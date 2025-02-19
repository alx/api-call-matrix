#!/usr/bin/env python3
import json
import os
import itertools
import traceback
import datetime

import webuiapi
from webuiapi import b64_img, raw_b64_img

from PIL import Image
import exif

from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

import subprocess
import shutil

CONFIG_FILE = 'config.json'
UPLOAD_FOLDER = './uploads'
GALLERY_FOLDER = './gallery'
GIT_REPO_FOLDER = '.'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['GALLERY_FOLDER'] = GALLERY_FOLDER
app.config['GIT_REPO_FOLDER'] = GIT_REPO_FOLDER
app.config['CONFIG_FILE'] = CONFIG_FILE

def load_config():

    if not os.path.exists(app.config['CONFIG_FILE']):
        raise OSError(f"❌ Config file not found: {app.config['CONFIG_FILE']}")

    with open(app.config['CONFIG_FILE'], 'r') as f:
        config = json.load(f)

    return config

def load_api():

    config = load_config()

    if "api" not in config:
        raise KeyError(f"❌ api not found in config file")

    if "a1111" not in config["api"]:
        raise KeyError(f"❌ a1111 not found in config file")

    return webuiapi.WebUIApi(**config["api"]["a1111"])

config = load_config()
api = load_api()

def process_interrogator(
        input_image
):
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
        app.logger.error(f"❌ interrogator runtime error")

    return interrogator_prompt

def load_prompt_data(input_image, slug="", prompt_text="", width=1024, height=1024):

    sd_run = [
        r for r in config["runs"]
        if r["enabled"]
    ][0]

    available_prompts = [
        p for p in config["prompts"]
        if p["enabled"] and p["slug_id"] == slug
    ]
    if len(available_prompts) == 0:
        if len(prompt_text) > 0:
            prompt = {
                "slug_id": "forced_prompt",
                "positive": prompt_text
            }
        else:
            return None
    else:
        prompt = available_prompts[0]

    # populate prompt_data with sd_run
    prompt_data = sd_run["params"]
    prompt_data["prompt"] = ""
    prompt_data["negative_prompt"] = ""

    prompt_data["width"] = width
    prompt_data["height"] = height

    if "positive" in prompt:
        prompt_data["prompt"] = prompt["positive"]
    if "positive" in sd_run:
        prompt_data["prompt"] += sd_run["positive"]
    if "positive_prefix" in sd_run:
        prompt_data["prompt"] = sd_run["positive_prefix"] + prompt_data["prompt"]
    if "positive_suffix" in sd_run:
        prompt_data["prompt"] = prompt_data["prompt"] + sd_run["positive_suffix"]

    if "negative" in prompt:
        prompt_data["negative_prompt"] = prompt["negative"]
    if "negative" in sd_run:
        prompt_data["negative_prompt"] += sd_run["negative"]

    controlnet_units = []
    if "alwayson_scripts" in prompt_data:
        if "ControlNet" in prompt_data["alwayson_scripts"]:
            if "args" in prompt_data["alwayson_scripts"]["ControlNet"]:

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

    return prompt_data

def get_resized_image_file(input_image):

    input_filename = secure_filename(input_image.filename)
    input_filename = input_filename.replace(".jpg", datetime.datetime.now().strftime("_%Y-%m-%d_%H-%M-%S.jpg"))
    input_filepath = os.path.join(app.config['UPLOAD_FOLDER'], input_filename)
    input_image.save(input_filepath)

    resized_image = Image.open(input_filepath).convert("RGB")
    width, height = resized_image.size
    is_square = width == height
    is_landscape = width > height

    # Calculate target dimensions
    if is_square:
        target_width = 1024
        target_height = 1024
    else:
        if is_landscape:
            target_width = 1344
            target_height = 768
        else:
            target_width = 768
            target_height = 1344

    # Calculate aspect ratios
    aspect_ratio = width / height
    target_aspect_ratio = target_width / target_height

    # Resize image
    if aspect_ratio > target_aspect_ratio:
        new_height = target_height
        new_width = int(new_height * aspect_ratio)
    else:
        new_width = target_width
        new_height = int(new_width / aspect_ratio)

    resized_image = resized_image.resize((new_width, new_height), Image.LANCZOS)

    # Center crop
    left = (new_width - target_width) // 2
    top = (new_height - target_height) // 2
    right = left + target_width
    bottom = top + target_height
    resized_image = resized_image.crop((left, top, right, bottom))

    new_width = int(right - left)
    new_height = int(bottom - top)

    resized_filename = input_filename.replace(".jpg", "_resized.jpg")
    resized_filepath = os.path.join(app.config['UPLOAD_FOLDER'], resized_filename)
    resized_image.save(resized_filepath)

    return resized_image, input_filename, new_width, new_height

@app.route("/interrogate", methods=['POST'])
def interrogate_image():
    if 'image' not in request.files:
        return "Bad Request", 400
    input_image = request.files['image']
    resized_image, input_filename, width, height = get_resized_image_file(input_image)
    interrogator_prompt = process_interrogator(resized_image)
    return interrogator_prompt

@app.route("/gen", methods=['POST'])
def gen_image():

    if 'image' not in request.files:
        return "Bad Request", 400

    input_image = request.files['image']
    resized_image, input_filename, width, height = get_resized_image_file(input_image)

    if "prompt" in request.values:
        prompt_data = load_prompt_data(
            resized_image,
            slug=request.values["prompt"],
            width=width,
            height=height
        )

    if "prompt-text" in request.values:
        prompt_data = load_prompt_data(
            resized_image,
            prompt_text=request.values["prompt-text"],
            width=width,
            height=height
        )

    if prompt_data is None:
        return "Prompt slug not found", 404

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

        response_filename = input_filename.replace(".jpg", "_response.png")
        response_filepath = os.path.join(app.config['UPLOAD_FOLDER'], response_filename)
        response.images[0].save(response_filepath)

        # TODO save prompt inside exif data
        # with open(response_filepath, 'wb') as image_file:
        #     exif_image = exif.Image(image_file)
        #     exif_image["prompt"] = prompt_data["positive"]
        #     exif_image.write(exif_image.get_file())

        return send_from_directory(
            app.config['UPLOAD_FOLDER'],
            response_filename
        )

    # TODO print exception stacktrace
    except RuntimeError as e:
        traceback.print_exc()
        return "Internal Server Error", 500

@app.route("/prompts")
def prompts():
    return jsonify(config["prompts"])

@app.route("/keep")
def publish_image():

    # Add latest response file to git repo index
    latest_response_path = max(
        [
            os.path.join(app.config['UPLOAD_FOLDER'], f)
            for f in os.listdir(app.config['UPLOAD_FOLDER'])
            if f.endswith('_response.png')
        ]
        , key=os.path.getctime)
    filename = os.path.basename(latest_response_path)

    destination_path = os.path.join(app.config['GALLERY_FOLDER'], os.path.basename(latest_response_path))
    shutil.copy(latest_response_path, destination_path)

    try:
        subprocess.run(['git', 'add', destination_path], check=True)
        subprocess.run(['git', 'commit', '-m', "publish: add latest response"], check=True)
        subprocess.run(['git', 'push', 'origin'], check=True)
    except Exception as e:
        app.logger.error("error while keeping latest generated image inside git repository: %s", e)

    return f"https://raw.githubusercontent.com/alx/api-call-matrix/refs/heads/main/gallery/{filename}"
