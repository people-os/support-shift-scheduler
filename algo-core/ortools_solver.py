"""
Copyright 2020 Balena Ltd.

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
import collections
import datetime
import json
import math
import sys
from pathlib import Path

import colorama
import jsonschema
import pandas as pd
from ortools.sat.python import cp_model

# Cost weight assigned to various soft constraints:
coeff_non_preferred = 80
coeff_shorter_than_pref = 30
coeff_longer_than_pref = 70
coeff_total_week_hours = 3
coeff_agent = 30
coeff_handover = 30

# Onboarding:
onboarding_shift_length = 4
onboarding_weekly_hours = 8

# Other constants:
max_avg_per_week = 40
week_working_hours = 40
slots_in_day = 24
date_format = "%Y-%m-%d"

# Input filenames:
filename_onboarding = "onboarding_agents.txt"
filename_mentors = "mentors.txt"
filename_new = "new_agents.txt"


def hours_to_range(week_hours):
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


def setup_dataframes():
    """Set up dataframes for agents (df_a) and night shift info (df_n)."""
    global min_week_average_hours

    # Baseline for agent history:
    min_week_average_hours = 100

    # Initialize dataframes:
    df_a = pd.DataFrame(
        data=None,
        columns=[
            "handle",
            "email",
            "avg_hours_per_week",
            "pref_ideal_length",
            "hours",
            "hour_ranges",
        ],
    )

    df_n_indices = pd.MultiIndex.from_product(
        [[t for t in range(num_tracks)], [d for d in range(num_days)]],
        names=("track", "day"),
    )

    df_n = pd.DataFrame(
        data="", columns=list(range(19, 24)), index=df_n_indices
    )

    # Fill dataframes per agent:
    agents = input_json["agents"]
    agents_with_fix_hours = scheduler_options["specialAgentConditions"]["agentsWithFixHours"]

    for agent in agents:
        week_average_hours = math.trunc(float(agent["weekAverageHours"]))
        min_week_average_hours = min(
            min_week_average_hours, week_average_hours
        )

        week_hours = agent["availableHours"]

        for (d, _) in enumerate(week_hours):
            # Set availability to 0 outside balena support hours:
            for i in range(start_hour):
                week_hours[d][i] = 0
            for i in range(end_hour, slots_in_day):
                week_hours[d][i] = 0

            # Fill df_n dataframe with night shifts:
            # (Night shifts encoded as 4 in Team Model)
            indices_4 = [i for i, x in enumerate(week_hours[d]) if x == 4]

            # If agent has a night shift today, check into which track
            # it can slot, and fill df_n accordingly:
            if len(indices_4) > 0:
                track_found = False
                t = 0

                while t <= num_tracks - 1 and not track_found:
                    track_found = True
                    for s in indices_4:
                        track_found = track_found and df_n.loc[(t, d), s] == ""

                    if track_found:
                        for s in indices_4:
                            df_n.loc[(t, d), s] = agent["handle"]
                    else:
                        t += 1

                if not track_found:
                    print(
                        f"{colorama.Fore.RED}\nWARNING! The night shift "
                        f"for {agent['handle']} could not be fitted in."
                        f"{colorama.Style.RESET_ALL}"
                    )

                # For Agents with fix hours, remove all availability except night shifts:
                if agent['handle'] in agents_with_fix_hours:
                    for h in range(0, slots_in_day):
                        if week_hours[d][h] == 1 or week_hours[d][h] == 2:
                            week_hours[d][h] = 0

                # Reset all 1s and 4s to 2s in night shift agent's preferences:
                # This will also disincentivise algorithm from giving night
                # shift volunteers other shifts during the week as well.
                for h in range(0, slots_in_day):
                    if week_hours[d][h] == 1 or week_hours[d][h] == 4:
                        week_hours[d][h] = 2

                # Give agent a break until 15:00 the next day if he/she was
                # on night shift:
                if d != 4:
                    week_hours[d + 1][0:14] = [0 for i in range(14)]

        hour_ranges = hours_to_range(week_hours)

        df_a.loc[len(df_a)] = {
            "handle": agent["handle"],
            "email": agent["email"],
            "avg_hours_per_week": week_average_hours,
            "pref_ideal_length": agent["idealShiftLength"],
            "hours": week_hours,
            "hour_ranges": hour_ranges,
        }

    # hours: list of 5 lists, each of which has 24 items that mark the
    # availability of each hour (e.g.
    # [ [0,0,0,0,...,1,2,0,0], [0,0,0,0,...,1,2,0,0], [...], [...], [...] ])

    # hour_ranges: list of 5 lists, each of the 5 lists has a number
    # of nested lists that mark the ranges that an agent is available to do
    # support (e.g. [ [[8,12], [16, 24]], [], [...], [...], [...])
    # NB: e.g. [8,12] indicates agent is available 8-12, NOT 8-13.

    df_a.set_index("handle", inplace=True)
    return [df_a, df_n]


def read_onboarding_files():
    """Read agent handles from onboarding-related files into pandas series."""
    if Path(filename_onboarding).exists():
        ser_o = pd.read_csv(
            filename_onboarding, squeeze=True, header=None, names=["agents"]
        )
    else:
        ser_o = pd.Series(data=None, name="agents", dtype="str")

    if Path(filename_onboarding).exists():
        ser_m = pd.read_csv(
            filename_mentors, squeeze=True, header=None, names=["agents"]
        )
    else:
        ser_m = pd.Series(data=None, name="agents", dtype="str")

    if Path(filename_new).exists():
        ser_n = pd.read_csv(
            filename_new, squeeze=True, header=None, names=["agents"]
        )
    else:
        ser_n = pd.Series(data=None, name="agents", dtype="str")

    return [ser_o, ser_m, ser_n]


def get_unavailable_agents(day):
    """Determine agents with no availability for a given day."""
    day_number = day.weekday()
    unavailable = set()

    for handle in df_agents.index:
        if len(df_agents.loc[handle, "hour_ranges"][day_number]) == 0:
            unavailable.add(handle)

    print(f"\nUnavailable employees on {day}")
    [print(e) for e in unavailable]

    return unavailable


def remove_agents_not_available_this_week():
    """Agents not available at all this week are removed from the model."""
    print("")

    original_handles = df_agents.index.tolist()

    for handle in original_handles:
        out = True

        for d in range(num_days):
            out = out and (handle in unavailable_agents[d])

        if out:
            df_agents.drop(index=handle, inplace=True)
            print(handle, "was removed for this week.")

    return df_agents


def print_final_schedules(schedule_results):
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

        day_dict = {}
        day_dict["start_date"] = epoch["start_date"].strftime("%Y-%m-%d")
        day_dict["shifts"] = shifts
        output_json.append(day_dict)

    # JSON output format
    # {
    #   "start_date": YYYY-MM-DD # date is in YYYY-MM-DD format
    #   "shifts": [{
    #       "@agentHandle <agentEmail>": [ startHour, endHour ],
    #       '...'
    #   }]
    # }

    output_json_schema = json.load(
        open("../../lib/schemas/support-shift-scheduler-output.schema.json")
    )

    try:
        jsonschema.validate(output_json, output_json_schema)
    except jsonschema.exceptions.ValidationError as err:
        print("Output JSON validation error", err)
        sys.exit(1)

    print("\nSuccessfully validated JSON output.")

    with open("support-shift-scheduler-output.json", "w") as outfile:
        outfile.write(json.dumps(output_json, indent=4))

    return output_json


def flatten(l):
    """Flatten nested lists."""
    for el in l:
        if isinstance(el, collections.Iterable) and not isinstance(
            el, (str, bytes)
        ):
            yield from flatten(el)
        else:
            yield el


def parse_json_input():
    """Read, validate and return json input."""
    # Production (read input from command line):
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
        open("../../lib/schemas/support-shift-scheduler-input.schema.json")
    )
    try:
        jsonschema.validate(input_json, input_json_schema)
    except jsonschema.exceptions.ValidationError as err:
        print("Input JSON validation error", err)
        sys.exit(1)

    return input_json


def setup_var_dataframes_veterans():
    """Create dataframes that will contain model variables for veterans."""
    global v_h, v_td, v_tdh, v_tdsh

    # h - veterans:
    v_h = pd.DataFrame(
        data=None,
        index=agents_vet,
        columns=[
            "total_week_hours",
            "total_week_hours_squared",
            "total_week_hours_cost",
        ],
    )

    # td - veterans:
    td_multi_index = pd.MultiIndex.from_product(
        [[t for t in range(num_tracks)], [d for d in range(num_days)]],
        names=("track", "day"),
    )

    v_td = pd.DataFrame(
        data=None, index=td_multi_index, columns=["handover_cost"]
    )

    # tdh - veterans (with extra Monday track):
    tdh_multi_index = pd.MultiIndex.from_product(
        [
            [t for t in range(num_tracks + 1)],  # extra Monday track
            [d for d in range(num_days)],
            [h for h in agents_vet],
        ],
        names=("track", "day", "handle"),
    )[
        : -(num_days - 1) * len(agents_vet)
    ]  # Slicing removes extra track's Tuesday-Friday.

    v_tdh = pd.DataFrame(
        data=None,
        index=tdh_multi_index,
        columns=[
            "shift_start",
            "shift_end",
            "shift_duration",
            "interval",
            "is_agent_on",
            "agent_cost",
            "is_duration_shorter_than_ideal",
            "duration_cost",
            "is_in_pref_range",
        ],
    )

    # tdsh - veterans (with extra Monday track):
    tdsh_multi_index = pd.MultiIndex.from_product(
        [
            [t for t in range(num_tracks + 1)],  # extra Monday track
            [d for d in range(num_days)],
            [s for s in range(start_hour, end_hour)],
            [h for h in agents_vet],
        ],
        names=("track", "day", "slot", "handle"),
    )[: -(num_days - 1) * work_hours * len(agents_vet) - 12 * len(agents_vet)]
    # (Slicing removes extra track's Tue-Fri, as well as 12-midnight on Mon.)

    v_tdsh = pd.DataFrame(
        data=None,
        index=tdsh_multi_index,
        columns=[
            "is_start_smaller_equal_hour",
            "is_end_greater_than_hour",
            "is_hour_cost",
            "hour_cost",
        ],
    )


def setup_var_dataframes_onboarding():
    """Create dataframes that will contain model variables for onboarders."""
    global v_mentors, v_h_on, v_dh_on, v_dhs_on

    # v_mentors dataframe will contain onboarding agent - mentor associations:
    mentors_indices = pd.MultiIndex.from_product(
        [[d for d in range(num_days)], agents_onb], names=("day", "agent")
    )

    v_mentors = pd.DataFrame(
        data=None, index=mentors_indices, columns=agents_mentors
    )

    # h - onboarding:
    v_h_on = pd.DataFrame(
        data=None, index=agents_onb, columns=["total_week_hours"]
    )

    # dh - onboarding:
    dh_multi_index_on = pd.MultiIndex.from_product(
        [[d for d in range(num_days)], [h for h in agents_onb]],
        names=("day", "handle"),
    )

    v_dh_on = pd.DataFrame(
        data=None,
        index=dh_multi_index_on,
        columns=[
            "shift_start",
            "shift_end",
            "shift_duration",
            "interval",
            "is_agent_on",
            "is_in_pref_range",
        ],
    )

    # dhs - onboarding:
    dhs_multi_index_on = pd.MultiIndex.from_product(
        [
            [d for d in range(num_days)],
            [h for h in agents_onb],
            [s for s in range(start_hour, end_hour)],
        ],
        names=("day", "handle", "slot"),
    )

    v_dhs_on = pd.DataFrame(
        data=None,
        index=dhs_multi_index_on,
        columns=[
            "is_start_smaller_equal_hour",
            "is_end_greater_than_hour",
            "is_hour_cost",
            "hour_cost",
        ],
    )


def fill_var_dataframes_veterans():
    """Fill veteran variable dataframes with OR-Tools model variables."""
    # h - veterans:
    for h in v_h.index:
        v_h.loc[h, "total_week_hours"] = model.NewIntVar(
            0, week_working_hours, f"total_week_hours_{h}"
        )

        v_h.loc[h, "total_week_hours_squared"] = model.NewIntVarFromDomain(
            cp_model.Domain.FromValues(
                [x ** 2 for x in range(0, week_working_hours + 1)]
            ),
            f"total_week_hours_squared_{h}",
        )

        v_h.loc[h, "total_week_hours_cost"] = model.NewIntVarFromDomain(
            cp_model.Domain.FromValues(
                [
                    coeff_total_week_hours * x ** 2
                    for x in range(0, week_working_hours + 1)
                ]
            ),
            f"total_week_hours_cost_{h}",
        )

    # td - veterans:
    for t in range(num_tracks):
        for d in range(num_days):
            v_td.loc[(t, d), "handover_cost"] = model.NewIntVarFromDomain(
                cp_model.Domain.FromValues(
                    [
                        coeff_handover * x
                        for x in range(0, max_daily_handovers + 1)
                    ]
                ),
                f"handover_cost_{t}_{d}",
            )

    # tdh - veterans (with extra Monday track):
    print("")

    for t in range(num_tracks + 1):
        if t == num_tracks:
            max_days = 1
        else:
            max_days = num_days

        for d in range(max_days):
            for h in agents_vet:
                if h in unavailable_agents[d]:
                    v_tdh.loc[(t, d, h), "shift_start"] = model.NewIntVar(
                        8, 8, f"shift_start_{t}_{d}_{h}"
                    )
                    v_tdh.loc[(t, d, h), "shift_end"] = model.NewIntVar(
                        8, 8, f"shift_end_{t}_{d}_{h}"
                    )
                    v_tdh.loc[(t, d, h), "shift_duration"] = model.NewIntVar(
                        0, 0, f"shift_duration_{t}_{d}_{h}"
                    )
                else:
                    if t == num_tracks:
                        v_tdh.loc[
                            (t, d, h), "shift_start"
                        ] = model.NewIntVarFromDomain(
                            d_prefs.loc[(d, h)], f"shift_start_{t}_{d}_{h}"
                        )
                        v_tdh.loc[
                            (t, d, h), "shift_end"
                        ] = model.NewIntVarFromDomain(
                            d_prefs.loc[(d, h)], f"shift_end_{t}_{d}_{h}"
                        )
                        # Extra Monday track always from 8-12 (4 hours):
                        v_tdh.loc[
                            (t, d, h), "shift_duration"
                        ] = model.NewIntVarFromDomain(
                            cp_model.Domain.FromValues([0, 4]),
                            f"shift_duration_{t}_{d}_{h}",
                        )
                    else:
                        when_on_night_shift = [
                            19 + i
                            for i, x in enumerate(
                                df_nights.loc[(t, d)].to_list()
                            )
                            if x == h
                        ]

                        if len(when_on_night_shift) > 0:
                            start = when_on_night_shift[0]
                            end = when_on_night_shift[-1] + 1
                            duration = end - start

                            v_tdh.loc[
                                (t, d, h), "shift_start"
                            ] = model.NewIntVar(
                                start, start, f"shift_start_{t}_{d}_{h}"
                            )

                            v_tdh.loc[
                                (t, d, h), "shift_end"
                            ] = model.NewIntVar(
                                end, end, f"shift_end_{t}_{d}_{h}"
                            )

                            v_tdh.loc[
                                (t, d, h), "shift_duration"
                            ] = model.NewIntVar(
                                duration,
                                duration,
                                f"shift_duration_{t}_{d}_{h}",
                            )
                            print(f"{h} on duty on night of {days[d]}")

                        else:
                            v_tdh.loc[
                                (t, d, h), "shift_start"
                            ] = model.NewIntVarFromDomain(
                                d_prefs.loc[(d, h)], f"shift_start_{t}_{d}_{h}"
                            )
                            v_tdh.loc[
                                (t, d, h), "shift_end"
                            ] = model.NewIntVarFromDomain(
                                d_prefs.loc[(d, h)], f"shift_end_{t}_{d}_{h}"
                            )
                            v_tdh.loc[
                                (t, d, h), "shift_duration"
                            ] = model.NewIntVarFromDomain(
                                d_duration, f"shift_duration_{t}_{d}_{h}"
                            )

                v_tdh.loc[(t, d, h), "interval"] = model.NewIntervalVar(
                    v_tdh.loc[(t, d, h), "shift_start"],
                    v_tdh.loc[(t, d, h), "shift_duration"],
                    v_tdh.loc[(t, d, h), "shift_end"],
                    f"interval_{t}_{d}_{h}",
                )

                v_tdh.loc[(t, d, h), "is_agent_on"] = model.NewBoolVar(
                    f"is_agent_on_{t}_{d}_{h}"
                )

                v_tdh.loc[(t, d, h), "agent_cost"] = model.NewIntVarFromDomain(
                    cp_model.Domain.FromValues(
                        [coeff_agent * x for x in range(0, max_avg_per_week)]
                    ),
                    f"agent_cost_{t}_{d}_{h}",
                )

                v_tdh.loc[
                    (t, d, h), "is_duration_shorter_than_ideal"
                ] = model.NewBoolVar(
                    f"is_duration_shorter_than_ideal_{t}_{d}_{h}"
                )

                duration_cost_list = set(
                    [
                        coeff_shorter_than_pref * x
                        for x in range(0, max_duration - min_duration)
                    ]
                )
                duration_cost_list = list(
                    duration_cost_list.union(
                        set(
                            [
                                coeff_longer_than_pref * x
                                for x in range(0, max_duration - min_duration)
                            ]
                        )
                    )
                )
                duration_cost_list.sort()

                v_tdh.loc[
                    (t, d, h), "duration_cost"
                ] = model.NewIntVarFromDomain(
                    cp_model.Domain.FromValues(duration_cost_list),
                    f"duration_cost_{t}_{d}_{h}",
                )

                v_tdh.loc[(t, d, h), "is_in_pref_range"] = [
                    model.NewBoolVar(f"is_in_pref_range_{t}_{d}_{h}_{j}")
                    for (j, sec) in enumerate(
                        df_agents.loc[h, "hour_ranges"][d]
                    )
                ]

    # tdsh - veterans (with extra Monday track):
    for t in range(num_tracks + 1):
        if t == num_tracks:
            max_days = 1
            max_hour = 12
        else:
            max_days = num_days
            max_hour = end_hour

        for d in range(max_days):
            for s in range(start_hour, max_hour):
                for h in agents_vet:
                    v_tdsh.loc[
                        (t, d, s, h), "is_start_smaller_equal_hour"
                    ] = model.NewBoolVar(
                        f"is_start_smaller_equal_hour_{t}_{d}_{s}_{h}"
                    )

                    v_tdsh.loc[
                        (t, d, s, h), "is_end_greater_than_hour"
                    ] = model.NewBoolVar(
                        f"is_end_greater_than_hour_{t}_{d}_{s}_{h}"
                    )

                    v_tdsh.loc[
                        (t, d, s, h), "is_hour_cost"
                    ] = model.NewBoolVar(f"is_hour_cost_{t}_{d}_{s}_{h}")

                    v_tdsh.loc[
                        (t, d, s, h), "hour_cost"
                    ] = model.NewIntVarFromDomain(
                        d_hour_cost, f"hour_cost_{t}_{d}_{s}_{h}"
                    )


def fill_var_dataframes_onboarding():
    """Fill onboarding variable dataframes with OR-Tools model variables."""
    # Onboarding mentors:
    for d in range(num_days):
        for h in agents_onb:
            for m in agents_mentors:
                v_mentors.loc[(d, h), m] = model.NewBoolVar(
                    f"mentor_{d}_{h}_{m}"
                )

    # h - onboarding:
    for h in v_h_on.index:
        v_h_on.loc[h, "total_week_hours"] = model.NewIntVar(
            0, week_working_hours, f"total_week_hours_{h}"
        )

    # dh - onboarding:
    print("")

    for d in range(num_days):
        for h in agents_onb:
            if h in unavailable_agents[d]:
                v_dh_on.loc[(d, h), "shift_start"] = model.NewIntVar(
                    8, 8, f"shift_start_{d}_{h}"
                )
                v_dh_on.loc[(d, h), "shift_end"] = model.NewIntVar(
                    8, 8, f"shift_end_{d}_{h}"
                )
                v_dh_on.loc[(d, h), "shift_duration"] = model.NewIntVar(
                    0, 0, f"shift_duration_{d}_{h}"
                )

            else:
                v_dh_on.loc[(d, h), "shift_start"] = model.NewIntVarFromDomain(
                    d_prefs.loc[(d, h)], f"shift_start_{d}_{h}"
                )
                v_dh_on.loc[(d, h), "shift_end"] = model.NewIntVarFromDomain(
                    d_prefs.loc[(d, h)], f"shift_end_{d}_{h}"
                )
                v_dh_on.loc[
                    (d, h), "shift_duration"
                ] = model.NewIntVarFromDomain(
                    cp_model.Domain.FromValues([0, onboarding_shift_length]),
                    f"shift_duration_{d}_{h}",
                )

            v_dh_on.loc[(d, h), "interval"] = model.NewIntervalVar(
                v_dh_on.loc[(d, h), "shift_start"],
                v_dh_on.loc[(d, h), "shift_duration"],
                v_dh_on.loc[(d, h), "shift_end"],
                f"interval_{d}_{h}",
            )

            v_dh_on.loc[(d, h), "is_agent_on"] = model.NewBoolVar(
                f"is_agent_on_{d}_{h}"
            )

            v_dh_on.loc[(d, h), "is_in_pref_range"] = [
                model.NewBoolVar(f"is_in_pref_range_{d}_{h}_{j}")
                for (j, sec) in enumerate(df_agents.loc[h, "hour_ranges"][d])
            ]

    # dhs - onboarding:
    for d in range(num_days):
        for h in agents_onb:
            for s in range(start_hour, end_hour):
                v_dhs_on.loc[
                    (d, h, s), "is_start_smaller_equal_hour"
                ] = model.NewBoolVar(
                    f"is_start_smaller_equal_hour_{d}_{h}_{s}"
                )

                v_dhs_on.loc[
                    (d, h, s), "is_end_greater_than_hour"
                ] = model.NewBoolVar(f"is_end_greater_than_hour_{d}_{h}_{s}")

                v_dhs_on.loc[(d, h, s), "is_hour_cost"] = model.NewBoolVar(
                    f"is_hour_cost_{d}_{h}_{s}"
                )

                v_dhs_on.loc[
                    (d, h, s), "hour_cost"
                ] = model.NewIntVarFromDomain(
                    d_hour_cost, f"hour_cost_{d}_{h}_{s}"
                )


def define_custom_var_domains():
    """Define custom model variable domains."""
    global d_hour_cost, d_duration, d_prefs
    # Hour cost domain:
    d_hour_cost = cp_model.Domain.FromValues([0, coeff_non_preferred])

    # Duration domain:
    d_duration = cp_model.Domain.FromIntervals(
        [[0, 0], [min_duration, max_duration]]
    )

    # Create preference domains:
    dh_multi_index = pd.MultiIndex.from_product(
        [[d for d in range(num_days)], [h for h in df_agents.index]],
        names=("day", "handle"),
    )

    d_prefs = pd.Series(data=None, index=dh_multi_index, dtype="float64")

    for d in range(num_days):
        for h in df_agents.index:
            d_prefs.loc[(d, h)] = cp_model.Domain.FromIntervals(
                df_agents.loc[h, "hour_ranges"][d]
            )


def constraint_new_agents_non_simultaneous():
    """Recently onboarded agents should not be scheduled simultaneously."""
    for d in range(num_days):
        for h1 in agents_new:
            for h2 in agents_new:
                if h1 != h2:
                    model.AddNoOverlap(
                        [
                            v_tdh.loc[(0, d, h1), "interval"],
                            v_tdh.loc[(1, d, h2), "interval"],
                        ]
                    )
                    if d == 0:  # Then there is an extra Monday track.
                        model.AddNoOverlap(
                            [
                                v_tdh.loc[(0, d, h1), "interval"],
                                v_tdh.loc[(2, d, h2), "interval"],
                            ]
                        )
                        model.AddNoOverlap(
                            [
                                v_tdh.loc[(1, d, h1), "interval"],
                                v_tdh.loc[(2, d, h2), "interval"],
                            ]
                        )


def constraint_cover_num_tracks_without_overlapping():
    """Shifts in each track must cover required hours, without overlapping."""
    # Sum of agents' shifts must equal work_hours:
    for t in range(num_tracks):  # N/A to extra Monday track.
        for d in range(num_days):
            model.Add(
                sum(v_tdh.loc[(t, d), "shift_duration"].values.tolist())
                == work_hours
            )

    # Agents' shifts must not overlap with each other:
    for t in range(num_tracks):  # N/A to extra Monday track.
        for d in range(num_days):
            model.AddNoOverlap(v_tdh.loc[(t, d), "interval"].values.tolist())


def constraint_configure_extra_Monday_track():
    """Define the additional track running on Mondays 8-12."""
    # Sum of all shifts in this track must equal 4 hours
    # (i.e.) single shift of 4 hours:
    model.Add(
        sum(v_tdh.loc[(num_tracks, 0), "shift_duration"].values.tolist()) == 4
    )

    # This shift starts at 8 and ends at 12:
    for h in agents_vet:
        model.Add(
            v_tdh.loc[(num_tracks, 0, h), "shift_start"] == 8
        ).OnlyEnforceIf(v_tdh.loc[(num_tracks, 0, h), "is_agent_on"])
        model.Add(
            v_tdh.loc[(num_tracks, 0, h), "shift_end"] == 12
        ).OnlyEnforceIf(v_tdh.loc[(num_tracks, 0, h), "is_agent_on"])


def constraint_honour_agent_availability_veterans():
    """Make sure that each veteran's availability is honoured.

    Each shift must start and end within that agent's available hours.
    """
    # Note: AddBoolOr works with just one boolean as well, in which case that
    # boolean has to be true.
    for t in range(num_tracks + 1):  # Applies to extra Monday track as well.
        if t == num_tracks:
            max_days = 1
        else:
            max_days = num_days

        for d in range(max_days):
            for h in agents_vet:
                if not (h in unavailable_agents[d]):
                    model.AddBoolOr(v_tdh.loc[(t, d, h), "is_in_pref_range"])

                    for (j, sec) in enumerate(
                        df_agents.loc[h, "hour_ranges"][d]
                    ):

                        model.Add(
                            v_tdh.loc[(t, d, h), "shift_start"] >= sec[0]
                        ).OnlyEnforceIf(
                            v_tdh.loc[(t, d, h), "is_in_pref_range"][j]
                        )
                        model.Add(
                            v_tdh.loc[(t, d, h), "shift_start"]
                            + v_tdh.loc[(t, d, h), "shift_duration"]
                            <= sec[1]
                        ).OnlyEnforceIf(
                            v_tdh.loc[(t, d, h), "is_in_pref_range"][j]
                        )


def constraint_avoid_assigning_agent_multiple_tracks_per_day():
    """Ensure each veteran is scheduled in at most 1 track per day."""
    for d in range(num_days):
        for h in agents_vet:
            is_agent_on_list = []

            if d == 0:  # Applies to extra Monday track as well.
                max_tracks = num_tracks + 1
            else:
                max_tracks = num_tracks

            for t in range(max_tracks):
                is_agent_on_list.append(v_tdh.loc[(t, d, h), "is_agent_on"])

            model.Add(sum(is_agent_on_list) <= 1)


def constraint_honour_agent_availability_onboarding():
    """Make sure that each onboarder's availability is honoured.

    Each shift must start and end within that agent's available hours.
    """
    for d in range(num_days):
        for h in agents_onb:
            if not (h in unavailable_agents[d]):
                model.AddBoolOr(v_dh_on.loc[(d, h), "is_in_pref_range"])

                for (j, sec) in enumerate(df_agents.loc[h, "hour_ranges"][d]):

                    model.Add(
                        v_dh_on.loc[(d, h), "shift_start"] >= sec[0]
                    ).OnlyEnforceIf(v_dh_on.loc[(d, h), "is_in_pref_range"][j])
                    model.Add(
                        v_dh_on.loc[(d, h), "shift_start"]
                        + v_dh_on.loc[(d, h), "shift_duration"]
                        <= sec[1]
                    ).OnlyEnforceIf(v_dh_on.loc[(d, h), "is_in_pref_range"][j])


def constraint_various_custom_conditions():
    """Define custom constraints (usually temporary) as needed."""

    agents_with_max_shift_hours = scheduler_options["specialAgentConditions"]["agentsWithMaxHoursShift"]
    agents_with_min_week_hours = scheduler_options["specialAgentConditions"]["agentsWithMinHoursWeek"]

    for agent in agents_with_max_shift_hours:
        handle = agent["handle"]
        hours = int(agent["value"])
        for t in range(num_tracks):
            for d in range(num_days):
                if not (handle in unavailable_agents[d]):
                    model.Add(v_tdh.loc[(t, d, handle), "shift_duration"] <= hours)

    for agent in agents_with_max_shift_hours:
        handle = agent["handle"]
        hours = int(agent["value"])
        if handle in df_agents.index:
            hugh_daily_quota = hours / 5  # hours per week converted to per day
            hugh_weekly_lower_limit = 0

            for d in range(num_days):
                if not (handle in unavailable_agents[d]):
                    hugh_weekly_lower_limit += hugh_daily_quota

            hugh_weekly_lower_limit = round(hugh_weekly_lower_limit)

            model.Add(
                v_h.loc[handle, "total_week_hours"]
                >= hugh_weekly_lower_limit
            )


def constraint_setup_onboarding_hours():
    """Define shift length for onboarders, as well as total weekly support."""
    # If agent is on, the shift length must be <onboarding_shift_length> hours:
    for d in range(num_days):
        for h in agents_onb:
            model.Add(
                v_dh_on.loc[(d, h), "shift_duration"]
                == onboarding_shift_length
            ).OnlyEnforceIf(v_dh_on.loc[(d, h), "is_agent_on"])
            model.Add(
                v_dh_on.loc[(d, h), "shift_duration"] == 0
            ).OnlyEnforceIf(v_dh_on.loc[(d, h), "is_agent_on"].Not())

    # Agent is only scheduled for <onboarding_weekly_hours> hours for the week:
    for h in agents_onb:
        model.Add(
            v_h_on.loc[h, "total_week_hours"]
            == sum(
                v_dh_on["shift_duration"]
                .xs(h, axis=0, level=1, drop_level=False)
                .values.tolist()
            )
        )
        model.Add(v_h_on.loc[h, "total_week_hours"] == onboarding_weekly_hours)


def constraint_avoid_onboarding_before_Monday_1400():
    """Avoid onboarding on Mondays (d=0) before 14:00.

    This is to allow the Monday morning veterans to focus on clearing
    up the tickets that have piled up over the weekend.
    """
    # Constraint: There will be no onboarding on Mondays (d=0) before 14:00:
    for h in agents_onb:
        model.Add(v_dh_on.loc[(0, h), "shift_start"] >= 14).OnlyEnforceIf(
            v_dh_on.loc[(0, h), "is_agent_on"]
        )


def constraint_avoid_simultaneous_onboarding():
    """At most one agent should be onboarded at any given time.

    In other words, onboarding shifts should not overlap.
    """
    if len(v_dh_on) > 0:
        for d in range(num_days):
            model.AddNoOverlap(v_dh_on.loc[d, "interval"].values.tolist())


def constraint_configure_mentoring():
    """Configure the mentoring of onboarders appropriately."""
    # If agent is on, he/she to be paired with exactly 1 mentor:
    for d in range(num_days):
        for h in agents_onb:
            model.Add(
                sum(v_mentors.loc[(d, h)].values.tolist()) == 1
            ).OnlyEnforceIf(v_dh_on.loc[(d, h), "is_agent_on"])
            model.Add(
                sum(v_mentors.loc[(d, h)].values.tolist()) == 0
            ).OnlyEnforceIf(v_dh_on.loc[(d, h), "is_agent_on"].Not())

            for m in v_mentors.columns:
                is_mentor_on_list = []

                for t in range(num_tracks):
                    is_mentor_on_list.append(
                        v_tdh.loc[(t, d, m), "is_agent_on"]
                    )

                model.AddBoolOr(is_mentor_on_list).OnlyEnforceIf(
                    v_mentors.loc[(d, h), m]
                )

                for t in range(num_tracks):
                    # The mentor and onboarder start at the same time.
                    model.Add(
                        v_dh_on.loc[(d, h), "shift_start"]
                        == v_tdh.loc[(t, d, m), "shift_start"]
                    ).OnlyEnforceIf(
                        [
                            v_mentors.loc[(d, h), m],
                            v_tdh.loc[(t, d, m), "is_agent_on"],
                        ]
                    )

                    # Mentor's shift may not be shorter than onboarder's:
                    model.Add(
                        v_dh_on.loc[(d, h), "shift_duration"]
                        - v_tdh.loc[(t, d, m), "shift_duration"]
                        <= 0
                    ).OnlyEnforceIf(
                        [
                            v_mentors.loc[(d, h), m],
                            v_tdh.loc[(t, d, m), "is_agent_on"],
                        ]
                    )

    # A mentor should not have to mentor more than 1 onboarder per day:
    for d in range(num_days):
        for m in v_mentors.columns:
            model.Add(sum(v_mentors.loc[(d,), m].values.tolist()) < 2)

    # To avoid overloading mentors, constrain weekly hours to <= 10 hours:
    #    for h in agents_mentors:
    #        model.Add(v_h.loc[h, "total_week_hours"] <= 10)


def cost_total_agent_hours_for_week():
    """Define cost associated with total weekly hours per veteran."""
    v_coeff_tot_wk_hrs = model.NewIntVar(
        coeff_total_week_hours, coeff_total_week_hours, "coeff_tot_wk_hrs"
    )

    for h in agents_vet:
        model.Add(
            v_h.loc[h, "total_week_hours"]
            == sum(
                v_tdh["shift_duration"]
                .xs(h, axis=0, level=2, drop_level=False)
                .values.tolist()
            )
        )

        model.AddProdEquality(
            v_h.loc[h, "total_week_hours_squared"],
            [v_h.loc[h, "total_week_hours"], v_h.loc[h, "total_week_hours"]],
        )

        model.AddProdEquality(
            v_h.loc[h, "total_week_hours_cost"],
            [v_coeff_tot_wk_hrs, v_h.loc[h, "total_week_hours_squared"]],
        )


def cost_number_of_handovers():
    """Define cost associated with number of support handovers taking place."""
    for t in range(num_tracks):
        for d in range(num_days):  # (N/A for extra Monday track.)
            model.Add(
                v_td.loc[(t, d), "handover_cost"]
                == coeff_handover
                * (sum(v_tdh.loc[(t, d), "is_agent_on"].values.tolist()) - 1)
            )


def cost_agent_history():
    """Define cost associated with veteran's historical support score."""
    for t in range(num_tracks + 1):
        if t == num_tracks:
            max_days = 1
        else:
            max_days = num_days

        for d in range(max_days):
            for h in agents_vet:
                # Put toggles in place reflecting whether agent was assigned:
                model.Add(
                    v_tdh.loc[(t, d, h), "shift_duration"] != 0
                ).OnlyEnforceIf(v_tdh.loc[(t, d, h), "is_agent_on"])
                model.Add(
                    v_tdh.loc[(t, d, h), "shift_duration"] == 0
                ).OnlyEnforceIf(v_tdh.loc[(t, d, h), "is_agent_on"].Not())

                # Add cost due to agent history:
                agent_cost_value = coeff_agent * (
                    df_agents.loc[h, "avg_hours_per_week"]
                    - min_week_average_hours
                )

                model.Add(
                    v_tdh.loc[(t, d, h), "agent_cost"] == agent_cost_value
                ).OnlyEnforceIf(v_tdh.loc[(t, d, h), "is_agent_on"])
                model.Add(
                    v_tdh.loc[(t, d, h), "agent_cost"] == 0
                ).OnlyEnforceIf(v_tdh.loc[(t, d, h), "is_agent_on"].Not())


