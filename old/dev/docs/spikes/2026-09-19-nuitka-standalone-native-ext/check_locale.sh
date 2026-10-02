#!/usr/bin/env bash
cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../../../.."
env -i HOME="$HOME" PATH="$PWD/.venv/bin:/usr/bin:/bin" .venv/bin/python -m uedcli --help
