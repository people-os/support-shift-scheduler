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
import { mkdirp } from 'mkdirp';
import { promises as fs } from 'fs';

import { getJWTAuthClient } from '../lib/gauth';
import { getOnboardingInput } from '../lib/gsheets';

/**
 * Read and configure input data from Google Sheets, and save as JSON object
 */
async function getData(startDate: string, supportName: string) {
	try {
		const supportStr = await fs.readFile(
			'helper-scripts/options/' + supportName + '.json',
			'utf8',
		);
		const support = JSON.parse(supportStr);
		const auth = await getJWTAuthClient();
		const onboardingInput = await getOnboardingInput(auth, startDate, support);

		const fileDir = `./logs/${startDate}_` + supportName;
		await mkdirp(fileDir);
		if (
			onboardingInput.mentors.length > 0 &&
			onboardingInput.onboarders.length > 0
		) {
			await fs.writeFile(
				fileDir + '/mentors.txt',
				onboardingInput.mentors.map((a) => `@${a}`).join('\n'),
			);
			await fs.writeFile(
				fileDir + '/onboarding_agents.txt',
				onboardingInput.onboarders.map((a) => `@${a}`).join('\n'),
			);
		}
	} catch (e) {
		console.error(e);
		process.exit(1);
	}
}

// Read starting date and support type from command line arguments.
const args = process.argv.slice(2);
if (args.length !== 2) {
	console.log(
		`Please specify the starting date (Monday) in YYYY-MM-DD format, as well as the support type.`,
	);
	process.exit(2);
}

// Load JSON object from output file:
const nextMondayDate = args[0];
const supportModel = args[1];

void getData(nextMondayDate, supportModel);