def cost_shift_duration():
    """Define cost associated with the lengths of veterans' assigned shifts."""
    for t in range(num_tracks + 1):
        if t == num_tracks:
            max_days = 1
        else:
            max_days = num_days

        for d in range(max_days):
            for h in agents_vet:
                # Define is_duration_shorter_than_ideal switch:
                model.Add(
                    v_tdh.loc[(t, d, h), "shift_duration"]
                    < df_agents.loc[h, "pref_ideal_length"]
                ).OnlyEnforceIf(
                    v_tdh.loc[(t, d, h), "is_duration_shorter_than_ideal"]
                )

                model.Add(
                    v_tdh.loc[(t, d, h), "shift_duration"]
                    >= df_agents.loc[h, "pref_ideal_length"]
                ).OnlyEnforceIf(
                    v_tdh.loc[
                        (t, d, h), "is_duration_shorter_than_ideal"
                    ].Not()
                )

                # Zero cost for zero duration:
                model.Add(
                    v_tdh.loc[(t, d, h), "duration_cost"] == 0
                ).OnlyEnforceIf(v_tdh.loc[(t, d, h), "is_agent_on"].Not())

                # Cost for duration shorter than preference:
                model.Add(
                    v_tdh.loc[(t, d, h), "duration_cost"]
                    == coeff_shorter_than_pref
                    * (
                        df_agents.loc[h, "pref_ideal_length"]
                        - v_tdh.loc[(t, d, h), "shift_duration"]
                    )
                ).OnlyEnforceIf(
                    [
                        v_tdh.loc[(t, d, h), "is_agent_on"],
                        v_tdh.loc[(t, d, h), "is_duration_shorter_than_ideal"],
                    ]
                )

                # Cost for duration longer than preference:
                model.Add(
                    v_tdh.loc[(t, d, h), "duration_cost"]
                    == coeff_longer_than_pref
                    * (
                        v_tdh.loc[(t, d, h), "shift_duration"]
                        - df_agents.loc[h, "pref_ideal_length"]
                    )
                ).OnlyEnforceIf(
                    v_tdh.loc[
                        (t, d, h), "is_duration_shorter_than_ideal"
                    ].Not()
                )


