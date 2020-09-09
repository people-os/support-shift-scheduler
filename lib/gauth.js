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
const Promise = require('bluebird');
const fs = require('mz/fs');
const { google } = require('googleapis');

const SCOPES = [
	'https://www.googleapis.com/auth/spreadsheets',
	'https://www.googleapis.com/auth/calendar',
];

const TOKEN_PATH = process.env.TOKEN;
const CRED = process.env.CREDENTIALS;
/**
 * Obtains a Google OAuth 2.0 access token for access to Sheets and Calendar.
 * @return {object}     OAuth 2.0 access token
 */
async function getAuthClient(authType) {
	if (authType === 'JWT') {
		return getJWTAuthClient();
	} else {
		return getOAuth2Client();
	}
}

async function getJWTAuthClient() {
	const content = await fs.readFile(process.env.GAPI_SERVICE_ACCOUNT_JWT);
	const jwt = JSON.parse(content);
	let auth = new google.auth.JWT({
		email: jwt.client_email,
		key: jwt.private_key,
		scopes: SCOPES,
	});
	await auth.authorizeAsync();
	return auth;
}

async function getOAuth2Client() {
	const content = fs.readFileSync(CRED, 'utf8');
	const oAuth = JSON.parse(content);
	const { client_secret, client_id, redirect_uris } = oAuth.installed;
	const oAuth2Client = new google.auth.OAuth2(
		client_id,
		client_secret,
		redirect_uris[0]
	);

	const token = fs.readFileSync(TOKEN_PATH, 'utf-8');

	oAuth2Client.setCredentials(JSON.parse(token));

	return oAuth2Client;
}

exports.getAuthClient = getAuthClient;
