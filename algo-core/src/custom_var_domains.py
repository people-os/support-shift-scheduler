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
from ortools.sat.python import cp_model
import pandas as pd

from .veterans import week_working_slots


def define_custom_var_domains(coefficients, df_agents, config):
    """Define custom model variable domains."""
    custom_domains = {}

    # slot cost domain:
    values_list = []
    for allowed_availability in config["allowed_availabilities"]:
        values_list.append(
            coefficients["non_preferred"] * (allowed_availability - 1)
        )
    custom_domains["slot_cost"] = cp_model.Domain.FromValues(values_list)

    # Duration domain:
    custom_domains["duration"] = cp_model.Domain.FromIntervals(
        [[0, 0], [config["min_duration"], config["max_duration"]]]
    )

    # Create preference domains:
    dh_multi_index = pd.MultiIndex.from_product(
        [[d for d in range(config["num_days"])], [h for h in df_agents.index]],
        names=("day", "handle"),
    )

    custom_domains["prefs"] = pd.Series(
        data=None, index=dh_multi_index, dtype="float64"
    )

    for d in range(config["num_days"]):
        for h in df_agents.index:
            custom_domains["prefs"].loc[
                (d, h)
            ] = cp_model.Domain.FromIntervals(
                df_agents.loc[h, "slot_ranges"][d]
            )

    # Duration cost domain:
    duration_cost_list = set(
        [
            coefficients["shorter_than_pref"] * x
            for x in range(0, config["max_duration"] - config["min_duration"])
        ]
    )
    duration_cost_list = list(
        duration_cost_list.union(
            set(
                [
                    coefficients["longer_than_pref"] * x
                    for x in range(
                        0, config["max_duration"] - config["min_duration"]
                    )
                ]
            )
        )
    )
    duration_cost_list.sort()
    custom_domains["duration_cost"] = cp_model.Domain.FromValues(
        duration_cost_list
    )

    # Total slots per week cost domain:
    total_week_slots_cost_list = [
        coefficients["fair_share"] * x
        for x in range(
            0,
            week_working_slots**2
            - 2 * week_working_slots * config["min_fair_share"]
            + (config["min_fair_share"]) ** 2,
        )
    ]

    custom_domains["total_week_slots_cost"] = cp_model.Domain.FromValues(
        total_week_slots_cost_list
    )

    return custom_domains
