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
import collections
import datetime
import math
import colorama
import onboarding
import scheduler_utils
import pandas as pd
from ortools.sat.python import cp_model

# Cost weight assigned to various soft constraints:
coeff_non_preferred = 80
coeff_shorter_than_pref = 30
coeff_longer_than_pref = 70
coeff_total_week_slots = 3
coeff_agent = 30
coeff_handover = 30

# Other constants:
max_avg_per_week = 80
week_working_slots = 80
date_format = "%Y-%m-%d"


def setup_dataframes():
    """Set up dataframes for agents (df_a) and night shift info (df_n)."""
    global min_week_average_slots

    # Baseline for agent history:
    min_week_average_slots = 200

    # Initialize dataframes:
    df_a = pd.DataFrame(
        data=None,
        columns=[
            "handle",
            "email",
            "avg_slots_per_week",
            "pref_ideal_length",
            "slots",
            "slot_ranges",
        ],
    )

    i_tuple = []

    # Index for night-shifts (starting at 19hs => slot 38, ending 02hs => slot 52)
    for t, track in enumerate(tracks):
        if 38 in range(track["start_slot"], track["end_slot"]):
            for d in range(track["start_day"], track["end_day"] + 1):
                i_tuple.append((t, d))

    df_n_indices = pd.MultiIndex.from_tuples(i_tuple, names=("track", "day"))

    df_n = pd.DataFrame(
        data="", columns=list(range(38, 52)), index=df_n_indices
    )

    # Fill dataframes per agent:
    agents = input_json["agents"]
    agents_with_fix_hours = scheduler_options["specialAgentConditions"]["agentsWithFixHours"]

    for agent in agents:
        week_average_slots = math.trunc(float(agent["weekAverageHours"]*2))
        min_week_average_slots = min(
            min_week_average_slots, week_average_slots
        )

        week_slots = agent["availableHours"]

        for (d, _) in enumerate(week_slots):
            # Set availability to 0 outside balena support hours:
            for i in range(start_slot):
                week_slots[d][i] = 0
            for i in range(end_slot, slots_in_day):
                week_slots[d][i] = 0

            # Fill df_n dataframe with night shifts:
            # (Night shifts encoded as 4 in Team Model)
            indices_4 = [i for i, x in enumerate(week_slots[d]) if x == 4]

            # If agent has a night shift today, check into which track
            # it can slot, and fill df_n accordingly:
            if len(indices_4) > 0:
                track_found = False
                # TODO should be improved: It is first come first serve without considering
                #  length of track and length of night shift
                for t, track in enumerate(tracks):
                    if d in range(track["start_day"], track["end_day"] + 1) and not track_found:
                        if set(indices_4).issubset(set(range(track["start_slot"], track["end_slot"]))):
                            for s in indices_4:
                                df_n.loc[(t, d), s] = agent["handle"]
                            track_found = True

                if not track_found:
                    print(
                        f"{colorama.Fore.RED}\nWARNING! The night shift "
                        f"for {agent['handle']} could not be fitted in."
                        f"{colorama.Style.RESET_ALL}"
                    )

                # For Agents with fix hours, remove all availability except night shifts:
                if agent['handle'] in agents_with_fix_hours:
                    for h in range(0, slots_in_day):
                        if week_slots[d][h] == 1 or week_slots[d][h] == 2:
                            week_slots[d][h] = 0

                # Reset all 1s and 4s to 2s in night shift agent's preferences:
                # This will also disincentivise algorithm from giving night
                # shift volunteers other shifts during the week as well.
                for h in range(0, slots_in_day):
                    if week_slots[d][h] == 1 or week_slots[d][h] == 4:
                        week_slots[d][h] = 2

                # Give agent a break until 15:00 the next day if he/she was
                # on night shift:
                if d != 4:
                    week_slots[d + 1][0:28] = [0 for i in range(28)]

        slot_ranges = scheduler_utils.slots_to_range(week_slots, end_slot)

        df_a.loc[len(df_a)] = {
            "handle": agent["handle"],
            "email": agent["email"],
            "avg_slots_per_week": week_average_slots,
            "pref_ideal_length": agent["idealShiftLength"] * 2,
            "slots": week_slots,
            "slot_ranges": slot_ranges,
        }

    # slots: list of 5 lists, each of which has 24 items that mark the
    # availability of each slot (e.g.
    # [ [0,0,0,0,...,1,2,0,0], [0,0,0,0,...,1,2,0,0], [...], [...], [...] ])

    # slot_ranges: list of 5 lists, each of the 5 lists has a number
    # of nested lists that mark the ranges that an agent is available to do
    # support (e.g. [ [[8,12], [16, 24]], [], [...], [...], [...])
    # NB: e.g. [8,12] indicates agent is available 8-12, NOT 8-13.

    df_a.set_index("handle", inplace=True)
    return [df_a, df_n]


