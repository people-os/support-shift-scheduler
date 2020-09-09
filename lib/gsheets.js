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
const { google } = require('googleapis');
const _ = require('lodash');

/**
 * Convert array from Next Cycle Dates Google Sheet into object.
 * @param  {array}   rawDates   Array of 2-element arrays in format [<schedule type>, <start-date>]
 * @return {object}             Object with key:value pairs like <schedule type>:<start-date>
 */
async function parseDates(rawDates) {
	const parsedDates = {};
	for (let i = 0; i < rawDates.length; i++) {
		parsedDates[rawDates[i][0]] = rawDates[i][1];
	}
	return parsedDates;
}

/**
 * Read and parse content of Next Cycle Dates Google Sheet.
 * @param  {object} auth   OAuth 2.0 access token
 * @return {object}        Object with key:value pairs like <schedule type>:<start-date>
 */
async function getNextCycleDates(auth) {
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
 * @return {object}             Object with keys in format @<github-handle>
 */
async function createObject(rawInput) {
	return _.reduce(
		rawInput,
		(dict, row) => {
			const [handle, ...data] = row;
			dict['@' + handle] = data;
			return dict;
		},
		{}
	);
}

/**
 * Check if input object has duplicate keys, and if so throw error.
 * @param  {array}  inputObjects    Raw spreadsheet data as nested arrays
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
 * @return {object}          Checked agent object
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
			throw new Error('Missing required option:', opt);
		}
	}
	return _.create({}, opts);
}

/**
 * Parse agent data read from Support Scheduler History.
 * @param  {array}  rawInput    Raw spreadsheet data as nested arrays
 * @param  {string} startDate   Schedule start date in format YYYY-MM-DD
 * @param  {number} numDays     Number of consecutive days to schedule
 * @return {object}             Parsed input object for scheduler
 */
async function parseInput(rawInput, startDate = null, numDays = 5) {
	if (_.isEmpty(startDate)) {
		throw new Error('Need start date');
	}
	const schedulerInput = {
		agents: [],
		options: {},
	};
	const inputByGithubHandle = await createObject(rawInput);
	await checkForDuplicates(inputByGithubHandle);
	const agentsEmail = {};
	const agentsWeekAverageHours = {};
	const agentsIdealShiftLength = {};
	const agentsAvailableHours = {};

	for (const handle of Object.keys(inputByGithubHandle)) {
		agentsEmail[handle] = inputByGithubHandle[handle].splice(0, 1);

		agentsWeekAverageHours[handle] = _.toInteger(
			inputByGithubHandle[handle].splice(0, 1)
		);

		agentsIdealShiftLength[handle] = _.toInteger(
			inputByGithubHandle[handle].splice(0, 1)
		);

		agentsAvailableHours[handle] = [];

		for (let i = 0; i < numDays; i++) {
			let slotAvailability = inputByGithubHandle[handle].splice(0, 48);
			const hourAvailability = [];
			const allowedValues = ['1', '2', '4'];

			slotAvailability = slotAvailability.map(item => {
				if (allowedValues.includes(item.toString())) return Number(item);
				else return 0;
			});

			for (let h = 0; h < 24; h++) {
				let p1 = slotAvailability[h * 2];
				let p2 = slotAvailability[h * 2 + 1];
				let h_pref = 0;

				if (p1 !== 0 && p2 !== 0) {
					if (p1 === 1) {
						if (p2 === 2) {
							h_pref = 2;
						} else if (p2 === 1) {
							h_pref = 1;
						}
					} else if (p1 === 2) {
						h_pref = 2;
					} else if (p1 === 4) {
						h_pref = Number(p2);
					}
				}
				hourAvailability.push(h_pref);
			}
			agentsAvailableHours[handle].push(hourAvailability);
		}

		const newAgent = await createAgent({
			handle: handle,
			email: agentsEmail[handle][0],
			weekAverageHours: agentsWeekAverageHours[handle],
			idealShiftLength: agentsIdealShiftLength[handle],
			availableHours: agentsAvailableHours[handle],
		});
		schedulerInput.agents.push(newAgent);
	}
	//TODO only if over 24 hours
	schedulerInput.agents.forEach(agent => {
		agent.availableHours.forEach((day, dayIndex) => {
			let followingDay = dayIndex + 1;
			if (dayIndex < 5) {
				day.push(agent.availableHours[followingDay][0]);
				day.push(agent.availableHours[followingDay][1]);
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
 * @param  {number} numDays        Number of consecutive days to schedule
 * @return {object}                Parsed input object for scheduler (more options will be added to this object by download-and-configure-input.js)
 */
async function getSchedulerInput(auth, nextMondayDate, numDays, supportModel) {
	const sheets = google.sheets({ version: 'v4', auth });
	const sheet = supportModel === 'productOS' ? '_productOS' : '_input';
	const range = nextMondayDate + sheet + '!A3:KF';
	const result = await sheets.spreadsheets.values.get({
		spreadsheetId: process.env.SUPPORT_SCHEDULER_HISTORY_ID,
		range,
		valueRenderOption: 'FORMATTED_VALUE',
	});
	const parsedInput = await parseInput(
		result.data.values,
		nextMondayDate,
		numDays
	);
	return parsedInput;
}

exports.getNextCycleDates = getNextCycleDates;
exports.getSchedulerInput = getSchedulerInput;
