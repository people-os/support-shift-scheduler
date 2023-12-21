/*
 * Copyright 2019-2023 Balena Ltd.
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
import * as dotenv from 'dotenv';
dotenv.config();

import * as _ from 'lodash';
import * as fs from 'mz/fs';
import zulipInit = require('zulip-js');
import { readAndParseJSONSchedule } from '../lib/validate-json';

const MINUTES = 60 * 1000;

const dateFormat = new Intl.DateTimeFormat('en', {
	timeZone: 'UTC',
	weekday: 'long',
	month: 'long',
	day: 'numeric',
});
const dayFormat = new Intl.DateTimeFormat('en', {
	timeZone: 'UTC',
	weekday: 'short',
});

function prettyHourStr(hour) {
	hour = hour / 2;
	hour = hour % 24;

	if (hour % 1 === 0) {
		return `${_.padStart(hour, 2, '0')}:00`;
	} else {
		return `${_.padStart(`${Math.floor(hour)}`, 2, '0')}:30`;
	}
}

async function getZulipUsers() {
	// Initialize Zulip
	const zulipConfig = {
		username: process.env.ZULIP_EMAIL,
		apiKey: process.env.ZULIP_API_KEY,
		realm: process.env.ZULIP_ORG_URL,
	};
	const zulipClient = await zulipInit(zulipConfig);
	// pull all users from Zulip
	const results = await zulipClient.users.retrieve();
	const usersByEmail: { [x: string]: string } = {};
	for (const user of results.members) {
		if (!user.is_bot && user.is_active) {
			usersByEmail[user.email.toLowerCase()] = user.full_name;
		}
	}
	return usersByEmail;
}

/**
 * Write beautified schedule, as well as Markdown message, to text files.
 * @param  {object}   shiftsJson   Scheduling algorithm output object (read from file)
 */
