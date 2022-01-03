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
import pandas as pd

# Onboarding (given in terms of number of 30-min slots):
onboarding_shift_length = 8
onboarding_weekly_slots = 16

# In the model below, the following abbreviations are used:
# t: track
# d: day
# h: Github handle
# s: slot number


def tracks_in_day(d: int, tracks):
    tracks_containing_d = []
    for t, track in enumerate(tracks):
        if d in range(track["start_day"], track["end_day"] + 1):
            tracks_containing_d.append(t)
    return tracks_containing_d


def setup_var_dataframes_onboarding(agent_categories, config):
    """Create dataframes that will contain model variables for onboarders."""
    var_onboarding = {}

    # var_onboarding["mentors"] dataframe will contain onboarding agent - mentor associations:
    mentors_indices = pd.MultiIndex.from_product(
        [
            [d for d in range(config["num_days"])],
            agent_categories["onboarding"],
        ],
        names=("day", "agent"),
    )

    var_onboarding["mentors"] = pd.DataFrame(
        data=None, index=mentors_indices, columns=agent_categories["mentors"]
    )

    # h:
    var_onboarding["h"] = pd.DataFrame(
        data=None,
        index=agent_categories["onboarding"],
        columns=["total_week_slots"],
    )

    # dh:
    dh_multi_index_on = pd.MultiIndex.from_product(
        [
            [d for d in range(config["num_days"])],
            [h for h in agent_categories["onboarding"]],
        ],
        names=("day", "handle"),
    )

    var_onboarding["dh"] = pd.DataFrame(
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

    # dhs:
    dhs_multi_index_on = pd.MultiIndex.from_product(
        [
            [d for d in range(config["num_days"])],
            [h for h in agent_categories["onboarding"]],
            [s for s in range(config["start_slot"], config["end_slot"])],
        ],
        names=("day", "handle", "slot"),
    )

    var_onboarding["dhs"] = pd.DataFrame(
        data=None,
        index=dhs_multi_index_on,
        columns=[
            "is_start_smaller_equal_hour",
            "is_end_greater_than_hour",
            "is_slot_cost",
            "slot_cost",
        ],
    )
    return var_onboarding


def fill_var_dataframes_onboarding(
    model, custom_domains, var_onboarding, df_agents, agent_categories, config
):
    """Fill onboarding variable dataframes with OR-Tools model variables."""
    # Onboarding mentors:
    for d in range(config["num_days"]):
        for h in agent_categories["onboarding"]:
            for m in agent_categories["mentors"]:
                var_onboarding["mentors"].loc[(d, h), m] = model.NewBoolVar(
                    f"mentor_{d}_{h}_{m}"
                )

    # h:
    for h in var_onboarding["h"].index:
        var_onboarding["h"].loc[h, "total_week_slots"] = model.NewIntVar(
            0, onboarding_weekly_slots, f"total_week_slots_{h}"
        )

    # dh:
    print("")

    for d in range(config["num_days"]):
        for h in agent_categories["onboarding"]:
            if h in agent_categories["unavailable"][d]:
                var_onboarding["dh"].loc[
                    (d, h), "shift_start"
                ] = model.NewIntVar(8, 8, f"shift_start_{d}_{h}")
                var_onboarding["dh"].loc[
                    (d, h), "shift_end"
                ] = model.NewIntVar(8, 8, f"shift_end_{d}_{h}")
                var_onboarding["dh"].loc[
                    (d, h), "shift_duration"
                ] = model.NewIntVar(0, 0, f"shift_duration_{d}_{h}")

            else:
                var_onboarding["dh"].loc[
                    (d, h), "shift_start"
                ] = model.NewIntVarFromDomain(
                    custom_domains["prefs"].loc[(d, h)], f"shift_start_{d}_{h}"
                )
                var_onboarding["dh"].loc[
                    (d, h), "shift_end"
                ] = model.NewIntVarFromDomain(
                    custom_domains["prefs"].loc[(d, h)], f"shift_end_{d}_{h}"
                )
                var_onboarding["dh"].loc[
                    (d, h), "shift_duration"
                ] = model.NewIntVarFromDomain(
                    cp_model.Domain.FromValues([0, onboarding_shift_length]),
                    f"shift_duration_{d}_{h}",
                )

            var_onboarding["dh"].loc[
                (d, h), "interval"
            ] = model.NewIntervalVar(
                var_onboarding["dh"].loc[(d, h), "shift_start"],
                var_onboarding["dh"].loc[(d, h), "shift_duration"],
                var_onboarding["dh"].loc[(d, h), "shift_end"],
                f"interval_{d}_{h}",
            )

            var_onboarding["dh"].loc[(d, h), "is_agent_on"] = model.NewBoolVar(
                f"is_agent_on_{d}_{h}"
            )

            var_onboarding["dh"].loc[(d, h), "is_in_pref_range"] = [
                model.NewBoolVar(f"is_in_pref_range_{d}_{h}_{j}")
                for (j, _) in enumerate(df_agents.loc[h, "slot_ranges"][d])
            ]

    # dhs - onboarding:
    for d in range(config["num_days"]):
        for h in agent_categories["onboarding"]:
            for s in range(config["start_slot"], config["end_slot"]):
                var_onboarding["dhs"].loc[
                    (d, h, s), "is_start_smaller_equal_hour"
                ] = model.NewBoolVar(
                    f"is_start_smaller_equal_hour_{d}_{h}_{s}"
                )

                var_onboarding["dhs"].loc[
                    (d, h, s), "is_end_greater_than_hour"
                ] = model.NewBoolVar(f"is_end_greater_than_hour_{d}_{h}_{s}")

                var_onboarding["dhs"].loc[
                    (d, h, s), "is_slot_cost"
                ] = model.NewBoolVar(f"is_slot_cost_{d}_{h}_{s}")

                var_onboarding["dhs"].loc[
                    (d, h, s), "slot_cost"
                ] = model.NewIntVarFromDomain(
                    custom_domains["slot_cost"], f"slot_cost_{d}_{h}_{s}"
                )
    return [model, var_onboarding]


def constraint_honour_agent_availability_onboarding(
    model, var_onboarding, df_agents, agent_categories, config
):
    """Make sure that each onboarder's availability is honoured.

    Each shift must start and end within that agent's available hours.
    """
    for d in range(config["num_days"]):
        for h in agent_categories["onboarding"]:
            if not (h in agent_categories["unavailable"][d]):
                model.AddBoolOr(
                    var_onboarding["dh"].loc[(d, h), "is_in_pref_range"]
                ) .OnlyEnforceIf(var_onboarding["dh"].loc[(d, h), "is_agent_on"])
                for (j, sec) in enumerate(df_agents.loc[h, "slot_ranges"][d]):
                    model.Add(
                        var_onboarding["dh"].loc[(d, h), "shift_start"]
                        >= sec[0]
                    ).OnlyEnforceIf(
                        var_onboarding["dh"].loc[(d, h), "is_in_pref_range"][j]
                    )
                    model.Add(
                        var_onboarding["dh"].loc[(d, h), "shift_start"]
                        + var_onboarding["dh"].loc[(d, h), "shift_duration"]
                        <= sec[1]
                    ).OnlyEnforceIf(
                        var_onboarding["dh"].loc[(d, h), "is_in_pref_range"][j]
                    )

    return model


def constraint_setup_onboarding_hours(
    model, var_onboarding, agent_categories, config
):
    """Define shift length for onboarders, as well as total weekly support."""
    # If agent is on, the shift length must be <onboarding_shift_length> hours:
    for d in range(config["num_days"]):
        for h in agent_categories["onboarding"]:
            model.Add(
                var_onboarding["dh"].loc[(d, h), "shift_duration"]
                == onboarding_shift_length
            ).OnlyEnforceIf(var_onboarding["dh"].loc[(d, h), "is_agent_on"])
            model.Add(
                var_onboarding["dh"].loc[(d, h), "shift_duration"] == 0
            ).OnlyEnforceIf(
                var_onboarding["dh"].loc[(d, h), "is_agent_on"].Not()
            )

    # Agent is only scheduled for <onboarding_weekly_slots> hours for the week:
    for h in agent_categories["onboarding"]:
        model.Add(
            var_onboarding["h"].loc[h, "total_week_slots"]
            == sum(
                var_onboarding["dh"]["shift_duration"]
                .xs(h, axis=0, level=1, drop_level=False)
                .values.tolist()
            )
        )
        model.Add(
            var_onboarding["h"].loc[h, "total_week_slots"]
            == onboarding_weekly_slots
        )
    return model


def constraint_avoid_onboarding_before_Monday_1400(
    model, var_onboarding, agent_categories
):
    """Avoid onboarding on Mondays (d=0) before 14:00.

    This is to allow the Monday morning veterans to focus on clearing
    up the tickets that have piled up over the weekend.
    """
    # Constraint: There will be no onboarding on Mondays (d=0) before 14:00:
    for h in agent_categories["onboarding"]:
        model.Add(
            var_onboarding["dh"].loc[(0, h), "shift_start"] >= 28
        ).OnlyEnforceIf(var_onboarding["dh"].loc[(0, h), "is_agent_on"])
    return model


def constraint_avoid_simultaneous_onboarding(model, var_onboarding, config):
    """At most one agent should be onboarded at any given time.

    In other words, onboarding shifts should not overlap.
    """
    if len(var_onboarding["dh"]) > 0:
        for d in range(config["num_days"]):
            model.AddNoOverlap(
                var_onboarding["dh"].loc[d, "interval"].values.tolist()
            )

    return model


def constraint_configure_mentoring(
    model, var_veterans, var_onboarding, agent_categories, config
):
    """Configure the mentoring of onboarders appropriately."""
    # If agent is on, he/she to be paired with exactly 1 mentor:
    for d in range(config["num_days"]):
        for h in agent_categories["onboarding"]:
            model.Add(
                sum(var_onboarding["mentors"].loc[(d, h)].values.tolist()) == 1
            ).OnlyEnforceIf(var_onboarding["dh"].loc[(d, h), "is_agent_on"])
            model.Add(
                sum(var_onboarding["mentors"].loc[(d, h)].values.tolist()) == 0
            ).OnlyEnforceIf(
                var_onboarding["dh"].loc[(d, h), "is_agent_on"].Not()
            )

            for m in var_onboarding["mentors"].columns:
                is_mentor_on_list = []

                for t in tracks_in_day(d, config["tracks"]):
                    is_mentor_on_list.append(
                        var_veterans["tdh"].loc[(t, d, m), "is_agent_on"]
                    )

                model.AddBoolOr(is_mentor_on_list).OnlyEnforceIf(
                    var_onboarding["mentors"].loc[(d, h), m]
                )

                for t in tracks_in_day(d, config["tracks"]):
                    # The mentor and onboarder start at the same time.
                    model.Add(
                        var_onboarding["dh"].loc[(d, h), "shift_start"]
                        == var_veterans["tdh"].loc[(t, d, m), "shift_start"]
                    ).OnlyEnforceIf(
                        [
                            var_onboarding["mentors"].loc[(d, h), m],
                            var_veterans["tdh"].loc[(t, d, m), "is_agent_on"],
                        ]
                    )

                    # Mentor's shift may not be shorter than onboarder's:
                    model.Add(
                        var_onboarding["dh"].loc[(d, h), "shift_duration"]
                        - var_veterans["tdh"].loc[(t, d, m), "shift_duration"]
                        <= 0
                    ).OnlyEnforceIf(
                        [
                            var_onboarding["mentors"].loc[(d, h), m],
                            var_veterans["tdh"].loc[(t, d, m), "is_agent_on"],
                        ]
                    )

    # A mentor should not have to mentor more than 1 onboarder per day:
    for d in range(config["num_days"]):
        for m in var_onboarding["mentors"].columns:
            model.Add(
                sum(var_onboarding["mentors"].loc[(d,), m].values.tolist()) < 2
            )

    # To avoid overloading mentors, constrain weekly hours to <= 10 hours:
    #    for h in agents_mentors:
    #        model.Add(v_h.loc[h, "total_week_slots"] <= 10)

    return model


def cost_hours_onboarding(
    model, var_onboarding, coefficients, df_agents, agent_categories, config
):
    """Define onboarders' cost for assigned hours based on availability."""
    for d in range(config["num_days"]):
        for h in agent_categories["onboarding"]:
            for (s_count, s_cost) in enumerate(
                df_agents.loc[h, "slots"][d][
                    config["start_slot"] : config["end_slot"]
                ]
            ):
                s = s_count + config["start_slot"]

                model.Add(
                    var_onboarding["dh"].loc[(d, h), "shift_start"] <= s
                ).OnlyEnforceIf(
                    var_onboarding["dhs"].loc[
                        (d, h, s), "is_start_smaller_equal_hour"
                    ]
                )
                model.Add(
                    var_onboarding["dh"].loc[(d, h), "shift_start"] > s
                ).OnlyEnforceIf(
                    var_onboarding["dhs"]
                    .loc[(d, h, s), "is_start_smaller_equal_hour"]
                    .Not()
                )

                model.Add(
                    var_onboarding["dh"].loc[(d, h), "shift_end"] > s
                ).OnlyEnforceIf(
                    var_onboarding["dhs"].loc[
                        (d, h, s), "is_end_greater_than_hour"
                    ]
                )
                model.Add(
                    var_onboarding["dh"].loc[(d, h), "shift_end"] <= s
                ).OnlyEnforceIf(
                    var_onboarding["dhs"]
                    .loc[(d, h, s), "is_end_greater_than_hour"]
                    .Not()
                )

                model.AddBoolAnd(
                    [
                        var_onboarding["dhs"].loc[
                            (d, h, s), "is_start_smaller_equal_hour"
                        ],
                        var_onboarding["dhs"].loc[
                            (d, h, s), "is_end_greater_than_hour"
                        ],
                    ]
                ).OnlyEnforceIf(
                    var_onboarding["dhs"].loc[(d, h, s), "is_slot_cost"]
                )

                model.AddBoolOr(
                    [
                        var_onboarding["dhs"]
                        .loc[(d, h, s), "is_start_smaller_equal_hour"]
                        .Not(),
                        var_onboarding["dhs"]
                        .loc[(d, h, s), "is_end_greater_than_hour"]
                        .Not(),
                    ]
                ).OnlyEnforceIf(
                    var_onboarding["dhs"].loc[(d, h, s), "is_slot_cost"].Not()
                )
                # For "preferred", (s_cost - 1) = 0, so no hourly cost.
                # For "non_preferred", (s_cost - 1) = 1.
                model.Add(
                    var_onboarding["dhs"].loc[(d, h, s), "slot_cost"]
                    == coefficients["non_preferred"] * (s_cost - 1)
                ).OnlyEnforceIf(
                    var_onboarding["dhs"].loc[(d, h, s), "is_slot_cost"]
                )

                model.Add(
                    var_onboarding["dhs"].loc[(d, h, s), "slot_cost"] == 0
                ).OnlyEnforceIf(
                    var_onboarding["dhs"].loc[(d, h, s), "is_slot_cost"].Not()
                )

    return model


def extend_model_onboarding(
    model,
    var_veterans,
    custom_domains,
    full_cost_list,
    coefficients,
    df_agents,
    agent_categories,
    config,
):
    # Configure model variables:
    var_onboarding = setup_var_dataframes_onboarding(agent_categories, config)
    [model, var_onboarding] = fill_var_dataframes_onboarding(
        model,
        custom_domains,
        var_onboarding,
        df_agents,
        agent_categories,
        config,
    )
    # Add constraints:
    model = constraint_honour_agent_availability_onboarding(
        model, var_onboarding, df_agents, agent_categories, config
    )
    model = constraint_setup_onboarding_hours(
        model, var_onboarding, agent_categories, config
    )
    model = constraint_avoid_onboarding_before_Monday_1400(
        model, var_onboarding, agent_categories
    )
    model = constraint_avoid_simultaneous_onboarding(
        model, var_onboarding, config
    )
    model = constraint_configure_mentoring(
        model, var_veterans, var_onboarding, agent_categories, config
    )
    # Add cost:
    model = cost_hours_onboarding(
        model,
        var_onboarding,
        coefficients,
        df_agents,
        agent_categories,
        config,
    )

    # Extend list of cost terms:
    full_cost_list = (
        full_cost_list + var_onboarding["dhs"]["slot_cost"].values.tolist()
    )
    return [model, var_veterans, var_onboarding, full_cost_list]
