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
import * as dotenv from 'dotenv';
dotenv.config();

import * as VictorOpsApiClient from 'victorops-api-client';
import * as devOps from './options/devOps.json';
import * as _ from 'lodash';
import { google } from 'googleapis';
import type { calendar_v3 } from 'googleapis';
import { getJWTAuthClient } from '../lib/gauth';
import { differenceInCalendarDays } from 'date-fns';

const vOpsToGh = _.invert(devOps.victoropsUsernames);

// Victorops returns the date in UTC, I think..
const TIMEZONE = 'Etc/UTC';
const scheduleName = 'devOps';

function isoDateWithoutTimezone(date) {
	// ISO string without the `z` timezone
	return date.toISOString().slice(0, -1);
}

function getRoundedDate(d: Date) {
	const ms = 1000 * 60; // 1 minutes
	const roundedDate = new Date(Math.round(d.getTime() / ms) * ms);

	return roundedDate;
}

const devopsTeam = 'team-N8nHYAN7UHGG8CUb';
const v = new VictorOpsApiClient({ maxContentLength: 500000 });
const calendar = google.calendar({ version: 'v3' });

const DRY_RUN = process.env.DRY_RUN === 'true';
const DAY_SKIP_MAX = 90;
const DAYS_FORWARD_MAX = 123;

function requireEnv(name: string) {
	const value = process.env[name];
	if (!value) {
		throw new Error(`Environment variable ${name} is not set.`);
	}
	return value;
}

function parseColumn(name: string, fallback: string) {
	// Empty values are rejected by validation rather than falling back.
	const column = (process.env[name] ?? fallback).trim().toUpperCase();
	if (!/^[A-Z]+$/.test(column)) {
		throw new Error(
			`Environment variable ${name} must be a column letter (e.g. A, B, AA), got '${column}'.`,
		);
	}
	return column;
}

async function loadHandleToEmail() {
	const spreadsheetId = requireEnv('DEVOPS_AGENT_DEFINITIONS_SPREADSHEET_ID');
	const sheetName = requireEnv('DEVOPS_AGENT_DEFINITIONS_SHEET_NAME');
	const handleColumn = parseColumn(
		'DEVOPS_AGENT_DEFINITIONS_HANDLE_COLUMN',
		'A',
	);
	const emailColumn = parseColumn('DEVOPS_AGENT_DEFINITIONS_EMAIL_COLUMN', 'B');
	if (handleColumn === emailColumn) {
		throw new Error(
			'DEVOPS_AGENT_DEFINITIONS_HANDLE_COLUMN and DEVOPS_AGENT_DEFINITIONS_EMAIL_COLUMN must be different columns.',
		);
	}

	const startRowValue = process.env.DEVOPS_AGENT_DEFINITIONS_START_ROW ?? '2';
	const startRow = Number.parseInt(startRowValue, 10);
	if (!Number.isInteger(startRow) || startRow < 1) {
		throw new Error(
			`Environment variable DEVOPS_AGENT_DEFINITIONS_START_ROW must be a positive integer, got '${startRowValue}'.`,
		);
	}

	// With sheetName="Agents", this is "'Agents'".
	const sheetPrefix = `'${sheetName.replace(/'/g, "''")}'`;
	// With default values, this is "'Agents'!A2:A".
	const handleRange = `${sheetPrefix}!${handleColumn}${startRow}:${handleColumn}`;
	// With default values, this is "'Agents'!B2:B".
	const emailRange = `${sheetPrefix}!${emailColumn}${startRow}:${emailColumn}`;

	const auth = await getJWTAuthClient();
	const sheets = google.sheets({ version: 'v4', auth });
	const result = await sheets.spreadsheets.values.batchGet({
		spreadsheetId,
		ranges: [handleRange, emailRange],
		valueRenderOption: 'FORMATTED_VALUE',
	});

	const [handleValueRange, emailValueRange] = result.data.valueRanges ?? [];
	const handles = handleValueRange?.values ?? [];
	const emails = emailValueRange?.values ?? [];

	const handleToEmail: Record<string, string> = {};
	const rowCount = Math.max(handles.length, emails.length);
	for (let i = 0; i < rowCount; i++) {
		// Read the first cell in the handle row, trim whitespace, and allow either "user" or "@user".
		const handle = String(handles[i]?.[0] ?? '')
			.trim()
			.replace(/^@/, '');
		// Read the first cell in the email row and normalize blank/missing cells to an empty string.
		const email = String(emails[i]?.[0] ?? '').trim();
		if (!handle && !email) {
			continue;
		}
		if (!handle || !email) {
			throw new Error(
				`Missing handle or email in ${sheetName} row ${startRow + i}.`,
			);
		}
		if (handleToEmail[handle]) {
			throw new Error(`Duplicate GitHub handle '${handle}' in ${sheetName}.`);
		}
		handleToEmail[handle] = email;
	}

	if (_.isEmpty(handleToEmail)) {
		throw new Error(`No agent definitions found in ${sheetName}.`);
	}
	return handleToEmail;
}

