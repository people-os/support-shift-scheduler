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
require('dotenv').config();
const Promise = require('bluebird');
const fs = require('mz/fs');
const _ = require('lodash');
const { google } = require('googleapis');
const { getAuthClient } = require('../lib/gauth');
const { Validator, ValidationError } = require('jsonschema');
const { validateJSONScheduleOutput } = require('../lib/validate-json');
const TIMEZONE = 'Europe/London';

/**
 * Read, parse and validate JSON output file from scheduling algorithm.
 * @param  {string}   jsonPath   Path to output file
 * @return {object}              Parsed and validated object with schedule
 */
async function readAndParseJSONSchedule(jsonPath) {
	const jsonContent = await fs.readFile(jsonPath);
	const jsonObject = JSON.parse(jsonContent);
	const schedulerOutputValidation = await validateJSONScheduleOutput(
		jsonObject
	);
	return jsonObject;
}

/**
 * From the object containing the optimized shifts, create array of "events resources" in the format required by the Google Calendar API.
 * @param  {object}   shiftsObject   Shifts optimized by scheduling algorithm
 * @return {array}                   Array of events resources to be passed to Google Calendar API.
 */
async function createEventResourceArray(shiftsObject) {
	const returnArray = [];
	for (const epoch of shiftsObject) {
		const date = epoch.start_date;
		for (const shift of epoch.shifts) {
			const eventResource = {};
			let [handle, email] = shift.agent.split(' ');
			email = email.match(new RegExp(/<(.*)>/))[1];

			eventResource.summary = `${handle} on support`;
			eventResource.description =
				'Resources on support: ' + process.env.SUPPORT_RESOURCES;
			eventResource.start = {
				timeZone: TIMEZONE,
				dateTime: `${date}T${_.padStart(shift.start, 2, '0')}:00:00`,
			};
			eventResource.end = {
				timeZone: TIMEZONE,
			};

			if (shift.end === 24) {
				let endDate = new Date(Date.parse(date));
				endDate.setDate(endDate.getDate() + 1);
				endDate = endDate.toISOString().split('T')[0];
				eventResource.end.dateTime = `${endDate}T00:00:00`;
			} else {
				eventResource.end.dateTime = `${date}T${_.padStart(
					shift.end,
					2,
					'0'
				)}:00:00`;
			}
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
async function createEvents(jsonPath) {
	try {
		const shiftsObject = await readAndParseJSONSchedule(jsonPath);
		const eventResourceArray = await createEventResourceArray(shiftsObject);
		const jwtClient = await getAuthClient();
		const calendar = google.calendar({ version: 'v3' });
		const eventIDs = [];

		for (const eventResource of eventResourceArray) {
			const eventResponse = await calendar.events.insert({
				auth: jwtClient,
				calendarId: process.env.CALENDAR_ID,
				conferenceDataVersion: 1,
				sendUpdates: 'all',
				resource: eventResource,
			});
			const summary = `${eventResponse.data.summary} ${eventResponse.data.start.dateTime}`;
			console.log(
				'Event created: %s - %s',
				eventResponse.data.summary,
				eventResponse.data.htmlLink
			);
			eventIDs.push(eventResponse.data.id);
		}
		await fs.writeFile(
			logsFolder + '/event-ids-written-to-calendar.json',
			JSON.stringify(eventIDs, null, 2)
		);
	} catch (e) {
		console.error(e);
	}
}

// Read scheduler output file name from command line:
const args = process.argv.slice(2);
if (args.length != 1) {
	console.log(
		`Usage: node ${__filename} <path-to-support-shift-scheduler-output.json>`
	);
	process.exit(1);
}
const jsonPath = args[0];

// Derive path for output:
let logsFolder = '';
if (jsonPath.indexOf('/') === -1) {
	logsFolder = '.';
} else {
	logsFolder = jsonPath.slice(0, jsonPath.lastIndexOf('/'));
}

// Create calendar events:
createEvents(jsonPath);
