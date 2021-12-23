from ortools.sat.python import cp_model
import pandas as pd

week_working_slots = 80

# In the model below, the following abbreviations are used:
# t: track
# d: day
# h: Github handle
# s: slot number

def setup_var_dataframes_veterans(agent_categories, config):
    """Create dataframes that will contain model variables for veterans."""
    var_veterans = {}

    var_veterans["h"] = pd.DataFrame(
        data=None,
        index=agent_categories["veterans"],
        columns=[
            "total_week_slots",
            "total_week_slots_cost",
        ],
    )

    # td:
    # td_tuple = []

    # for t, track in enumerate(config["tracks"]):
    #     for d in range(track["start_day"], track["end_day"] + 1):
    #         td_tuple.append((t, d))

    # td_multi_index = pd.MultiIndex.from_tuples(
    #     td_tuple,
    #     names=("track", "day"),
    # )

    # v_td = pd.DataFrame(
    #     data=None, index=td_multi_index, columns=["handover_cost"]
    # )
    
    # tdh - veterans:
    # In this specific case, from_tuples is more suitable than from_product:
    tdh_tuple = []

    for t, track in enumerate(config["tracks"]):
        for d in range(track["start_day"], track["end_day"] + 1):
            for h in agent_categories["veterans"]:
                tdh_tuple.append((t, d, h))

    tdh_multi_index = pd.MultiIndex.from_tuples(
        tdh_tuple,
        names=("track", "day", "handle"),
    )

    var_veterans["tdh"] = pd.DataFrame(
        data=None,
        index=tdh_multi_index,
        columns=[
            "shift_start",
            "shift_end",
            "shift_duration",
            "interval",
            "is_agent_on",
            # "agent_cost",
            "is_duration_shorter_than_ideal",
            "duration_cost",
            "is_in_pref_range",
        ],
    )

    tdsh_tuple = []

    for t, track in enumerate(config["tracks"]):
        for d in range(track["start_day"], track["end_day"] + 1):
            for s in range(track["start_slot"], track["end_slot"]):
                for h in agent_categories["veterans"]:
                    tdsh_tuple.append((t, d, s, h))

    tdsh_multi_index = pd.MultiIndex.from_tuples(
        tdsh_tuple, names=("track", "day", "slot", "handle")
    )

    var_veterans["tdsh"] = pd.DataFrame(
        data=None,
        index=tdsh_multi_index,
        columns=[
            "is_start_smaller_equal_slot",
            "is_end_greater_than_slot",
            "is_slot_cost",
            "slot_cost",
        ],
    )
    return var_veterans


