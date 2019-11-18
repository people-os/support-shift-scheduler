import sys
import json
from datetime import timedelta
from dateutil.parser import parse as dateparse
import argparse
import jsonschema
from ortools.sat.python import cp_model
import math
import collections
import pandas as pd

       
        
def hours2range(week_hours):
    """ Convert per-hour availability flags into ranges format. """
    week_ranges = []

    for day_hours in week_hours:

        day_ranges = []
        start = None

        for i, value in enumerate(day_hours):

            # Start of new range:
            if (start == None and value != 0):
                start = i
                continue

            # End of range:
            # (A range will end if either the current slot is unavailable 
            # (value 0) or if the current slot is the last one.)
            if (start != None):
                if (value == 0): # Unavailable
                    day_ranges.append([start, i])
                    start = None
                elif (i == end_hour - 1): # Last slot
                    day_ranges.append([start, end_hour])
                else:
                    continue

        week_ranges.append(day_ranges)

    return week_ranges


def setup_dataframes():
    """ Set up dataframes for agents (df_a) and night shift info (df_n). """
    
    global min_week_average_hours  
    
    min_week_average_hours = 100  # This will form a baseline for agent history. 
    agents = input_json["agents"]
    
    df_a = pd.DataFrame(data=None, columns=[
                       'Handle', 'Email', 'AvgHoursPerWeek', 'PrefIdealLength',
                       'Hours', 'HourRanges'
                       ])

    df_n_indices = pd.MultiIndex.from_product(
        [[t for t in range(num_tracks)], [d for d in range(num_days)]], 
        names=('Track', 'Day')
        )
    
    df_n = pd.DataFrame(data='', columns=list(range(19, 24)), 
                             index=df_n_indices)
    
    for agent in agents:
        week_average_hours = math.trunc(
            float(agent['week_average_hours'])
            )
        min_week_average_hours = min(min_week_average_hours, 
                                     week_average_hours)
        
        week_hours = agent['available_hours']
        
        for (d, _) in enumerate(week_hours):
            
            # Set availability to 0 outside balena support hours:
            
            for i in range(start_hour):
                week_hours[d][i] = 0
            for i in range(end_hour, num_slots):
                week_hours[d][i] = 0
            
            # Fill df_n dataframe with night shifts:
            
            indices_3 = [i for i, x in enumerate(week_hours[d]) if x == 3]
            
            if len(indices_3)>0:
                
                start = indices_3[0]
                end = indices_3[-1] + 1
                
                if len(indices_3) == 5:
                    if list(df_n.loc[(0, d)]) == ['', '', '', '', '']:
                        t=0
                    else:
                        t=1
                    
                    for s in indices_3:
                        df_n.loc[(t, d), s] = agent['handle']
                        
                else:   # Always have the half-shifts in track t=1:
                    for s in indices_3:
                        df_n.loc[(1, d), s] = agent['handle']
                
                # Reset agent preference to 2 for duration of night shift:
                
                week_hours[d][start:end] = [2 for i in range(start, end)]
                
                # Give agent a break until 15:00 the next day if he/she was
                # on night shift:
                
                if d != 4:
                    week_hours[d+1][0:15] = [0 for i in range(15)]
        
        hour_ranges = hours2range(week_hours)
        
        df_a.loc[len(df_a)] = {
            'Handle': agent['handle'],
            'Email': agent['email'],
            'AvgHoursPerWeek': week_average_hours,
            'PrefIdealLength': agent['ideal_shift_length'], 
            'Hours': week_hours,
            'HourRanges': hour_ranges
            }

    # Hours: list of 5 lists, each of which has 24 items that mark the 
    # availability of each hour (e.g. 
    # [ [0,0,0,0,...,1,2,0,0], [0,0,0,0,...,1,2,0,0], [...], [...], [...] ])
    
    # HourRanges: list of 5 lists, each of the 5 lists has a number 
    # of nested lists that mark the ranges that an agent is available to do 
    # support (e.g. [ [[8,12], [16, 24]], [], [...], [...], [...])
    # NB: e.g. [8,12] indicates agent is available 8-12, NOT 8-13.
        
    df_a.set_index('Handle', inplace=True)
    
    return [df_a, df_n]


