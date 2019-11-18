require('dotenv').config()
const Promise = require('bluebird')
const readFileAsync = Promise.promisify(require('fs').readFile)
const { google } = require('googleapis')


const SCOPES = [
  'https://www.googleapis.com/auth/spreadsheets',
  'https://www.googleapis.com/auth/calendar'
]

/**
 * Obtains a Google OAuth 2.0 access token for access to Sheets and Calendar.
 * @return {object}     OAuth 2.0 access token
 */
async function getAuthClient() {
  const content = await readFileAsync(process.env.GAPI_SERVICE_ACCOUNT_JWT).catch((e) => console.log(e))

  let jwt = JSON.parse(content)

  let auth = new google.auth.JWT({
    email: jwt.client_email,
    key: jwt.private_key,
    scopes: SCOPES
  })
  await auth.authorizeAsync()
  return auth
}

exports.getAuthClient = getAuthClient