def fill_var_dataframes_veterans(model, custom_domains, coefficients, var_veterans, df_agents, agent_categories, config):
    """Fill veteran variable dataframes with OR-Tools model variables."""
    # h - veterans:
    for h in var_veterans["h"].index:
        var_veterans["h"].loc[h, "total_week_slots"] = model.NewIntVar(
            0, week_working_slots, f"total_week_slots_{h}"
        )

        var_veterans["h"].loc[h, "total_week_slots_cost"] = model.NewIntVarFromDomain(
            cp_model.Domain.FromValues(
                [
                    coefficients["fair_share"] * x
                    for x in range(
                        - config["max_fair_share"],
                        week_working_slots - config["min_fair_share"],
                    )
                ]
            ),
            f"total_week_slots_cost_{h}",
        )

    # td - veterans:

    # for t, track in enumerate(config["tracks"]):
    #     for d in range(track["start_day"], track["end_day"] + 1):
    #         v_td.loc[(t, d), "handover_cost"] = model.NewIntVarFromDomain(
    #             cp_model.Domain.FromValues(
    #                 [
    #                     coeff_handover * x
    #                     for x in range(0, max_daily_handovers + 1)
    #                 ]
    #             ),
    #             f"handover_cost_{t}_{d}",
    #         )

    # tdh - veterans:
    print("")

    for t, track in enumerate(config["tracks"]):
        for d in range(track["start_day"], track["end_day"] + 1):
            for h in agent_categories["veterans"]:
                if (
                    h in agent_categories["unavailable_agents"][d]
                    or custom_domains["prefs"].loc[(d, h)].Min() > track["end_slot"]
                ):
                    var_veterans["tdh"].loc[(t, d, h), "shift_start"] = model.NewIntVar(
                        8, 8, f"shift_start_{t}_{d}_{h}"
                    )
                    var_veterans["tdh"].loc[(t, d, h), "shift_end"] = model.NewIntVar(
                        8, 8, f"shift_end_{t}_{d}_{h}"
                    )
                    var_veterans["tdh"].loc[(t, d, h), "shift_duration"] = model.NewIntVar(
                        0, 0, f"shift_duration_{t}_{d}_{h}"
                    )
                else:
                    var_veterans["tdh"].loc[
                        (t, d, h), "shift_start"
                    ] = model.NewIntVarFromDomain(
                        custom_domains["prefs"].loc[(d, h)], f"shift_start_{t}_{d}_{h}"
                    )
                    var_veterans["tdh"].loc[
                        (t, d, h), "shift_end"
                    ] = model.NewIntVarFromDomain(
                        custom_domains["prefs"].loc[(d, h)], f"shift_end_{t}_{d}_{h}"
                    )
                    var_veterans["tdh"].loc[
                        (t, d, h), "shift_duration"
                    ] = model.NewIntVarFromDomain(
                        custom_domains["duration"], f"shift_duration_{t}_{d}_{h}"
                    )

                var_veterans["tdh"].loc[(t, d, h), "interval"] = model.NewIntervalVar(
                    var_veterans["tdh"].loc[(t, d, h), "shift_start"],
                    var_veterans["tdh"].loc[(t, d, h), "shift_duration"],
                    var_veterans["tdh"].loc[(t, d, h), "shift_end"],
                    f"interval_{t}_{d}_{h}",
                )

                var_veterans["tdh"].loc[(t, d, h), "is_agent_on"] = model.NewBoolVar(
                    f"is_agent_on_{t}_{d}_{h}"
                )

                var_veterans["tdh"].loc[
                    (t, d, h), "is_duration_shorter_than_ideal"
                ] = model.NewBoolVar(
                    f"is_duration_shorter_than_ideal_{t}_{d}_{h}"
                )

                var_veterans["tdh"].loc[
                    (t, d, h), "duration_cost"
                ] = model.NewIntVarFromDomain(
                    custom_domains["duration_cost"],
                    f"duration_cost_{t}_{d}_{h}",
                )

                var_veterans["tdh"].loc[(t, d, h), "is_in_pref_range"] = [
                    model.NewBoolVar(f"is_in_pref_range_{t}_{d}_{h}_{j}")
                    for (j, sec) in enumerate(
                        df_agents.loc[h, "slot_ranges"][d]
                    )
                ]

    # tdsh - veterans
    for t, track in enumerate(config["tracks"]):
        for d in range(track["start_day"], track["end_day"] + 1):
            for s in range(track["start_slot"], track["end_slot"]):
                for h in agent_categories["veterans"]:
                    var_veterans["tdsh"].loc[
                        (t, d, s, h), "is_start_smaller_equal_slot"
                    ] = model.NewBoolVar(
                        f"is_start_smaller_equal_slot_{t}_{d}_{s}_{h}"
                    )

                    var_veterans["tdsh"].loc[
                        (t, d, s, h), "is_end_greater_than_slot"
                    ] = model.NewBoolVar(
                        f"is_end_greater_than_slot_{t}_{d}_{s}_{h}"
                    )

                    var_veterans["tdsh"].loc[
                        (t, d, s, h), "is_slot_cost"
                    ] = model.NewBoolVar(f"is_slot_cost_{t}_{d}_{s}_{h}")

                    var_veterans["tdsh"].loc[
                        (t, d, s, h), "slot_cost"
                    ] = model.NewIntVarFromDomain(
                        custom_domains["slot_cost"], f"slot_cost_{t}_{d}_{s}_{h}"
                    )
    return [model, var_veterans]


