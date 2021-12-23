import json
import sys
from pathlib import Path
import jsonschema
import pandas as pd

from read_input import get_project_root

def print_final_schedules(schedule_results, df_agents, num_days, options):
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
                    "agentName": f"{name}",
                    "start": start,
                    "end": end,
                }
            )

        day_dict = {
            "start_date": epoch["start_date"].strftime("%Y-%m-%d"),
            "shifts": shifts,
        }
        output_json.append(day_dict)

    output_json_schema = json.load(
        open(
            Path(
                get_project_root() / "lib/schemas/",
                "support-shift-scheduler-output.schema.json",
            )
        )
    )

    try:
        jsonschema.validate(output_json, output_json_schema)
    except jsonschema.exceptions.ValidationError as err:
        print("Output JSON validation error", err)
        sys.exit(1)

    print("\nSuccessfully validated JSON output.")

    input_folder = (
        get_project_root()
        / "logs"
        / f'{options["startMondayDate"]}_{options["modelName"]}'
    )  # Here options refers to input_json["options"]

    with open(
        Path(input_folder, "support-shift-scheduler-output.json"), "w"
    ) as outfile:
        outfile.write(json.dumps(output_json, indent=4))

    return output_json