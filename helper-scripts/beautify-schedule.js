const dateformat = require('dateformat')
const fs = require('fs')
const _ = require('lodash')


/**
 * Convert array from Next Cycle Dates Google Sheet into object.
 * @param  {object}   date   Date object
 * @return {string}          Formatted like like Monday, November 18th
 */
function prettyDateStr(date) {
  return dateformat(date, "dddd, mmmm dS")
}


/**
 * Write beautified schedule, as well as Flowdock message, to text files.
 * @param  {object}   scheduleJSON   Scheduling algorithm output object (read from file)
 */
function writePrettifiedText(scheduleJSON) {

  // Write pretty schedule, to be used for sanity check:

  let agentHours = {}
  let prettySchedule = ""

  for (let epoch of scheduleJSON) {
    //let startDate = new Date(epoch.start_date)
    prettySchedule += `\nShifts for ${prettyDateStr(epoch.start_date)}\n`

    for (let shift of epoch.shifts) {
      let agentName = shift.agent.replace(/ <.*>/, '')
      let len = shift.end - shift.start
      let startStr = `${_.padStart(shift.start, 2, '0')}:00`
      let endStr = `${_.padStart(shift.end, 2, '0')}:00`
      prettySchedule += `${startStr} - ${endStr} (${len} hours) - ${agentName}\n`
      agentHours[agentName] = agentHours[agentName] || 0
      agentHours[agentName] += len
    }
  }
  prettySchedule += `\n#rollcall\n\n`
  prettySchedule += 'Support hours\n-------------\n'

  let agentHoursList = _.map(agentHours, (hours, handle) => { handle = handle.replace(/ <.*>/, ''); return { handle, hours }})
  agentHoursList = _.sortBy(agentHoursList, (agent) => { return agent.hours }).reverse()

  for (let agent of agentHoursList) {
    let handle = agent.handle.replace(/@/, '').replace(/ <.*>/, '')
    prettySchedule += `${handle}: ${agent.hours}\n`
  }

  fs.writeFile('beautified-schedule.txt', prettySchedule, 'utf8', err => {})

  // Write Flowdock message, with which to ping agents to check their calendars:

  let flowdockMessage = ""

  flowdockMessage += `**Agents, please check your calendars for the support schedule for next week (starting on ${dateformat(scheduleJSON[0].start_date, "mmmm dS")}).**\n\n`

  flowdockMessage += 'Please acknowledge, or let me know if you require any changes.\n'
  flowdockMessage += `\n#rollcall\n\n`

  for (let agent of agentHoursList) {
    flowdockMessage += `${agent.handle}\n`
  }
  fs.writeFile('flowdock-message.txt', flowdockMessage, 'utf8', err => {})
}


// Read scheduling algorithm output file name from command line:
let args = process.argv.slice(2)
if (args.length != 1) {
  console.log(`Usage: node ${__filename} <path-to-support-shift-scheduler-output.json>`)
  process.exit(1)
}

// Load JSON object from output file:
const jsonPath = args[0]
const jsonObject = JSON.parse(fs.readFileSync(jsonPath))

// Write beautified-schedule.txt and flowdock-message.txt:
writePrettifiedText(jsonObject)
