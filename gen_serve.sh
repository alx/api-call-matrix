#!/usr/bin/env sh

python3 ./gen_images.py
python3 ./gen_content.py
hugo server
