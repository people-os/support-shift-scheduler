/*
 * Copyright 2019-2022 Balena Ltd.
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

import * as VictorOpsApiClient from 'victorops-api-client';
import { readAndParseJSONSchedule } from '../lib/validate-json';

const TIMEZONE = 'Europe/London';

/**
 * Load JSON object containing optimized schedule from file, and write to Support schedule Google Calendar, saving ID's of created events for reference.
 * @param  {string}   date   The date  we're targeting, e.g. `2021-05-03`
 * @param  {string}   scheduleName   The schedule we're targeting, e.g. `devOps`
 */
async function createScheduleOverrides(date, scheduleName) {
	const { victoropsUsernames } = await import(`./options/${scheduleName}.json`);

	const v = new VictorOpsApiClient();

	try {
		const shiftsObject = await readAndParseJSONSchedule(date, scheduleName);

		for (const epoch of shiftsObject) {
			const epochDate = new Date(epoch.start_date);
			for (const shift of epoch.shifts) {
				const start = new Date(
					epochDate.getTime() + shift.start * 30 * 60 * 1000,
				);
				const end = new Date(epochDate.getTime() + shift.end * 30 * 60 * 1000);
				const { override } = await v.scheduledOverrides.createOverride({
					username: 'balena',
					timezone: TIMEZONE,
					start: start.toISOString(),
					end: end.toISOString(),
				});
				for (const assignment of override.assignments) {
					await v.scheduledOverrides.updateAssignment(
						override.publicId,
						assignment.policy,
						{ username: victoropsUsernames[shift.agentName.slice(1)] },
					);
				}
			}
		}
	} catch (e) {
		console.error(e);
	}
}

// Read scheduler output file name from command line:
const args = process.argv.slice(2);
if (args.length !== 2) {
	console.log(`Usage: node ${__filename} <yyyy-mm-dd> <model-name>`);
	process.exit(1);
}
const [$date, $scheduleName] = args;

// Create schedule overrides:
createScheduleOverrides($date, $scheduleName);
