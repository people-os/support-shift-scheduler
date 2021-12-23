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
import math
import colorama
import onboarding
import scheduler_utils
import pandas as pd
from ortools.sat.python import cp_model

# The availabilities we allow, by default 1 and 2, but 3 can be added as well if no schedule is feasible without




# Other constants:
# max_avg_per_week = 80
week_working_slots = 80


def flatten(lists):
    """Flatten nested lists."""
    for el in lists:
        if isinstance(el, collections.Iterable) and not isinstance(
            el, (str, bytes)
        ):
            yield from flatten(el)
        else:
            yield el

v_mentors, v_h_on, v_dh_on, v_dhs_on, agents_onb, num_days, start_hour, end_hour















# MODEL:

