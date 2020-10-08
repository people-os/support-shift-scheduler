/*
 * Copyright 2020 Balena Ltd.
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
const dateformat = require('dateformat');
const _ = require('lodash');
const fs = require('mz/fs');

/**
 * Convert array from Next Cycle Dates Google Sheet into object.
 * @param  {object}   date   Date object
 * @return {string}          Formatted like Monday, November 18th
 */
function prettyDateStr(date) {
	return dateformat(date, 'dddd, mmmm dS');
}

function prettyHourStr(hour) {
	hour = hour / 2;
	if (hour > 23) {
		hour = hour - 24;
	}
	if ((hour * 10) % 10 === 0) {
		return `${_.padStart(hour, 2, '0')}:00`;
	} else {
		return `${_.padStart(parseInt(hour, 10), 2, '0')}:30`;
	}
}

/**
 * Write beautified schedule, as well as Flowdock message, to text files.
 * @param  {object}   scheduleJSON   Scheduling algorithm output object (read from file)
 */
function writePrettifiedText(scheduleJSON) {
	// Write pretty schedule, to be used for sanity check:
	let agentHours = {};
	let prettySchedule = '';

	for (let epoch of scheduleJSON) {
		let startDate = new Date(epoch.start_date);
		prettySchedule += `\nShifts for ${prettyDateStr(startDate)}\n`;

		for (let shift of epoch.shifts) {
			let agentName = shift.agent.replace(/ <.*>/, '');
			let len = (shift.end - shift.start) / 2;
			let startStr = prettyHourStr(shift.start);
			let endStr = prettyHourStr(shift.end);
			prettySchedule += `${startStr} - ${endStr} (${len} hours) - ${agentName}\n`;
			agentHours[agentName] = agentHours[agentName] || 0;
			agentHours[agentName] += len;
		}
	}
	prettySchedule += `\n#rollcall\n\n`;
	prettySchedule += 'Support hours\n-------------\n';

	let agentHoursList = _.map(agentHours, (hours, handle) => {
		handle = handle.replace(/ <.*>/, '');
		return { handle, hours };
	});
	agentHoursList = _.sortBy(agentHoursList, agent => {
		return agent.hours;
	}).reverse();

	for (let agent of agentHoursList) {
		let handle = agent.handle.replace(/@/, '').replace(/ <.*>/, '');
		prettySchedule += `${handle}: ${agent.hours}\n`;
	}

	fs.writeFile('beautified-schedule.txt', prettySchedule, 'utf8', err => {});

	// Write Flowdock message, with which to ping agents to check their calendars:
	let flowdockMessage = '';
	flowdockMessage += `**Agents, please check your calendars for the support schedule for next week (starting on ${scheduleJSON[0].start_date}).**\n\n`;
	flowdockMessage += 'Please let me know if you require any changes.\n\n';

	for (let agent of agentHoursList) {
		flowdockMessage += `${agent.handle}\n`;
	}
	fs.writeFile('flowdock-message.txt', flowdockMessage, 'utf8', err => {});
}

// Read scheduling algorithm output file name from command line:
const args = process.argv.slice(2);
if (args.length != 1) {
	console.log(
		`Usage: node ${__filename} <path-to-support-shift-scheduler-output.json>`
	);
	process.exit(1);
}

// Load JSON object from output file:
const jsonPath = args[0];
const jsonObject = JSON.parse(fs.readFileSync(jsonPath));

// Write beautified-schedule.txt and flowdock-message.txt:
writePrettifiedText(jsonObject);