def cost_hours_veterans():
    """Define veterans' cost for assigned hours based on availability."""
    for t in range(num_tracks + 1):  # Applicable to extra Monday track.
        if t == num_tracks:
            max_days = 1
            max_hour = 12
        else:
            max_days = num_days
            max_hour = end_hour

        for d in range(max_days):
            for h in agents_vet:
                for (s_count, s_cost) in enumerate(
                    df_agents.loc[h, "hours"][d][start_hour:max_hour]
                ):
                    s = s_count + start_hour

                    model.Add(
                        v_tdh.loc[(t, d, h), "shift_start"] <= s
                    ).OnlyEnforceIf(
                        v_tdsh.loc[(t, d, s, h), "is_start_smaller_equal_hour"]
                    )
                    model.Add(
                        v_tdh.loc[(t, d, h), "shift_start"] > s
                    ).OnlyEnforceIf(
                        v_tdsh.loc[
                            (t, d, s, h), "is_start_smaller_equal_hour"
                        ].Not()
                    )

                    model.Add(
                        v_tdh.loc[(t, d, h), "shift_end"] > s
                    ).OnlyEnforceIf(
                        v_tdsh.loc[(t, d, s, h), "is_end_greater_than_hour"]
                    )
                    model.Add(
                        v_tdh.loc[(t, d, h), "shift_end"] <= s
                    ).OnlyEnforceIf(
                        v_tdsh.loc[
                            (t, d, s, h), "is_end_greater_than_hour"
                        ].Not()
                    )

                    model.AddBoolAnd(
                        [
                            v_tdsh.loc[
                                (t, d, s, h), "is_start_smaller_equal_hour"
                            ],
                            v_tdsh.loc[
                                (t, d, s, h), "is_end_greater_than_hour"
                            ],
                        ]
                    ).OnlyEnforceIf(v_tdsh.loc[(t, d, s, h), "is_hour_cost"])

                    model.AddBoolOr(
                        [
                            v_tdsh.loc[
                                (t, d, s, h), "is_start_smaller_equal_hour"
                            ].Not(),
                            v_tdsh.loc[
                                (t, d, s, h), "is_end_greater_than_hour"
                            ].Not(),
                        ]
                    ).OnlyEnforceIf(
                        v_tdsh.loc[(t, d, s, h), "is_hour_cost"].Not()
                    )
                    # For "preferred", (s_cost - 1) = 0, so no hourly cost.
                    # For "non-preferred", (s_cost - 1) = 1.
                    model.Add(
                        v_tdsh.loc[(t, d, s, h), "hour_cost"]
                        == coeff_non_preferred * (s_cost - 1)
                    ).OnlyEnforceIf(v_tdsh.loc[(t, d, s, h), "is_hour_cost"])

                    model.Add(
                        v_tdsh.loc[(t, d, s, h), "hour_cost"] == 0
                    ).OnlyEnforceIf(
                        v_tdsh.loc[(t, d, s, h), "is_hour_cost"].Not()
                    )