def constraint_cover_num_tracks_without_overlapping(model, var_veterans, agent_categories, tracks):
    """Shifts in each track must cover required slots, without overlapping."""
    # Sum of agents' shifts must equal work hours:
    for t, track in enumerate(tracks):
        for d in range(track["start_day"], track["end_day"] + 1):
            model.Add(
                sum(var_veterans["tdh"].loc[(t, d), "shift_duration"].values.tolist())
                == track["end_slot"] - track["start_slot"]
            )
            # Since different starting and ending slot throughout tracks,
            # avoid scheduling outside tracks slots
            for h in agent_categories["veterans"]:
                # Put toggles in place reflecting whether agent was assigned:
                model.Add(
                    var_veterans["tdh"].loc[(t, d, h), "shift_duration"] != 0
                ).OnlyEnforceIf(var_veterans["tdh"].loc[(t, d, h), "is_agent_on"])
                model.Add(
                    var_veterans["tdh"].loc[(t, d, h), "shift_duration"] == 0
                ).OnlyEnforceIf(var_veterans["tdh"].loc[(t, d, h), "is_agent_on"].Not())

                # Lower limit:
                model.Add(
                    var_veterans["tdh"].loc[(t, d, h), "shift_start"] >= track["start_slot"]
                ).OnlyEnforceIf(var_veterans["tdh"].loc[(t, d, h), "is_agent_on"])

                # Upper limit:
                model.Add(
                    var_veterans["tdh"].loc[(t, d, h), "shift_end"] <= track["end_slot"]
                ).OnlyEnforceIf(var_veterans["tdh"].loc[(t, d, h), "is_agent_on"])

    # Agents' shifts must not overlap with each other:
    for t, track in enumerate(tracks):
        for d in range(track["start_day"], track["end_day"] + 1):
            model.AddNoOverlap(var_veterans["tdh"].loc[(t, d), "interval"].values.tolist())
    return model


def constraint_honour_agent_availability_veterans(model, var_veterans, df_agents, agent_categories, tracks):
    """Make sure that each veteran's availability is honoured.

    Each shift must start and end within that agent's available hours.
    """
    # Note: AddBoolOr works with just one boolean as well, in which case that
    # boolean has to be true.
    for t, track in enumerate(tracks):
        for d in range(track["start_day"], track["end_day"] + 1):
            for h in agent_categories["veterans"]:
                if not (h in agent_categories["unavailable"][d]):
                    model.AddBoolOr(var_veterans["tdh"].loc[(t, d, h), "is_in_pref_range"])
                    # TODO: I think .OnlyEnforceIf(var_veterans["tdh"].loc[(t, d, h), "is_agent_on"]) should be added above.
                    for (j, sec) in enumerate(
                        df_agents.loc[h, "slot_ranges"][d]
                    ):
                        if sec[0] < track["end_slot"]:
                            model.Add(
                                var_veterans["tdh"].loc[(t, d, h), "shift_start"] >= sec[0]
                            ).OnlyEnforceIf(
                                var_veterans["tdh"].loc[(t, d, h), "is_in_pref_range"][j]
                            )
                            model.Add(
                                var_veterans["tdh"].loc[(t, d, h), "shift_start"]
                                + var_veterans["tdh"].loc[(t, d, h), "shift_duration"]
                                <= sec[1]
                            ).OnlyEnforceIf(
                                var_veterans["tdh"].loc[(t, d, h), "is_in_pref_range"][j]
                            )
    return model


def constraint_avoid_assigning_agent_multiple_tracks_per_day(model, var_veterans, agent_categories, tracks):
    """Ensure each veteran is scheduled in at most 1 track per day."""
    day_occurrences = []
    for track in tracks:
        day_occurrences.extend(
            list(range(track["start_day"], track["end_day"] + 1))
        )

    for d in set(day_occurrences):
        for h in agent_categories["veterans"]:
            is_agent_on_list = []

            for t, track in enumerate(tracks):
                if d in range(track["start_day"], track["end_day"] + 1):
                    is_agent_on_list.append(
                        var_veterans["tdh"].loc[(t, d, h), "is_agent_on"]
                    )

            model.Add(sum(is_agent_on_list) <= 1)
    return model


