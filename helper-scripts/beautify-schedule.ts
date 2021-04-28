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
import * as dateformat from 'dateformat';
import * as _ from 'lodash';
import * as fs from 'mz/fs';
import { readAndParseJSONSchedule } from '../lib/validate-json';

const MINUTES = 60 * 1000;

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
	hour = hour % 24;

	if (hour % 1 === 0) {
		return `${_.padStart(hour, 2, '0')}:00`;
	} else {
		return `${_.padStart(`${Math.floor(hour)}`, 2, '0')}:30`;
	}
}

/**
 * Write beautified schedule, as well as Flowdock message, to text files.
 * @param  {object}   scheduleJSON   Scheduling algorithm output object (read from file)
 */
async function writePrettifiedText(
	date: string,
	scheduleName: string,
	scheduleJSON,
) {
	// Write pretty schedule, to be used for sanity check:
	const agentHours = {};
	let prettySchedule = '';
	const dailyAgents = [];
	let maxHours = 0;

	for (const epoch of scheduleJSON) {
		const epochDate = new Date(epoch.start_date);
		const maxDayHours = _.maxBy(epoch.shifts, (s: { end: number }) => s.end)
			.end;
		maxHours = Math.max(maxHours, maxDayHours);
		const hours = new Array(maxDayHours).fill(0);

		let lastStartDate = new Date(epochDate.getTime() - 24 * 60 * MINUTES);

		for (const shift of epoch.shifts) {
			const startDate = new Date(
				epochDate.getTime() + shift.start * 30 * MINUTES,
			);
			if (startDate.getUTCDay() !== lastStartDate.getUTCDay()) {
				lastStartDate = startDate;
				prettySchedule += `\nShifts for ${prettyDateStr(startDate)}\n`;
			}
			const agentName = shift.agent.replace(/ <.*>/, '');
			const len = (shift.end - shift.start) / 2;
			const startStr = prettyHourStr(shift.start);
			const endStr = prettyHourStr(shift.end);
			prettySchedule += `${startStr} - ${endStr} (${len} hours) - ${agentName}\n`;
			agentHours[agentName] = agentHours[agentName] || 0;
			agentHours[agentName] += len;
			for (let i = shift.start; i < shift.end; i++) {
				const h = Math.floor(i / 2);
				hours[h] = hours[h] + 0.5;
			}
		}

		dailyAgents.push({ day: epochDate, hours });
	}
	prettySchedule += `\n#rollcall\n\n`;
	prettySchedule += 'Support hours\n-------------\n';

	let agentHoursList = _.map(agentHours, (hours, handle) => {
		handle = handle.replace(/ <.*>/, '');
		return { handle, hours };
	});
	agentHoursList = _.sortBy(agentHoursList, (agent) => {
		return agent.hours;
	}).reverse();

	for (const agent of agentHoursList) {
		const handle = agent.handle.replace(/@/, '').replace(/ <.*>/, '');
		prettySchedule += `${handle}: ${agent.hours}\n`;
	}

	let header = ' ';

	dailyAgents.forEach(
		(da) => (header = header.concat('\t\t', dateformat(da.day, 'ddd'))),
	);

	prettySchedule += '\n\nAgents per day \n\n';
	prettySchedule += header;

	for (let i = 0; i < maxHours; i++) {
		prettySchedule += '\n'.concat(
			`${i % 24}\t\t`,
			dailyAgents.map((d) => d.hours[i]).join('\t\t'),
		);
	}

	await fs.writeFile(
		`logs/${date}_${scheduleName}/beautified-schedule.txt`,
		prettySchedule,
		'utf8',
	);

	// Write Flowdock message, with which to ping agents to check their calendars:
	let flowdockMessage = '';
	flowdockMessage += `**Agents, please check your calendars for the support schedule for next week (starting on ${scheduleJSON[0].start_date}).**\n\n`;
	flowdockMessage +=
		'Please ping `@@support_ops` if you require any changes.\n\n';

	for (const agent of agentHoursList) {
		flowdockMessage += `${agent.handle}\n`;
	}
	await fs.writeFile(
		`logs/${date}_${scheduleName}/flowdock-message.txt`,
		flowdockMessage,
		'utf8',
	);
}

async function beautify(date: string, scheduleName: string) {
	const outputJsonObject = await readAndParseJSONSchedule(date, scheduleName);

	// Write beautified-schedule.txt and flowdock-message.txt:
	writePrettifiedText(date, scheduleName, outputJsonObject);
}

// Read scheduler output file name from command line:
const args = process.argv.slice(2);
if (args.length !== 2) {
	console.log(`Usage: node ${__filename} <yyyy-mm-dd> <model-name>`);
	process.exit(1);
}
const [$date, $scheduleName] = args;

beautify($date, $scheduleName);
