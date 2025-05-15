"""
Copyright 2019-2025 Balena Ltd.

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

import datetime
import math
import pandas as pd
import numpy as np

# A higher value here will compensate more aggressively for historical
# teamwork balances:
rebalancing_urgency = 7

# def tracks_hours_to_slots(tracks):
#     for track in tracks:
#         track["start_slot"] = track["start_hour"] * 2
#         track["end_slot"] = track["end_hour"] * 2
#     return tracks


# def get_total_slots_covered(tracks):
#     total_slots_covered = 0
#     for t, track in enumerate(tracks):
#         for d in range(track["start_day"], track["end_day"] + 1):
#             total_slots_covered += 2 * (
#                 track["end_hour"] - track["start_hour"]
#             )
#     return total_slots_covered


def get_total_slots_covered(hours_coverage):
    """Calculate (maximum) total slots to be covered for the week."""
    total_slots_covered = 0
    for day_cover in hours_coverage:
        total_slots_covered += day_cover["max_slots"]
    return total_slots_covered


def get_datetime_days(start_date, num_days):
    """Generate list of dates over which schedule needs to be generated."""
    delta = datetime.timedelta(days=1)
    days = [start_date]

    for d in range(1, num_days):
        days.append(days[d - 1] + delta)
    return days


def slots_to_range(available_slots, end_slot, allowed_availabilities):
    """Convert per-hour availability flags into ranges format."""
    slot_ranges = []

    for day_slots in available_slots:
        day_ranges = []
        start = None

        for i, value in enumerate(day_slots):
            # Start of new range:
            if start is None and value != 0:
                start = i
                continue

            # End of range:
            # (A range will end if either the current slot is unavailable
            # (value 0) or if the current slot is the last one.)
            if start is not None:
                if value not in allowed_availabilities:  # Unavailable
                    day_ranges.append([start, i])
                    start = None
                elif i == end_slot - 1:  # Last slot
                    day_ranges.append([start, end_slot])
                else:
                    continue

        slot_ranges.append(day_ranges)
    return slot_ranges


def get_unavailable_agents(df_agents, day):
    """Determine agents with no availability for a given day."""
    day_number = day.weekday()
    unavailable = set()

    for handle in df_agents.index:
        if len(df_agents.loc[handle, "slot_ranges"][day_number]) == 0:
            unavailable.add(handle)

    print(f"\nUnavailable employees for day starting on {day}")
    [print(e) for e in unavailable]
    return unavailable


def remove_agents_not_available_this_week(
    unavailable_agents, df_agents, num_days
):
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


def calculate_fair_shares(df_agents, total_slots_covered):
    """Determine fair share per agent.

    Fair share is based on hours to be covered, agents' responsibility
    weights, existing scheduled teamwork for next week, and agents'
    current teamwork balances.
    """
    total_next_week = total_slots_covered + df_agents["next_week_credit"].sum()
    df_agents["fair_share"] = (
        total_next_week
        * df_agents["weight"]
        / df_agents["weight"].sum()
        * (
            1
            - np.tanh(
                0.0001 * rebalancing_urgency * df_agents["teamwork_balance"]
            )
        )
    )
    rescaling_factor1 = total_next_week / df_agents["fair_share"].sum()
    df_agents["fair_share"] = df_agents["fair_share"] * rescaling_factor1
    df_agents["fair_share"] = (
        df_agents["fair_share"] - df_agents["next_week_credit"]
    )
    df_agents["fair_share"] = df_agents["fair_share"].apply(
        lambda x: x if x >= 0 else 0
    )
    rescaling_factor2 = total_slots_covered / df_agents["fair_share"].sum()
    df_agents["fair_share"] = df_agents["fair_share"] * rescaling_factor2
    df_agents["fair_share"] = df_agents["fair_share"].apply(
        lambda x: math.trunc(x)
    )
    print("\nFair shares (hours per week):\n")
    print((df_agents["fair_share"] / 2.0).to_string())
    return df_agents


def setup_agents_dataframe(agents, config):
    """Set up dataframe containing the relevant properties of each agent."""
    df_agents = pd.DataFrame(
        data=None,
        columns=[
            "handle",
            "email",
            "weight",
            "is_support_engineer",
            "teamwork_balance",
            "next_week_credit",
            "ideal_shift_length",
            "slots",
            "slot_ranges",
        ],
    )

    # Fill dataframes per agent:
    for agent in agents:
        available_slots = agent["availableSlots"]

        for d, _ in enumerate(available_slots):
            # Set availability to 0 outside balena support hours:
            for i in range(config["start_slot"]):
                available_slots[d][i] = 0
            # For agents with fixed hours, remove all availability:
            # TODO: when volunteered shifts are reconfigured,
            # we need to make sure these are not zeroed out below:
            if ("agentsFixHours" in config["special_agent_conditions"]) and (
                agent["handle"]
                in config["special_agent_conditions"]["agentsFixHours"]
            ):
                for s in range(0, config["end_slot"]):
                    available_slots[d][s] = 0

        slot_ranges = slots_to_range(
            available_slots,
            config["end_slot"],
            config["allowed_availabilities"],
        )

        df_agents.loc[len(df_agents)] = {
            "handle": agent["handle"],
            "email": agent["email"],
            "weight": agent["weight"],
            "is_support_engineer": int(agent["isSupportEngineer"]),
            "teamwork_balance": 2 * float(agent["teamworkBalance"]),
            "next_week_credit": 2 * float(agent["nextWeekCredit"]),
            "ideal_shift_length": agent["idealShiftLength"] * 2,
            "slots": available_slots,
            "slot_ranges": slot_ranges,
        }

    # slots: list of 5 lists, each of which has items that mark the
    # availability of each slot (e.g.
    # [ [0,0,0,0,...,1,2,0,0], [0,0,0,0,...,1,2,0,0], [...], [...], [...] ])

    # slot_ranges: list of 5 lists, each of the 5 lists has a number
    # of nested lists that mark the ranges that an agent is available to do
    # support (e.g. [ [[8,12], [16, 24]], [], [...], [...], [...])
    # NB: e.g. [8,12] indicates agent is available 8-12, NOT 8-13.

    df_agents.set_index("handle", inplace=True)

    # Determine unavailable agents for each day, and remove these
    # dataframe entries:
    unavailable_agents = []

    for d in range(config["num_days"]):
        unavailable_agents.append(
            get_unavailable_agents(df_agents, config["days"][d])
        )

    # Remove agents from the model who are not available at all this week:
    df_agents = remove_agents_not_available_this_week(
        unavailable_agents, df_agents, config["num_days"]
    )

    # Calculate fair shares per agent:
    df_agents = calculate_fair_shares(df_agents, config["total_slots_covered"])
    return [df_agents, unavailable_agents]


def process_input_data(input_json, sr_onboarding, sr_mentors):
    """Convert json input to convenient Python variables."""
    # Properties derived from input:
    config = {}
    config["start_date"] = datetime.datetime.strptime(
        input_json["options"]["startMondayDate"], "%Y-%m-%d"
    ).date()
    config["model_name"] = input_json["options"]["modelName"]
    config["num_days"] = int(input_json["options"]["numDays"])
    config["start_slot"] = int(input_json["options"]["startHour"] * 2)
    config["end_slot"] = int(input_json["options"]["endHour"] * 2)
    config["min_duration"] = int(input_json["options"]["shiftMinDuration"]) * 2
    config["max_duration"] = int(input_json["options"]["shiftMaxDuration"]) * 2
    config["optimization_timeout"] = int(
        3600 * input_json["options"]["optimizationTimeout"]
    )
    config["special_agent_conditions"] = input_json["options"][
        "specialAgentConditions"
    ]
    config["hours_coverage"] = input_json["options"]["hoursCoverage"]
    for h_cover, _ in enumerate(config["hours_coverage"]):
        config["hours_coverage"][h_cover]["min_slots"] = (
            config["hours_coverage"][h_cover]["min_hours"] * 2
        )
        config["hours_coverage"][h_cover]["max_slots"] = (
            config["hours_coverage"][h_cover]["max_hours"] * 2
        )

    config["agent_distribution"] = input_json["options"]["agentDistribution"]
    for a_distribution, _ in enumerate(config["agent_distribution"]):
        config["agent_distribution"][a_distribution]["start_slot"] = (
            config["agent_distribution"][a_distribution]["start_hour"] * 2
        )
        config["agent_distribution"][a_distribution]["end_slot"] = (
            config["agent_distribution"][a_distribution]["end_hour"] * 2
        )

    # Additional properties:
    config["allowed_availabilities"] = [1]
    if input_json["options"]["useTwos"]:
        config["allowed_availabilities"].append(2)
    if input_json["options"]["useThrees"]:
        config["allowed_availabilities"].append(3)

    config["max_shifts_per_agent_per_day"] = int(
        input_json["options"]["maxShiftsPerAgentPerDay"]
    )

    config["total_slots_covered"] = get_total_slots_covered(
        config["hours_coverage"]
    )
    config["days"] = get_datetime_days(
        config["start_date"], config["num_days"]
    )

    # Set up agents dataframe, and unavailable category:
    agent_categories = {}
    [df_agents, agent_categories["unavailable"]] = setup_agents_dataframe(
        input_json["agents"], config
    )

    # Find minimum and maximum fair shares:
    config["min_fair_share"] = df_agents["fair_share"].min()
    config["max_fair_share"] = df_agents["fair_share"].max()

    # Onboarding agent category:
    agent_categories["onboarding"] = df_agents[
        df_agents.index.isin(sr_onboarding.tolist())
    ].index.tolist()

    # Veteran agent category (all "non-onboarders"):
    agent_categories["veterans"] = df_agents[
        ~df_agents.index.isin(sr_onboarding.tolist())
    ].index.tolist()

    # Mentors for onboarding agents (they are all also included in agents_vet).
    # (Filter, since some mentors may be on leave that week:)
    agent_categories["mentors"] = [
        x for x in sr_mentors.tolist() if x in df_agents.index
    ]
    return [df_agents, agent_categories, config]
