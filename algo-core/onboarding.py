import pandas as pd
from ortools.sat.python import cp_model

# Onboarding:
onboarding_shift_length = 4
onboarding_weekly_hours = 8


def tracks_in_day(d: int, tracks):
    tracks_containing_d = []
    for t, track in enumerate(tracks):
        if d in range(track["start_day"], track["end_day"]+1):
            tracks_containing_d.append(t)

    return tracks_containing_d

def setup_var_dataframes_onboarding(number_days, agents_onboarding, agents_mentors,starting_hour, ending_hour ):
    """Create dataframes that will contain model variables for onboarders."""
    global v_mentors, v_h_on, v_dh_on, v_dhs_on, agents_onb, num_days, start_hour, end_hour

    agents_onb = agents_onboarding
    num_days = number_days
    start_hour = starting_hour
    end_hour = ending_hour
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
    return v_mentors, v_h_on, v_dh_on, v_dhs_on


def fill_var_dataframes_onboarding(model, agents_mentors, week_working_hours, unavailable_agents, d_prefs,
                                   df_agents, d_hour_cost):
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
    return model
#
# Constraints
#


def constraints_for_onboarding(model, unavailable_agents, df_agents, tracks, v_tdh):
    model = constraint_honour_agent_availability_onboarding(model, unavailable_agents, df_agents)
    model = constraint_setup_onboarding_hours(model)
    model = constraint_avoid_onboarding_before_Monday_1400(model)
    model = constraint_avoid_simultaneous_onboarding(model)
    model = constraint_configure_mentoring(model, tracks, v_tdh)

    return model


def constraint_honour_agent_availability_onboarding(model, unavailable_agents, df_agents):
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

    return model


def constraint_setup_onboarding_hours(model):
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

    return model


def constraint_avoid_onboarding_before_Monday_1400(model):
    """Avoid onboarding on Mondays (d=0) before 14:00.

    This is to allow the Monday morning veterans to focus on clearing
    up the tickets that have piled up over the weekend.
    """
    # Constraint: There will be no onboarding on Mondays (d=0) before 14:00:
    for h in agents_onb:
        model.Add(v_dh_on.loc[(0, h), "shift_start"] >= 14).OnlyEnforceIf(
            v_dh_on.loc[(0, h), "is_agent_on"]
        )

    return model


def constraint_avoid_simultaneous_onboarding(model):
    """At most one agent should be onboarded at any given time.

    In other words, onboarding shifts should not overlap.
    """
    if len(v_dh_on) > 0:
        for d in range(num_days):
            model.AddNoOverlap(v_dh_on.loc[d, "interval"].values.tolist())

    return model


def constraint_configure_mentoring(model, tracks, v_tdh):
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

                for t in tracks_in_day(d, tracks):
                    is_mentor_on_list.append(
                        v_tdh.loc[(t, d, m), "is_agent_on"]
                    )

                model.AddBoolOr(is_mentor_on_list).OnlyEnforceIf(
                    v_mentors.loc[(d, h), m]
                )

                for t in tracks_in_day(d, tracks):
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

    return model


def cost_hours_onboarding(model, df_agents, coeff_non_preferred):
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

    return model
