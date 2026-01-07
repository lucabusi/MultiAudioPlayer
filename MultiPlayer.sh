#!/usr/bin/env bash
# Simple launcher script for the project
# Runs the Python launcher in the project root

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$DIR/MultiPlayer.py" "$@"