def cost_hours_onboarding():
    """Define onboarders' cost for assigned hours based on availability."""
    for d in range(num_days):
        for h in agents_onb:
            for (s_count, s_cost) in enumerate(
                df_agents.loc[h, "hours"][d][start_hour:end_hour]
            ):
                s = s_count + start_hour

                model.Add(
                    v_dh_on.loc[(d, h), "shift_start"] <= s
                ).OnlyEnforceIf(
                    v_dhs_on.loc[(d, h, s), "is_start_smaller_equal_hour"]
                )
                model.Add(
                    v_dh_on.loc[(d, h), "shift_start"] > s
                ).OnlyEnforceIf(
                    v_dhs_on.loc[
                        (d, h, s), "is_start_smaller_equal_hour"
                    ].Not()
                )

                model.Add(v_dh_on.loc[(d, h), "shift_end"] > s).OnlyEnforceIf(
                    v_dhs_on.loc[(d, h, s), "is_end_greater_than_hour"]
                )
                model.Add(v_dh_on.loc[(d, h), "shift_end"] <= s).OnlyEnforceIf(
                    v_dhs_on.loc[(d, h, s), "is_end_greater_than_hour"].Not()
                )

                model.AddBoolAnd(
                    [
                        v_dhs_on.loc[(d, h, s), "is_start_smaller_equal_hour"],
                        v_dhs_on.loc[(d, h, s), "is_end_greater_than_hour"],
                    ]
                ).OnlyEnforceIf(v_dhs_on.loc[(d, h, s), "is_hour_cost"])

                model.AddBoolOr(
                    [
                        v_dhs_on.loc[
                            (d, h, s), "is_start_smaller_equal_hour"
                        ].Not(),
                        v_dhs_on.loc[
                            (d, h, s), "is_end_greater_than_hour"
                        ].Not(),
                    ]
                ).OnlyEnforceIf(v_dhs_on.loc[(d, h, s), "is_hour_cost"].Not())
                # For "preferred", (s_cost - 1) = 0, so no hourly cost.
                # For "non-preferred", (s_cost - 1) = 1.
                model.Add(
                    v_dhs_on.loc[(d, h, s), "hour_cost"]
                    == coeff_non_preferred * (s_cost - 1)
                ).OnlyEnforceIf(v_dhs_on.loc[(d, h, s), "is_hour_cost"])

                model.Add(
                    v_dhs_on.loc[(d, h, s), "hour_cost"] == 0
                ).OnlyEnforceIf(v_dhs_on.loc[(d, h, s), "is_hour_cost"].Not())


