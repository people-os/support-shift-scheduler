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
import * as devOps from './helper-scripts/options/devOps.json';
import * as _ from 'lodash';
import { google, calendar_v3 } from 'googleapis';
import { getAuthClient } from './lib/gauth';
import { agents } from './logs/2022-08-01_devOps/support-shift-scheduler-input.json';
import { setTimeout } from 'timers/promises';
import { differenceInCalendarDays } from 'date-fns';

const handleToEmail = _(agents)
	.keyBy((a) => a.handle.replace(/^@/, ''))
	.mapValues((a) => a.email)
	.value();

const vOpsToGh = _.invert(devOps.victoropsUsernames);

// Victorops returns the date in UTC, I think..
const TIMEZONE = 'Etc/UTC';
const scheduleName = 'devOps';

function isoDateWithoutTimezone(date) {
	// ISO string without the `z` timezone
	return date.toISOString().slice(0, -1);
}

function getRoundedDate(d: Date) {
	let ms = 1000 * 60; // 1 minutes
	let roundedDate = new Date(Math.round(d.getTime() / ms) * ms);

	return roundedDate;
}

const devopsTeam = 'team-N8nHYAN7UHGG8CUb';
const v = new VictorOpsApiClient();
const calendar = google.calendar({ version: 'v3' });

const DAY_SKIP_MAX = 90;
const DAYS_FORWARD_MAX = 123;
async function futureWeekends(start: Date, end: Date) {
	const daysInFuture = differenceInCalendarDays(start, NOW);
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

	const authClient = await getAuthClient(devOps);

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
						const start = getRoundedDate(new Date(roll.start));
						const end = getRoundedDate(new Date(roll.end));

						const eventResource: calendar_v3.Schema$Event = {
							summary: `${ghName} on ${scheduleName} support`,
							start: {
								timeZone: TIMEZONE,
								dateTime: isoDateWithoutTimezone(start),
							},
							end: {
								timeZone: TIMEZONE,
								dateTime: isoDateWithoutTimezone(end),
							},
							attendees: [{ email: handleToEmail[ghName] }],
						};

						await calendar.events.insert({
							auth: authClient,
							calendarId: devOps.calendarID,
							conferenceDataVersion: 1,
							sendUpdates: 'all',
							requestBody: eventResource,
						});
					}
				}
			}
		}
	}
}

async function pastSchedule(start: Date, end: Date, onlyWeekends = true) {
	const authClient = await getAuthClient(devOps);

	const until = end;

	while (end <= until) {
		const x = (await v.reporting.getShiftChanges(devopsTeam, {
			start: start.toISOString(),
			end: end.toISOString(),
		})) as {
			teamSlug: string;
			start: string; //'2022-01-11T00:00:00.000Z',
			end: string; //'2022-01-11T14:34:45.066Z',
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
				const start = getRoundedDate(new Date(log.on));
				const end = getRoundedDate(new Date(log.off));

				if (
					onlyWeekends &&
					// Starts on Friday or Saturday, since it's based on shift changes so they get merged - they need to be sorted/split manually :(
					(!(start.getUTCDay() === 5 || start.getUTCDay() === 6) ||
						// Ends on Monday
						end.getUTCDay() !== 1)
				) {
					continue;
				}
				if (onlyWeekends && log.duration.hours > 48) {
					console.warn(
						`You will need to manually fix the entry for '${start}' to '${end}' for '${ghName}' as they had a normal shift run into a weekend shift and we don't separate them`,
					);
				}

				const eventResource: calendar_v3.Schema$Event = {
					summary: `${ghName} on ${scheduleName} support`,
					start: {
						timeZone: TIMEZONE,
						dateTime: isoDateWithoutTimezone(start),
					},
					end: {
						timeZone: TIMEZONE,
						dateTime: isoDateWithoutTimezone(end),
					},
					attendees: [{ email: handleToEmail[ghName] }],
				};

				await calendar.events.insert({
					auth: authClient,
					calendarId: devOps.calendarID,
					conferenceDataVersion: 1,
					sendUpdates: 'all',
					requestBody: eventResource,
				});
			}
		}

		start = new Date(start.getTime() + 7 * 24 * 60 * 60 * 1000);
		end = new Date(end.getTime() + 7 * 24 * 60 * 60 * 1000);
		await setTimeout(500);
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

const args = process.argv.slice(2);
if (args.length !== 2) {
	console.log(`Usage: node ${__filename} <start yyyy-mm-dd> <end yyyy-mm-dd>`);
	console.log(
		`If both start and end dates are in the past then we fetch historical info, if both are now/in the future then we fetch future shifts`,
	);
	process.exit(1);
}
const startDate = parseDate(args[0]);
const endDate = parseDate(args[1]);
const NOW = parseDate(Date());

if (endDate < startDate) {
	throw new Error('Start date must be earlier than end date');
}

if (startDate <= NOW && endDate <= NOW) {
	pastSchedule(startDate, endDate);
} else if (startDate >= NOW && endDate >= NOW) {
	futureWeekends(startDate, endDate);
} else {
	throw new Error(`Both dates need to be in the past/now, or in the future/now`);
}
