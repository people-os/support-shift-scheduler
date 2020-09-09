import argparse
import json
import sys
from pathlib import Path
import jsonschema
import pandas as pd


# Input filenames:
filename_onboarding = "onboarding_agents.txt"
filename_mentors = "mentors.txt"
filename_new = "new_agents.txt"
input_folder = ""

def get_project_root() -> str:
    return str(Path(__file__).parent.parent)


def parse_json_input():
    """Read, validate and return json input."""
    # Production (read input from command line):
    global input_folder
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-i", "--input", help="Scheduler input JSON file path", required=True
    )
    args = parser.parse_args()
    input_filename = args.input.strip()

    # Testing (define input directly):
    # input_filename = 'support-shift-scheduler-input.json'

    # Load and validate JSON input:
    input_json = json.load(open(input_filename))
    input_json_schema = json.load(
        open(get_project_root() + "/lib/schemas/support-shift-scheduler-input.schema.json")
    )
    try:
        jsonschema.validate(input_json, input_json_schema)
    except jsonschema.exceptions.ValidationError as err:
        print("Input JSON validation error", err)
        sys.exit(1)

    input_folder = get_project_root() + '/logs/' + input_json["options"]["startMondayDate"] + '_' + input_json["options"]["modelName"] + '/'

    return input_json


def hours_to_range(week_hours, end_hour):
    """Convert per-hour availability flags into ranges format."""
    week_ranges = []

    for day_hours in week_hours:
        day_ranges = []
        start = None

        for i, value in enumerate(day_hours):
            # Start of new range:
            if start is None and value != 0:
                start = i
                continue

            # End of range:
            # (A range will end if either the current slot is unavailable
            # (value 0) or if the current slot is the last one.)
            if start is not None:
                if value == 0:  # Unavailable
                    day_ranges.append([start, i])
                    start = None
                elif i == end_hour - 1:  # Last slot
                    day_ranges.append([start, end_hour])
                else:
                    continue

        week_ranges.append(day_ranges)

    return week_ranges


def print_final_schedules(schedule_results, df_agents, num_days):
    """Print final schedule, validate output JSON, and write to file."""
    for d in range(num_days):
        print(
            f"\n{schedule_results[d]['start_date'].strftime('%Y-%m-%d')} "
            "shifts:"
        )

        for (i, e) in enumerate(schedule_results[d]["shifts"]):
            print(e)

    output_json = []

    for epoch in schedule_results:
        # Substitute agent info from 'handle' to 'handle <email>'
        shifts = []

        for (name, start, end) in epoch["shifts"]:
            shifts.append(
                {
                    "agent": f"{name} <{df_agents.loc[name, 'email']}>",
                    "start": start,
                    "end": end,
                }
            )

        day_dict = {"start_date": epoch["start_date"].strftime("%Y-%m-%d"), "shifts": shifts}
        output_json.append(day_dict)

    output_json_schema = json.load(
        open(get_project_root() + "/lib/schemas/support-shift-scheduler-output.schema.json")
        )

    try:
        jsonschema.validate(output_json, output_json_schema)
    except jsonschema.exceptions.ValidationError as err:
        print("Output JSON validation error", err)
        sys.exit(1)

    print("\nSuccessfully validated JSON output.")

    with open(input_folder + "support-shift-scheduler-output.json", "w") as outfile:
        outfile.write(json.dumps(output_json, indent=4))

    return output_json


def read_onboarding_files():
    """Read agent handles from onboarding-related files into pandas series."""

    if Path(input_folder + filename_onboarding).exists():
        ser_o = pd.read_csv(
            input_folder + filename_onboarding, squeeze=True, header=None, names=["agents"]
        )
    else:
        ser_o = pd.Series(data=None, name="agents", dtype="str")

    if Path(input_folder + filename_onboarding).exists():
        ser_m = pd.read_csv(
            input_folder + filename_mentors, squeeze=True, header=None, names=["agents"]
        )
    else:
        ser_m = pd.Series(data=None, name="agents", dtype="str")

    if Path(input_folder + filename_new).exists():
        ser_n = pd.read_csv(
            input_folder + filename_new, squeeze=True, header=None, names=["agents"]
        )
    else:
        ser_n = pd.Series(data=None, name="agents", dtype="str")

    return [ser_o, ser_m, ser_n]