async function writePrettifiedShiftsText(
	date: string,
	scheduleName: string,
	shiftsJson,
) {
	// Write pretty schedule, to be used for sanity check:
	const agentHours = {};
	let prettySchedule = '';
	const dailyAgents = [];
	let maxHours = 0;

	for (const epoch of shiftsJson) {
		if (epoch.shifts.length > 0) {
			const epochDate = new Date(epoch.start_date);
			const maxDayHours = _.maxBy(
				epoch.shifts,
				(s: { end: number }) => s.end,
			).end;
			maxHours = Math.max(maxHours, maxDayHours);
			const hours = new Array(maxDayHours).fill(0);
	
			let lastStartDate = new Date(epochDate.getTime() - 24 * 60 * MINUTES);
	
			for (const shift of epoch.shifts) {
				const startDate = new Date(
					epochDate.getTime() + shift.start * 30 * MINUTES,
				);
				if (startDate.getUTCDay() !== lastStartDate.getUTCDay()) {
					lastStartDate = startDate;
					prettySchedule += `\nShifts for ${dateFormat.format(startDate)}\n`;
				}
				const agentName =
					shift.agent.replace(/ <.*>/, '').replace(/@/, '@**') + '**';
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
	}
	prettySchedule += '\nSupport hours\n-------------\n';

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
		(da) => (header = header.concat('\t\t', dayFormat.format(da.day))),
	);

	prettySchedule += '\n\n```';
	prettySchedule += '\nAgents per day \n\n';
	prettySchedule += header;

	for (let i = 0; i < maxHours; i++) {
		prettySchedule += '\n'.concat(
			`${i % 24}\t\t`,
			dailyAgents.map((d) => d.hours[i]).join('\t\t'),
		);
	}
	prettySchedule += '\n\n```';

	try {
		await fs.writeFile(
			`logs/${date}_${scheduleName}/beautified-schedule.txt`,
			prettySchedule,
			'utf8',
		);
	} catch (e) {
		console.error(e);
		process.exit(1);
	}

	// Write Markdown message, with which to ping agents to check their calendars:
	let markdownMessage = '';
	markdownMessage += `**Agents, please check your calendars for the support schedule for next week (starting on ${shiftsJson[0].start_date}).**\n\n`;
	markdownMessage +=
		'Please follow [this procedure](https://github.com/people-os/process/tree/master/process/support#what-if-you-cannot-make-the-shift-you-have-been-allocated) if you require any changes.\n\n';

	for (const agent of agentHoursList) {
		markdownMessage += `${agent.handle}\n`;
	}
	try {
		await fs.writeFile(
			`logs/${date}_${scheduleName}/markdown-agents.txt`,
			markdownMessage,
			'utf8',
		);
	} catch (e) {
		console.error(e);
		process.exit(1);
	}
}

async function writePrettifiedOnboardingText(
	date,
	scheduleName,
	onboardingJson,
) {
	let onboardingMessage =
		'**Support agent onboarding next week**' +
		'\n\nEach new onboarding agent has been paired with a senior ' +
		'support agent for each of their shifts. The senior agent ' +
		'will act as a mentor for the onboarding agents, showing ' +
		'them the ropes during these onboarding shifts (see the ' +
		'[onboarding document]' +
		'(https://github.com/balena-io/process/blob/master/process/support/onboarding_agents_to_support.md) ' +
		'for background). Here are the mentor-novice pairings ' +
		'for next week:';
	for (const epoch of onboardingJson) {
		if (epoch.shifts.length > 0) {
			onboardingMessage += `\n\n**Onboarding on ${epoch.start_date}**`;
			for (const shift of epoch.shifts) {
				onboardingMessage += `\n${shift.mentor} will mentor ${shift.onboarder}.`;
			}
		}
	}
	onboardingMessage += `\n\ncc @@support_ops`;
	onboardingMessage += `\n\nHappy onboarding! :ship:\n`;
	try {
		await fs.writeFile(
			`logs/${date}_${scheduleName}/markdown-onboarding.txt`,
			onboardingMessage,
			'utf8',
		);
	} catch (e) {
		console.error(e);
		process.exit(1);
	}
}

async function readAndParseJSONOnboarding(date, scheduleName) {
	const jsonObject = await import(
		`../logs/${date}_${scheduleName}/onboarding_pairings.json`
	);
	return jsonObject;
}

async function convertTeamworkHandlesToZulipHandles(shiftsJson: any) {
	const usersByEmail = await getZulipUsers();
	for (const epoch of shiftsJson) {
		for (const shift of epoch.shifts) {
			const agentHandleAndEmail = shift.agent;
			const emailRegex = /<([^<>]+)>/;
			const matches = agentHandleAndEmail.match(emailRegex);
			const email = matches ? matches[1].toLowerCase() : null;
			if (email && email in usersByEmail) {
				const zulipHandle = usersByEmail[email];
				shift.agent = agentHandleAndEmail.replace(
					/@\S+[ <]/,
					`@${zulipHandle} `,
				);
			}
		}
	}
}

async function beautify(date: string, scheduleName: string) {
	const shiftsJson = await readAndParseJSONSchedule(date, scheduleName);
	const onboardingJson = await readAndParseJSONOnboarding(date, scheduleName);
	// TODO: convert onboardingJson too
	await convertTeamworkHandlesToZulipHandles(shiftsJson);

	// Write beautified-schedule.txt, markdown-agents.txt, markdown-onboarding.txt:
	await writePrettifiedShiftsText(date, scheduleName, shiftsJson);
	await writePrettifiedOnboardingText(date, scheduleName, onboardingJson);
}

// Read scheduler output file name from command line:
const args = process.argv.slice(2);
if (args.length !== 2) {
	console.log(`Usage: node ${__filename} <yyyy-mm-dd> <model-name>`);
	process.exit(2);
}
const [$date, $scheduleName] = args;

void beautify($date, $scheduleName);
