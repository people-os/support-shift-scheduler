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
const { Validator } = require('jsonschema');
const scheduleInputSchema = require('./schemas/support-shift-scheduler-input.schema.json');
const scheduleOutputSchema = require('./schemas/support-shift-scheduler-output.schema.json');

/**
 * Validate JSON input for scheduler
 * @param  {object}   json   JSON input object
 * @return {Promise<object>}         jsonschema Validator object
 */
async function validateJSONScheduleInput(json = {}) {
	let validator = new Validator();
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
async function validateJSONScheduleOutput(json = {}) {
	let validator = new Validator();
	return validator.validate(json, scheduleOutputSchema, {
		throwError: true,
		nestedErrors: true,
	});
}

exports.validateJSONScheduleInput = validateJSONScheduleInput;
exports.validateJSONScheduleOutput = validateJSONScheduleOutput;