def constraint_various_custom_conditions(model, var_veterans, df_agents, agent_categories, config):
    """Define custom constraints (usually temporary) as needed."""

    # Maximum hours per shift
    for agent in config["special_agent_conditions"]["agentsMaxHoursShift"]:
        handle = agent["handle"]
        slots = int(agent["value"] * 2)
        for t, track in enumerate(config["tracks"]):
            for d in range(track["start_day"], track["end_day"] + 1):
                if not (handle in agent_categories["unavailable"][d]):
                    model.Add(
                        var_veterans["tdh"].loc[(t, d, handle), "shift_duration"] <= slots
                    )

    # Minimum hours per week
    for agent in config["special_agent_conditions"]["agentsMinHoursWeek"]:
        handle = agent["handle"]
        slots = int(agent["value"] * 2)
        if handle in df_agents.index:
            agent_daily_quota = (
                slots / 5
            )  # slots per week converted to per day
            agent_weekly_lower_limit = 0

            for d in range(config["num_days"]):
                if not (handle in agent_categories["unavailable"][d]):
                    agent_weekly_lower_limit += agent_daily_quota

            agent_weekly_lower_limit = round(agent_weekly_lower_limit)

            model.Add(
                var_veterans["h"].loc[handle, "total_week_slots"] >= agent_weekly_lower_limit
            )

    # Maximum hours per week
    for agent in config["special_agent_conditions"]["agentsMaxHoursWeek"]:
        handle = agent["handle"]
        slots = int(agent["value"] * 2)
        if handle in df_agents.index:
            agent_daily_quota = (
                slots / 5
            )  # slots per week converted to per day
            agent_weekly_lower_limit = 0

            for d in range(config["num_days"]):
                if not (handle in agent_categories["unavailable"][d]):
                    agent_weekly_lower_limit += agent_daily_quota

            agent_weekly_lower_limit = round(agent_weekly_lower_limit)

            model.Add(
                var_veterans["h"].loc[handle, "total_week_slots"] <= agent_weekly_lower_limit
            )
    return model


# def constraint_new_agents_non_simultaneous():
#     """Recently onboarded agents should not be scheduled simultaneously."""
#     # TODO remove hard coding and add input flexibility
#     for d in range(num_days):
#         for h1 in agents_new:
#             for h2 in agents_new:
#                 if h1 != h2:
#                     model.AddNoOverlap(
#                         [
#                             v_tdh.loc[(0, d, h1), "interval"],
#                             v_tdh.loc[(1, d, h2), "interval"],
#                         ]
#                     )
#                     if d == 0:  # Then there is an extra Monday track.
#                         model.AddNoOverlap(
#                             [
#                                 v_tdh.loc[(0, d, h1), "interval"],
#                                 v_tdh.loc[(2, d, h2), "interval"],
#                             ]
#                         )
#                         model.AddNoOverlap(
#                             [
#                                 v_tdh.loc[(1, d, h1), "interval"],
#                                 v_tdh.loc[(2, d, h2), "interval"],
#                             ]
#                         )


def cost_total_agent_hours_for_week(model, var_veterans, coefficients, df_agents, agent_categories):
    """Define cost associated with total weekly hours per veteran."""
    # v_coeff_tot_wk_hrs = model.NewIntVar(
    #     coefficients["fair_share"], coefficients["fair_share"], "coeff_tot_wk_hrs"
    # )

    for h in agent_categories["veterans"]:
        model.Add(
            var_veterans["h"].loc[h, "total_week_slots"]
            == sum(
                var_veterans["tdh"]["shift_duration"]
                    .xs(h, axis=0, level=2, drop_level=False)
                    .values.tolist()
            )
        )
        model.Add(
            var_veterans["h"].loc[h, "total_week_slots_cost"]
            == coefficients["fair_share"]
            * (var_veterans["h"].loc[h, "total_week_slots"] - df_agents.loc[h, "fair_share"])
        )
        # model.AddProdEquality(
        #     var_veterans["h"].loc[h, "total_week_slots_squared"],
        #     [var_veterans["h"].loc[h, "total_week_slots"], var_veterans["h"].loc[h, "total_week_slots"]],
        # )

        # model.AddProdEquality(
        #     var_veterans["h"].loc[h, "total_week_slots_cost"],
        #     [v_coeff_tot_wk_hrs, var_veterans["h"].loc[h, "total_week_slots_squared"]],
        # )
    return model


# def cost_number_of_handovers():
#     """Define cost associated with number of support handovers taking place."""
#     for t, track in enumerate(tracks):
#         for d in range(track["start_day"], track["end_day"] + 1):
#             model.Add(
#                 v_td.loc[(t, d), "handover_cost"]
#                 == coeff_handover
#                 * (sum(var_veterans["tdh"].loc[(t, d), "is_agent_on"].values.tolist()) - 1)
#             )


