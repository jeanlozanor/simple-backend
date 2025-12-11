#!/bin/bash
pip install --upgrade pip setuptools wheel
pip install --no-build-isolation -r requirements.txt
playwright install chromium

