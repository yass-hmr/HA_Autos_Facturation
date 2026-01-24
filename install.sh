#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

sudo apt update
sudo apt install -y python3 python3-venv python3-pip

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "OK. Pour lancer : ./run.sh"