function getEmail(handleToEmail, ghName: string) {
	const email = handleToEmail[ghName];
	if (!email) {
		throw new Error(`Could not find email address for '${ghName}'`);
	}
	return email;
}

async function createSupportCalendarEvent(
	authClient: Awaited<ReturnType<typeof getJWTAuthClient>>,
	handleToEmail,
	ghName: string,
	eventStart: Date,
	eventEnd: Date,
) {
	const eventResource: calendar_v3.Schema$Event = {
		summary: `${ghName} on ${scheduleName} support`,
		start: {
			timeZone: TIMEZONE,
			dateTime: isoDateWithoutTimezone(eventStart),
		},
		end: {
			timeZone: TIMEZONE,
			dateTime: isoDateWithoutTimezone(eventEnd),
		},
		attendees: [{ email: getEmail(handleToEmail, ghName) }],
	};

	if (DRY_RUN) {
		console.log(
			'[DRY RUN] Would create event:',
			JSON.stringify(eventResource, null, 2),
		);
	} else {
		await calendar.events.insert({
			auth: authClient,
			calendarId: devOps.calendarID,
			conferenceDataVersion: 1,
			sendUpdates: 'all',
			requestBody: eventResource,
		});
	}
}

async function futureWeekends(
	start: Date,
	end: Date,
	now: Date,
	handleToEmail,
) {
	const daysInFuture = differenceInCalendarDays(start, now);
	if (Number.isNaN(daysInFuture) || daysInFuture > DAY_SKIP_MAX) {
		throw new Error(
			`The start date can be at most ${DAY_SKIP_MAX} days in the future, got ${daysInFuture} days in the future`,
		);
	}
	const daysForward = differenceInCalendarDays(end, start);
	if (Number.isNaN(daysForward) || daysForward > DAYS_FORWARD_MAX) {
		throw new Error(
			`The date range can be at most ${DAYS_FORWARD_MAX} days, got ${daysForward} days`,
		);
	}

	const authClient = await getJWTAuthClient();

	const x = (await v.oncall.getTeamSchedule(devopsTeam, {
		daysForward: daysForward, // 123 max
		daysSkip: daysInFuture,
	})) as {
		team: { name: string; slug: string };
		schedules: Array<{
			policy: { name: 'balena-production'; slug: 'pol-1jkqGm7URSxtfrVA' };
			schedule: Array<{
				onCallUser?: { username: string };
				overrideOnCallUser?: { username: string };
				onCallType: string;
				rotationName: string;
				shiftName: string;
				shiftRoll: string; // '2022-01-17T03:00:00Z'
				rolls: Array<{
					start: string; // '2022-01-17T03:00:00Z'
					end: string; // '2022-01-22T03:00:00Z'
					onCallUser: { username: string };
					isRoll: boolean;
				}>;
			}>;
			overrides: Array<{
				origOnCallUser: { username: string };
				overrideOnCallUser: { username: string };
				start: string; // '2022-01-18T11:00:00Z'
				end: string; // '2022-01-18T15:00:00Z'
				policy: { name: string; slug: string };
			}>;
		}>;
	};

	for (const { policy, schedule } of x.schedules) {
		if (policy.name === 'balena-production') {
			for (const { shiftName, rolls } of schedule) {
				if (shiftName === 'Weekend') {
					for (const roll of rolls) {
						const ghName = vOpsToGh[roll.onCallUser.username];
						const eventStart = getRoundedDate(new Date(roll.start));
						const eventEnd = getRoundedDate(new Date(roll.end));

						await createSupportCalendarEvent(
							authClient,
							handleToEmail,
							ghName,
							eventStart,
							eventEnd,
						);
					}
				}
			}
		}
	}
}

