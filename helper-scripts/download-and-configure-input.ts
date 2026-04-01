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
import * as _ from 'lodash';
import { mkdirp } from 'mkdirp';
import { promises as fs } from 'fs';
import * as moment from 'moment-timezone';

import { getJWTAuthClient } from '../lib/gauth';
import { getSchedulerInput } from '../lib/gsheets';
import { validateJSONScheduleInput } from '../lib/validate-json';

/**
 * Checks if this is a week where PT and UK time are only 7 hours
 * apart instead of  8, due to misaligned daylight savings time
 * changes.
 */
function testIsMisalignedDSTWeek(startDate: string) {
	// Parse the Monday and move to Wednesday:
	const checkDate = moment.utc(startDate).add(2, 'days').startOf('day');

	// Get the offsets for the middle of the week:
	const offsetPT = moment.tz(checkDate, 'America/Los_Angeles').utcOffset();
	const offsetUK = moment.tz(checkDate, 'Europe/London').utcOffset();

	// Return true if the gap is 7 hours (420 mins) instead of 8:
	return Math.abs(offsetUK - offsetPT - 420) < 0.001;
}

/**
 * Read and configure input data from Google Sheets, and save as JSON object.
 */
async function getData(startDate: string, supportName: string) {
	try {
		const supportJSONfile = await fs.readFile(
			'helper-scripts/options/' + supportName + '.json',
			'utf8',
		);
		const supportObj = JSON.parse(supportJSONfile);
		const auth = await getJWTAuthClient();
		let relevantChannelOptions;
		// First determine if an alternative cover configuration is relevant to this teamwork channel:
		if (supportObj.configureAlternativeCover) {
			// Get basic properties first:
			relevantChannelOptions = _.omit(supportObj, [
				'defaultCover',
				'alternativeCover',
				'configureAlternativeCover',
			]);
			// Get appropriate cover config:
			const coverKey = testIsMisalignedDSTWeek(startDate)
				? 'alternativeCover'
				: 'defaultCover';
			_.assign(relevantChannelOptions, supportObj[coverKey]);
		} else {
			// Then no nested "default" or "alternative" cover, just regular properties:
			relevantChannelOptions = _.omit(supportObj, [
				'configureAlternativeCover',
			]);
		}
		// Get agent preferences, combine with options and write to file:
		const schedulerInput = await getSchedulerInput(
			auth,
			startDate,
			relevantChannelOptions,
		);
		_.assign(schedulerInput.options, relevantChannelOptions);
		const stringifiedInput = JSON.stringify(schedulerInput, null, 2);
		validateJSONScheduleInput(schedulerInput);

		const fileDir = `./logs/${startDate}_` + supportName;
		await mkdirp(fileDir);
		await fs.writeFile(
			fileDir + '/support-shift-scheduler-input.json',
			stringifiedInput,
		);
	} catch (e) {
		console.error(e);
		process.exit(1);
	}
}

// Read starting date and support type from command line arguments.
const args = process.argv.slice(2);
if (args.length !== 2) {
	console.log(
		`Please specify the starting date (Monday) in YYYY-MM-DD format, as well as the support type.`,
	);
	process.exit(2);
}

// Load JSON object from output file:
const nextMondayDate = args[0];
const supportModel = args[1];

void getData(nextMondayDate, supportModel);
