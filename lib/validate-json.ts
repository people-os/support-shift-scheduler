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
import { Validator } from 'jsonschema';
import * as scheduleInputSchema from './schemas/support-shift-scheduler-input.schema.json';
import * as scheduleOutputSchema from './schemas/support-shift-scheduler-output.schema.json';

/**
 * Validate JSON input for scheduler
 * @param  {object}   json   JSON input object
 * @return {Promise<object>}         jsonschema Validator object
 */
export async function validateJSONScheduleInput(json = {}) {
	const validator = new Validator();
	return validator.validate(json, scheduleInputSchema, {
		throwError: true,
		nestedErrors: true,
	});
}

/**
 * Validate JSON output for scheduler
 * @param  {object}   json   JSON output object
 * @return {Promise<object>}         jsonschema Validator object
 */
export async function validateJSONScheduleOutput(json = {}) {
	const validator = new Validator();
	return validator.validate(json, scheduleOutputSchema, {
		throwError: true,
		nestedErrors: true,
	});
}

/**
 * Read, parse and validate JSON output file from scheduling algorithm.
 * @param  {string}   date   The date  we're targeting, eg `2021-05-03`
 * @param  {string}   scheduleName   The schedule we're targeting, eg `balenaio`
 * @return {Promise<object>}              Parsed and validated object with schedule
 */
export async function readAndParseJSONSchedule(date, scheduleName) {
	const jsonObject = await import(
		`../logs/${date}_${scheduleName}/support-shift-scheduler-output.json`
	);
	await validateJSONScheduleOutput(jsonObject);
	return jsonObject;
}
