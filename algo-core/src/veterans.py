"""
Copyright 2019-2023 Balena Ltd.

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
import pandas as pd

week_working_slots = 80

# In the model below, the following abbreviations are used:
# d: day
# h: Github handle
# s: slot number


def setup_var_dataframes_veterans(agent_categories, config):
    """Create dataframes that will contain model variables for veterans."""
    var_veterans = {}
    col_names = [
        "more_than_fair_share",
        "total_week_slots",
        "total_week_slots_squared",
        "total_week_slots_cost",
    ]
    var_veterans["h"] = pd.DataFrame(
        data=None,
        index=agent_categories["veterans"],
        columns=col_names,
    )

    # In this specific case, from_tuples is more suitable than from_product:
    dh_tuple = []

    for d in range(config["num_days"]):
        for h in agent_categories["veterans"]:
            dh_tuple.append((d, h))

    dh_multi_index = pd.MultiIndex.from_tuples(
        dh_tuple,
        names=("day", "handle"),
    )

    var_veterans["dh"] = pd.DataFrame(
        data=None,
        index=dh_multi_index,
        columns=[
            "shift_start",
            "shift_end",
            "shift_duration",
            "interval",
            "is_agent_on",
            "is_duration_shorter_than_ideal",
            "duration_cost",
            "is_in_pref_range",
        ],
    )

    dsh_tuple = []

    for d in range(config["num_days"]):
        for s in range(config["start_slot"], config["end_slot"]):
            for h in agent_categories["veterans"]:
                dsh_tuple.append((d, s, h))

    dsh_multi_index = pd.MultiIndex.from_tuples(
        dsh_tuple, names=("day", "slot", "handle")
    )

    var_veterans["dsh"] = pd.DataFrame(
        data=None,
        index=dsh_multi_index,
        columns=[
            "is_start_smaller_equal_slot",
            "is_end_greater_than_slot",
            "is_agent_on_slot",
            "is_support_engineer",
            "is_agent_on_slot_engineer",
            "slot_cost",
        ],
    )
    return var_veterans


def fill_var_dataframes_veterans(
    model,
    custom_domains,
    var_veterans,
    df_agents,
    agent_categories,
    config,
):
    """Fill veteran variable dataframes with OR-Tools model variables."""
    # h - veterans:
    for h in var_veterans["h"].index:
        var_veterans["h"].loc[h, "more_than_fair_share"] = model.NewBoolVar(
            f"more_than_fair_share_{h}"
        )
        var_veterans["h"].loc[h, "total_week_slots"] = model.NewIntVar(
            0, week_working_slots, f"total_week_slots_{h}"
        )
        var_veterans["h"].loc[
            h, "total_week_slots_squared"
        ] = model.NewIntVarFromDomain(
            cp_model.Domain.FromValues(
                [x**2 for x in range(0, week_working_slots)]
            ),
            f"total_week_slots_squared_{h}",
        )
        var_veterans["h"].loc[
            h, "total_week_slots_cost"
        ] = model.NewIntVarFromDomain(
            custom_domains["total_week_slots_cost"],
            f"total_week_slots_cost_{h}",
        )

    # dh - veterans:
    print("")

    for d in range(config["num_days"]):
        for h in agent_categories["veterans"]:
            if h in agent_categories["unavailable"][d]:
                var_veterans["dh"].loc[
                    (d, h), "shift_start"
                ] = model.NewIntVar(12, 12, f"shift_start_{d}_{h}")
                var_veterans["dh"].loc[(d, h), "shift_end"] = model.NewIntVar(
                    12, 12, f"shift_end_{d}_{h}"
                )
                var_veterans["dh"].loc[
                    (d, h), "shift_duration"
                ] = model.NewIntVar(0, 0, f"shift_duration_{d}_{h}")
            else:
                var_veterans["dh"].loc[
                    (d, h), "shift_start"
                ] = model.NewIntVarFromDomain(
                    custom_domains["prefs"].loc[(d, h)],
                    f"shift_start_{d}_{h}",
                )
                var_veterans["dh"].loc[
                    (d, h), "shift_end"
                ] = model.NewIntVarFromDomain(
                    custom_domains["prefs"].loc[(d, h)],
                    f"shift_end_{d}_{h}",
                )
                var_veterans["dh"].loc[
                    (d, h), "shift_duration"
                ] = model.NewIntVarFromDomain(
                    custom_domains["duration"],
                    f"shift_duration_{d}_{h}",
                )

            var_veterans["dh"].loc[(d, h), "interval"] = model.NewIntervalVar(
                var_veterans["dh"].loc[(d, h), "shift_start"],
                var_veterans["dh"].loc[(d, h), "shift_duration"],
                var_veterans["dh"].loc[(d, h), "shift_end"],
                f"interval_{d}_{h}",
            )

            var_veterans["dh"].loc[(d, h), "is_agent_on"] = model.NewBoolVar(
                f"is_agent_on_{d}_{h}"
            )

            var_veterans["dh"].loc[
                (d, h), "is_duration_shorter_than_ideal"
            ] = model.NewBoolVar(f"is_duration_shorter_than_ideal_{d}_{h}")

            var_veterans["dh"].loc[
                (d, h), "duration_cost"
            ] = model.NewIntVarFromDomain(
                custom_domains["duration_cost"],
                f"duration_cost_{d}_{h}",
            )

            var_veterans["dh"].loc[(d, h), "is_in_pref_range"] = [
                model.NewBoolVar(f"is_in_pref_range_{d}_{h}_{j}")
                for (j, sec) in enumerate(df_agents.loc[h, "slot_ranges"][d])
            ]

    # dsh - veterans
    for d in range(config["num_days"]):
        for s in range(config["start_slot"], config["end_slot"]):
            for h in agent_categories["veterans"]:
                var_veterans["dsh"].loc[
                    (d, s, h), "is_start_smaller_equal_slot"
                ] = model.NewBoolVar(
                    f"is_start_smaller_equal_slot_{d}_{s}_{h}"
                )

                var_veterans["dsh"].loc[
                    (d, s, h), "is_end_greater_than_slot"
                ] = model.NewBoolVar(f"is_end_greater_than_slot_{d}_{s}_{h}")

                var_veterans["dsh"].loc[
                    (d, s, h), "is_agent_on_slot"
                ] = model.NewBoolVar(f"is_agent_on_slot_{d}_{s}_{h}")

                var_veterans["dsh"].loc[
                    (d, s, h), "slot_cost"
                ] = model.NewIntVarFromDomain(
                    custom_domains["slot_cost"],
                    f"slot_cost_{d}_{s}_{h}",
                )

                var_veterans["dsh"].loc[
                    (d, s, h), "is_support_engineer"
                ] = model.NewConstant(df_agents.loc[h, "is_support_engineer"])

                var_veterans["dsh"].loc[
                    (d, s, h), "is_agent_on_slot_engineer"
                ] = model.NewBoolVar(f"is_agent_on_slot_engineer_{d}_{s}_{h}")

                # Multiply is_support_engineer by is_agent_on_slot to get
                # is_agent_on_slot_engineer
                model.AddMultiplicationEquality(
                    var_veterans["dsh"].loc[(d, s, h), "is_agent_on_slot_engineer"],
                    [
                       var_veterans["dsh"].loc[(d, s, h), "is_support_engineer"],
                       var_veterans["dsh"].loc[(d, s, h), "is_agent_on_slot"],
                    ],
                    )
    return [model, var_veterans]


def constraint_hours_coverage(model, var_veterans, config):
    """Ensure that adequate converage as specified by hoursCoverage is achieved."""
    for h_cover in config["hours_coverage"]:
        total_slots = sum(
            var_veterans["dsh"]
            .loc[
                list(range(h_cover["start_day"], h_cover["end_day"] + 1)),
                "is_agent_on_slot",
            ]
            .values.tolist()
        )
        model.Add(total_slots >= h_cover["min_slots"])
        model.Add(total_slots <= h_cover["max_slots"])
    return model


def constraint_agent_distribution(model, var_veterans, config):
    """Ensure the specified agentDistribution is adhered to."""
    print(var_veterans["dsh"])
    for a_distribution in config["agent_distribution"]:
        for d in range(
            a_distribution["start_day"], a_distribution["end_day"] + 1
        ):
            for s in range(
                a_distribution["start_slot"], a_distribution["end_slot"]
            ):
                num_simultaneous_agents = sum(
                    var_veterans["dsh"]
                    .loc[(d, s), "is_agent_on_slot"]
                    .values.tolist()
                )
                model.Add(
                    num_simultaneous_agents >= a_distribution["min_agents"]
                )
                model.Add(
                    num_simultaneous_agents <= a_distribution["max_agents"]
                )

                # Add engineers constraint only if min_support_engineers
                # are specified in agent distributions
                if "min_support_engineers" in a_distribution:
                    num_simultaneous_engineers = sum(
                        var_veterans["dsh"]
                        .loc[(d, s), "is_agent_on_slot_engineer"]
                        .values.tolist()
                    )
                    model.Add(
                        num_simultaneous_engineers >= a_distribution["min_support_engineers"]
                    )
    return model


def constraint_honour_agent_availability_veterans(
    model, var_veterans, df_agents, agent_categories, config
):
    """Make sure that each veteran's availability is honoured.

    Each shift must start and end within that agent's available hours.
    """
    # Note: AddBoolOr works with just one boolean as well, in which case that
    # boolean has to be true.
    for d in range(config["num_days"]):
        for h in agent_categories["veterans"]:
            if not (h in agent_categories["unavailable"][d]):
                model.AddBoolOr(
                    var_veterans["dh"].loc[(d, h), "is_in_pref_range"]
                ).OnlyEnforceIf(var_veterans["dh"].loc[(d, h), "is_agent_on"])
                for (j, sec) in enumerate(df_agents.loc[h, "slot_ranges"][d]):
                    if sec[0] < config["end_slot"]:
                        model.Add(
                            var_veterans["dh"].loc[(d, h), "shift_start"]
                            >= sec[0]
                        ).OnlyEnforceIf(
                            var_veterans["dh"].loc[(d, h), "is_in_pref_range"][
                                j
                            ]
                        )
                        model.Add(
                            var_veterans["dh"].loc[(d, h), "shift_end"]
                            <= sec[1]
                        ).OnlyEnforceIf(
                            var_veterans["dh"].loc[(d, h), "is_in_pref_range"][
                                j
                            ]
                        )
    return model


def constraint_various_custom_conditions(
    model, var_veterans, df_agents, agent_categories, config
):
    """Define custom constraints (usually temporary) as needed."""
    # Maximum hours per shift
    if "agentsMaxHoursShift" in config["special_agent_conditions"]:
        for agent in config["special_agent_conditions"]["agentsMaxHoursShift"]:
            handle = agent["handle"]
            slots = int(agent["value"] * 2)
            for d in range(config["num_days"]):
                if not (handle in agent_categories["unavailable"][d]):
                    model.Add(
                        var_veterans["dh"].loc[(d, handle), "shift_duration"]
                        <= slots
                    )

    # Minimum hours per week
    if "agentsMinHoursWeek" in config["special_agent_conditions"]:
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
                    var_veterans["h"].loc[handle, "total_week_slots"]
                    >= agent_weekly_lower_limit
                )

    # Maximum hours per week
    if "agentsMaxHoursWeek" in config["special_agent_conditions"]:
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
                    var_veterans["h"].loc[handle, "total_week_slots"]
                    <= agent_weekly_lower_limit
                )
    return model


def cost_total_agent_hours_for_week(
    model, var_veterans, coefficients, df_agents, agent_categories
):
    """Define cost associated with total weekly hours per veteran."""
    for h in agent_categories["veterans"]:
        model.Add(
            var_veterans["h"].loc[h, "total_week_slots"]
            > df_agents.loc[h, "fair_share"]
        ).OnlyEnforceIf(var_veterans["h"].loc[h, "more_than_fair_share"])
        model.Add(
            var_veterans["h"].loc[h, "total_week_slots"]
            <= df_agents.loc[h, "fair_share"]
        ).OnlyEnforceIf(var_veterans["h"].loc[h, "more_than_fair_share"].Not())
        # Define total_week_slots:
        model.Add(
            var_veterans["h"].loc[h, "total_week_slots"]
            == sum(
                var_veterans["dh"]["shift_duration"]
                .xs(h, axis=0, level=1, drop_level=False)
                .values.tolist()
            )
        )
        # Define total_week_slots_squared:
        model.AddMultiplicationEquality(
            var_veterans["h"].loc[h, "total_week_slots_squared"],
            [
                var_veterans["h"].loc[h, "total_week_slots"],
                var_veterans["h"].loc[h, "total_week_slots"],
            ],
        )

        # Cost associated with total_week_slots:
        model.Add(
            var_veterans["h"].loc[h, "total_week_slots_cost"]
            == coefficients["fair_share"]
            * (
                var_veterans["h"].loc[h, "total_week_slots_squared"]
                - 2
                * var_veterans["h"].loc[h, "total_week_slots"]
                * df_agents.loc[h, "fair_share"]
                + (df_agents.loc[h, "fair_share"]) ** 2
            )
        ).OnlyEnforceIf(var_veterans["h"].loc[h, "more_than_fair_share"])
        model.Add(
            var_veterans["h"].loc[h, "total_week_slots_cost"] == 0
        ).OnlyEnforceIf(var_veterans["h"].loc[h, "more_than_fair_share"].Not())
    return model


def cost_shift_duration(
    model, var_veterans, coefficients, df_agents, agent_categories, config
):
    """Define cost associated with the lengths of veterans' assigned shifts."""
    for d in range(config["num_days"]):
        for h in agent_categories["veterans"]:
            # Define is_duration_shorter_than_ideal switch:
            model.Add(
                var_veterans["dh"].loc[(d, h), "shift_duration"]
                < df_agents.loc[h, "ideal_shift_length"]
            ).OnlyEnforceIf(
                var_veterans["dh"].loc[
                    (d, h), "is_duration_shorter_than_ideal"
                ]
            )
            model.Add(
                var_veterans["dh"].loc[(d, h), "shift_duration"]
                >= df_agents.loc[h, "ideal_shift_length"]
            ).OnlyEnforceIf(
                var_veterans["dh"]
                .loc[(d, h), "is_duration_shorter_than_ideal"]
                .Not()
            )

            # Put toggles in place reflecting whether agent was assigned:
            model.Add(
                var_veterans["dh"].loc[(d, h), "shift_duration"] != 0
            ).OnlyEnforceIf(var_veterans["dh"].loc[(d, h), "is_agent_on"])
            model.Add(
                var_veterans["dh"].loc[(d, h), "shift_duration"] == 0
            ).OnlyEnforceIf(
                var_veterans["dh"].loc[(d, h), "is_agent_on"].Not()
            )

            # Zero cost for zero duration:
            model.Add(
                var_veterans["dh"].loc[(d, h), "duration_cost"] == 0
            ).OnlyEnforceIf(
                var_veterans["dh"].loc[(d, h), "is_agent_on"].Not()
            )

            # Cost for duration shorter than preference:
            model.Add(
                var_veterans["dh"].loc[(d, h), "duration_cost"]
                == coefficients["shorter_than_pref"]
                * (
                    df_agents.loc[h, "ideal_shift_length"]
                    - var_veterans["dh"].loc[(d, h), "shift_duration"]
                )
            ).OnlyEnforceIf(
                [
                    var_veterans["dh"].loc[(d, h), "is_agent_on"],
                    var_veterans["dh"].loc[
                        (d, h), "is_duration_shorter_than_ideal"
                    ],
                ]
            )

            # Cost for duration longer than preference:
            model.Add(
                var_veterans["dh"].loc[(d, h), "duration_cost"]
                == coefficients["longer_than_pref"]
                * (
                    var_veterans["dh"].loc[(d, h), "shift_duration"]
                    - df_agents.loc[h, "ideal_shift_length"]
                )
            ).OnlyEnforceIf(
                var_veterans["dh"]
                .loc[(d, h), "is_duration_shorter_than_ideal"]
                .Not()
            )
    return model