def get_unavailable_agents(day):
    """Determine agents with no availability for a given day."""
    day_number = day.weekday()
    unavailable = set()

    for handle in df_agents.index:
        if len(df_agents.loc[handle, "slot_ranges"][day_number]) == 0:
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


def flatten(lists):
    """Flatten nested lists."""
    for el in lists:
        if isinstance(el, collections.Iterable) and not isinstance(
                el, (str, bytes)
        ):
            yield from flatten(el)
        else:
            yield el


def setup_var_dataframes_veterans():
    """Create dataframes that will contain model variables for veterans."""
    global v_h, v_td, v_tdh, v_tdsh

    # h - veterans:
    v_h = pd.DataFrame(
        data=None,
        index=agents_vet,
        columns=[
            "total_week_slots",
            "total_week_slots_squared",
            "total_week_slots_cost",
        ],
    )

    # td - veterans:
    td_tuple = []

    for t, track in enumerate(tracks):
        for d in range(track["start_day"], track["end_day"] + 1):
            td_tuple.append((t, d))

    td_multi_index = pd.MultiIndex.from_tuples(
        td_tuple,
        names=("track", "day"),
    )

    v_td = pd.DataFrame(
        data=None, index=td_multi_index, columns=["handover_cost"]
    )

    # tdh - veterans:
    tdh_tuple = []

    for t, track in enumerate(tracks):
        for d in range(track["start_day"], track["end_day"] + 1):
            for h in agents_vet:
                tdh_tuple.append((t, d, h))

    tdh_multi_index = pd.MultiIndex.from_tuples(
        tdh_tuple,
        names=("track", "day", "handle"),
    )

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

    tdsh_tuple = []

    for t, track in enumerate(tracks):
        for d in range(track["start_day"], track["end_day"] + 1):
            for s in range(track["start_slot"], track["end_slot"]):
                for h in agents_vet:
                    tdsh_tuple.append((t, d, s, h))

    tdsh_multi_index = pd.MultiIndex.from_tuples(tdsh_tuple, names=("track", "day", "slot", "handle"))

    v_tdsh = pd.DataFrame(
        data=None,
        index=tdsh_multi_index,
        columns=[
            "is_start_smaller_equal_slot",
            "is_end_greater_than_slot",
            "is_slot_cost",
            "slot_cost",
        ],
    )


def fill_var_dataframes_veterans():
    """Fill veteran variable dataframes with OR-Tools model variables."""
    # h - veterans:
    for h in v_h.index:
        v_h.loc[h, "total_week_slots"] = model.NewIntVar(
            0, week_working_slots, f"total_week_slots_{h}"
        )

        v_h.loc[h, "total_week_slots_squared"] = model.NewIntVarFromDomain(
            cp_model.Domain.FromValues(
                [x ** 2 for x in range(0, week_working_slots + 2)]
            ),
            f"total_week_slots_squared_{h}",
        )

        v_h.loc[h, "total_week_slots_cost"] = model.NewIntVarFromDomain(
            cp_model.Domain.FromValues(
                [
                    coeff_total_week_slots * x ** 2
                    for x in range(0, week_working_slots + 2)
                ]
            ),
            f"total_week_slots_cost_{h}",
        )

    # td - veterans:

    for t, track in enumerate(tracks):
        for d in range(track["start_day"], track["end_day"] + 1):
            v_td.loc[(t, d), "handover_cost"] = model.NewIntVarFromDomain(
                cp_model.Domain.FromValues(
                    [
                        coeff_handover * x
                        for x in range(0, max_daily_handovers + 1)
                    ]
                ),
                f"handover_cost_{t}_{d}",
            )

    # tdh - veterans:
    print("")

    for t, track in enumerate(tracks):
        for d in range(track["start_day"], track["end_day"] + 1):
            for h in agents_vet:
                if h in unavailable_agents[d] or d_prefs.loc[(d, h)].Min() > track["end_slot"]:
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
                    when_on_night_shift = []
                    seven_pm_slot = 38
                    if seven_pm_slot in range(track["start_slot"], track["end_slot"]):
                        when_on_night_shift = [
                            seven_pm_slot + i
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
                        df_agents.loc[h, "slot_ranges"][d]
                    )
                ]

    # tdsh - veterans
    for t, track in enumerate(tracks):
        for d in range(track["start_day"], track["end_day"] + 1):
            for s in range(track["start_slot"], track["end_slot"]):
                for h in agents_vet:
                    v_tdsh.loc[
                        (t, d, s, h), "is_start_smaller_equal_slot"
                    ] = model.NewBoolVar(
                        f"is_start_smaller_equal_slot_{t}_{d}_{s}_{h}"
                    )

                    v_tdsh.loc[
                        (t, d, s, h), "is_end_greater_than_slot"
                    ] = model.NewBoolVar(
                        f"is_end_greater_than_slot_{t}_{d}_{s}_{h}"
                    )

                    v_tdsh.loc[
                        (t, d, s, h), "is_slot_cost"
                    ] = model.NewBoolVar(f"is_slot_cost_{t}_{d}_{s}_{h}")

                    v_tdsh.loc[
                        (t, d, s, h), "slot_cost"
                    ] = model.NewIntVarFromDomain(
                        d_slot_cost, f"slot_cost_{t}_{d}_{s}_{h}"
                    )


