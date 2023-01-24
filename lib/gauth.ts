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
import * as fs from 'mz/fs';
import { google } from 'googleapis';

const SCOPES = [
	'https://www.googleapis.com/auth/spreadsheets',
	'https://www.googleapis.com/auth/calendar',
];

/**
 * Obtains a Google OAuth 2.0 access token for access to Sheets and Calendar.
 * @return {Promise<object>}     OAuth 2.0 access token
 */
export async function getJWTAuthClient() {
	let jwt: any;
	try {
		// Attempt to parse env var if already in JSON format
		jwt = JSON.parse(process.env.GAPI_SERVICE_ACCOUNT_JWT);
	} catch {
		// Fallback to treating string as file containing JWT token
		const content = await fs.readFile(
			process.env.GAPI_SERVICE_ACCOUNT_JWT,
			'utf8',
		);
		jwt = JSON.parse(content);
	}
	const auth = new google.auth.JWT({
		email: jwt.client_email,
		key: jwt.private_key,
		scopes: SCOPES,
	});
	await auth.authorize();
	return auth;
}
