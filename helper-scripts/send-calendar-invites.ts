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
import { config } from 'dotenv';
config();
import * as fs from 'mz/fs';
import { google } from 'googleapis';
import type { calendar_v3 } from 'googleapis';
import { getJWTAuthClient } from '../lib/gauth';
import { readAndParseJSONSchedule } from '../lib/validate-json';
const TIMEZONE = 'Europe/London';

const MINUTES = 60 * 1000;

function isoDateWithoutTimezone(date) {
	// ISO string without the `z` timezone
	return date.toISOString().slice(0, -1);
}

/**
 * From the object containing the optimized shifts, create array of "events resources" in the format required by the Google Calendar API.
 * @param  {object}   shiftsObject   Shifts optimized by scheduling algorithm
 * @param  {string}   modelName   The schedule we're targeting, eg `balenaio`
 * @return {Promise<Array<calendar_v3.Schema$Event>>}                   Array of events resources to be passed to Google Calendar API.
 */
function createEventResourceArray(shiftsObject, longName: string) {
	const returnArray: calendar_v3.Schema$Event[] = [];
	for (const epoch of shiftsObject) {
		const date = new Date(epoch.start_date);
		for (const shift of epoch.shifts) {
			const start = new Date(date.getTime() + shift.start * 30 * MINUTES);
			const end = new Date(date.getTime() + shift.end * 30 * MINUTES);
			const eventResource: calendar_v3.Schema$Event = {};
			const [handle, $email] = shift.agent.split(' ');
			const email = $email.match(new RegExp(/<(.*)>/))[1];

			eventResource.summary = `${handle} on ${longName}`;
			if (longName === 'balena-io support') {
				eventResource.description =
					'Resources on support: ' +
					process.env.SUPPORT_RESOURCES +
					'\n\nPlease ack in the "channel/support-operations" stream in Zulip.';
			}
			eventResource.start = {
				timeZone: TIMEZONE,
				dateTime: isoDateWithoutTimezone(start),
			};
			eventResource.end = {
				timeZone: TIMEZONE,
				dateTime: isoDateWithoutTimezone(end),
			};

			eventResource.attendees = [];
			eventResource.attendees.push({ email });
			returnArray.push(eventResource);
		}
	}
	return returnArray;
}

/**
 * Load JSON object containing optimized schedule from file, and write to Support schedule Google Calendar, saving ID's of created events for reference.
 * @param  {string}   date   The date  we're targeting, eg `2021-05-03`
 * @param  {string}   modelName   The schedule we're targeting, eg `balenaio`
 */
async function createEvents(date, modelName) {
	const support = await import(`./options/${modelName}.json`);

	try {
		const shiftsObject = await readAndParseJSONSchedule(date, modelName);
		const eventResourceArray = createEventResourceArray(
			shiftsObject,
			support.longName,
		);
		const authClient = await getJWTAuthClient();
		const calendar = google.calendar({ version: 'v3' });
		const eventIDs: Array<string | null | undefined> = [];

		for (const eventResource of eventResourceArray) {
			const eventResponse = await calendar.events.insert({
				auth: authClient,
				calendarId: support.calendarID,
				conferenceDataVersion: 1,
				sendUpdates: 'all',
				requestBody: eventResource,
			});
			const summary = `${eventResponse.data.summary} ${eventResponse.data.start?.dateTime}`;
			console.log(
				'Event created: %s - %s',
				summary,
				eventResponse.data.htmlLink,
			);
			eventIDs.push(eventResponse.data.id);
		}
		await fs.writeFile(
			__dirname +
				`/../logs/${date}_${modelName}/event-ids-written-to-calendar.json`,
			JSON.stringify(eventIDs, null, 2),
		);
	} catch (e) {
		console.error(e);
		process.exit(1);
	}
}

// Read scheduler output file name from command line:
const args = process.argv.slice(2);
if (args.length !== 2) {
	console.log(`Usage: node ${__filename} <yyyy-mm-dd> <model-name>`);
	process.exit(2);
}
const [$date, $modelName] = args;

// Create calendar events:
void createEvents($date, $modelName);