def define_custom_var_domains():
    """Define custom model variable domains."""
    global d_slot_cost, d_duration, d_prefs
    # slot cost domain:
    d_slot_cost = cp_model.Domain.FromValues([0, coeff_non_preferred])

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
                df_agents.loc[h, "slot_ranges"][d]
            )


def constraint_new_agents_non_simultaneous():
    """Recently onboarded agents should not be scheduled simultaneously."""
    # TODO remove hard coding and add input flexibility
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
    """Shifts in each track must cover required slots, without overlapping."""
    # Sum of agents' shifts must equal work hours:
    for t, track in enumerate(tracks):
        for d in range(track["start_day"], track["end_day"] + 1):
            model.Add(
                sum(v_tdh.loc[(t, d), "shift_duration"].values.tolist())
                == track["end_slot"] - track["start_slot"]
            )
            # Since different starting and ending slot throughout tracks,
            # avoid scheduling outside tracks slots
            for h in agents_vet:
                model.Add(v_tdh.loc[(t, d, h), "shift_end"] <= track["end_slot"])

    # Agents' shifts must not overlap with each other:
    for t, track in enumerate(tracks):
        for d in range(track["start_day"], track["end_day"] + 1):
            model.AddNoOverlap(v_tdh.loc[(t, d), "interval"].values.tolist())


def constraint_honour_agent_availability_veterans():
    """Make sure that each veteran's availability is honoured.

    Each shift must start and end within that agent's available hours.
    """
    # Note: AddBoolOr works with just one boolean as well, in which case that
    # boolean has to be true.
    for t, track in enumerate(tracks):
        track_end_slot = track["end_slot"]
        for d in range(track["start_day"], track["end_day"] + 1):
            for h in agents_vet:
                if not (h in unavailable_agents[d]):
                    model.AddBoolOr(v_tdh.loc[(t, d, h), "is_in_pref_range"])

                    for (j, sec) in enumerate(
                            df_agents.loc[h, "slot_ranges"][d]
                    ):
                        if sec[0] < track_end_slot:
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
    day_occurrences = []
    for track in tracks:
        day_occurrences.extend(list(range(track["start_day"], track["end_day"] + 1)))

    for d in set(day_occurrences):
        for h in agents_vet:
            is_agent_on_list = []

            for t, track in enumerate(tracks):
                if d in range(track["start_day"], track["end_day"] + 1):
                    is_agent_on_list.append(v_tdh.loc[(t, d, h), "is_agent_on"])

            model.Add(sum(is_agent_on_list) <= 1)


def constraint_various_custom_conditions():
    """Define custom constraints (usually temporary) as needed."""

    agents_with_max_shift_hours = scheduler_options["specialAgentConditions"]["agentsWithMaxHoursShift"]
    agents_with_min_week_hours = scheduler_options["specialAgentConditions"]["agentsWithMinHoursWeek"]

    for agent in agents_with_max_shift_hours:
        handle = agent["handle"]
        slots = int(agent["value"] * 2)
        for t, track in enumerate(tracks):
            for d in range(track["start_day"], track["end_day"] + 1):
                if not (handle in unavailable_agents[d]):
                    model.Add(v_tdh.loc[(t, d, handle), "shift_duration"] <= slots)

    for agent in agents_with_min_week_hours:
        handle = agent["handle"]
        slots = int(agent["value"] * 2)
        if handle in df_agents.index:
            agent_daily_quota = slots / 5  # slots per week converted to per day
            agent_weekly_lower_limit = 0

            for d in range(num_days):
                if not (handle in unavailable_agents[d]):
                    agent_weekly_lower_limit += agent_daily_quota

            agent_weekly_lower_limit = round(agent_weekly_lower_limit)

            model.Add(
                v_h.loc[handle, "total_week_slots"]
                >= agent_weekly_lower_limit
            )