async function pastSchedule(
	start: Date,
	end: Date,
	handleToEmail,
	onlyWeekends = true,
) {
	const authClient = await getJWTAuthClient();

	const x = (await v.reporting.getShiftChanges(devopsTeam, {
		start: start.toISOString(),
		end: end.toISOString(),
	})) as {
		teamSlug: string;
		start: string; // '2022-01-11T00:00:00.000Z',
		end: string; // '2022-01-11T14:34:45.066Z',
		results: number;
		userLogs: Array<{
			userId: string;
			adjustedTotal: { hours: number; minutes: number };
			total: { hours: number; minutes: number };
			log: [
				{
					on: string;
					off: string;
					duration: { hours: number; minutes: number };
					escalationPolicy: {
						name: 'balena-production';
						slug: 'pol-1jkqGm7URSxtfrVA';
					};
				},
			];
		}>;
	};

	for (const userLog of x.userLogs) {
		const ghName = vOpsToGh[userLog.userId];
		if (!ghName) {
			console.log(`skipping unknown user '${userLog.userId}'`);
			continue;
		}
		for (const log of userLog.log) {
			const eventStart = getRoundedDate(new Date(log.on));
			const eventEnd = getRoundedDate(new Date(log.off));

			if (
				onlyWeekends &&
				// Starts on Friday or Saturday, since it's based on shift changes so they get merged - they need to be sorted/split manually :(
				(!(eventStart.getUTCDay() === 5 || eventStart.getUTCDay() === 6) ||
					// Ends on Monday
					eventEnd.getUTCDay() !== 1)
			) {
				continue;
			}
			if (onlyWeekends && log.duration.hours > 48) {
				console.warn(
					`You will need to manually fix the entry for '${eventStart}' to '${eventEnd}' for '${ghName}' as they had a normal shift run into a weekend shift and we don't separate them`,
				);
			}

			await createSupportCalendarEvent(
				authClient,
				handleToEmail,
				ghName,
				eventStart,
				eventEnd,
			);
		}
	}
}

function parseDate(input: string) {
	const epoch = Date.parse(input);
	if (Number.isNaN(epoch)) {
		throw new Error(`Invalid start date '${input}'`);
	}
	const date = new Date(epoch);
	date.setUTCHours(0);
	date.setUTCMinutes(0);
	date.setUTCSeconds(0);
	date.setUTCMilliseconds(0);
	return date;
}

async function main() {
	const args = process.argv.slice(2);
	if (args.length !== 2) {
		console.log(
			`Usage: node ${__filename} <start yyyy-mm-dd> <end yyyy-mm-dd>`,
		);
		console.log(
			[
				'Agent emails are loaded from Google Sheets using these environment variables:',
				'DEVOPS_AGENT_DEFINITIONS_SPREADSHEET_ID',
				'DEVOPS_AGENT_DEFINITIONS_SHEET_NAME',
				'DEVOPS_AGENT_DEFINITIONS_HANDLE_COLUMN (defaults to A)',
				'DEVOPS_AGENT_DEFINITIONS_EMAIL_COLUMN (defaults to B)',
				'DEVOPS_AGENT_DEFINITIONS_START_ROW (defaults to 2)',
			].join('\n'),
		);
		process.exit(1);
	}
	const startDate = parseDate(args[0]);
	const endDate = parseDate(args[1]);
	const handleToEmail = await loadHandleToEmail();
	const NOW = parseDate(Date());

	if (DRY_RUN) {
		console.log('[DRY RUN] No calendar events will be created.');
	}

	if (endDate < startDate) {
		throw new Error('Start date must be earlier than end date');
	}

	if (startDate <= NOW && endDate <= NOW) {
		await pastSchedule(startDate, endDate, handleToEmail);
	} else if (startDate >= NOW && endDate >= NOW) {
		await futureWeekends(startDate, endDate, NOW, handleToEmail);
	} else {
		throw new Error(
			`Both dates need to be in the past/now, or in the future/now`,
		);
	}
}

void main().catch((e) => {
	console.error(e);
	process.exit(1);
});
