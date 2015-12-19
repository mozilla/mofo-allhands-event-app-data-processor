import argparse, os, sys, traceback
import github3
import gspread
import io
import json
import logging
import os
import requests
from datetime import datetime
from logging.config import dictConfig
from oauth2client.client import SignedJwtAssertionCredentials

GITHUB_CONFIG = {
    'TOKEN': os.environ['GITHUB_TOKEN'],
    'REPO_OWNER': 'mozilla',
    'REPO_NAME': 'mozfest-schedule-app',
    'TARGET_FILE': 'sessions.json',
    'TARGET_BRANCHES': ['gh-pages',],
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

def fetch_data(multiple_sheets=False, worksheets_to_skip=[]):
    spreadsheet = open_google_spreadsheet()

    if not multiple_sheets:
        # Return data from first worksheet in Google spreadsheet.
        worksheet = spreadsheet.get_worksheet(0)
        data = worksheet.get_all_records(empty2zero=False)

    else:
        # Return data from all worksheets in Google spreadsheet, optionally
        # skipping sheets identified by title in `WORKSHEETS_TO_SKIP`.
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
    * creates a concatenated `facilitators` key
    * removes invalid pathway labels that were used for GitHub workflow
    * creates a `scheduleblock` key based on data in `time` column
    * creates Saturday and Sunday versions of sessions marked 'all-weekend'
    * infers a `day` and `start` key based on data in `time` column
    * prepends `location` with the word 'Floor' 
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
        
        # create concatenated `facilitators` key for schedule list display
        # and `facilitator_array` key for session detail display
        name_list = []
        name_detail_list = []
        for key in _transformed_item.keys():
            if key.startswith('facilitator_'):
                name_list.append(_transformed_item[key].split(",")[0])
                name_detail_list.append(_transformed_item.pop(key))
        _transformed_item['facilitators'] = ', '.join(filter(None, name_list))
        _transformed_item['facilitator_array'] = filter(None, name_detail_list)
        
        # remove invalid pathway labels that were used for GitHub workflow
        pathway_skip_keywords = ['accepted','consideration','stipend','sample']
        pathway_list = _transformed_item['pathways'].split(',')
        pathway_list = [
            name for name in pathway_list if not set(pathway_skip_keywords).intersection(set(name.lower().split()))
        ]
        _transformed_item['pathways'] = ','.join(pathway_list)

        # create `scheduleblock` key based on `time`
        time_data = _transformed_item.pop('time', '').split('(')
        # "slugified" version of scheduleblock
        scheduleblock = time_data[0].strip()
        scheduleblock = scheduleblock.lower().replace(' ','-')
        _transformed_item['scheduleblock'] = scheduleblock

        # infer session day
        if 'saturday' in _transformed_item['scheduleblock']:
            _transformed_item['day'] = 'Saturday'
        if 'sunday' in _transformed_item['scheduleblock']:
            _transformed_item['day'] = 'Sunday'
        if 'all-s' in _transformed_item['scheduleblock']:
            _transformed_item['start'] = 'All Day'
        # infer start time
        if len(time_data) > 1:
            start_time = time_data[1].strip('()').split(' ')[0]
            try:
                # attempt to coerce to 12-hour format
                d = datetime.strptime(start_time, "%H:%M")
                start_time = d.strftime("%I:%M %p")
            except:
                pass
            _transformed_item['start'] = start_time
        # create Saturday and Sunday versions of sessions marked 'all-weekend'
        if 'weekend' in _transformed_item['scheduleblock']:
            _transformed_item['start'] = 'All Weekend'
            if 'clone_flag' in item:
                _transformed_item['scheduleblock'] = 'all-sunday'
                _transformed_item['day'] = 'Sunday'
                _transformed_item['start'] = 'All Day'
            else:
                _transformed_item['scheduleblock'] = 'all-saturday'
                _transformed_item['day'] = 'Saturday'
                _transformed_item['start'] = 'All Day'
                # create a cloned version for Sunday
                cloned_item = item.copy()
                cloned_item['clone_flag'] = True
                cloned_data.append(cloned_item)

        # prepend `location` with the word 'Floor'
        if _transformed_item['location'] and not _transformed_item['location'].startswith('Floor'):
            _transformed_item['location'] = 'Floor {0}'.format(_transformed_item['location'])
                
        # if we've triggered the skip flag anywhere, drop this record
        if skip:
            _transformed_item = None
            
        return _transformed_item
    
    # empty list to hold any items we need to duplicate
    cloned_data = []
    # pass initial data through the transformer
    transformed_data = filter(None, [_transform_response_item(item) for item in data])
    # and add in any items we had to duplicate
    transformed_data.extend(
        filter(None, [_transform_response_item(item) for item in cloned_data])
    )

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
    
    for branch in target_config['TARGET_BRANCHES']:
        # check to see whether data file exists
        contents = repo.contents(
            path=target_config['TARGET_FILE'],
            ref=branch
        )

        if commit:
            if not contents:
                # create file that doesn't exist
                repo.create_file(
                    path=target_config['TARGET_FILE'],
                    message='adding session data',
                    content=data,
                    branch=branch
                )
                logger.info('Created new data file in repo')
            else:
                # if data has changed, update existing file
                if data.decode('utf-8') == contents.decoded.decode('utf-8'):
                    logger.info('Data has not changed, no commit created')
                else:
                    repo.update_file(
                        path=target_config['TARGET_FILE'],
                        message='updating schedule data',
                        content=data,
                        sha=contents.sha,
                        branch=branch
                    )
                    logger.info('Data updated, new commit to repo')
                

def update_schedule():
    data = fetch_data(multiple_sheets=FETCH_MULTIPLE_WORKSHEETS, worksheets_to_skip=WORKSHEETS_TO_SKIP)
    #print 'Fetched the data ...'

    data = transform_data(data)
    #print 'Prepped the data ...'

    session_json = make_json(data, store_locally=MAKE_LOCAL_JSON)
    #print 'Made the local json!'

    commit_json(session_json)
    #print 'SENT THE DATA TO GITHUB!'


'''
Set up logging.
'''
LOGGING = {
    'version': 1,
    'disable_existing_loggers': True,
    'formatters': {
        'verbose': {
            'format': '%(levelname)s %(asctime)s %(message)s'
        },
        'simple': {
            'format': '%(levelname)s %(message)s'
        },
    },
    'handlers': {
        'file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': 'log.txt',
            'formatter': 'verbose'
        },
        'console':{
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple'
        },
    },
    'loggers': {
        'schedule_loader': {
            'handlers':['file','console'],
            'propagate': False,
            'level':'DEBUG',
        }
    }
}
dictConfig(LOGGING)
logger = logging.getLogger('schedule_loader')


if __name__ == "__main__":
    try:
        update_schedule()
    except Exception, e:
        sys.stderr.write('\n')
        traceback.print_exc(file=sys.stderr)
        sys.stderr.write('\n')
        sys.exit(1)
