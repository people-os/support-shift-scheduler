const { Validator, ValidationError } = require('jsonschema')
const scheduleInputSchema = require('./schemas/support-shift-scheduler-input.schema.json')
const scheduleOutputSchema = require('./schemas/support-shift-scheduler-output.schema.json')


/**
 * Validate JSON input for scheduler
 * @param  {array}   json   JSON input object
 * @return {object}         jsonschema Validator object
 */
async function validateJSONScheduleInput(json={}) {
  let validator = new Validator()
  return validator.validate(json, scheduleInputSchema, { "throwError": true, "lestedErrors": true })
}


/**
 * Validate JSON output for scheduler
 * @param  {array}   json   JSON output object
 * @return {object}         jsonschema Validator object
 */
async function validateJSONScheduleOutput(json={}) {
  let validator = new Validator()
  return validator.validate(json, scheduleOutputSchema, { "throwError": true, "lestedErrors": true })
}



exports.validateJSONScheduleInput = validateJSONScheduleInput
exports.validateJSONScheduleOutput = validateJSONScheduleOutput
