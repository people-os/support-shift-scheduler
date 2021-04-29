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
import { config } from 'dotenv';
config();
import { google } from 'googleapis';
import * as _ from 'lodash';

/**
 * Convert array from Next Cycle Dates Google Sheet into object.
 * @param  {array}   rawDates   Array of 2-element arrays in format [<schedule type>, <start-date>]
 * @return {Promise<object>}             Object with key:value pairs like <schedule type>:<start-date>
 */
async function parseDates(rawDates: any[][]) {
	const parsedDates: { [name: string]: string } = {};
	for (const rawDate of rawDates) {
		parsedDates[rawDate[0]] = rawDate[1];
	}
	return parsedDates;
}

/**
 * Read and parse content of Next Cycle Dates Google Sheet.
 * @param  {object} auth   OAuth 2.0 access token
 * @return {Promise<object>}        Object with key:value pairs like <schedule type>:<start-date>
 */
export async function getNextCycleDates(auth) {
	const sheets = google.sheets({ version: 'v4', auth });
	const result = await sheets.spreadsheets.values.get({
		spreadsheetId: process.env.TEAM_MODEL_ID,
		range: 'Next Cycle Dates!A1:B',
		valueRenderOption: 'FORMATTED_VALUE',
	});
	const parsedNextCycleDates = await parseDates(result.data.values);
	return parsedNextCycleDates;
}

/**
 * Create object from raw agent input.
 * @param  {array}  rawInput    Raw spreadsheet data as nested arrays
 * @return {Promise<object>}             Object with keys in format `@<github-handle>`
 */
async function createObject(rawInput) {
	return _.reduce(
		rawInput,
		(dict, row) => {
			const [handle, ...data] = row;
			dict['@' + handle] = data;
			return dict;
		},
		{},
	);
}

/**
 * Check if input object has duplicate keys, and if so throw error.
 * @param  {object}  inputObjects    Raw spreadsheet data as nested arrays
 */
async function checkForDuplicates(inputObjects = {}) {
	const handles = Object.keys(inputObjects);
	if (handles.length !== _.uniq(handles).length) {
		throw new Error('The input has duplicate agent handles');
	}
}

/**
 * Create agent object, checking for correct format for final scheduler input.
 * @param  {object}   opts   Object containing the necessary properties
 * @return {Promise<object>}          Checked agent object
 */
async function createAgent(opts) {
	const requiredOpts = [
		'handle',
		'email',
		'weekAverageHours',
		'idealShiftLength',
		'availableHours',
	];
	for (const opt of requiredOpts) {
		if (opts[opt] === undefined) {
			throw new Error('Missing required option:' + opt);
		}
	}
	return _.create({}, opts);
}

function parseAvailability(availability) {
	const allowedValues = ['1', '2', '4'];
	if (allowedValues.includes(availability.toString())) {
		return Number(availability);
	} else {
		return 0;
	}
}

/**
 * Parse agent data read from Support Scheduler History.
 * @param  {array}  rawInput    Raw spreadsheet data as nested arrays
 * @param  {string} startDate   Schedule start date in format YYYY-MM-DD
 * @param  {number} numDays     Number of consecutive days to schedule
 * @return {Promise<object>}             Parsed input object for scheduler
 */
async function parseInput(rawInput, startDate = null, numDays = 5, slotsInDay) {
	if (_.isEmpty(startDate)) {
		throw new Error('Need start date');
	}
	const schedulerInput = {
		agents: [],
		options: {},
	};
	const inputByGithubHandle = await createObject(rawInput);
	await checkForDuplicates(inputByGithubHandle);

	for (const handle of Object.keys(inputByGithubHandle)) {
		const email = inputByGithubHandle[handle].shift();

		const weekAverageHours = _.toInteger(inputByGithubHandle[handle].shift());

		const idealShiftLength = _.toInteger(inputByGithubHandle[handle].shift());

		const availableHours = [];

		for (let i = 0; i < numDays; i++) {
			const hourAvailability = inputByGithubHandle[handle]
				.splice(0, 48)
				.map(parseAvailability);

			availableHours.push(hourAvailability);
		}

		const newAgent = await createAgent({
			handle,
			email,
			weekAverageHours,
			idealShiftLength,
			availableHours,
		});
		schedulerInput.agents.push(newAgent);
	}
	console.log(slotsInDay);
	schedulerInput.agents.forEach((agent) => {
		agent.availableHours.forEach((day, dayIndex) => {
			const followingDay = dayIndex + 1;
			if (dayIndex < 5) {
				for (let i = 0; i < (slotsInDay - 24) * 2; i++) {
					day.push(agent.availableHours[followingDay][i]);
				}
			}
		});
		agent.availableHours.splice(5, 1);
	});
	schedulerInput.options['startMondayDate'] = startDate;
	return schedulerInput;
}

/**
 * Read and parse agent preferences and availability from Support Scheduler History sheet.
 * @param  {object} auth           OAuth 2.0 access token
 * @param  {string} nextMondayDate Schedule start date in format YYYY-MM-DD
 * @param  {object} support
 * @return {Promise<object>}                Parsed input object for scheduler (more options will be added to this object by download-and-configure-input)
 */
export async function getSchedulerInput(auth, nextMondayDate, support) {
	const sheets = google.sheets({ version: 'v4', auth });
	const range = nextMondayDate + '_input!A3:KF';
	const result = await sheets.spreadsheets.values.get({
		spreadsheetId: support.logSheet,
		range,
		valueRenderOption: 'FORMATTED_VALUE',
	});
	const parsedInput = await parseInput(
		result.data.values,
		nextMondayDate,
		support.numConsecutiveDays + 1,
		support.slotsInDay,
	);
	return parsedInput;
}