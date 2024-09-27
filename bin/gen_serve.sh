#!/usr/bin/env sh

python3 ./bin/gen_images.py
python3 ./bin/gen_content.py
hugo server
