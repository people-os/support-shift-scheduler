require('dotenv').config()
const { google } = require('googleapis')
const _ = require('lodash')


/**
 * Convert array from Next Cycle Dates Google Sheet into object.
 * @param  {array}   rawDates   Array of 2-element arrays in format [<schedule type>, <start-date>]
 * @return {object}             Object with key:value pairs like <schedule type>:<start-date>
 */
async function parseDates(rawDates) {

  var parsedDates = {}

  for (var i = 0; i < rawDates.length; i++) {
    parsedDates[rawDates[i][0]] = rawDates[i][1]
  }
  return parsedDates
}


/**
 * Read and parse content of Next Cycle Dates Google Sheet.
 * @param  {object} auth   OAuth 2.0 access token
 * @return {object}        Object with key:value pairs like <schedule type>:<start-date>
 */
async function getNextCycleDates(auth) {
  var sheets = google.sheets({version: 'v4', auth})
  const result = await sheets.spreadsheets.values.get({
      spreadsheetId: process.env.TEAM_MODEL_ID,
      range: 'Next Cycle Dates!A1:B',
      valueRenderOption: 'FORMATTED_VALUE'
    }).catch((e) => console.log(e))
  const parsedNextCycleDates = await parseDates(result.data.values).catch((e) => console.log(e))
  return parsedNextCycleDates
}


/**
 * Create object from raw agent input.
 * @param  {array}  rawInput    Raw spreadsheet data as nested arrays
 * @return {object}             Object with keys in format @<github-handle>
 */
async function createObject(rawInput) {
  return _.reduce(rawInput, (dict, row) => {
    let [ handle, ...data ] = row
    dict['@' + handle] = data
    return dict
  }, {})
}


/**
 * Check if input object has duplicate keys, and if so throw error.
 * @param  {array}  inputObjects    Raw spreadsheet data as nested arrays
 */
async function checkForDuplicates(inputObjects = {}) {
  let handles = Object.keys(inputObjects)
  if (handles.length !== _.uniq(handles).length) {
    throw new Error('The input has duplicate agent handles')
  }
}


/**
 * Create agent object, checkingfor correct format for final scheduler input.
 * @param  {object}   opts   Object containing the necessary properties
 * @return {object}          Checked agent object
 */
async function createAgent(opts) {
  const requiredOpts = [
    "handle",
    "email",
    "week_average_hours",
    "ideal_shift_length",
    "available_hours"
  ]

  for (let opt of requiredOpts) {
    if (!opts[opt]) {
      throw new Error("Missing required option:", opt)
    }
  }
  return _.create({}, opts)
}


/**
 * Parse agent data read from Support Scheduler History.
 * @param  {array}  rawInput    Raw spreadsheet data as nested arrays
 * @param  {string} startDate   Schedule start date in format YYYY-MM-DD
 * @param  {number} numDays     Number of consecutive days to schedule
 * @return {object}             Parsed input object for scheduler
 */
async function parseInput(rawInput, startDate=null, numDays=5) {

  if (_.isEmpty(startDate)) {
    throw new Error('Need start date')
  }

  let schedulerInput = {
    "agents": [],
    "options": {}
  }

  let inputByGithubHandle = await createObject(rawInput).catch((e) => console.log(e))
  console.log(inputByGithubHandle)
  await checkForDuplicates(inputByGithubHandle).catch((e) => console.log(e))

  let agents_email = {}
  let agents_week_average_hours = {}
  let agents_ideal_shift_length = {}
  let agents_available_hours = {}

  for (let handle of Object.keys(inputByGithubHandle)) {
    agents_email[handle] = inputByGithubHandle[handle].splice(0, 1)

    agents_week_average_hours[handle]  = _.toInteger(inputByGithubHandle[handle].splice(0, 1))

    agents_ideal_shift_length[handle] = _.toInteger(inputByGithubHandle[handle].splice(0, 1))

    agents_available_hours[handle] = []

    for (let i = 0; i < numDays; i++) {

      var slotAvailability = inputByGithubHandle[handle].splice(0, 48)
      var hourAvailability = []
      const allowedValues = ['1', '2', '3']

      slotAvailability = slotAvailability.map((item) => {
        if (allowedValues.includes(item.toString())) return Number(item)
        else return 0
      })

      for (var h = 0; h < 24; h++) {
        var p1 = slotAvailability[h * 2]
        var p2 = slotAvailability[h * 2 + 1]
        var h_pref = 0
        // Add exception for temporary 21:30 shift starts by some agents...
        if (h === 21 && p1 !== 3 && p2 === 3) p1 = 3

        // Then the general logic:
        if (p1 !== 0 && p2 !== 0) {
          if (p1 === 1) {
            if (p2 === 2) h_pref = 2
            else h_pref = 1
          }
          if (p1 === 2) h_pref = 2
          else if (p1 === 3) h_pref = Number(p2)
        }
        hourAvailability.push(h_pref)
      }
      agents_available_hours[handle].push(hourAvailability)
    }
    let newAgent = await createAgent({
      "handle": handle,
      "email": agents_email[handle][0],
      "week_average_hours": agents_week_average_hours[handle],
      "ideal_shift_length": agents_ideal_shift_length[handle],
      "available_hours": agents_available_hours[handle]
    }).catch((e) => console.log(e))
    schedulerInput.agents.push(newAgent)
  }
  schedulerInput.options['start_Monday_date'] = startDate
  return schedulerInput
}


/**
 * Read and parse agent preferences and availability from Support Scheduler History sheet.
 * @param  {object} auth           OAuth 2.0 access token
 * @param  {string} nextMondayDate Schedule start date in format YYYY-MM-DD
 * @param  {number} numDays        Number of consecutive days to schedule
 * @return {object}                Parsed input object for scheduler (more options will be added to this object by download-and-configure-input.js)
 */
async function getSchedulerInput(auth, nextMondayDate, numDays) {
  var sheets = google.sheets({version: 'v4', auth})

  const result = await sheets.spreadsheets.values.get({
    spreadsheetId: process.env.SUPPORT_SCHEDULER_HISTORY_ID,
    range: nextMondayDate + '_input!A3:IJ',
    valueRenderOption: 'FORMATTED_VALUE'
  }).catch((e) => console.log(e))

  const parsedInput = await parseInput(result.data.values, nextMondayDate, numDays).catch((e) => console.log(e))

  return parsedInput
}

exports.getNextCycleDates = getNextCycleDates
exports.getSchedulerInput = getSchedulerInput
