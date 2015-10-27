'''
### What this script does
This script takes data from a Google spreadsheet, converts it to a JSON array
where each object has keys corresponding to the spreadsheet column names, then
then stores that JSON locally and/or automatically commits it to a GitHub repo.

There are four methods chained together to perform these task(s).

* fetch_from_spreadsheet(): uses Oauth2 credentials to authenticate with
    Google and copy data from a spreadsheet into a Python dict.
  
* transform_data(): passes each item in the Python dict through a filter,
    providing an opportunity to validate, transform, remove fields, etc.
  
* make_json(): converts the Python dict into a JSON array, and provides
    an opportunity to store a local copy of the JSON (useful for testing).
  
* commit_json(): authenticates with GitHub and commits a JSON file
    to the identified repository.

Running `update_schedule()` will execute these four methods in succession.
It can also be run from the command line: `python update_mozfest_schedule.py`

### Authentication
For authentication to work, you must generate Google and GitHub credentials.
These should be stored as environment variables, and *not* committed to the
repository.

* GitHub: Follow these instructions to create a person API token:
    https://github.com/blog/1509-personal-api-tokens
    
    You should generate the token from an account that has write access
    to the repository where you want to store the JSON. It should be stored
    in an environment variable called `GITHUB_TOKEN`.
    
* Google: Follow these instructions to create *a service account*:
    https://developers.google.com/console/help/new/?hl=en_US#credentials-access-security-and-identity
    
    Creating a service account will generate a special client email address
    and a new private key. The client email address should be stored in
    an environment variable called `GOOGLE_API_CLIENT_EMAIL`. The private key
    should be stored in an environment variable called `GOOGLE_API_PRIVATE_KEY`.

### Customization
You should change the values in `GITHUB_CONFIG` according to your project.

* REPO_OWNER: a string representing the GitHub username of the account
    that owns the repository you want to commit to.
    
* REPO_NAME: a string representing the name of the repository to commit to.

* TARGET_FILE: a string representing the name of the file you want to create
     or update in the GitHub repository. This can include path information,
     e.g. 'sessions.json', or '_data/sessions.json'

* TARGET_BRANCH': a string representing the branch of the repository you want
    to commit to, e.g. 'gh-pages'

You should also change these values according to your project.

* GOOGLE_SPREADSHEET_KEY: a string representing the unique ID of the Google
    spreadsheet storing your data. This can be stored as an environment
    variable called GOOGLE_SPREADSHEET_KEY for extra security, or can simply
    be stored as a string in this script.
    
* MAKE_LOCAL_JSON: should likely be set to `False` in production, but can
    be set to `True` for  testing. If set to `True`, the `make_json()` method
    will create a local file containing the JSON for you to inspect.

* COMMIT_JSON_TO_GITHUB: should be set to `True` in production. If set
    to `True`, the `commit_json()` method will create or update a JSON file
    in the GitHub repository you specify. Can be set to `False` for testing,
    which will authenticate with GitHub but not create or update any files.

### Usage notes
Data is pulled from the spreadsheet identified in `GOOGLE_SPREADSHEET_KEY`.
The script assumes that data is in the *first* worksheet in the spreadsheet:

    datasheet = spreadsheet.get_worksheet(0)
    
If data is *not* in the first worksheet, `spreadsheet.get_worksheet(0)`
should be changed to identify the worksheet by title:

    datasheet = spreadsheet.worksheet("SHEET NAME")

'''
import argparse, os, sys, traceback
import github3
import gspread
import io
import json
import os
import requests

from oauth2client.client import SignedJwtAssertionCredentials

GITHUB_CONFIG = {
    'TOKEN': os.environ['GITHUB_TOKEN'],
    'REPO_OWNER': 'mozilla',
    'REPO_NAME': 'mozfest-schedule-app',
    'TARGET_FILE': 'sessions.json',
    'TARGET_BRANCH': 'gh-pages',
}

GOOGLE_API_CONFIG = {
    'CLIENT_EMAIL': os.environ['GOOGLE_API_CLIENT_EMAIL'],
    'PRIVATE_KEY': os.environ['GOOGLE_API_PRIVATE_KEY'].decode('unicode_escape'),
    'SCOPE': ['https://spreadsheets.google.com/feeds']
}

# can be stored as an environment variable if worried
# about security or simply stored as string here 
GOOGLE_SPREADSHEET_KEY = os.environ['GOOGLE_SPREADSHEET_KEY'] or ''

FETCH_MULTIPLE_WORKSHEETS = True
WORKSHEETS_TO_SKIP = ['Template', '(backup) original imported data']

MAKE_LOCAL_JSON = False
COMMIT_JSON_TO_GITHUB = True


def authenticate_with_google():
    '''
    Connect to Google Spreadsheet with gspread library.
    '''
    credentials = SignedJwtAssertionCredentials(
        GOOGLE_API_CONFIG['CLIENT_EMAIL'], GOOGLE_API_CONFIG['PRIVATE_KEY'], GOOGLE_API_CONFIG['SCOPE']
    )
    google_api_conn = gspread.authorize(credentials)
    
    return google_api_conn
    
