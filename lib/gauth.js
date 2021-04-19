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
const fs = require('mz/fs');
const { google } = require('googleapis');
const readlineSync = require('readline-sync');

const SCOPES = [
	'https://www.googleapis.com/auth/spreadsheets',
	'https://www.googleapis.com/auth/calendar',
];

const TOKEN_PATH = process.env.TOKEN;
const CRED = process.env.CREDENTIALS;
/**
 * Obtains a Google OAuth 2.0 access token for access to Sheets and Calendar.
 * @return {Promise<object>}     OAuth 2.0 access token
 */
async function getAuthClient(support) {
	if (support.useServiceAccount) {
		return getJWTAuthClient();
	} else {
		return getOAuth2Client();
	}
}

async function getJWTAuthClient() {
	const content = await fs.readFile(
		process.env.GAPI_SERVICE_ACCOUNT_JWT,
		'utf8',
	);
	const jwt = JSON.parse(content);
	let auth = new google.auth.JWT({
		email: jwt.client_email,
		key: jwt.private_key,
		scopes: SCOPES,
	});
	await auth.authorize();
	return auth;
}

async function getOAuth2Client() {
	const content = fs.readFileSync(CRED, 'utf8');
	const oAuth = JSON.parse(content);
	const { client_secret, client_id, redirect_uris } = oAuth.installed;
	const oAuth2Client = new google.auth.OAuth2(
		client_id,
		client_secret,
		redirect_uris[0],
	);

	let token;
	if (!fs.existsSync(TOKEN_PATH)) {
		token = await getAccessToken(oAuth2Client);
	} else {
		token = fs.readFileSync(TOKEN_PATH, 'utf-8');
	}
	oAuth2Client.setCredentials(JSON.parse(token));

	return oAuth2Client;
}

async function getAccessToken(oAuth2Client) {
	const authUrl = oAuth2Client.generateAuthUrl({
		access_type: 'offline',
		scope: SCOPES,
	});
	console.log('Authorize this app by visiting this url:', authUrl);

	const code = readlineSync.question('Enter the code from that page here: ');
	const result = await oAuth2Client.getToken(code);
	const token = JSON.stringify(result.tokens);
	fs.writeFileSync(TOKEN_PATH, token);
	return token;
}

exports.getAuthClient = getAuthClient;
