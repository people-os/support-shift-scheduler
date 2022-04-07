"""
Copyright 2019-2022 Balena Ltd.

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


def tracks_hours_to_slots(tracks):
    for track in tracks:
        track["start_slot"] = track["start_hour"] * 2
        track["end_slot"] = track["end_hour"] * 2
    return tracks


def get_total_slots_covered(tracks):
    total_slots_covered = 0
    for t, track in enumerate(tracks):
        for d in range(track["start_day"], track["end_day"] + 1):
            total_slots_covered += 2 * (
                track["end_hour"] - track["start_hour"]
            )
    return total_slots_covered


def get_datetime_days(start_date, num_days):
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


def calculate_fair_shares(df_agents, total_slots_covered, config):
    """Determine fair share per agent

    Fair share is based on hours to be covered, and agents' current
    teamwork balances."""
    df_agents["fair_share"] = [-x for x in df_agents["teamwork_balance"].tolist()]
    # unadjusted_slots_per_agent = total_slots_covered / float(len(df_agents))
    # df_agents["fair_share"] = [
    #     (unadjusted_slots_per_agent + (-x) ** 0.5) if x < 0 else 
    #     (unadjusted_slots_per_agent - x ** 0.5)
    #     for x in df_agents["teamwork_balance"].tolist()
    # ]    
    df_agents["fair_share"] = df_agents["fair_share"] - df_agents["fair_share"].min()

    rescaling_factor = total_slots_covered / df_agents["fair_share"].sum()
    df_agents["fair_share"] = df_agents["fair_share"] * rescaling_factor
    df_agents["fair_share"] = df_agents["fair_share"].apply(
        lambda x: math.trunc(x)
    )
    print("Fair shares (hours per week):\n")
    print(df_agents["fair_share"]/2.0)
    return df_agents


def setup_agents_dataframe(agents, config):
    """Set up dataframe containing the relevant properties of each agent."""
    df_agents = pd.DataFrame(
        data=None,
        columns=[
            "handle",
            "email",
            "teamwork_balance",
            "ideal_shift_length",
            "slots",
            "slot_ranges",
        ],
    )

    # Fill dataframes per agent:
    for agent in agents:
        available_slots = agent["availableSlots"]

        for (d, _) in enumerate(available_slots):
            # Set availability to 0 outside balena support hours:
            for i in range(config["start_slot"]):
                available_slots[d][i] = 0
            # For agents with fixed hours, remove all availability:
            # TODO: when volunteered shifts are reconfigured, we need to make sure these are not zeroed out below:
            if (
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
            "teamwork_balance": 2
            * math.trunc(float(agent["teamworkBalance"])),
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

    # Determine unavailable agents for each day, and remove these dataframe entries:
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
    df_agents = calculate_fair_shares(df_agents, config["total_slots_covered"], config)

    return [df_agents, unavailable_agents]


def process_input_data(input_json, sr_onboarding, sr_mentors):
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
    config["optimization_timeout"] = 3600 * int(
        input_json["options"]["optimizationTimeout"]
    )
    config["tracks"] = tracks_hours_to_slots(input_json["options"]["tracks"])
    config["special_agent_conditions"] = input_json["options"][
        "specialAgentConditions"
    ]

    # Additional properties:
    config["allowed_availabilities"] = [1, 2]
    if input_json["options"]["useThrees"]:
        config["allowed_availabilities"].append(3)

    config["total_slots_covered"] = get_total_slots_covered(config["tracks"])
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