# def cost_agent_history():
#     """Define cost associated with veteran's historical support score."""
#     for t, track in enumerate(tracks):
#         for d in range(track["start_day"], track["end_day"] + 1):
#             for h in agent_categories["veterans"]:

#                 # Add cost due to agent history:
#                 agent_cost_value = coeff_agent * (
#                         df_agents.loc[h, "avg_slots_per_week"]
#                         - min_week_average_slots
#                 )

#                 model.Add(
#                     var_veterans["tdh"].loc[(t, d, h), "agent_cost"] == agent_cost_value
#                 ).OnlyEnforceIf(var_veterans["tdh"].loc[(t, d, h), "is_agent_on"])
#                 model.Add(
#                     var_veterans["tdh"].loc[(t, d, h), "agent_cost"] == 0
#                 ).OnlyEnforceIf(var_veterans["tdh"].loc[(t, d, h), "is_agent_on"].Not())


def cost_shift_duration(model, var_veterans, coefficients, df_agents, agent_categories, tracks):
    """Define cost associated with the lengths of veterans' assigned shifts."""
    for t, track in enumerate(tracks):
        for d in range(track["start_day"], track["end_day"] + 1):
            for h in agent_categories["veterans"]:
                # Define is_duration_shorter_than_ideal switch:
                model.Add(
                    var_veterans["tdh"].loc[(t, d, h), "shift_duration"]
                    < df_agents.loc[h, "ideal_shift_length"]
                ).OnlyEnforceIf(
                    var_veterans["tdh"].loc[(t, d, h), "is_duration_shorter_than_ideal"]
                )
                model.Add(
                    var_veterans["tdh"].loc[(t, d, h), "shift_duration"]
                    >= df_agents.loc[h, "ideal_shift_length"]
                ).OnlyEnforceIf(
                    var_veterans["tdh"].loc[
                        (t, d, h), "is_duration_shorter_than_ideal"
                    ].Not()
                )

                # Zero cost for zero duration:
                model.Add(
                    var_veterans["tdh"].loc[(t, d, h), "duration_cost"] == 0
                ).OnlyEnforceIf(var_veterans["tdh"].loc[(t, d, h), "is_agent_on"].Not())

                # Cost for duration shorter than preference:
                model.Add(
                    var_veterans["tdh"].loc[(t, d, h), "duration_cost"]
                    == coefficients["shorter_than_pref"]
                    * (
                        df_agents.loc[h, "ideal_shift_length"]
                        - var_veterans["tdh"].loc[(t, d, h), "shift_duration"]
                    )
                ).OnlyEnforceIf(
                    [
                        var_veterans["tdh"].loc[(t, d, h), "is_agent_on"],
                        var_veterans["tdh"].loc[(t, d, h), "is_duration_shorter_than_ideal"],
                    ]
                )

                # Cost for duration longer than preference:
                model.Add(
                    var_veterans["tdh"].loc[(t, d, h), "duration_cost"]
                    == coefficients["longer_than_pref"]
                    * (
                        var_veterans["tdh"].loc[(t, d, h), "shift_duration"]
                        - df_agents.loc[h, "ideal_shift_length"]
                    )
                ).OnlyEnforceIf(
                    var_veterans["tdh"].loc[
                        (t, d, h), "is_duration_shorter_than_ideal"
                    ].Not()
                )
    return model