def get_unavailable_employees(day):
    """ Exclude employees with no availability for a given day. """
    
    dayNumber = day.weekday()
    unavailable = set()
    
    for handle in df_agents.index:
        if len(df_agents.loc[handle, 'HourRanges'][dayNumber])==0:
            unavailable.add(handle)
     
    print('\nUnavailable employees on %s' % day)
    [print(e) for e in unavailable]
    
    return unavailable


def remove_agents_not_available_this_week():
    """ Agents not available at all this week are removed from the model. """
    
    print('')
    global df_agents
    
    for handle in df_agents.index:
        
        out = True
        
        for d in range(num_days):
            out = out and (handle in unavailable_employees[d])
        
        if out:
            df_agents.drop(index=handle, inplace=True)
            print(handle, 'was removed for this week.')


def print_final_schedules(schedule_results):
    """ Print final schedule, validate output JSON, and write to file. """
    
    for d in range(num_days):
        
        print('\n%s shifts:' 
              % schedule_results[d]['start_date'].strftime("%Y-%m-%d"))
        
        for (i, e) in enumerate(schedule_results[d]['shifts']):
            print(e)
            
    output_json = []
    
    for epoch in schedule_results:
        # Substitute agent info from 'handle' to 'handle <email>'
        shifts = []
        
        for (name, start, end) in epoch['shifts']:
            shifts.append(
                {"agent": "%s <%s>" % (name, df_agents.loc[name, 'Email']), 
                 "start": start,
                 "end": end}
                )
        
        day_dict = {}
        day_dict['start_date'] = epoch['start_date'].strftime("%Y-%m-%d")
        day_dict["shifts"] = shifts
        output_json.append(day_dict)
    
    # JSON output format
    # {
    #   "start_date": YYYY-MM-DD # date is in YYYY-MM-DD format
    #   "shifts": [{
    #       "@agentHandle <agentEmail>": [ startHour, endHour ],
    #       '...'
    #   }]
    # }
    
#    print(json.dumps(output_json, indent=4), file=sys.stdout)
    
    output_json_schema = json.load(
        open('../lib/schemas/support-shift-scheduler-output.schema.json')
        )    
    
    try:
        jsonschema.validate(output_json, output_json_schema)
    except jsonschema.exceptions.ValidationError as err:
        print('Output JSON validation error', err)
        sys.exit(1)
    
    print('\nSuccessfully validated JSON output.')
    
    with open('support-shift-scheduler-output.json', 'w') as outfile:  
        outfile.write(json.dumps(output_json, indent=4))
    
    return output_json


def flatten(l):
    """ Flatten nested lists. """
    
    for el in l:
        if isinstance(el, collections.Iterable) and not isinstance(el, (str, bytes)):
            yield from flatten(el)
        else:
            yield el


