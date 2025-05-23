# Balena support shift scheduler

At balena, we practise support-driven development - you can read more about this philosophy in our [Support Driven Development blog post](https://www.balena.io/blog/support-driven-development/) from a few years ago. This means that we don’t outsource our customer support; it’s handled by our own engineers, who work from a wide variety of time zones, and across flexible working hours.  We offer customer support 21 hours every weekday, from 6 am to 3 am London time (UTC+1 during daylight saving time, UTC otherwise), every week of the year.

This scheduling project enables us to schedule our engineers to cover our support hours, considering multiple factors, for example avoiding scheduling agents outside of their preferred hours. Hence the goal of the support scheduler: maximising support scheduling fairness and efficiency, while minimising pain. You can find a detailed discussion of the considerations relevant to the scheduler in our blog post titled [The unreasonable effectiveness of algorithms in boosting team happiness](https://www.balena.io/blog/the-unreasonable-effectiveness-of-algorithms-in-boosting-team-happiness/). You will notice that the soft constraints as defined in [./algo-core/src/veterans.py](./algo-core/src/veterans.py) have been redefined since the blog post, but the underlying principles are still the same.

The current version of the solver also includes the following functionality that was not recorded in the blog post:

* **Configuration for other support rotations:** Initially, we only used the scheduler for our regular balena.io support rotation, but we have extended its use to also scheduled other channels, i.e. the auditors of our regular support rotation (`supportAuditing`), our SRE on-call rotation (`devOps`), and the rotation for engineers providing support to the team for our internal software (`productOS`). (The latter channel is currently inactive, however.) The `json` configurations for these channels are maintained in the [./helper_scripts/options](./helper_scripts/options) folder.
* **Configurable tracks:** Previously, we had 2 agents on support at any given time during our support hours. However, we have since included the ability to specify a highly customizable configuration of parallel "tracks" through the `hoursCoverage` and `agentDistribution` options, in the [./helper_scripts/options](./helper_scripts/options) folder.
* **Onboarding of new agents:** Once newly hired engineers have been with balena for a few months, they are onboarded to balena.io support. This involves scheduling them for two 4-hour onboarding shifts per week for 2 weeks, during which they are mentored by one of a selected group of senior support agents. These onboarding shifts are additional to the default number of parallel tracks, and require their own set of solver constraints. See the "Usage" section below for more detail on how to configure this.

The core of the algorithm is a constraint solver, and we currently use the [Google OR-tools CP-SAT solver](https://developers.google.com/optimization/cp/cp_solver), which is well suited to [scheduling optimisation](<https://developers.google.com/optimization/scheduling/job_shop>).



## Requirements

For local development, you need to `Clone or download` the repository to your local machine. You will need working installations of:

- [Python](https://www.python.org/downloads/) (>=3.12) for the core scheduling algorithm, 
- [Python Poetry](https://python-poetry.org/) for installing the Python modules.
- [Node.js](https://nodejs.org/en/download/) (>= 11.12.0, including npm) for the helper scripts.

Then, you need to install the prerequisite modules by executing the following on your command line, from within the project's root directory:

```bash
# Install node modules, creating a node_modules folder:
$ npm install
# Install Python modules:
$ poetry install     
```

### For balena team members

You will also need:

- For creating a `balena.io` schedule, a JSON file with credentials associated with the existing service account of our `Support Algo Calendar` Google Cloud project.
- A `.env` file in the project root directory, which you can base on the included [.env.dist](.env.dist).

For assistance, please contact `@AlidaOdendaal` `@gantonayde`, `@cmfcruz`, or teamOS operations.



### For the public

**The explanation in this section is just for clarity; if you just want to test the scheduling algorithm, you can skip to the *Usage* section below.**

This project makes use of the Google Sheets API to download input data, and the Google Calendar API to create calendar events, and hence needs Google authentication to be set up. *If* you'd like to set up a similar Google Cloud Project, you have to create a `.env` file in the project root directory, with `GAPI_SERVICE_ACCOUNT_JWT` set to the path to the JSON credentials associated with your [Google Service Account](https://cloud.google.com/compute/docs/access/service-accounts).

You would also need to modify the code in [`./lib/`](./lib/) and [`./helper-scripts/download-and-configure-input.ts`](./helper-scripts/download-and-configure-input.ts) to make sure that the correct data is being downloaded from your Google Sheets, and configured correctly for the scheduler.



## Usage

In this section, `<supportName>` indicates the relevant support channel, with currently supported values being `balenaio`, `devOps`, `productOS` and `supportAuditing`.

### 1. Configure Google Sheet input

#### For balena team members

In the `Full Team Model` Google Sheet:

* Under the `Extensions` menu, go to `Apps Script`, and navigate to the `Executions` tab on the left. Check that the function `callRefreshUKtimeTeamAvailabilities` has run successfully at least once during the past hour. If not, navigate to the `Custom scripts` menu in the GSheet, run `Full refresh of UK Time Team Availabilities`, and wait for the script to finish.

In the `Teamwork Model` Google Sheet:

* If there will be new team members onboarding to support in the week to be scheduled, ensure that you have onboarded them by following the procedure outlined [here](https://github.com/people-os/teamwork-model).
* From the `Custom scripts` menu, run `Trigger full prep for <supportName> scheduler run` , and wait for the script to finish.

Open the Google Sheet titled `<supportName> Support Scheduler Logs`, navigate to the sheet name `<next-Monday-date>_input`, and confirm that the full agent list appears there.

### 2. Downloading and configuring the algorithm input

#### For balena team members

From the project root directory, run:

```bash
$ npm run download-and-configure-input $startDate $supportName
```

This script will download the availability of each support agent for this cycle (compiled from working hours, time zones, time-off data, existing calendar appointments and possible opt-outs, and including e-mail addresses, teamwork balances and shift length preferences). It will create a JSON input object for the scheduling algorithm. This JSON object is validated against the [json input schema](./lib/schemas/support-shift-scheduler-input.schema.json), and then stored in the file `./logs/<startDate>_<supportName>/support-shift-scheduler-input.json` .

#### For the public

Since you do not have access to our private Google Spreadsheets, an example JSON input file has already been created for you, to enable you to do a test run of the algorithm. It is located under [`./logs/example/support-shift-scheduler-input.json`](./logs/example/support-shift-scheduler-input.json).

#### Then, for everyone

The JSON input object thus created has two main properties:

- `agents`, containing the data for all the support agents, and
- `options`, containing a number of options that are fed into the scheduler. This includes the optimisation timeout for the solver, with a default value of 1 hour set by the `download-and-configure-input` script. If necessary, these should be modified before running the core algorithm.

For more detail regarding these `options`, as well as the rest of the input file structure, see the associated [json input schema](./lib/schemas/support-shift-scheduler-input.schema.json).



### 3. Creating input files for onboarding

#### Manually
If there will be new team members onboarding to support in the week to be scheduled, you have to create the following 2 text files in the `./logs/<startDate>_<supportName>/` folder:

1. `onboarding_agents.txt`: A list of Github handles for the onboarding agents.
2. `mentors.txt`: A list of Github handles for the onboarding mentors.

In each of the files above, each handle should start with `@`, and each handle should be on a new line.

#### Automatically

You can also try to generate the files automatically with the following command:

```bash
$ npm run check-for-onboarding $startDate $supportName
```

This script will look for a Google spreadsheet whose `id` is specified as the value of `onboardingSheet` in `helper-scripts/options/$supportName.json`. Next the script will try to find a tab called `$startDate`. If it finds one, the data after the first row will be used to generate the `mentors.txt` and `onboarding_agents.txt` files from the first and second column, respectively. Note that the handles in the spreadsheet should not contain `@`, the script will add the prefix automatically.

### 4. Running the scheduling algorithm

While in the project's root directory on your local machine, run the following on the command line to activate the virtual Python environment:

```bash
$ poetry shell
```

From within the relevant `./logs/<startDate>_<supportName>`  directory (or `./logs/example` if you are using the example data), launch the solver with:

```bash
$ python ../../algo-core --input support-shift-scheduler-input.json
```

Upon completion, the algorithm will write the optimised schedule to the file `support-shift-scheduler-output.json` (after validating against the [json output schema](./lib/schemas/support-shift-scheduler-output.schema.json)).

If the `Solution type` is `OPTIMAL`, it means that the solver has determined this to be the solution with the lowest possible cost ("pain") value given the defined parameter space. If the `Solution type` is `FEASIBLE`, it means that this solution is the best one the solver could find given the set optimisation timeout.



### 5. Beautifying the schedule

```bash
$ npm run beautify-schedule $startDate $supportName
```

This script writes a formatted schedule to the file `beautified-schedule.txt`, which is a helpful view as a sanity check that the schedule is legitimate. The script also writes message text for our internal chat to the files `markdown-agents.txt`, which prompts the scheduled agents to check their calendars after the Google Calendar invites have been sent, and `markdown-onboarding.txt`, which alerts the onboarders and mentors to the onboarding shifts.

If, for some reason, the schedule needs to be modified, it should be edited directly in `support-shift-scheduler-output.json`, after which the `beautify-schedule` script should be rerun as above to update the text files.



### 6. Sending the calendar invites

#### For balena team members

From the project root directory, run:

```bash
$ npm run send-calendar-invites $startDate $supportName
```

to write the finalised schedule to the relevant Google Calendar, sending invites to all the associated agents.



### 7. Setting the victorops schedule

#### For devOps team members

From the project root directory, run:

```bash
$ npm run set-victorops-schedule $startDate $supportName
```

to set the scheduled overrides in victorops.



### 8. Notify the team in Zulip

#### For balena team members

* In the case of balena-io support, paste the contents of `markdown-agents.txt` to a new topic (named something along the lines of `balena-io support schedule for week of DD MMM YYYY` in the `channel/support-operations` stream in Zulip.
* If agents are onboarding this week, paste the contents of `markdown-onboarding.txt` to this topic as well.



## Built with

This project makes use of:

- [Google Cloud Platform](https://cloud.google.com/)
- [Google OR-tools CP-SAT solver](https://developers.google.com/optimization/cp/cp_solver)
- [Python 3](https://www.python.org/downloads/) 
- [Node.js](https://nodejs.org/en/download/)



## License

This project is licensed under the terms of the Apache License, Version 2.0.
