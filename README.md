# Balena support shift scheduler

At Balena, we practise support-driven development - you can read more about this philosophy in our [Support Driven Development blog post](https://www.balena.io/blog/support-driven-development/) from a few years ago. This means that we don’t outsource our customer support; it’s handled by our own engineers, who work from a wide variety of time zones, and across flexible working hours.  We offer customer support 16 hours every weekday, from 8 am to midnight London time (UTC+1 during daylight saving time, UTC otherwise), every week of the year.

This scheduling project enables us to schedule our engineers to cover our support hours, considering multiple factors, for example avoiding scheduling agents outside of their preferred hours. Hence the goal of the support scheduler: maximising support scheduling fairness and efficiency, while minimising pain. You can find a detailed discussion of the considerations relevant to the scheduler in our blog post titled [The unreasonable effectiveness of algorithms in boosting team happiness](<link-to-blog-post>).

The core of the algorithm is a constraint solver, and we currently use the [Google OR-tools CP-SAT solver](https://developers.google.com/optimization/cp/cp_solver), which is well suited to [scheduling optimisation](<https://developers.google.com/optimization/scheduling/job_shop>).



## Requirements

For local development, you need to `Clone or download` the repository to your local machine. You will need working installations of:

* [Python](https://www.python.org/downloads/) (>=3.7.5) for the core scheduling algorithm, 
* [pip](<https://pypi.org/project/pip/>) for installing the Python modules, and
* [Node.js](https://nodejs.org/en/download/) (>= 11.12.0), including npm) for the helper scripts.

Then, you need to install the prerequisite modules by executing the following on your command line, from within the project's root directory:

```bash
# Install node modules, creating a node_modules folder:
$ npm install
# Install Python modules (depending on your environment, you might need to prepend this with sudo):
$ pip3 install -r requirements.txt     
```

### For balena team members

You will also need:

* A JSON file with credentials associated with the existing service account of our `Support Algo Calendar` Google Cloud project.
* To create a `.env` file in the project root directory, defining the following environment variables:
  * `TEAM_MODEL_ID `: Google Spreadsheet ID of the `Team Model` sheet.
  * `SUPPORT_SCHEDULER_HISTORY_ID`: Google Spreadsheet ID of the `Support Scheduler History` sheet.
  * `GAPI_SERVICE_ACCOUNT_JWT`: The path to the JSON credentials.
  * `CALENDAR_ID`: Google Calendar ID of the `Support schedule` calendar.

For assistance, please contact `@AlidaOdendaal`, or operations.



### For the public

**The explanation in this section is just for clarity; if you just want to test the scheduling algorithm, you can skip to the *Usage* section below.**

This project makes use of a [Google Service Account](https://cloud.google.com/compute/docs/access/service-accounts) to authenticate with the Google Sheets API to download input data, and with the Google Calendar API to create calendar events. *If* you'd like to set up a similar Google Cloud Project, you have to create a `.env` file in the project root directory, defining the following environment variables:

- `GAPI_SERVICE_ACCOUNT_JWT`: The path to the JSON credentials associated with your service account.
- `CALENDAR_ID`: Google Calendar ID of the calendar you would like the events to be written to.

You would also need to modify [`./lib/gsheets.js`](./lib/gsheets.js) and [`./helper-scripts/download-and-configure-input.js`](./helper-scripts/download-and-configure-input.js) to make sure that the correct data is being downloaded from your Google Sheets, and configured correctly for the scheduler.



## Usage



### Downloading and configuring the algorithm input



#### For balena team members

From the project root directory, run

``` bash
$ node ./helper-scripts/download-and-configure-input.js
```

This script will determine the start date of the next support cycle, and download the availability of each support agent for this cycle (compiled from working hours, time zones, time-off data, existing calendar appointments and possible opt-outs, and including e-mail addresses, historical support load and shift length preferences). It will create a JSON input object for the scheduling algorithm. This JSON object is validated against the [json input schema](./lib/schemas/support-shift-scheduler-input.schema.json), and then stored in the file `./logs-<start-date>/support-shift-scheduler-input.json` .



#### For the public

Since you do not have access to our private Google Spreadsheets, an example JSON input file has already been created for you, to enable you to do a test run of the algorithm. It is located under [`./logs-example/support-shift-scheduler-input.json`](./logs-example/support-shift-scheduler-input.json).



#### Then, for everyone

The JSON input object thus created has two main properties:

* `agents`, containing the data for all the support agents, and
* `options`, containing a number of options that are fed into the scheduler. This includes the optimisation timeout for the solver, which is set to 1 hour by default. If necessary, these should be modified before running the core algorithm.

For more detail regarding these `options`, as well as the rest of the input file structure, see the associated [json input schema](./lib/schemas/support-shift-scheduler-input.schema.json).



### Running the scheduling algorithm

From within the relevant `./logs-<start-date>`  directory (or `./logs-example` if you are using the example data), launch the solver with

```bash
$ python3 ../algo-core/ortools_solver.py --input support-shift-scheduler-input.json
```

Upon completion, the algorithm will write the optimised schedule to the file `support-shift-scheduler-output.json` (after validating against the [json output schema](./lib/schemas/support-shift-scheduler-output.schema.json)), and also display a summary in the terminal.

If the `Solution type` is `OPTIMAL`, it means that the solver has determined this to be the solution with the lowest possible cost ("pain") value given the defined parameter space. If the `Solution type` is `FEASIBLE`, it means that this solution is the best one the solver could find given the set optimisation timeout.



### Beautifying the schedule

From within the `./logs-<start-date>`  directory (or `./logs-example` if you are using the example data), run

```bash
$ node ../helper-scripts/beautify-schedule.js support-shift-scheduler-output.json
```

This script writes a formatted schedule to the file `beautified-schedule.txt`, which is a helpful view as a sanity check that the schedule is legitimate. The script also writes message text for our internal chat to the file `flowdock-message.txt`, which is used to ping the support agents to go check their calendars after the Google Calendar invites have been sent.

If, for some reason, the schedule needs to be modified, it should be edited directly in `support-shift-scheduler-output.json`, after which the `beautify-schedule.js` script should be rerun as above to update the text files.



### Sending the calendar invites

#### For balena team members

From the project root directory, run

```bash
$ node ./helper-scripts/send-calendar-invites.js logs-<start-date>/support-shift-scheduler-output.json
```

to write the finalised schedule to the `Support schedule` Google Calendar, sending invites to all the associated agents.  Now, paste the content of `flowdock-message.txt` to the support room in Flowdock.



## Built with

This project makes use of:

* [Google Cloud Platform](https://cloud.google.com/)
* [Google OR-tools CP-SAT solver](https://developers.google.com/optimization/cp/cp_solver)
* [Python 3](https://www.python.org/downloads/) 
* [Node.js](https://nodejs.org/en/download/)



## Contributors

* Alida Odendaal (@AlidaOdendaal)
* Alexandros Marinos (@alexandrosm)
* Petros Angelatos (@petrosagg)
* Kostas Lekkas (@lekkas)



## License

...
