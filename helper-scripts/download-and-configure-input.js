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
const _ = require('lodash');
const fs = require('mz/fs');
const Promise = require('bluebird');
const mkdirp = Promise.promisify(require('mkdirp'));
const { getAuthClient } = require('../lib/gauth');
const { getNextCycleDates } = require('../lib/gsheets');
const { getSchedulerInput } = require('../lib/gsheets');
const { validateJSONScheduleInput } = require('../lib/validate-json');

const SCHEDULE_OPTS = {
	numConsecutiveDays: 5,
	numSimultaneousTracks: 2,
	supportStartHour: 8,
	supportEndHour: 24,
	shiftMinDuration: 2,
	shiftMaxDuration: 8,
	optimizationTimeout: 3600,
};

/**
 * Read and configure input data from Google Sheets, and save as JSON object
 */
async function getData() {
	try {
		const auth = await getAuthClient();
		const parsedNextCycleDates = await getNextCycleDates(auth);
		const nextMondayDate = parsedNextCycleDates.support;

		const schedulerInput = await getSchedulerInput(
			auth,
			nextMondayDate,
			SCHEDULE_OPTS.numConsecutiveDays
		);
		_.assign(schedulerInput.options, SCHEDULE_OPTS);
		console.log(JSON.stringify(schedulerInput, null, 2));
		const schedulerInputValidation = await validateJSONScheduleInput(
			schedulerInput
		);

		const fileDir = `./logs-${nextMondayDate}`;
		await mkdirp(fileDir);

		await fs.writeFile(
			fileDir + '/support-shift-scheduler-input.json',
			JSON.stringify(schedulerInput, null, 2)
		);
	} catch (e) {
		console.error(e);
	}
}

getData();