def generate_schedule_with_ortools():
    """ Create and solve model with OR-Tools, producing final schedule. """
    
    global df_agents
    
    # In this function, the following abbreviations are used:
    # t: track
    # d: day
    # h: Github handle
    # s: slot number
    
    model = cp_model.CpModel()
    
    # Constants / domains:
    
    v_constant2 = model.NewIntVar(2, 2, 'constant2')
    d_hourCost = cp_model.Domain.FromValues([0, 80])
    d_duration = cp_model.Domain.FromIntervals(
                     [[0, 0], [min_duration, max_duration]]
                     )
    
    # Create preference domains:
    
    dh_index_array = [[], []]
    
    for d in range(num_days):
        for h in df_agents.index:
            dh_index_array[0].append(d)
            dh_index_array[1].append(h)
    
    dh_multi_index = pd.MultiIndex.from_arrays(dh_index_array, 
                                            names=('Day', 'Handle'))
    
    d_prefs = pd.Series(data=None, index=dh_multi_index)
    
    for d in range(num_days):
        for h in df_agents.index:
            d_prefs.loc[(d, h)] = cp_model.Domain.FromIntervals(
                                      df_agents.loc[h, 'HourRanges'][d]
                                      )
    
    # Indexed by handle:
    
    v_h = pd.DataFrame(data=None, index=df_agents.index, columns=[
              'TotalWeekHours', 'TotalWeekHoursSquared', 'TotalWeekHoursCost'
              ])
    
    # Indexed by track, day:
    
    td_index_array = [[], []]
    
    for t in range(num_tracks):
        for d in range(num_days):
            td_index_array[0].append(t)
            td_index_array[1].append(d)
    
    td_multi_index = pd.MultiIndex.from_arrays(td_index_array, 
                                            names=('Track', 'Day'))
    
    v_td = pd.DataFrame(data=None, index=td_multi_index, 
                        columns=['HandoverCost'])
    
    # Indexed by track, day, handle:
    
    tdh_index_array = [[], [], []]
    
    for t in range(num_tracks):
        for d in range(num_days):
            for h in df_agents.index:
                tdh_index_array[0].append(t)
                tdh_index_array[1].append(d)
                tdh_index_array[2].append(h)
                
    tdh_multi_index = pd.MultiIndex.from_arrays(tdh_index_array, 
                                            names=('Track', 'Day', 'Handle'))
    
    v_tdh = pd.DataFrame(data=None, index=tdh_multi_index, columns=[
                     'Start', 'End', 'Duration', 'Interval', 'IsAgentOn',
                     'AgentCost', 'IsDurationShorterThanIdeal',
                     'DurationCost', 'IsInPrefRange'
                     ])
    
    # Indexed by track, day, handle, slot:
    
    tdhs_index_array = [[], [], [], []]
    
    for t in range(num_tracks):
        for d in range(num_days):
            for h in df_agents.index:
                for s in range(start_hour, end_hour):
                    tdhs_index_array[0].append(t)
                    tdhs_index_array[1].append(d)
                    tdhs_index_array[2].append(h)
                    tdhs_index_array[3].append(s)
    
    tdhs_multi_index = pd.MultiIndex.from_arrays(
                           tdhs_index_array, 
                           names=('Track', 'Day', 'Handle', 'Slot')
                           )
    
    v_tdhs = pd.DataFrame(data=None, index=tdhs_multi_index, columns=[
                     'IsStartSmallerEqualHour', 'IsEndGreaterThanHour',
                     'IsHourCost', 'HourCost'
                     ])
    
    # Fill dataframes with variables:
    
    # h:
    
    for h in v_h.index:
        
        v_h.loc[h, 'TotalWeekHours'] = \
        model.NewIntVar(0, 40, 'TotalWeekHours_%s' % h) #...
        
        v_h.loc[h, 'TotalWeekHoursSquared'] = \
        model.NewIntVarFromDomain(
            cp_model.Domain.FromValues(
                [x**2 for x in range(0, 41)]
                ),
            'TotalWeekHoursSquared_%s' % h
            )
        
        v_h.loc[h, 'TotalWeekHoursCost'] = \
        model.NewIntVarFromDomain(
            cp_model.Domain.FromValues(
                [2*x**2 for x in range(0, 41)]
                ), 
            'TotalWeekHoursCost_%s' % h
            )
    
    # td:
    
    for t in range(num_tracks):
        for d in range(num_days):
            v_td.loc[(t, d), 'HandoverCost'] = \
            model.NewIntVarFromDomain(
               cp_model.Domain.FromValues(
                [30*x for x in range(0, 8)]
                ),
               'HandoverCost_%d_%d' % (t, d)
               )
    
    # tdh:
    
    print('')
    
    for t in range(num_tracks):
        for d in range(num_days):
            for h in df_agents.index:
                
                when_on_night_shift = \
                [19+i for i, x in enumerate(df_nights.loc[(t, d)].to_list()) 
                 if x == h]
                
                if h in unavailable_employees[d]:
                    v_tdh.loc[(t, d, h), 'Start'] = model.NewIntVar(
                        8, 8, 'Start_%d_%d_%s' % (t, d, h)
                        )
                    v_tdh.loc[(t, d, h), 'End'] = model.NewIntVar(
                        8, 8, 'End_%d_%d_%s' % (t, d, h)
                        )
                    v_tdh.loc[(t, d, h), 'Duration'] = \
                    model.NewIntVar(0, 0, 'Duration_%d_%d_%s' % (t, d, h))
                
                elif len(when_on_night_shift) > 0:
                    start = when_on_night_shift[0]
                    end = when_on_night_shift[-1] + 1
                    duration = end - start
                    
                    v_tdh.loc[(t, d, h), 'Start'] = \
                    model.NewIntVar(start, start, 'Start_%d_%d_%s' % (t, d, h))
                    
                    v_tdh.loc[(t, d, h), 'End'] = \
                    model.NewIntVar(end, end, 'End_%d_%d_%s' % (t, d, h))
                    
                    v_tdh.loc[(t, d, h), 'Duration'] = \
                    model.NewIntVar(
                        duration, duration, 'Duration_%d_%d_%s' % (t, d, h)
                        )
                    print(h + ' on duty on night ' + str(d+1))
                                        
                else:
                    v_tdh.loc[(t, d, h), 'Start'] = \
                    model.NewIntVarFromDomain(d_prefs.loc[(d, h)], 
                                              'Start_%d_%d_%s' % (t, d, h))
                    v_tdh.loc[(t, d, h), 'End'] = \
                    model.NewIntVarFromDomain(d_prefs.loc[(d, h)], 
                                              'End_%d_%d_%s' % (t, d, h))
                    v_tdh.loc[(t, d, h), 'Duration'] = \
                    model.NewIntVarFromDomain(
                        d_duration, 'Duration_%d_%d_%s' % (t, d, h)
                        )
                
                v_tdh.loc[(t, d, h), 'Interval'] = \
                model.NewIntervalVar(v_tdh.loc[(t, d, h), 'Start'],
                                     v_tdh.loc[(t, d, h), 'Duration'],
                                     v_tdh.loc[(t, d, h), 'End'],
                                     'Interval_%d_%d_%s' % (t, d, h))
                
                v_tdh.loc[(t, d, h), 'IsAgentOn'] = \
                model.NewBoolVar('IsAgentOn_%d_%d_%s' % (t, d, h))
                              
                v_tdh.loc[(t, d, h), 'AgentCost'] = \
                model.NewIntVarFromDomain(
                    cp_model.Domain.FromValues( 
                        [30*x for x in range(0, 65)]    
                        ),
                    'AgentCost_%d_%d_%s' % (t, d, h)
                    )
                
                v_tdh.loc[(t, d, h), 'IsDurationShorterThanIdeal'] = \
                model.NewBoolVar(
                    'IsDurationShorterThanIdeal_%d_%d_%s' % (t, d, h)
                    )
                
                duration_cost_list = set([30*x for x in range(0, 9)])
                duration_cost_list = list(duration_cost_list.union(
                                        set([40*x for x in range(0, 9)])
                                        ))
                duration_cost_list.sort()
                
                v_tdh.loc[(t, d, h), 'DurationCost'] = \
                model.NewIntVarFromDomain(
                    cp_model.Domain.FromValues(duration_cost_list),
                    'DurationCost_%d_%d_%s' % (t, d, h)
                    )
                
                v_tdh.loc[(t, d, h), 'IsInPrefRange'] = \
                [model.NewBoolVar('IsInPrefRange_%d_%d_%s_%d' % (t, d, h, j)) 
                  for (j,sec) in enumerate(df_agents.loc[h, 'HourRanges'][d])]
    
    # tdhs:
    
    for t in range(num_tracks):
        for d in range(num_days):
            for h in df_agents.index:
                for s in range(start_hour, end_hour):
                    
                    v_tdhs.loc[(t, d, h, s), 'IsStartSmallerEqualHour'] = \
                    model.NewBoolVar('IsStartSmallerEqualHour_%d_%d_%s_%d' 
                                     % (t, d, h, s))
                    
                    v_tdhs.loc[(t, d, h, s), 'IsEndGreaterThanHour'] = \
                    model.NewBoolVar('IsEndGreaterThanHour_%d_%d_%s_%d' 
                                     % (t, d, h, s))
                    
                    v_tdhs.loc[(t, d, h, s), 'IsHourCost'] = \
                    model.NewBoolVar('IsHourCost_%d_%d_%s_%d' % (t, d, h, s))
                    
                    v_tdhs.loc[(t, d, h, s), 'HourCost'] = \
                    model.NewIntVarFromDomain(d_hourCost, 
                                              'HourCost_%d_%d_%s_%d' 
                                              % (t, d, h, s)
                     )
    
    # Constraint: The sum of agents' shifts must equal work_hours:
    
    for t in range(num_tracks):
        for d in range(num_days):
            model.Add(
                sum(v_tdh.loc[(t, d), 'Duration'].values.tolist())==work_hours
                )
    
    # Constraint: Agent shifts must not overlap with each other:
    
    for t in range(num_tracks):
        for d in range(num_days):
            model.AddNoOverlap(v_tdh.loc[(t, d), 'Interval'].values.tolist())
    
    # Constraint: Honour agent availability requirements - a shift 
    # must start and end within an agent's availability hours:
    # NB: AddBoolOr works with just one boolean as well, in which case that
    # boolean has to be true.

    for t in range(num_tracks):        
        for d in range(num_days):
            for h in df_agents.index:
                if not(h in unavailable_employees[d]):
                    
                    model.AddBoolOr(v_tdh.loc[(t, d, h), 'IsInPrefRange'])
                    
                    for (j, sec) \
                        in enumerate(df_agents.loc[h, 'HourRanges'][d]):
                        
                        model.Add(
                            v_tdh.loc[(t, d, h), 'Start']>=sec[0]
                            ).OnlyEnforceIf(
                                v_tdh.loc[(t, d, h), 'IsInPrefRange'][j]
                                )
                        model.Add(v_tdh.loc[(t, d, h), 'Start'] 
                                  + v_tdh.loc[(t, d, h), 'Duration']
                                  <=sec[1]).OnlyEnforceIf(
                                      v_tdh.loc[(t, d, h), 'IsInPrefRange'][j]
                                      )
     
    # Constraint: Ensure agent not scheduled for more than one track at a time:
    
    for d in range(num_days):       
        for h in df_agents.index:
            
            isAgentOn_list = []
            
            for t in range(num_tracks):
                isAgentOn_list.append(v_tdh.loc[(t, d, h), 'IsAgentOn'].Not())
                
            model.AddBoolOr(isAgentOn_list)
    
    # Constraint: Add cost term due to total hours per agent:
    
    for h in df_agents.index:
        
        model.Add(
            v_h.loc[h, 'TotalWeekHours']==sum(
                v_tdh['Duration'].xs(
                    h, axis=0, level=2, drop_level=False
                    ).values.tolist()
                )
            )
        
        model.AddProdEquality(v_h.loc[h, 'TotalWeekHoursSquared'],
                              [v_h.loc[h, 'TotalWeekHours'], 
                               v_h.loc[h, 'TotalWeekHours']])
        
        model.AddProdEquality(v_h.loc[h, 'TotalWeekHoursCost'],
                              [v_constant2, 
                               v_h.loc[h, 'TotalWeekHoursSquared']])
        
    # Constraint: Add other cost terms:
    
    for t in range(num_tracks):
        
        for d in range(num_days):
      
            # Add cost due to number of handovers:
            
            model.Add(
                v_td.loc[(t, d), 'HandoverCost'] == 30
                * (sum(v_tdh.loc[(t, d), 'IsAgentOn'].values.tolist()) - 1)
                )
            
            for h in df_agents.index:
                
                # Put toggles in place reflecting whether agent was assigned:
                
                model.Add(v_tdh.loc[(t, d, h), 'Duration']!=0).OnlyEnforceIf(
                    v_tdh.loc[(t, d, h), 'IsAgentOn']
                    )
                model.Add(v_tdh.loc[(t, d, h), 'Duration']==0).OnlyEnforceIf(
                    v_tdh.loc[(t, d, h), 'IsAgentOn'].Not()
                    )
                
                # Add cost due to agent history:
                
                agent_cost = 30 * (
                   df_agents.loc[h, 'AvgHoursPerWeek'] - min_week_average_hours
                   )
                
                model.Add(
                    v_tdh.loc[(t, d, h), 'AgentCost']==agent_cost
                    ).OnlyEnforceIf(v_tdh.loc[(t, d, h), 'IsAgentOn'])
                model.Add(
                    v_tdh.loc[(t, d, h), 'AgentCost']==0
                    ).OnlyEnforceIf(v_tdh.loc[(t, d, h), 'IsAgentOn'].Not())
                
                # Add cost due to shift duration:
                
                model.Add(
                    v_tdh.loc[(t, d, h), 'Duration'] 
                    < df_agents.loc[h, 'PrefIdealLength']
                    ).OnlyEnforceIf(v_tdh.loc[(t, d, h), 
                                    'IsDurationShorterThanIdeal'])

                model.Add(
                    v_tdh.loc[(t, d, h), 'Duration'] 
                    >= df_agents.loc[h, 'PrefIdealLength']
                    ).OnlyEnforceIf(v_tdh.loc[(t, d, h), 
                                   'IsDurationShorterThanIdeal'].Not())
                
                # Cost for zero duration:
                
                model.Add(
                    v_tdh.loc[(t, d, h), 'DurationCost'] == 0
                    ).OnlyEnforceIf(v_tdh.loc[(t, d, h), 'IsAgentOn'].Not())
                
                # Cost for duration shorter than preference:
                
                model.Add(
                    v_tdh.loc[(t, d, h), 'DurationCost'] == 30 * (
                        df_agents.loc[h, 'PrefIdealLength'] 
                        - v_tdh.loc[(t, d, h), 'Duration']
                        )
                    ).OnlyEnforceIf([
                        v_tdh.loc[(t, d, h), 'IsAgentOn'],
                        v_tdh.loc[(t, d, h), 'IsDurationShorterThanIdeal']
                        ]) 
                
                # Cost for duration longer than preference:
                
                model.Add(
                    v_tdh.loc[(t, d, h), 'DurationCost'] == 40 * (
                        v_tdh.loc[(t, d, h), 'Duration']
                        - df_agents.loc[h, 'PrefIdealLength']
                        )
                    ).OnlyEnforceIf(
                       v_tdh.loc[(t, d, h), 'IsDurationShorterThanIdeal'].Not()
                       )
                
                # Add hour cost:
                
                for (s_count, s_cost) in enumerate(
                            df_agents.loc[h, 'Hours'][d][start_hour:end_hour]
                            ):
                    
                    s = s_count + start_hour
                    
                    model.Add(
                        v_tdh.loc[(t, d, h), 'Start']<=s
                        ).OnlyEnforceIf(
                            v_tdhs.loc[(t, d, h, s), 'IsStartSmallerEqualHour']
                            )
                    model.Add(
                        v_tdh.loc[(t, d, h), 'Start']>s
                        ).OnlyEnforceIf(
                            v_tdhs.loc[(t, d, h, s), 
                                       'IsStartSmallerEqualHour'].Not()
                            )
                    
                    model.Add(
                        v_tdh.loc[(t, d, h), 'End']>s
                        ).OnlyEnforceIf(
                            v_tdhs.loc[(t, d, h, s), 'IsEndGreaterThanHour']
                            )
                    model.Add(
                        v_tdh.loc[(t, d, h), 'End']<=s
                        ).OnlyEnforceIf(
                            v_tdhs.loc[(t, d, h, s), 
                                       'IsEndGreaterThanHour'].Not()
                            )
                    
                    model.AddBoolAnd(
                        [v_tdhs.loc[(t, d, h, s), 'IsStartSmallerEqualHour'], 
                        v_tdhs.loc[(t, d, h, s), 'IsEndGreaterThanHour']]
                        ).OnlyEnforceIf(
                            v_tdhs.loc[(t, d, h, s), 'IsHourCost']
                            )
                    
                    model.AddBoolOr(
                        [v_tdhs.loc[(t, d, h, s), 
                                    'IsStartSmallerEqualHour'].Not(),
                        v_tdhs.loc[(t, d, h, s), 'IsEndGreaterThanHour'].Not()]
                        ).OnlyEnforceIf(
                            v_tdhs.loc[(t, d, h, s), 'IsHourCost'].Not()
                            )
                    
                    model.Add(
                        v_tdhs.loc[(t, d, h, s), 
                                   'HourCost'] == 80 * (s_cost - 1)
                        ).OnlyEnforceIf(v_tdhs.loc[(t, d, h, s), 'IsHourCost'])
                    
                    model.Add(
                        v_tdhs.loc[(t, d, h, s), 'HourCost']==0
                        ).OnlyEnforceIf(
                            v_tdhs.loc[(t, d, h, s), 'IsHourCost'].Not()
                            )
    
    full_cost_list = v_h['TotalWeekHoursCost'].values.tolist() \
                     + v_td['HandoverCost'].values.tolist() \
                     + v_tdh['AgentCost'].values.tolist() \
                     + v_tdh['DurationCost'].values.tolist() \
                     + v_tdhs['HourCost'].values.tolist()
    
    model.Minimize(sum(full_cost_list))
    print(model.Validate())
    
    # Solve model:
    
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = solver_timeout
    solver.parameters.log_search_progress = True
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)
    print(solver.StatusName(status))
    
    # Extract solution:
    
    if not(status in [cp_model.OPTIMAL, cp_model.FEASIBLE]):
        print('Cannot create schedule')
        return
    
    else:
        
        print('\n---------------------')
        print('| OR-Tools schedule |')
        print('---------------------')
        
        print('\nSolution type: ', solver.StatusName(status))
        print('\nMinimized cost: ', solver.ObjectiveValue())
        print('After', solver.WallTime(), 'seconds.')
        
        schedule_results = []
        
        for d in range(num_days):
            
            day_dict = {}
            day_dict['start_date'] = days[d]
            day_dict['shifts'] = []
            
            for t in range(num_tracks):
                for h in df_agents.index:
                    if solver.Value(v_tdh.loc[(t, d, h), 'Duration'])!=0:
                        day_dict['shifts'].append(
                            (h, solver.Value(v_tdh.loc[(t, d, h), 'Start']),
                            solver.Value(v_tdh.loc[(t, d, h), 'End']))
                            )
            
            schedule_results.append(day_dict)
            
        # Sort shifts by start times to improve output readability:
        
        for i in range(len(schedule_results)):
            
            shifts = schedule_results[i]['shifts']
            sorted_shifts = sorted(shifts, key=lambda x: x[1])
            schedule_results[i]['shifts'] = sorted_shifts
        
        return print_final_schedules(schedule_results)



