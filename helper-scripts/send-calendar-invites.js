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
require('dotenv').config();
const fs = require('mz/fs');
const _ = require('lodash');
const { google } = require('googleapis');
const { getAuthClient } = require('../lib/gauth');
const { validateJSONScheduleOutput } = require('../lib/validate-json');
const TIMEZONE = 'Europe/London';

/**
 * Read, parse and validate JSON output file from scheduling algorithm.
 * @param  {string}   jsonPath   Path to output file
 * @return {Promise<object>}              Parsed and validated object with schedule
 */
async function readAndParseJSONSchedule(jsonPath) {
	const jsonContent = await fs.readFile(jsonPath, 'utf8');
	const jsonObject = JSON.parse(jsonContent);
	await validateJSONScheduleOutput(jsonObject);
	return jsonObject;
}

function prettyHourStr(date, hour) {
	if ((hour * 10) % 10 === 0) {
		return `${date}T${_.padStart(hour, 2, '0')}:00:00`;
	} else {
		return `${date}T${_.padStart(`${Math.floor(hour)}`, 2, '0')}:30:00`;
	}
}

function getDate(eventDate, eventHour) {
	let resultDateTime = '';
	eventHour = eventHour / 2;

	if (eventHour >= 24) {
		let finalDate = new Date(Date.parse(eventDate));
		finalDate.setDate(finalDate.getDate() + 1);
		const finalDateStr = finalDate.toISOString().split('T')[0];
		const endHour = eventHour - 24;
		resultDateTime = prettyHourStr(finalDateStr, endHour);
	} else {
		resultDateTime = prettyHourStr(eventDate, eventHour);
	}

	return resultDateTime;
}

/**
 * From the object containing the optimized shifts, create array of "events resources" in the format required by the Google Calendar API.
 * @param  {object}   shiftsObject   Shifts optimized by scheduling algorithm
 * @return {Promise<array>}                   Array of events resources to be passed to Google Calendar API.
 */
async function createEventResourceArray(shiftsObject, supportName) {
	const returnArray = [];
	for (const epoch of shiftsObject) {
		const date = epoch.start_date;
		for (const shift of epoch.shifts) {
			const eventResource = {};
			let [handle, email] = shift.agent.split(' ');
			email = email.match(new RegExp(/<(.*)>/))[1];

			eventResource.summary = `${handle} on ${supportName} support`;
			eventResource.description =
				'Resources on support: ' + process.env.SUPPORT_RESOURCES;
			eventResource.start = {
				timeZone: TIMEZONE,
				dateTime: getDate(date, shift.start),
			};
			eventResource.end = {
				timeZone: TIMEZONE,
				dateTime: getDate(date, shift.end),
			};

			eventResource.attendees = [];
			eventResource.attendees.push({ email: email });
			returnArray.push(eventResource);
		}
	}
	return returnArray;
}

/**
 * Load JSON object containing optimized schedule from file, and write to Support schedule Google Calendar, saving ID's of created events for reference.
 * @param  {string}   jsonPath   Path to JSON output of scheduling algorithm
 */
async function createEvents(jsonPath, supportName) {
	const support = JSON.parse(
		fs.readFileSync('helper-scripts/options/' + supportName + '.json', 'utf8'),
	);

	try {
		const shiftsObject = await readAndParseJSONSchedule(jsonPath);
		const eventResourceArray = await createEventResourceArray(
			shiftsObject,
			supportName,
		);
		const authClient = await getAuthClient(support);
		const calendar = google.calendar({ version: 'v3' });
		const eventIDs = [];

		for (const eventResource of eventResourceArray) {
			const eventResponse = await calendar.events.insert({
				auth: authClient,
				calendarId: support.calendarID,
				conferenceDataVersion: 1,
				sendUpdates: 'all',
				requestBody: eventResource,
			});
			const summary = `${eventResponse.data.summary} ${eventResponse.data.start.dateTime}`;
			console.log(
				'Event created: %s - %s',
				summary,
				eventResponse.data.htmlLink,
			);
			eventIDs.push(eventResponse.data.id);
		}
		await fs.writeFile(
			logsFolder + '/event-ids-written-to-calendar.json',
			JSON.stringify(eventIDs, null, 2),
		);
	} catch (e) {
		console.error(e);
	}
}

// Read scheduler output file name from command line:
const args = process.argv.slice(2);
if (args.length !== 2) {
	console.log(
		`Usage: node ${__filename} <path-to-support-shift-scheduler-output.json> <model-name>`,
	);
	process.exit(1);
}
const [$jsonPath, $supportName] = args;

// Derive path for output:
let logsFolder = '';
if ($jsonPath.indexOf('/') === -1) {
	logsFolder = '.';
} else {
	logsFolder = $jsonPath.slice(0, $jsonPath.lastIndexOf('/'));
}

// Create calendar events:
createEvents($jsonPath, $supportName);