def solve_model_and_extract_solution():
    """Solve model, extract, print and save solution."""
    model.Minimize(sum(full_cost_list))
    print(model.Validate())

    # Solve model:
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = solver_timeout
    solver.parameters.log_search_progress = True
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)
    print(solver.StatusName(status))

    if not (status in [cp_model.OPTIMAL, cp_model.FEASIBLE]):
        print("Cannot create schedule")
        return

    else:
        # Extract solution:
        print("\n---------------------")
        print("| OR-Tools schedule |")
        print("---------------------")

        print("\nSolution type: ", solver.StatusName(status))
        print("\nMinimized cost: ", solver.ObjectiveValue())
        print("After", solver.WallTime(), "seconds.\n")

        schedule_results = []

        # This file will contain the onboarding message for Flowdock:
        if len(agents_onb) > 0:
            o_path = "onboarding_message.txt"
            o_file = open(o_path, "w")
            o_file.write(
                "**Support agent onboarding next week**"
                "\n\nEach new onboarding agent has been paired with a senior "
                "support agent for each of their shifts. The senior agent "
                "will act as a mentor for the onboarding agents, showing "
                "them the ropes during these onboarding shifts (see the "
                "[onboarding document](https://github.com/balena-io/process/blob/master/process/support/onboarding_agents_to_support.md) "
                "for background). Here are the mentor-novice pairings "
                "for next week:"
            )

        for d in range(num_days):
            if len(agents_onb) > 0:
                o_file.write(
                    f"\n\n**Onboarding on {days[d].strftime('%Y-%m-%d')}**"
                )

            day_dict = {}
            day_dict["start_date"] = days[d]
            day_dict["shifts"] = []

            if d == 0:
                max_tracks = num_tracks + 1
            else:
                max_tracks = num_tracks

            for t in range(max_tracks):
                for h in agents_vet:
                    if (
                        solver.Value(v_tdh.loc[(t, d, h), "shift_duration"])
                        != 0
                    ):
                        day_dict["shifts"].append(
                            (
                                h,
                                solver.Value(
                                    v_tdh.loc[(t, d, h), "shift_start"]
                                ),
                                solver.Value(
                                    v_tdh.loc[(t, d, h), "shift_end"]
                                ),
                            )
                        )

            for h in agents_onb:
                if solver.Value(v_dh_on.loc[(d, h), "shift_duration"]) != 0:
                    day_dict["shifts"].append(
                        (
                            h,
                            solver.Value(v_dh_on.loc[(d, h), "shift_start"]),
                            solver.Value(v_dh_on.loc[(d, h), "shift_end"]),
                        )
                    )

                for m in v_mentors.columns:
                    if solver.Value(v_mentors.loc[(d, h), m]) == 1:
                        o_file.write(f"\n{m} will mentor {h}")

            schedule_results.append(day_dict)
        if len(agents_onb) > 0:
            o_file.close()

        # Sort shifts by start times to improve output readability:
        for i in range(len(schedule_results)):
            shifts = schedule_results[i]["shifts"]
            sorted_shifts = sorted(shifts, key=lambda x: x[1])
            schedule_results[i]["shifts"] = sorted_shifts

        return print_final_schedules(schedule_results)


