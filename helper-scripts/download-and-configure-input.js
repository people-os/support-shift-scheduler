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
const _ = require('lodash');
const fs = require('mz/fs');
const Promise = require('bluebird');
const mkdirp = Promise.promisify(require('mkdirp'));

const { getAuthClient } = require('../lib/gauth');
const { getNextCycleDates } = require('../lib/gsheets');
const { getSchedulerInput } = require('../lib/gsheets');
const { validateJSONScheduleInput } = require('../lib/validate-json');

/**
 * Read and configure input data from Google Sheets, and save as JSON object
 */
async function getData(supportModel) {
	const scheduleOpts = JSON.parse(
		fs.readFileSync('helper-scripts/options/' + supportModel + '.json')
	);

	try {
		const auth = await getAuthClient(supportModel);
		const parsedNextCycleDates = await getNextCycleDates(auth);
		const nextMondayDate = parsedNextCycleDates.support;

		const schedulerInput = await getSchedulerInput(
			auth,
			nextMondayDate,
			scheduleOpts.numConsecutiveDays + 1,
			supportModel
		);
		_.assign(schedulerInput.options, scheduleOpts);
		console.log(JSON.stringify(schedulerInput, null, 2));
		const schedulerInputValidation = await validateJSONScheduleInput(
			schedulerInput
		);

		const fileDir = `./logs/${nextMondayDate}_` + supportModel;
		await mkdirp(fileDir);

		await fs.writeFile(
			fileDir + '/support-shift-scheduler-input.json',
			JSON.stringify(schedulerInput, null, 2)
		);
	} catch (e) {
		console.error(e);
	}
}

// Read scheduling algorithm output file name from command line:
const args = process.argv.slice(2);
if (args.length != 1) {
	console.log(`please specify Scheduling Options file`);
	process.exit(1);
}

// Load JSON object from output file:
const supportModel = args[0];

getData(supportModel);
