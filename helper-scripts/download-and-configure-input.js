const _ = require('lodash')
const fs = require('fs')
const Promise = require('bluebird')
const mkdirp = Promise.promisify(require('mkdirp'))

const { getAuthClient } = require('../lib/gauth')
const { getNextCycleDates } = require('../lib/gsheets')
const { getSchedulerInput } = require('../lib/gsheets')
const { validateJSONScheduleInput } = require('../lib/validate-json')



const SCHEDULE_OPTS = {
  "num_consecutive_days": 5,
  "num_simultaneous_tracks": 2,
  "support_start_hour": 8,
  "support_end_hour": 24,
  "shift_min_duration": 2,
  "shift_max_duration": 8,
  "optimization_timeout": 3600
}


/**
 * Read and configure input data from Google Sheets, and save as JSON object
 */
async function getData() {
  let auth = await getAuthClient().catch((e) => console.log(e))
  console.log('Got auth token successfully')

  let parsedNextCycleDates = await getNextCycleDates(auth).catch((e) => console.log(e))
  console.log(JSON.stringify(parsedNextCycleDates, null, 2))

  const nextMondayDate = parsedNextCycleDates.support

  var schedulerInput = await getSchedulerInput(auth, nextMondayDate, SCHEDULE_OPTS.num_consecutive_days).catch((e) => console.log(e))

  _.assign(schedulerInput.options, SCHEDULE_OPTS)
  console.log(JSON.stringify(schedulerInput, null, 2))

  let schedulerInputValidation = await validateJSONScheduleInput(schedulerInput).catch((e) => console.log(e))

  const fileDir = './logs_' + nextMondayDate
  await mkdirp(fileDir).catch((e) => console.log(e.stack))

  fs.writeFile(fileDir + '/support-shift-scheduler-input.json', JSON.stringify(schedulerInput, null, 2), 'utf8', err => {})
}

getData()
