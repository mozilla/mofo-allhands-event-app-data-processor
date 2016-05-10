# Requirements

## Create a Python virtual environment

To install the requirements for this script, create a Python virtual environment 
using `virtualenv` and `virtualenvwrapper` (see [this guide](http://www.silverwareconsulting.com/index.cfm/2012/7/24/Getting-Started-with-virtualenv-and-virtualenvwrapper-in-Python) 
if you're unfamiliar). Then `pip install -r requirements.txt`.

## Authentication

For authentication to work, you must generate Google and GitHub credentials.
These should be stored as environment variables, and **NOT** committed to the
repository along with this.

#### GitHub

Follow these instructions to create a person API token: https://github.com/blog/1509-personal-api-tokens
    
You should generate the token from an account that has write access to the 
repository where you want to store the JSON. It should be stored in an environment 
variable called `GITHUB_TOKEN`.
    
#### Google 

Follow these instructions to create *a service account*: https://developers.google.com/console/help/new/?hl=en_US#credentials-access-security-and-identity
    
Creating a service account will generate a special client email address and
a new private key. The client email address should be stored in an environment 
variable called [`GOOGLE_API_CLIENT_EMAIL`](https://github.com/mozilla/schedule-app-data-processor/blob/master/docs/REQUIREMENTS.md#environment-variables). The private key should be stored in an environment variable called [`GOOGLE_API_PRIVATE_KEY`](https://github.com/mozilla/schedule-app-data-processor/blob/master/docs/REQUIREMENTS.md#environment-variables).

## Project settings

### Environment variables

These are the values that should NOT be committed to the repo. You can start by 
copying [sample.env](https://github.com/mozilla/schedule-app-data-processor/blob/master/sample.env): `cp sample.env .env` and updating the values in the `.env` file.
    
| variable name | description |
|-----|-----|
| **`REPO_OWNER`**                | A string representing the GitHub username of the account that,owns the repository you want to commit to |
| **`REPO_NAME`**                 | A string representing the name of the repository to commit to |
| **`TARGET_DIR`**                | Name of the directory you are committing `sessions.json` file to. Leave blank or omit this variable if `sessions.json` is going to live on root directory. |
| **`TARGET_BRANCHES`**           | a list(in comma-separated format) representing the branch(es) of the repository you want to commit to, e.g. `'gh-pages'` or `'gh-pages, master'`. Default value is `gh-pages` if this `TARGET_BRANCHES` is not set. |
| **`GITHUB_TOKEN`**              | Your GitHub token. See [authentication docs](https://github.com/mozilla/schedule-app-data-processor/blob/master/docs/REQUIREMENTS.md#authentication) on how to acquire a GitHub token. |
| **`GOOGLE_API_CLIENT_EMAIL`**   | Your Google API client email. See [authentication docs](https://github.com/mozilla/schedule-app-data-processor/blob/master/docs/REQUIREMENTS.md#authentication) on how to create a Google service account. |
| **`GOOGLE_API_PRIVATE_KEY`**    | Your Google API private key. See [authentication docs](https://github.com/mozilla/schedule-app-data-processor/blob/master/docs/REQUIREMENTS.md#authentication) on how to create a Google service account. |
| **`GOOGLE_SPREADSHEET_KEY`**    | A string representing the unique ID of the Google spreadsheet storing your data. |
| **`WORKSHEETS_TO_FETCH`**       | if `FETCH_MULTIPLE_WORKSHEETS` is set to `True`, you may define a list of worksheet names(in comma-separated format) to fetch data from. e.g. `'sheet1, sheet2, sheet3'` |
| **`FETCH_MULTIPLE_WORKSHEETS`** | set to `True` if `GOOGLE_SPREADSHEET_KEY` points to a document with data in multiple worksheets. The import will retrieve data from all worksheets and compile into a single JSON file. _NOTE:_ The import will not perform any validation or normalization on column names, so if worksheets have varying column names, the resulting JSON objects will have varied key names as well. |
| **`MAKE_LOCAL_JSON`**           | should likely be set to `False` in production, but can be set to `True` for testing. If set to `True`, the `make_json()` method will create a local file containing the JSON for you to inspect. |
| **`COMMIT_JSON_TO_GITHUB`**     | should be set to `True` in production. If set to `True`, the `commit_json()` method will create or update a JSON file in the GitHub repository you specify. Can be set to `False` for testing, which will authenticate with GitHub but not create or update any files. |
| **`PROMPT_BEFORE_COMMIT_TO_GITHUB`** | Set to `True` if you want to get a confirmation prompt before the script commits JSON file to GitHub. This is useful on development mode (script triggered from the command line) to avoid accidental commits to GitHub. |


### Other settings

In `update_schedule.py`...

You should change the values according to your project.

* **TARGET_FILE:** a string representing the name of the file you want to
  create or update in the GitHub repository. By default, it is set to `sessions.json`


## Other notes about the script

### Primary methods of the script

There are 5 primary methods chained together to perform these task(s).

- **`fetch_data()`** uses Oauth2 credentials to authenticate with Google and copy 
data from a spreadsheet into a Python dict.
  
- **`transform_timeblock_data()`** passes each item in the Python dict through a
filter, providing an opportunity to validate, transform, remove fields, etc.

- **`transform_session_data()`** passes each item in the Python dict through a
as filter, providing an opportunity to validate, transform, remove fields, etc.
  
- **`make_json()`** converts the Python dict into a JSON array, and provides an
opportunity to store a local copy of the JSON (useful for testing).
  
- **`commit_json()`** authenticates with GitHub and commits a JSON file to the
identified repository if data has changed since last update.
