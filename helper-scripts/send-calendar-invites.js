require('dotenv').config()
const Promise = require('bluebird')
const readFile = Promise.promisify(require('fs').readFile)
const fs = require('fs')
const _ = require('lodash')

const { google } = require('googleapis')
const { getAuthClient } = require('../lib/gauth')
const { Validator, ValidationError } = require('jsonschema')
const { validateJSONScheduleOutput } = require('../lib/validate-json')

const TIMEZONE = 'Europe/London'


/**
 * Read, parse and validate JSON output file from scheduling algorithm.
 * @param  {string}   jsonPath   Path to output file
 * @return {object}              Parsed and validated object with schedule
 */
async function readAndParseJSONSchedule (jsonPath) {
  let jsonContent = await readFile(jsonPath).catch((e) => console.log(e))
  let jsonObject = JSON.parse(jsonContent)

  let schedulerOutputValidation = await validateJSONScheduleOutput(jsonObject).catch((e) => console.log(e))
  return jsonObject
}


/**
 * From the object containing the optimized shifts, create array of "events resources" in the format required by the Google Calendar API.
 * @param  {object}   shiftsObject   Shifts optimized by scheduling algorithm
 * @return {array}                   Array of events resources to be passed to Google Calendar API.
 */
async function createEventResourceArray(shiftsObject) {
  let returnArray = []
  for (let epoch of shiftsObject) {
    let date = epoch.start_date
    for (let shift of epoch.shifts) {
      let eventResource = {}
      let [handle, email] = shift.agent.split(' ')
      email = email.match(new RegExp(/<(.*)>/))[1]

      eventResource.summary = `${handle} on support`
      eventResource.description = 'Resources on support: https://github.com/resin-io/process/blob/master/process/support/README.md'

      eventResource.start = {}
      eventResource.start.timeZone = TIMEZONE
      eventResource.start.dateTime = `${date}T${_.padStart(shift.start, 2, '0')}:00:00`

      eventResource.end = {}
      eventResource.end.timeZone = TIMEZONE
      if (shift.end === 24) {
        let endDate = new Date(Date.parse(date))
        endDate.setDate(endDate.getDate() + 1)
        endDate = endDate.toISOString().split('T')[0]
        eventResource.end.dateTime = `${endDate}T00:00:00`
      } else {
        eventResource.end.dateTime = `${date}T${_.padStart(shift.end, 2, '0')}:00:00`
      }
      eventResource.attendees = []
      eventResource.attendees.push({ 'email': email })

      returnArray.push(eventResource)
    }
  }
  return returnArray
}


/**
 * Load JSON object containing optimized schedule from file, and write to Support schedule Google Calendar, saving ID's of created events for reference.
 * @param  {string}   jsonPath   Path to JSON output of scheduling algorithm
 */
async function createEvents(jsonPath) {
  let shiftsObject = await readAndParseJSONSchedule(jsonPath).catch((e) => console.log(e))
  let eventResourceArray = await createEventResourceArray(shiftsObject).catch((e) => console.log(e))

  let jwtClient = await getAuthClient().catch((e) => console.log(e))
  console.log('Got auth token successfully')

  let calendar = google.calendar({ version: 'v3' })
  let eventIDs = []

  for (let eventResource of eventResourceArray) {
    try {
      let eventResponse = await calendar.events.insert({
        auth: jwtClient,
        calendarId: process.env.CALENDAR_ID,
        conferenceDataVersion: 1,
        sendUpdates: 'all',
        resource: eventResource
      })
      console.log('Created event')
      let summary = `${eventResponse.data.summary} ${eventResponse.data.start.dateTime}`
      console.log('Event created: %s - %s', eventResponse.data.summary, eventResponse.data.htmlLink)
      eventIDs.push(eventResponse.data.id)
    } catch (err) {
      console.log('Could not add event')
      console.log('There was an error contacting the Calendar service: ' + err)
    }
  }
  fs.writeFile(logsFolder + '/event-ids-written-to-calendar.json', JSON.stringify(eventIDs, null, 2), 'utf8', err => {})
}


// Read scheduler output file name from command line:
let args = process.argv.slice(2)
if (args.length != 1) {
  console.log(`Usage: node ${__filename} <path-to-support-shift-scheduler-output.json>`)
  process.exit(1)
}
let jsonPath = args[0]

// Derive path for output:
let logsFolder = ''
if (jsonPath.indexOf('/') === -1) logsFolder = '.'
else logsFolder = jsonPath.slice(0, jsonPath.lastIndexOf('/'))


// Create calendar events:
createEvents(jsonPath)
