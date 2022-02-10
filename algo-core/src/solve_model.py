"""
Copyright 2021 Balena Ltd.

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
from ortools.sat.python import cp_model
import json
from pathlib import Path
import jsonschema
import sys

from .custom_var_domains import define_custom_var_domains
from .veterans import setup_model_veterans, max_weekly_slots
from .onboarding import extend_model_onboarding
from .read_input import get_project_root

# Cost coefficients assigned to various soft constraints:
coefficients = {
    "non_preferred": 1,
    "shorter_than_pref": 1,
    "longer_than_pref": 1,
    "fair_share": 1,
    "overload_factor": 3,
}


# TODO: split the verification out to a separate python script, so
# that it can be run independently after possible manual changes to the output json.
def verify_solution(
    objective, sol_shifts, df_agents, agent_categories, config
):
    """Verify schedule against availability, and verify cost"""
    slot_cost = 0
    shift_length_cost = 0
    total_week_slots_cost = 0
    total_week_slots_by_veteran = {}
    # Verify that agents were only scheduled when they are available,
    for d in range(config["num_days"]):
        for shift in sol_shifts[d]["shifts"]:
            handle = shift["agentName"]
            ideal_length = df_agents.loc[handle, "ideal_shift_length"]
            shift_length = shift["end"] - shift["start"]

            if handle in agent_categories["veterans"]:
                # Find total slots per week cost per agent:
                if handle in total_week_slots_by_veteran.keys():
                    total_week_slots_by_veteran[handle] += shift_length
                else:
                    total_week_slots_by_veteran[handle] = shift_length
                # Find cost due to non-ideal shift lengths:
                shift_delta = shift_length - ideal_length
                if shift_delta > 0:
                    shift_length_cost += (
                        coefficients["longer_than_pref"] * shift_delta
                    )
                    print(
                        f"{handle} has a shift {shift_delta/2} hours longer than preferred."
                    )
                elif shift_delta < 0:
                    shift_length_cost += coefficients["shorter_than_pref"] * (
                        -shift_delta
                    )
                    print(
                        f"{handle} has a shift {-shift_delta/2} hours shorter than preferred."
                    )
            for slot in range(shift["start"], shift["end"]):
                slot_value = df_agents.loc[handle, "slots"][d][slot]
                if slot_value in config["allowed_availabilities"]:
                    slot_delta = slot_value - 1
                    slot_cost += slot_delta
                    if slot_delta == 1:
                        print(
                            f"30 minutes of non-preferred time was used for {handle}."
                        )
                    elif slot_delta == 2:
                        print(
                            f"30 minutes of 'ask-me-nicely' time was used for {handle}."
                        )
                else:
                    print(
                        f"ERROR: Agent {handle} was scheduled for slot {slot} on day {config['days'][d].strftime('%Y-%m-%d')}, but is not available!"
                    )
                    sys.exit(1)
    print("VERIFIED: Agents only scheduled when available.")
    slot_cost = coefficients["non_preferred"] * slot_cost

    for handle in total_week_slots_by_veteran.keys():
        if config["overload_protection"] and (
            df_agents.loc[handle, "fair_share"] == 0
            or total_week_slots_by_veteran[handle] > max_weekly_slots
        ):
            total_week_slots_cost += (
                coefficients["overload_factor"]
                * coefficients["fair_share"]
                * total_week_slots_by_veteran[handle]
            )
        else:
            total_week_slots_cost += coefficients["fair_share"] * (
                total_week_slots_by_veteran[handle]
                - df_agents.loc[handle, "fair_share"]
            )
    total_cost = total_week_slots_cost + shift_length_cost + slot_cost
    if total_cost == objective:
        print(f"VERIFIED: Minimized cost of {total_cost} is correct.")
    else:
        print(
            f"WARNING: The solver found a minimized cost of {objective}, while the calculated cost is {total_cost}!"
        )


def write_output_files(sol_shifts, sol_mentoring, config):
    # Write shifts:
    input_folder = (
        get_project_root()
        / "logs"
        / f'{config["start_date"].strftime("%Y-%m-%d")}_{config["model_name"]}'
    )

    with open(
        Path(input_folder, "support-shift-scheduler-output.json"), "w"
    ) as outfile:
        outfile.write(json.dumps(sol_shifts, indent=4))

    # Write mentoring:
    with open(Path(input_folder, "onboarding_pairings.json"), "w") as outfile:
        outfile.write(json.dumps(sol_mentoring, indent=4))


def run_solver(model, full_cost_list, config):
    model.Minimize(sum(full_cost_list))
    print(model.Validate())

    # Solve model:
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = config["optimization_timeout"]
    solver.parameters.log_search_progress = True
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)
    return [solver, status]


def extract_solution(
    solver, var_veterans, var_onboarding, df_agents, agent_categories, config
):
    # Extract solution:
    sol_shifts = []
    # TODO: Change agent, agentName to simply handle and email.

    sol_mentoring = []

    for d in range(config["num_days"]):
        # day_shifts = {"start_date": config["days"][d], "shifts": []}
        day_shifts = {
            "start_date": config["days"][d].strftime("%Y-%m-%d"),
            "shifts": [],
        }
        day_mentoring = {
            "start_date": config["days"][d].strftime("%Y-%m-%d"),
            "shifts": [],
        }

        # Fetch shifts for veterans:
        for t, track in enumerate(config["tracks"]):
            if d in range(track["start_day"], track["end_day"] + 1):
                for h in agent_categories["veterans"]:
                    if (
                        solver.Value(
                            var_veterans["tdh"].loc[
                                (t, d, h), "shift_duration"
                            ]
                        )
                        != 0
                    ):
                        day_shifts["shifts"].append(
                            {
                                "agent": f"{h} <{df_agents.loc[h, 'email']}>",
                                "agentName": h,
                                "start": solver.Value(
                                    var_veterans["tdh"].loc[
                                        (t, d, h), "shift_start"
                                    ]
                                ),
                                "end": solver.Value(
                                    var_veterans["tdh"].loc[
                                        (t, d, h), "shift_end"
                                    ]
                                ),
                            }
                        )
        # Fetch shifts for onboarders:
        for h in agent_categories["onboarding"]:
            if (
                solver.Value(
                    var_onboarding["dh"].loc[(d, h), "shift_duration"]
                )
                != 0
            ):
                day_shifts["shifts"].append(
                    {
                        "agent": f"{h} <{df_agents.loc[h, 'email']}>",
                        "agentName": h,
                        "start": solver.Value(
                            var_onboarding["dh"].loc[(d, h), "shift_start"]
                        ),
                        "end": solver.Value(
                            var_onboarding["dh"].loc[(d, h), "shift_end"]
                        ),
                    }
                )

            for m in var_onboarding["mentors"].columns:
                if solver.Value(var_onboarding["mentors"].loc[(d, h), m]) == 1:
                    day_mentoring["shifts"].append(
                        {"onboarder": h, "mentor": m}
                    )

        sol_shifts.append(day_shifts)
        sol_mentoring.append(day_mentoring)

    # Sort shifts by start times to improve output readability:
    for i in range(len(sol_shifts)):
        shifts = sol_shifts[i]["shifts"]
        sorted_shifts = sorted(shifts, key=lambda x: x["start"])
        sol_shifts[i]["shifts"] = sorted_shifts

    # Validate shifts:
    output_json_schema = json.load(
        open(
            Path(
                get_project_root() / "lib/schemas/",
                "support-shift-scheduler-output.schema.json",
            )
        )
    )

    try:
        jsonschema.validate(sol_shifts, output_json_schema)
    except jsonschema.exceptions.ValidationError as err:
        print("Output JSON validation error", err)
        sys.exit(1)

    print("\nSuccessfully validated JSON output.")
    return [sol_shifts, sol_mentoring]


def generate_solution(df_agents, agent_categories, config):
    # Define custom variable domains:
    custom_domains = define_custom_var_domains(coefficients, df_agents, config)
    # Initialize model:
    model = cp_model.CpModel()
    # Set up model for veterans:
    [model, var_veterans, full_cost_list] = setup_model_veterans(
        model,
        custom_domains,
        coefficients,
        df_agents,
        agent_categories,
        config,
    )
    # Extend model for onboarding if necessary:
    var_onboarding = None
    if len(agent_categories["onboarding"]) > 0:
        [
            model,
            var_veterans,
            var_onboarding,
            full_cost_list,
        ] = extend_model_onboarding(
            model,
            var_veterans,
            custom_domains,
            full_cost_list,
            coefficients,
            df_agents,
            agent_categories,
            config,
        )
    # Solve:
    [solver, status] = run_solver(model, full_cost_list, config)
    if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        # Extract solution:
        [sol_shifts, sol_mentoring] = extract_solution(
            solver,
            var_veterans,
            var_onboarding,
            df_agents,
            agent_categories,
            config,
        )
        # Verify solution:
        verify_solution(
            solver.ObjectiveValue(),
            sol_shifts,
            df_agents,
            agent_categories,
            config,
        )
        # Write output:
        write_output_files(sol_shifts, sol_mentoring, config)