def cost_hours_veterans(
    model, var_veterans, coefficients, df_agents, agent_categories, config
):
    """Define veterans' cost for assigned hours based on availability."""
    for d in range(config["num_days"]):
        for h in agent_categories["veterans"]:
            for (s_count, s_cost) in enumerate(
                df_agents.loc[h, "slots"][d][
                    config["start_slot"]: config["end_slot"]
                ]
            ):
                s = s_count + config["start_slot"]

                model.Add(
                    var_veterans["dh"].loc[(d, h), "shift_start"] <= s
                ).OnlyEnforceIf(
                    var_veterans["dsh"].loc[
                        (d, s, h), "is_start_smaller_equal_slot"
                    ]
                )
                model.Add(
                    var_veterans["dh"].loc[(d, h), "shift_start"] > s
                ).OnlyEnforceIf(
                    var_veterans["dsh"]
                    .loc[(d, s, h), "is_start_smaller_equal_slot"]
                    .Not()
                )

                model.Add(
                    var_veterans["dh"].loc[(d, h), "shift_end"] > s
                ).OnlyEnforceIf(
                    var_veterans["dsh"].loc[
                        (d, s, h), "is_end_greater_than_slot"
                    ]
                )
                model.Add(
                    var_veterans["dh"].loc[(d, h), "shift_end"] <= s
                ).OnlyEnforceIf(
                    var_veterans["dsh"]
                    .loc[(d, s, h), "is_end_greater_than_slot"]
                    .Not()
                )

                model.AddBoolAnd(
                    [
                        var_veterans["dsh"].loc[
                            (d, s, h), "is_start_smaller_equal_slot"
                        ],
                        var_veterans["dsh"].loc[
                            (d, s, h), "is_end_greater_than_slot"
                        ],
                    ]
                ).OnlyEnforceIf(
                    var_veterans["dsh"].loc[(d, s, h), "is_agent_on_slot"]
                )

                model.AddBoolOr(
                    [
                        var_veterans["dsh"]
                        .loc[(d, s, h), "is_start_smaller_equal_slot"]
                        .Not(),
                        var_veterans["dsh"]
                        .loc[(d, s, h), "is_end_greater_than_slot"]
                        .Not(),
                    ]
                ).OnlyEnforceIf(
                    var_veterans["dsh"]
                    .loc[(d, s, h), "is_agent_on_slot"]
                    .Not()
                )
                # For "preferred", (s_cost - 1) = 0, so no hourly cost.
                # For "non_preferred", (s_cost - 1) = 1. If 3-slots included,
                # then (s_cost - 1) = 2.
                model.Add(
                    var_veterans["dsh"].loc[(d, s, h), "slot_cost"]
                    == coefficients["non_preferred"] * (s_cost - 1)
                ).OnlyEnforceIf(
                    var_veterans["dsh"].loc[(d, s, h), "is_agent_on_slot"]
                )

                model.Add(
                    var_veterans["dsh"].loc[(d, s, h), "slot_cost"] == 0
                ).OnlyEnforceIf(
                    var_veterans["dsh"]
                    .loc[(d, s, h), "is_agent_on_slot"]
                    .Not()
                )
    return model


