#!/usr/bin/env just --justfile

venv := "lulac/venv"
python := venv + "/bin/python3"

# TODO: make this work

[script("bash")]
lulac *args:
    if [ ! -d {{venv}} ]; then
        python3 -m venv {{venv}}
        {{python}} -m pip install --upgrade pip
        {{python}} -m pip install -r lulac/requirements.txt
    fi
    {{python}} -m lulac {{args}}