# MAIN CODE BLOCK

# Production (read input from command line):

sys.stderr.write("Command line args: %s\n" % sys.argv)
parser = argparse.ArgumentParser()
parser.add_argument('-i', '--input', 
                    help='Scheduler input JSON file path', 
                    required=True)
args = parser.parse_args()
input_filename = args.input.strip()

# Testing (define input directly):

#input_filename = 'support-shift-scheduler-input.json'


# Load and validate JSON input:

input_json = json.load(open(input_filename))
input_json_schema = json.load(
        open('../lib/schemas/support-shift-scheduler-input.schema.json')
        )
try:
    jsonschema.validate(input_json, input_json_schema)
except jsonschema.exceptions.ValidationError as err:
    print('Input JSON validation error', err)
    sys.exit(1)


# Define variables from options:

scheduler_options = input_json['options']

start_Monday = scheduler_options['start_Monday_date']
num_days = int(scheduler_options['num_consecutive_days'])
num_tracks = int(scheduler_options['num_simultaneous_tracks'])
start_hour = int(scheduler_options['support_start_hour'])
end_hour = int(scheduler_options['support_end_hour'])
min_duration = int(scheduler_options['shift_min_duration'])
max_duration = int(scheduler_options['shift_max_duration'])
solver_timeout = int(scheduler_options['optimization_timeout'])


# Other global variables:

work_hours = end_hour - start_hour
num_slots = 24  

start_date = dateparse(start_Monday).date()
delta = timedelta(days=1)
days = [start_date]

for d in range(1, num_days):
    days.append(days[d-1]+delta)

[df_agents, df_nights] = setup_dataframes()


# Determine unavailable agents for each day:

unavailable_employees = []

for d in range(num_days):
    unavailable_employees.append(get_unavailable_employees(days[d]))


# Remove agents from the model who are not available at all this week:

remove_agents_not_available_this_week()


# Create schedule:

output_sched = generate_schedule_with_ortools()