def setup_model_veterans(
    model, custom_domains, coefficients, df_agents, agent_categories, config
):
    """Set up all model variables and constraints for veteran agents."""
    # Configure model variables:
    var_veterans = setup_var_dataframes_veterans(agent_categories, config)
    [model, var_veterans] = fill_var_dataframes_veterans(
        model,
        custom_domains,
        var_veterans,
        df_agents,
        agent_categories,
        config,
    )
    model = constraint_hours_coverage(model, var_veterans, config)
    model = constraint_agent_distribution(model, var_veterans, config)
    model = constraint_honour_agent_availability_veterans(
        model, var_veterans, df_agents, agent_categories, config
    )
    model = constraint_various_custom_conditions(
        model, var_veterans, df_agents, agent_categories, config
    )
    # Add cost:
    model = cost_total_agent_hours_for_week(
        model, var_veterans, coefficients, df_agents, agent_categories
    )
    model = cost_shift_duration(
        model,
        var_veterans,
        coefficients,
        df_agents,
        agent_categories,
        config,
    )
    model = cost_hours_veterans(
        model,
        var_veterans,
        coefficients,
        df_agents,
        agent_categories,
        config,
    )
    # Add together resulting cost terms:
    full_cost_list = (
        var_veterans["h"]["total_week_slots_cost"].values.tolist()
        + var_veterans["dh"]["duration_cost"].values.tolist()
        + var_veterans["dsh"]["slot_cost"].values.tolist()
    )
    return [model, var_veterans, full_cost_list]
