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
from src.read_input import read_input_files
from src.process_input import process_input_data
from src.solve_model import generate_solution

# Read input:
[input_json, sr_onboarding, sr_mentors] = read_input_files()

# Transform input:
[df_agents, agent_categories, config] = process_input_data(
    input_json, sr_onboarding, sr_mentors
)

# Configure, solve and save model:
solution = generate_solution(df_agents, agent_categories, config)

# TODO: configure functionality for volunteered shifts.
