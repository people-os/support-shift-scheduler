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
import { agents } from './logs/2021-05-03_devOps/support-shift-scheduler-input.json';
import { setTimeout } from 'timers/promises';

const handleToEmail = _(agents)
	.keyBy((a) => a.handle.replace(/^@/, ''))
	.mapValues((a) => a.email)
	.value();

// console.error('===================================================')
// console.error('handleToEmail', require('util').inspect(handleToEmail, { depth: null, maxArrayLength: Infinity }))
// console.error('===================================================')
// process.exit()

const vOpsToGh = _.invert(devOps.victoropsUsernames);

const TIMEZONE = 'Europe/London';
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

// pastSchedule()
futureWeekends();

async function futureWeekends() {
	const authClient = await getAuthClient(devOps);

	const x = (await v.oncall.getTeamSchedule(devopsTeam, {
		daysForward: 123, // 123 max
		daysSkip: 7,
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

						console.error(
							'===================================================',
						);
						console.error(
							'eventResource',
							require('util').inspect(eventResource, {
								depth: null,
								maxArrayLength: Infinity,
							}),
						);
						console.error(
							'===================================================',
						);

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

async function pastSchedule() {
	const authClient = await getAuthClient(devOps);

	let start = new Date(2022, 0, 15, 6);
	let end = new Date(2022, 0, 17, 0);
	const until = end; //new Date(2022, 4, 1);

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
			//   {
			// 	userId: 'page',
			// 	adjustedTotal: { hours: 3, minutes: 34 },
			// 	total: { hours: 3, minutes: 34 },
			// 	log: [
			// 	  {
			// 		on: '2022-01-11T11:00:08Z',
			// 		off: '2022-01-11T14:34:45Z',
			// 		duration: { hours: 3, minutes: 34 },
			// 		escalationPolicy: { name: 'balena-production', slug: 'pol-1jkqGm7URSxtfrVA' }
			// 	  }
			// 	]
			//   }
		};
		// const x = await v.teams.getTeams();
		// console.error('===================================================');
		// console.error(
		// 	'x',
		// 	require('util').inspect(x, { depth: null, maxArrayLength: Infinity }),
		// );
		// console.error('===================================================');

		for (const userLog of x.userLogs) {
			const ghName = vOpsToGh[userLog.userId];
			if (!ghName) {
				console.log(`skipping unknown user '${userLog.userId}'`);
				continue;
			}
			for (const log of userLog.log) {
				const start = getRoundedDate(new Date(log.on));
				const end = getRoundedDate(new Date(log.off));

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

				console.error('===================================================');
				console.error(
					'log.duration',
					require('util').inspect(log.duration, {
						depth: null,
						maxArrayLength: Infinity,
					}),
				);
				console.error(
					'eventResource',
					require('util').inspect(eventResource, {
						depth: null,
						maxArrayLength: Infinity,
					}),
				);
				console.error('===================================================');

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
