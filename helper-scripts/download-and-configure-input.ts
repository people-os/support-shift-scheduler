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
import * as _ from 'lodash';
import * as fs from 'mz/fs';
import * as Promise from 'bluebird';
import * as mkdirp from 'mkdirp';
const mkdirpAsync = Promise.promisify(mkdirp);

import { getAuthClient } from '../lib/gauth';
import { getSchedulerInput } from '../lib/gsheets';
import { validateJSONScheduleInput } from '../lib/validate-json';

/**
 * Read and configure input data from Google Sheets, and save as JSON object
 */
async function getData(startDate: string, supportName: string) {
	const support = JSON.parse(
		fs.readFileSync('helper-scripts/options/' + supportName + '.json', 'utf8'),
	);

	try {
		const auth = await getAuthClient(support);
		const schedulerInput = await getSchedulerInput(auth, startDate, support);
		_.assign(schedulerInput.options, support);
		console.log(JSON.stringify(schedulerInput, null, 2));
		await validateJSONScheduleInput(schedulerInput);

		const fileDir = `./logs/${startDate}_` + supportName;
		await mkdirpAsync(fileDir);

		await fs.writeFile(
			fileDir + '/support-shift-scheduler-input.json',
			JSON.stringify(schedulerInput, null, 2),
		);
	} catch (e) {
		console.error(e);
	}
}

// Read starting date and support type from command line arguments.
const args = process.argv.slice(2);
if (args.length !== 2) {
	console.log(
		`Please specify the starting date (Monday) in YYYY-MM-DD format, as well as the support type.`,
	);
	process.exit(1);
}

// Load JSON object from output file:
const nextMondayDate = args[0];
const supportModel = args[1];

getData(nextMondayDate, supportModel);
