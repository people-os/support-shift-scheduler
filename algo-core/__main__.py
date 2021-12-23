from src.read_input import read_input_files
from src.process_input import process_input_data
from src.solve_model import generate_solution

# Read input:
[input_json, sr_onboarding, sr_mentors] = read_input_files()

# Transform input:
[df_agents, agent_categories, config] = process_input_data(
    input_json, sr_onboarding, sr_mentors
)

# Configure and solve model:

solution = generate_solution(df_agents, agent_categories, config)



# TODO: configure functionality for volunteered shifts.