input_json = parse_json_input()

# Define variables from options:
scheduler_options = input_json["options"]

start_Monday = scheduler_options["startMondayDate"]
num_days = int(scheduler_options["numConsecutiveDays"])
num_tracks = int(scheduler_options["numSimultaneousTracks"])
start_hour = int(scheduler_options["supportStartHour"])
end_hour = int(scheduler_options["supportEndHour"])
min_duration = int(scheduler_options["shiftMinDuration"])
max_duration = int(scheduler_options["shiftMaxDuration"])
solver_timeout = int(scheduler_options["optimizationTimeout"])

# Derived variables:
work_hours = end_hour - start_hour
max_daily_handovers = work_hours // min_duration - 1

start_date = datetime.datetime.strptime(start_Monday, date_format).date()
delta = datetime.timedelta(days=1)
days = [start_date]

for d in range(1, num_days):
    days.append(days[d - 1] + delta)

[df_agents, df_nights] = setup_dataframes()

[s_onboarding, s_mentors, s_new] = read_onboarding_files()

# Determine unavailable agents for each day:
unavailable_agents = []

for d in range(num_days):
    unavailable_agents.append(get_unavailable_agents(days[d]))

# Remove agents from the model who are not available at all this week:
df_agents = remove_agents_not_available_this_week()

