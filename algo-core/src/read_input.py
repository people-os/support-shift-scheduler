"""
Copyright 2019-2022 Balena Ltd.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

   http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
import argparse
import sys
import json
import jsonschema
import pandas as pd
from pathlib import Path

# Input filenames:
filename_onboarding = "onboarding_agents.txt"
filename_mentors = "mentors.txt"


def get_project_root() -> Path:
    return Path(__file__).parent.parent.parent


def parse_json_input():
    """Read, validate and return json input."""
    # Get input file name:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-i", "--input", help="Scheduler input JSON file path", required=True
    )
    args = parser.parse_args()
    input_filename = args.input.strip()

    # Load and validate JSON input:
    input_json = json.load(open(input_filename))
    path_to_schema = Path(
        get_project_root() / "lib/schemas/",
        "support-shift-scheduler-input.schema.json",
    )
    input_json_schema = json.load(open(path_to_schema))
    try:
        jsonschema.validate(input_json, input_json_schema)
    except jsonschema.exceptions.ValidationError as err:
        print("Input JSON validation error", err)
        sys.exit(1)
    return input_json


def read_onboarding_files(input_folder):
    """Read agent handles from onboarding-related files into pandas series."""

    if (path := Path(input_folder, filename_onboarding)).exists():
        ser_o = pd.read_csv(path, squeeze=True, header=None, names=["agents"])
    else:
        ser_o = pd.Series(data=None, name="agents", dtype="str")

    if (path := Path(input_folder, filename_mentors)).exists():
        ser_m = pd.read_csv(path, squeeze=True, header=None, names=["agents"])
    else:
        ser_m = pd.Series(data=None, name="agents", dtype="str")
    return [ser_o, ser_m]


def read_input_files():
    input_json = parse_json_input()
    input_folder = (
        get_project_root()
        / "logs"
        / f'{input_json["options"]["startMondayDate"]}_{input_json["options"]["modelName"]}'
    )
    [sr_onboarding, sr_mentors] = read_onboarding_files(input_folder)
    return [input_json, sr_onboarding, sr_mentors]
