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
const dateformat = require('dateformat');
const _ = require('lodash');
const fs = require('mz/fs');

/**
 * Convert array from Next Cycle Dates Google Sheet into object.
 * @param  {object}   date   Date object
 * @return {string}          Formatted like like Monday, November 18th
 */
function prettyDateStr(date) {
	return dateformat(date, 'dddd, mmmm dS');
}

/**
 * Write beautified schedule, as well as Flowdock message, to text files.
 * @param  {object}   scheduleJSON   Scheduling algorithm output object (read from file)
 */
async function writePrettifiedText(scheduleJSON) {
	// Write pretty schedule, to be used for sanity check:
	const agentHours = {};
	let prettySchedule = '';

	for (const epoch of scheduleJSON) {
		//let startDate = new Date(epoch.start_date)
		prettySchedule += `\nShifts for ${epoch.start_date}\n`;

		for (const shift of epoch.shifts) {
			const agentName = shift.agent.replace(/ <.*>/, '');
			const len = shift.end - shift.start;
			const startStr = `${_.padStart(shift.start, 2, '0')}:00`;
			const endStr = `${_.padStart(shift.end, 2, '0')}:00`;
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

	for (const agent of agentHoursList) {
		const handle = agent.handle.replace(/@/, '').replace(/ <.*>/, '');
		prettySchedule += `${handle}: ${agent.hours}\n`;
	}
	try {
		await fs.writeFile('beautified-schedule.txt', prettySchedule);
	} catch (e) {
		console.error(e);
	}

	// Write Flowdock message, with which to ping agents to check their calendars:
	let flowdockMessage = '';
	flowdockMessage += `**Agents, please check your calendars for the support schedule for next week (starting on ${scheduleJSON[0].start_date}).**\n\n`;
	flowdockMessage +=
		'Please acknowledge, or let me know if you require any changes.\n';
	flowdockMessage += `\n#rollcall\n\n`;

	for (const agent of agentHoursList) {
		flowdockMessage += `${agent.handle}\n`;
	}
	try {
		await fs.writeFile('flowdock-message.txt', flowdockMessage);
	} catch (e) {
		console.error(e);
	}
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
