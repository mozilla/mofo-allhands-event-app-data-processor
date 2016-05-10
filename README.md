# Schedule App Data Processor

This script is designed as a data processor helper for [schedule app core](https://github.com/mozilla/schedule-app-core/).

It handles the following tasks

1. takes data from a Google spreadsheet [TODO: add link to Google spreadsheet template],
2. converts it to a JSON array where each object has keys corresponding to the 
  spreadsheet column names,
3. then stores that JSON locally and/or automatically commits it to a GitHub 
  repo (your schedule app repo, e.g., [MoFo All-hands schedule app](https://github.com/m ozilla/mofo- allhands)).

## To run the script

1. Create a Python virtual environment and install all the required packages. See 
[create a Python virtual environment docs](https://github.com/mozilla/schedule-app-data-processor/blob/master/docs/REQUIREMENTS.md#create-a-python-virtual-environment) for instructions.
2. Get API creds from GitHub and Google. See [authentication docs](https://github.com/mozilla/schedule-app-data-processor/blob/master/docs/REQUIREMENTS.md#authentication) for instructions.
3. Set values for [environment variables](https://github.com/mozilla/schedule-app-data-processor/blob/master/docs/REQUIREMENTS.md#environment-variables) and run `source your-file-name.env`
4. Running `update_schedule()` will execute [these methods](https://github.com/mozilla/schedule-app-data-processor/blob/master/docs/REQUIREMENTS.md#primary-methods-of-the-script) in succession. You can trigger it from the command line: **`python update_schedule.py`**