# Onboarding agents:
agents_onb = df_agents[
    df_agents.index.isin(s_onboarding.tolist())
].index.tolist()

# Regular agents ("veterans"):
agents_vet = df_agents[
    ~df_agents.index.isin(s_onboarding.tolist())
].index.tolist()

# Recently onboarded ("new") agents:
agents_new = df_agents[df_agents.index.isin(s_new.tolist())].index.tolist()

# Mentors for onboarding agents (they are all also included in agents_vet).
# (Filter, since some mentors may be on leave that week:)
agents_mentors = [x for x in s_mentors.tolist() if x in df_agents.index]

# In the model below, the following abbreviations are used:
# t: track
# d: day
# h: Github handle
# s: slot number

# MODEL:

# Initialize model:
model = cp_model.CpModel()

setup_var_dataframes_veterans()
setup_var_dataframes_onboarding()

define_custom_var_domains()

fill_var_dataframes_veterans()
fill_var_dataframes_onboarding()

# Implement constraints - veterans:
constraint_new_agents_non_simultaneous()
constraint_cover_num_tracks_without_overlapping()
constraint_configure_extra_Monday_track()

constraint_honour_agent_availability_veterans()
constraint_avoid_assigning_agent_multiple_tracks_per_day()
constraint_various_custom_conditions()

# Implement constraints - onboarding:
constraint_honour_agent_availability_onboarding()
constraint_setup_onboarding_hours()
constraint_avoid_onboarding_before_Monday_1400()
constraint_avoid_simultaneous_onboarding()
constraint_configure_mentoring()

# Implement cost - veterans:
cost_total_agent_hours_for_week()
cost_number_of_handovers()
cost_agent_history()
cost_shift_duration()
cost_hours_veterans()

# Implement cost - onboarding:
cost_hours_onboarding()

# Add together resulting cost terms:
full_cost_list = (
    v_h["total_week_hours_cost"].values.tolist()
    + v_td["handover_cost"].values.tolist()
    + v_tdh["agent_cost"].values.tolist()
    + v_tdh["duration_cost"].values.tolist()
    + v_tdsh["hour_cost"].values.tolist()
    + v_dhs_on["hour_cost"].values.tolist()
)

# Solve model, extract and print solution:
final_schedule = solve_model_and_extract_solution()