def cost_hours_veterans(model, var_veterans, coefficients, df_agents, agent_categories, tracks):
    """Define veterans' cost for assigned hours based on availability."""
    for t, track in enumerate(tracks):
        start_slot = track["start_slot"]
        max_slot = track["end_slot"]
        for d in range(track["start_day"], track["end_day"] + 1):
            for h in agent_categories["veterans"]:
                for (s_count, s_cost) in enumerate(
                    df_agents.loc[h, "slots"][d][start_slot:max_slot]
                ):
                    s = s_count + start_slot

                    model.Add(
                        var_veterans["tdh"].loc[(t, d, h), "shift_start"] <= s
                    ).OnlyEnforceIf(
                        var_veterans["tdsh"].loc[(t, d, s, h), "is_start_smaller_equal_slot"]
                    )
                    model.Add(
                        var_veterans["tdh"].loc[(t, d, h), "shift_start"] > s
                    ).OnlyEnforceIf(
                        var_veterans["tdsh"].loc[
                            (t, d, s, h), "is_start_smaller_equal_slot"
                        ].Not()
                    )

                    model.Add(
                        var_veterans["tdh"].loc[(t, d, h), "shift_end"] > s
                    ).OnlyEnforceIf(
                        var_veterans["tdsh"].loc[(t, d, s, h), "is_end_greater_than_slot"]
                    )
                    model.Add(
                        var_veterans["tdh"].loc[(t, d, h), "shift_end"] <= s
                    ).OnlyEnforceIf(
                        var_veterans["tdsh"].loc[
                            (t, d, s, h), "is_end_greater_than_slot"
                        ].Not()
                    )

                    model.AddBoolAnd(
                        [
                            var_veterans["tdsh"].loc[
                                (t, d, s, h), "is_start_smaller_equal_slot"
                            ],
                            var_veterans["tdsh"].loc[
                                (t, d, s, h), "is_end_greater_than_slot"
                            ],
                        ]
                    ).OnlyEnforceIf(var_veterans["tdsh"].loc[(t, d, s, h), "is_slot_cost"])

                    model.AddBoolOr(
                        [
                            var_veterans["tdsh"].loc[
                                (t, d, s, h), "is_start_smaller_equal_slot"
                            ].Not(),
                            var_veterans["tdsh"].loc[
                                (t, d, s, h), "is_end_greater_than_slot"
                            ].Not(),
                        ]
                    ).OnlyEnforceIf(
                        var_veterans["tdsh"].loc[(t, d, s, h), "is_slot_cost"].Not()
                    )
                    # For "preferred", (s_cost - 1) = 0, so no hourly cost.
                    # For "non-preferred", (s_cost - 1) = 1. If 3-slots included, then (s_cost - 1) = 2.
                    model.Add(
                        var_veterans["tdsh"].loc[(t, d, s, h), "slot_cost"]
                        == coefficients["non-preferred"] * (s_cost - 1)
                    ).OnlyEnforceIf(var_veterans["tdsh"].loc[(t, d, s, h), "is_slot_cost"])

                    model.Add(
                        var_veterans["tdsh"].loc[(t, d, s, h), "slot_cost"] == 0
                    ).OnlyEnforceIf(
                        var_veterans["tdsh"].loc[(t, d, s, h), "is_slot_cost"].Not()
                    )
    return model


def setup_model_veterans(model, custom_domains, coefficients, df_agents, agent_categories, config):
    # Configure model variables:
    var_veterans = setup_var_dataframes_veterans(agent_categories, config)
    [model, var_veterans] = fill_var_dataframes_veterans(model, custom_domains, coefficients, var_veterans, df_agents, agent_categories, config)    
    # Add constraints:
    model = constraint_cover_num_tracks_without_overlapping(model, var_veterans, agent_categories, config["tracks"])
    model = constraint_honour_agent_availability_veterans(model, var_veterans, df_agents, agent_categories, config["tracks"])
    model = constraint_avoid_assigning_agent_multiple_tracks_per_day(model, var_veterans, agent_categories, config["tracks"])
    model = constraint_various_custom_conditions(model, var_veterans, df_agents, agent_categories, config)
    # Add cost:
    model = cost_total_agent_hours_for_week(model, var_veterans, coefficients, df_agents, agent_categories)
    # cost_number_of_handovers()
    # cost_agent_history()
    model = cost_shift_duration(model, var_veterans, coefficients, df_agents, agent_categories, config["tracks"])
    model = cost_hours_veterans(model, var_veterans, coefficients, df_agents, agent_categories, config["tracks"])
    # Add together resulting cost terms:
    full_cost_list = (
        var_veterans["h"]["total_week_slots_cost"].values.tolist()
        # + v_td["handover_cost"].values.tolist()
        # + var_veterans["tdh"]["agent_cost"].values.tolist()
        + var_veterans["tdh"]["duration_cost"].values.tolist()
        + var_veterans["tdsh"]["slot_cost"].values.tolist()
    )
    return [model, var_veterans, full_cost_list]