def cost_total_agent_hours_for_week():
    """Define cost associated with total weekly hours per veteran."""
    v_coeff_tot_wk_hrs = model.NewIntVar(
        coeff_total_week_slots, coeff_total_week_slots, "coeff_tot_wk_hrs"
    )

    for h in agents_vet:
        model.Add(
            v_h.loc[h, "total_week_slots"]
            == sum(
                v_tdh["shift_duration"]
                    .xs(h, axis=0, level=2, drop_level=False)
                    .values.tolist()
            )
        )

        model.AddProdEquality(
            v_h.loc[h, "total_week_slots_squared"],
            [v_h.loc[h, "total_week_slots"], v_h.loc[h, "total_week_slots"]],
        )

        model.AddProdEquality(
            v_h.loc[h, "total_week_slots_cost"],
            [v_coeff_tot_wk_hrs, v_h.loc[h, "total_week_slots_squared"]],
        )


def cost_number_of_handovers():
    """Define cost associated with number of support handovers taking place."""
    for t, track in enumerate(tracks):
        for d in range(track["start_day"], track["end_day"] + 1):
            model.Add(
                v_td.loc[(t, d), "handover_cost"]
                == coeff_handover
                * (sum(v_tdh.loc[(t, d), "is_agent_on"].values.tolist()) - 1)
            )


def cost_agent_history():
    """Define cost associated with veteran's historical support score."""
    for t, track in enumerate(tracks):
        for d in range(track["start_day"], track["end_day"] + 1):
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
                        df_agents.loc[h, "avg_slots_per_week"]
                        - min_week_average_slots
                )

                model.Add(
                    v_tdh.loc[(t, d, h), "agent_cost"] == agent_cost_value
                ).OnlyEnforceIf(v_tdh.loc[(t, d, h), "is_agent_on"])
                model.Add(
                    v_tdh.loc[(t, d, h), "agent_cost"] == 0
                ).OnlyEnforceIf(v_tdh.loc[(t, d, h), "is_agent_on"].Not())


def cost_shift_duration():
    """Define cost associated with the lengths of veterans' assigned shifts."""
    for t, track in enumerate(tracks):
        for d in range(track["start_day"], track["end_day"] + 1):
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
    for t, track in enumerate(tracks):
        start_slot = track["start_slot"]
        max_slot = track["end_slot"]
        for d in range(track["start_day"], track["end_day"] + 1):
            for h in agents_vet:
                for (s_count, s_cost) in enumerate(
                        df_agents.loc[h, "slots"][d][start_slot:max_slot]
                ):
                    s = s_count + start_slot

                    model.Add(
                        v_tdh.loc[(t, d, h), "shift_start"] <= s
                    ).OnlyEnforceIf(
                        v_tdsh.loc[(t, d, s, h), "is_start_smaller_equal_slot"]
                    )
                    model.Add(
                        v_tdh.loc[(t, d, h), "shift_start"] > s
                    ).OnlyEnforceIf(
                        v_tdsh.loc[
                            (t, d, s, h), "is_start_smaller_equal_slot"
                        ].Not()
                    )

                    model.Add(
                        v_tdh.loc[(t, d, h), "shift_end"] > s
                    ).OnlyEnforceIf(
                        v_tdsh.loc[(t, d, s, h), "is_end_greater_than_slot"]
                    )
                    model.Add(
                        v_tdh.loc[(t, d, h), "shift_end"] <= s
                    ).OnlyEnforceIf(
                        v_tdsh.loc[
                            (t, d, s, h), "is_end_greater_than_slot"
                        ].Not()
                    )

                    model.AddBoolAnd(
                        [
                            v_tdsh.loc[
                                (t, d, s, h), "is_start_smaller_equal_slot"
                            ],
                            v_tdsh.loc[
                                (t, d, s, h), "is_end_greater_than_slot"
                            ],
                        ]
                    ).OnlyEnforceIf(v_tdsh.loc[(t, d, s, h), "is_slot_cost"])

                    model.AddBoolOr(
                        [
                            v_tdsh.loc[
                                (t, d, s, h), "is_start_smaller_equal_slot"
                            ].Not(),
                            v_tdsh.loc[
                                (t, d, s, h), "is_end_greater_than_slot"
                            ].Not(),
                        ]
                    ).OnlyEnforceIf(
                        v_tdsh.loc[(t, d, s, h), "is_slot_cost"].Not()
                    )
                    # For "preferred", (s_cost - 1) = 0, so no hourly cost.
                    # For "non-preferred", (s_cost - 1) = 1.
                    model.Add(
                        v_tdsh.loc[(t, d, s, h), "slot_cost"]
                        == coeff_non_preferred * (s_cost - 1)
                    ).OnlyEnforceIf(v_tdsh.loc[(t, d, s, h), "is_slot_cost"])

                    model.Add(
                        v_tdsh.loc[(t, d, s, h), "slot_cost"] == 0
                    ).OnlyEnforceIf(
                        v_tdsh.loc[(t, d, s, h), "is_slot_cost"].Not()
                    )


