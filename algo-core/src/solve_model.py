from ortools.sat.python import cp_model
from custom_var_domains import define_custom_var_domains
from veterans import setup_model_veterans
from onboarding import extend_model_onboarding

# Cost coefficients assigned to various soft constraints:
coefficients = {
    "non-preferred": 4,
    "shorter_than_pref": 4,
    "longer_than_pref": 4,
    "coeff_fair_share": 2
}


def solve_model_and_extract_solution(model, full_cost_list, agent_categories, config):
    """Solve model, extract, print and save """
    model.Minimize(sum(full_cost_list))
    print(model.Validate())

    # Solve model:
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = config["optimization_timeout"]
    solver.parameters.log_search_progress = True
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)
    print(solver.StatusName(status))

    if not (status in [cp_model.OPTIMAL, cp_model.FEASIBLE]):
        print("Cannot create schedule")
        return

    else:
        # Extract solution:
        print("\n---------------------")
        print("| OR-Tools schedule |")
        print("---------------------")

        print("\nSolution type: ", solver.StatusName(status))
        print("\nMinimized cost: ", solver.ObjectiveValue())
        print("After", solver.WallTime(), "seconds.\n")
        schedule_results = []

        # This file will contain the onboarding message for Flowdock:
        if len(agent_categories["onboarding"]) > 0:
            o_path = "onboarding_message.txt"
            o_file = open(o_path, "w")
            o_file.write(
                "**Support agent onboarding next week**"
                "\n\nEach new onboarding agent has been paired with a senior "
                "support agent for each of their shifts. The senior agent "
                "will act as a mentor for the onboarding agents, showing "
                "them the ropes during these onboarding shifts (see the "
                "[onboarding document]"
                "(https://github.com/balena-io/process/blob/master/process/support/onboarding_agents_to_support.md) "
                "for background). Here are the mentor-novice pairings "
                "for next week:"
            )

        for d in range(config["num_days"]):
            if len(agent_categories["onboarding"]) > 0:
                o_file.write(
                    f"\n\n**Onboarding on {days[d].strftime('%Y-%m-%d')}**"
                )

            day_dict = {"start_date": days[d], "shifts": []}

            for t, track in enumerate(tracks):
                if d in range(track["start_day"], track["end_day"] + 1):
                    for h in agents_vet:
                        if (
                            solver.Value(
                                v_tdh.loc[(t, d, h), "shift_duration"]
                            )
                            != 0
                        ):
                            day_dict["shifts"].append(
                                (
                                    h,
                                    solver.Value(
                                        v_tdh.loc[(t, d, h), "shift_start"]
                                    ),
                                    solver.Value(
                                        v_tdh.loc[(t, d, h), "shift_end"]
                                    ),
                                )
                            )

            for h in agent_categories["onboarding"]:
                if solver.Value(v_dh_on.loc[(d, h), "shift_duration"]) != 0:
                    day_dict["shifts"].append(
                        (
                            h,
                            solver.Value(v_dh_on.loc[(d, h), "shift_start"]),
                            solver.Value(v_dh_on.loc[(d, h), "shift_end"]),
                        )
                    )

                for m in v_mentors.columns:
                    if solver.Value(v_mentors.loc[(d, h), m]) == 1:
                        o_file.write(f"\n{m} will mentor {h}")

            schedule_results.append(day_dict)
        if len(agent_categories["onboarding"]) > 0:
            o_file.write("\n\ncc @@support_ops")
            o_file.close()

        # Sort shifts by start times to improve output readability:
        for i in range(len(schedule_results)):
            shifts = schedule_results[i]["shifts"]
            sorted_shifts = sorted(shifts, key=lambda x: x[1])
            schedule_results[i]["shifts"] = sorted_shifts

        return scheduler_utils.print_final_schedules(
            schedule_results, df_agents, config["num_days"]
        )  # Add input_folder as last arg here.


def generate_solution(df_agents, agent_categories, config):
    # Define custom variable domains:
    custom_domains = define_custom_var_domains(coefficients, df_agents, config)
    # Initialize model:
    model = cp_model.CpModel()
    # Set up model for veterans:
    [model, var_veterans, full_cost_list] = setup_model_veterans(model, custom_domains, coefficients, df_agents, agent_categories, config)
    # Extend model for onboarding if necessary:
    if len(agent_categories["onboarding"] > 0):
        [model, var_veterans, var_onboarding, full_cost_list] = extend_model_onboarding(model, var_veterans, custom_domains, full_cost_list, coefficients, df_agents, agent_categories, config)
    


# Implement constraints - veterans:
# constraint_new_agents_non_simultaneous()

  

# Solve model, extract and print solution:
final_schedule = solve_model_and_extract_solution()
