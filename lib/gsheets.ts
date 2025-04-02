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
import { google } from 'googleapis';
import * as _ from 'lodash';

interface Agent {
	handle: string;
	email: string;
	weight: number;
	isSupportEngineer: number;
	teamworkBalance: number;
	nextWeekCredit: number;
	idealShiftLength: number;
	availableSlots: number[][];
}

/**
 * Create object from raw agent input.
 * @param  {array}  rawInput    Raw spreadsheet data as nested arrays
 * @return {object}             Object with keys in format `@<github-handle>`
 */
function createObject(rawInput) {
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
function checkForDuplicates(inputObjects = {}) {
	const handles = Object.keys(inputObjects);
	if (handles.length !== _.uniq(handles).length) {
		throw new Error('The input has duplicate agent handles');
	}
}

/**
 * Create agent object, checking for correct format for final scheduler input.
 * @param  {object}   opts   Object containing the necessary properties
 * @return {Agent}          Checked agent object
 */
function createAgent(opts) {
	const requiredOpts = [
		'handle',
		'email',
		'weight',
		'isSupportEngineer',
		'teamworkBalance',
		'nextWeekCredit',
		'idealShiftLength',
		'availableSlots',
	];
	for (const opt of requiredOpts) {
		if (opts[opt] === undefined) {
			throw new Error('Missing required option:' + opt);
		}
	}
	return _.create({}, opts);
}

function parseAvailability(availability) {
	const allowedValues = ['1', '2', '3', '4'];
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
 * @return {object}             Parsed input object for scheduler
 */
function parseInput(rawInput, startDate = null, numDays = 5, endHour) {
	if (_.isEmpty(startDate)) {
		throw new Error('Need start date');
	}
	const schedulerInput = {
		agents: [] as Agent[],
		options: {},
	};
	const inputByGithubHandle = createObject(rawInput);
	checkForDuplicates(inputByGithubHandle);

	for (const handle of Object.keys(inputByGithubHandle)) {
		const email = inputByGithubHandle[handle].shift();
		const weight = Number(inputByGithubHandle[handle].shift());
		const isSupportEngineer = Number(inputByGithubHandle[handle].shift());
		const teamworkBalance = Number(inputByGithubHandle[handle].shift());
		const nextWeekCredit = Number(inputByGithubHandle[handle].shift());
		const idealShiftLength = _.toInteger(inputByGithubHandle[handle].shift());
		const availableSlots: number[][] = [];
		for (let i = 0; i < numDays; i++) {
			const slotAvailability = inputByGithubHandle[handle]
				.splice(0, 48)
				.map(parseAvailability);
			availableSlots.push(slotAvailability);
		}
		const newAgent = createAgent({
			handle,
			email,
			weight,
			isSupportEngineer,
			teamworkBalance,
			nextWeekCredit,
			idealShiftLength,
			availableSlots,
		});
		schedulerInput.agents.push(newAgent);
	}
	schedulerInput.agents.forEach((agent) => {
		agent.availableSlots.forEach((day, dayIndex) => {
			const followingDay = dayIndex + 1;
			if (dayIndex < 5 && endHour > 24) {
				for (let i = 0; i < (endHour - 24) * 2; i++) {
					day.push(agent.availableSlots[followingDay][i]);
				}
			}
		});
		agent.availableSlots.splice(5, 1);
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
	const range = nextMondayDate + '_input!A3:KH';
	const result = await sheets.spreadsheets.values.get({
		spreadsheetId: support.logSheet,
		range,
		valueRenderOption: 'FORMATTED_VALUE',
	});
	const parsedInput = parseInput(
		result.data.values,
		nextMondayDate,
		support.numDays + 1,
		support.endHour,
	);
	return parsedInput;
}

/**
 * Parse agent data read from Support Scheduler History.
 * @param  {array}  rawInput    Raw spreadsheet data as nested arrays
 * @return {object}             Parsed input object for scheduler
 */
function parseOnboardingInput(rawInput) {
	const columns = rawInput;
	const onboarderInput = {
		mentors: [],
		onboarders: [],
	};
	if (columns.length > 0) {
		onboarderInput.mentors = columns[0];
		onboarderInput.onboarders = columns[1];
	}
	const allAgents = onboarderInput.mentors.concat(onboarderInput.onboarders);
	if (allAgents.length !== _.uniq(allAgents).length && allAgents.length !== 0) {
		throw new Error('The input has duplicate agent handles');
	}
	return onboarderInput;
}

/**
 * Read and parse agent preferences and availability from Support Scheduler History sheet.
 * @param  {object} auth           OAuth 2.0 access token
 * @param  {string} nextMondayDate Schedule start date in format YYYY-MM-DD
 * @param  {object} support
 * @return {Promise<object>}                Parsed input object for scheduler (more options will be added to this object by download-and-configure-input)
 */
export async function getOnboardingInput(auth, nextMondayDate, support) {
	const sheets = google.sheets({ version: 'v4', auth });
	const range = nextMondayDate + '!A2:B';
	let agents: any[][] | null | undefined = [];
	try {
		const result = await sheets.spreadsheets.values.get({
			spreadsheetId: support.onboardingSheet,
			range,
			valueRenderOption: 'FORMATTED_VALUE',
			majorDimension: 'COLUMNS',
		});
		agents = result.data.values;
	} catch (err) {
		console.log(
			'Onboarding data for',
			support.modelName,
			'on',
			nextMondayDate,
			'not found:',
			err,
		);
		return process.exit(0);
	}
	const parsedInput = parseOnboardingInput(agents);
	return parsedInput;
}