def open_google_spreadsheet():
    '''
    Authenticate and return spreadsheet by `GOOGLE_SPREADSHEET_KEY`.
    '''
    google_api_conn = authenticate_with_google()
    spreadsheet = google_api_conn.open_by_key(GOOGLE_SPREADSHEET_KEY)
    
    return spreadsheet

def fetch_from_worksheet():
    '''
    Return data from first worksheet in Google spreadsheet.
    '''
    spreadsheet = open_google_spreadsheet()
    worksheet = spreadsheet.get_worksheet(0)
    data = worksheet.get_all_records(empty2zero=False)

    return data
    
def fetch_from_all_worksheets(worksheets_to_skip=[]):
    '''
    Return data from all worksheets in Google spreadsheet, optionally
    skipping sheets identified by title in `WORKSHEETS_TO_SKIP`.
    '''
    spreadsheet = open_google_spreadsheet()
    data = []
    worksheet_list = [
        sheet for sheet in spreadsheet.worksheets() if sheet.title not in WORKSHEETS_TO_SKIP
    ]

    for worksheet in worksheet_list:
        worksheet.title
        data.extend(worksheet.get_all_records(empty2zero=False))

    return data

def transform_data(data):
    '''
    Transforms data and filters individual schedule items for fields we want
    to publish. Currently, this:
    
    * ensures that all variables going into the JSON are strings
    * removes `proposalSpreadsheetRowNumber` to make JSON smaller
    * transforms column name `name` into JSON key `title`
    * transforms column name `githubIssueNumber` into JSON key `id`
    * removes any rows that don't have a numeric `id`
    '''
    def _transform_response_item(item, skip=False):
        # make sure vars are strings
        _transformed_item = {k: unicode(v) for k, v in item.iteritems() if k}
        
        # don't need `proposalSpreadsheetRowNumber` for schedule app
        if 'proposalSpreadsheetRowNumber' in _transformed_item:
            del _transformed_item['proposalSpreadsheetRowNumber']
        
        # transform `name` column name into `title` key
        # and skip rows that represent pathways, or have no name
        if 'name' in _transformed_item:
            _transformed_item['title'] = _transformed_item.pop('name', '')
            if not _transformed_item['title']:
                skip = True
            if _transformed_item['title'].lower().startswith('[path'):
                print _transformed_item['title']
                skip = True
        
        # transform `githubIssueNumber` column name into `id` key
        # (and skip rows without a valid id)
        if 'githubIssueNumber' in _transformed_item:
            _transformed_item['id'] = _transformed_item.pop('githubIssueNumber', '')

            # remove rows with `id` that is blank or provides instructions
            try:
                int(_transformed_item['id'])
            except:
                skip = True

        if skip:
            _transformed_item = None
            
        return _transformed_item
    
    transformed_data = filter(None, [_transform_response_item(item) for item in data])

    return transformed_data

def make_json(data, store_locally=False, filename=GITHUB_CONFIG['TARGET_FILE']):
    '''
    Turns data into nice JSON, and optionally stores to a local file.
    '''
    json_out = json.dumps(data, sort_keys=True, indent=4, ensure_ascii=False)
    
    if store_locally:
        with io.open(filename, 'w', encoding='utf8') as outfile:
            outfile.write(unicode(json_out))

    return json_out.encode('utf-8')

def commit_json(data, target_config=GITHUB_CONFIG, commit=COMMIT_JSON_TO_GITHUB):
    '''
    Uses token to log into GitHub as `ryanpitts`, then gets the appropriate
    repo based on owner/name defined in GITHUB_CONFIG.
    
    Creates sessions data file if it does not exist in the repo, otherwise
    updates existing data file.
    
    If `COMMIT_JSON_TO_GITHUB` is False, this will operate in "dry run" mode,
    authenticating against GitHub but not changing any files.
    '''
    
    # authenticate with GitHub
    gh = github3.login(token=target_config['TOKEN'])
    
    # get the right repo
    repo = gh.repository(target_config['REPO_OWNER'], target_config['REPO_NAME'])
    
    # check to see whether data file exists
    contents = repo.file_contents(
        path=target_config['TARGET_FILE'],
        ref=target_config['TARGET_BRANCH']
    )

    if commit:
        if not contents:
            # create file that doesn't exist
            repo.create_file(
                path=target_config['TARGET_FILE'],
                message='adding session data',
                content=data,
                branch=target_config['TARGET_BRANCH']
            )
        else:
            # update existing file
            contents.update(
                message='updating session data',
                content=data,
                branch=GITHUB_CONFIG['TARGET_BRANCH']
        )

def update_schedule():
    if FETCH_MULTIPLE_WORKSHEETS:
        data = fetch_from_all_worksheets(worksheets_to_skip=WORKSHEETS_TO_SKIP)
    else:
        data = fetch_from_worksheet()
    #print 'Fetched the data ...'

    data = transform_data(data)
    #print 'Prepped the data ...'

    session_json = make_json(data, store_locally=MAKE_LOCAL_JSON)
    #print 'Made the local json!'

    commit_json(session_json)
    #print 'SENT THE DATA TO GITHUB!'


if __name__ == "__main__":
    try:
        update_schedule()
    except Exception, e:
        sys.stderr.write('\n')
        traceback.print_exc(file=sys.stderr)
        sys.stderr.write('\n')
        sys.exit(1)
