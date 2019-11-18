/*
 * Copyright 2019 Balena Ltd.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *    http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
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
  try {
    const auth = await getAuthClient()
    console.log('Got auth token successfully')

    const parsedNextCycleDates = await getNextCycleDates(auth)
    console.log(JSON.stringify(parsedNextCycleDates, null, 2))
    const nextMondayDate = parsedNextCycleDates.support

    const schedulerInput = await getSchedulerInput(auth, nextMondayDate, SCHEDULE_OPTS.num_consecutive_days)
    _.assign(schedulerInput.options, SCHEDULE_OPTS)
    console.log(JSON.stringify(schedulerInput, null, 2))
    const schedulerInputValidation = await validateJSONScheduleInput(schedulerInput)

    const fileDir = './logs-' + nextMondayDate
    await mkdirp(fileDir)

    fs.writeFile(fileDir + '/support-shift-scheduler-input.json', JSON.stringify(schedulerInput, null, 2), 'utf8', err => {})
  } catch (e) {
  console.error(e)
  }
}

getData()