def solve_model_and_extract_solution():
    """Solve model, extract, print and save """
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
                "[onboarding document]: "
                "(https://github.com/balena-io/process/blob/master/process/support/onboarding_agents_to_support.md) "
                "for background). Here are the mentor-novice pairings "
                "for next week:"
            )

        for d in range(num_days):
            if len(agents_onb) > 0:
                o_file.write(
                    f"\n\n**Onboarding on {days[d].strftime('%Y-%m-%d')}**"
                )

            day_dict = {"start_date": days[d], "shifts": []}

            for t, track in enumerate(tracks):
                if d in range(track["start_day"], track["end_day"] + 1):
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

        return scheduler_utils.print_final_schedules(schedule_results, df_agents, num_days)


input_json = scheduler_utils.parse_json_input()

# Define variables from options:
scheduler_options = input_json["options"]
start_Monday = scheduler_options["startMondayDate"]
num_days = int(scheduler_options["numConsecutiveDays"])
tracks = scheduler_utils.tracks_hours_to_slots(scheduler_options["tracks"])
start_slot = int(scheduler_options["supportStartHour"] * 2)
slots_in_day = int(scheduler_options["slotsInDay"] * 2)
end_slot = int(scheduler_options["supportEndHour"] * 2)
min_duration = int(scheduler_options["shiftMinDuration"]) * 2
max_duration = int(scheduler_options["shiftMaxDuration"]) * 2
solver_timeout = int(scheduler_options["optimizationTimeout"])

# Derived variables:
work_slots = end_slot - start_slot
max_daily_handovers = work_slots // min_duration - 2

start_date = datetime.datetime.strptime(start_Monday, date_format).date()
delta = datetime.timedelta(days=1)
days = [start_date]

for d in range(1, num_days):
    days.append(days[d - 1] + delta)

[df_agents, df_nights] = setup_dataframes()
[s_onboarding, s_mentors, s_new] = scheduler_utils.read_onboarding_files()

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

if len(agents_onb) > 0:
    [v_mentors, v_h_on, v_dh_on, v_dhs_on] = onboarding.setup_var_dataframes_onboarding(
        num_days, agents_onb, agents_mentors, start_slot, end_slot)

define_custom_var_domains()

fill_var_dataframes_veterans()
if len(agents_onb) > 0:
    model = onboarding.fill_var_dataframes_onboarding(model, agents_mentors, week_working_slots, unavailable_agents,
                                                      d_prefs, df_agents, d_slot_cost)

# Implement constraints - veterans:
constraint_new_agents_non_simultaneous()
constraint_cover_num_tracks_without_overlapping()
constraint_honour_agent_availability_veterans()
constraint_avoid_assigning_agent_multiple_tracks_per_day()
constraint_various_custom_conditions()

# Implement constraints - onboarding:
if len(agents_onb) > 0:
    model = onboarding.constraints_for_onboarding(model, unavailable_agents, df_agents, tracks, v_tdh)

# Implement cost - veterans:
cost_total_agent_hours_for_week()
cost_number_of_handovers()
cost_agent_history()
cost_shift_duration()
cost_hours_veterans()

# Implement cost - onboarding:
if len(agents_onb) > 0:
    model = onboarding.cost_hours_onboarding(model, df_agents, coeff_non_preferred)

# Add together resulting cost terms:
full_cost_list = (
        v_h["total_week_slots_cost"].values.tolist()
        + v_td["handover_cost"].values.tolist()
        + v_tdh["agent_cost"].values.tolist()
        + v_tdh["duration_cost"].values.tolist()
        + v_tdsh["slot_cost"].values.tolist()
)

if len(agents_onb) > 0:
    full_cost_list = full_cost_list + v_dhs_on["slot_cost"].values.tolist()

# Solve model, extract and print solution:
final_schedule = solve_model_and_extract_solution()
