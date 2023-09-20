#!/usr/bin/python

"""
f5-cp-sync-check.py
Version 1.0 Sept. 19, 2023
https://github.com/wd-tim-haynie/bt-netengops-f5-cp-sync-healthcheck
Author: Tim Haynie, CWNE #254, ACMX #508 https://www.linkedin.com/in/timhaynie/
"""

from re import match
from json import loads, load, dump, dumps
from datetime import datetime, timedelta
from ssl import _create_unverified_context
from logging import getLogger, Formatter, FileHandler, INFO
from os import getenv, path
from sys import exit
from socket import timeout
from time import time
#from glob import glob

# compatibility with python2 and python3
try:
    from urllib2 import Request, urlopen, HTTPError, URLError
    # This will encode data to bytes in Python 2. However, in Python 2, the str type is already bytes.
    encode_to_bytes = lambda s: s
except ModuleNotFoundError:
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError
    # In Python 3, you need to explicitly encode the str to bytes.
    encode_to_bytes = lambda s: s.encode('utf-8')


# retrieve environment variables
NODE_IP = getenv('NODE_IP')
MON_TMPL_NAME = getenv("MON_TMPL_NAME")
CLIENT_SECRET = getenv("CLIENT_SECRET")
CLIENT_ID = getenv("CLIENT_ID")
BUFFER_TIME = getenv("BUFFER_TIME") # 10 minutes (600 seconds) by default for token refresh
MON_INTERVAL = getenv("MON_INTERVAL") # 5 seconds by default for monitor interval


# define additional global constants
MON_NAME = MON_TMPL_NAME.split('/')[-1] # removes the path from the monitor name
INSECURE = _create_unverified_context()  # For insecure SSL requests
BEARER_TOKEN_FILE = "/var/tmp/{}-token.json".format(MON_NAME)


# convert ipv6 to ipv4 if necessary
if '.' in NODE_IP:
    NODE_IP = NODE_IP[7:]


# setup logging
def setup_logger():
    logger = getLogger('{}'.format(MON_TMPL_NAME))
    logger.setLevel(INFO)

    handler = FileHandler('/var/log/ltm')
    handler.setLevel(INFO)

    formatter = Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt='%b %d %H:%M:%S')
    handler.setFormatter(formatter)

    logger.addHandler(handler)

    return logger


LOGGER = setup_logger()
LOGGER.debug("{} monitor script start".format(NODE_IP))


if BUFFER_TIME is None:
    BUFFER_TIME = 600 # 10 minutes (600 seconds) by default if not specified
    LOGGER.debug("BUFFER_TIME set to 600 seconds")
else:
    try:
        BUFFER_TIME = int(BUFFER_TIME)
        LOGGER.debug("BUFFER_TIME set to {} seconds".format(BUFFER_TIME))

    except ValueError:
        BUFFER_TIME = 600
        LOGGER.warning("Invalid BUFFER_TIME provided, defaulting to 600 seconds")


if MON_INTERVAL is None:
    MON_INTERVAL = 5 # 5 seconds for monitor interval, F5 default
    LOGGER.debug("MON_INTERVAL set to 5 seconds")
else:
    try:
        MON_INTERVAL = int(MON_INTERVAL)
        LOGGER.debug("MON_INTERVAL set to {} seconds".format(MON_INTERVAL))
    except ValueError:
        MON_INTERVAL = 5
        LOGGER.warning("Invalid MON_INTERVAL, defaulting to 5 seconds")


def main():
    token = get_token()

    req = Request("https://{}/api/cluster/server".format(NODE_IP))
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/json")
    req.add_header("Connection", "close")

    try:
        response = urlopen(req, context=INSECURE, timeout=MON_INTERVAL - 1)

        content = response.read()
        response.close()
        servers = loads(content)["_embedded"]["items"]

        # iterate through the list of servers. find the highest replication timestamp and the server's replication timestamp
        max_epoch = 0
        test_epoch = 0
        for server in servers:
            if server['last_replication_timestamp'] is not None:
                this_epoch = datestring_to_epoch(server['last_replication_timestamp'])

                if this_epoch > max_epoch:
                    max_epoch = this_epoch

            if server['server_ip'] == NODE_IP or server['management_ip'] == NODE_IP:
                if server['is_master']:
                    print("{} UP as publisher".format(NODE_IP))
                    exit() # no need to go any further for the publisher
                else:
                    test_epoch = this_epoch

        """
        ClearPass updates last_replication_timestamp value every 180 seconds (3 minutes).
        We will fail the check if the time variance is more than 185 + MON_INTERVAL seconds since the monitor runs every
        MON_INTERVAL seconds and we need to allow a few seconds of clock variance.
        NTP is required on both ClearPass and F5.
        """
        if max_epoch < int(time()) - MON_INTERVAL - 185:
            LOGGER.info("{} last replication timestamp too old. Marking down. F5 epoch: {}, CPPM epoch: {}, delta: "
                        "{}".format(NODE_IP, int(time()), max_epoch, int(time()) - max_epoch))
        else: # time is in range
            if test_epoch < max_epoch - 10:  # test failed, node timestamp more than 10 seconds behind
                LOGGER.info("{} failed sync check. Marking down. max_epoch: {}, test_epoch: {}, delta: {}"
                            .format(NODE_IP, max_epoch, test_epoch, max_epoch - test_epoch))
            else:  # test succeeded
                print("{} UP".format(NODE_IP))

    except HTTPError as e:
        LOGGER.error("{}:  HTTP Error: {} retrieving server timestamp".format(NODE_IP, e.code))

    except URLError as e:
        LOGGER.error("{}:  URL Error: {} retrieving server timestamp".format(NODE_IP, e.reason))

    except timeout:
        LOGGER.error("{}:  Request timed out fetching server timestamp".format(NODE_IP))

    except KeyError:
        LOGGER.error("{}: Unexpected response structure from ClearPass fetching server timestamp".format(NODE_IP))

    except Exception as e:
        LOGGER.error("Unhandled Error fetching server timestamp: {}".format(str(e)))


def datestring_to_epoch(date_string):
    # YYYY-MM-DD HH:MM:SS[-/+]timezone offset from UTC
    # groups:   (  YY - MM  - DD  ) ( HH  : MM  : SS  )( tzoffset)
    m = match(r'(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})([-+]\d{2})', date_string)

    if not m:
        LOGGER.info('{}: Invalid date format.'.format(NODE_IP))
        raise ValueError("Invalid date format")
        exit()

    date_part, time_part, tz_offset = m.groups()
    naive_dt = datetime.strptime('{} {}'.format(date_part, time_part), '%Y-%m-%d %H:%M:%S')

    hours_offset = int(tz_offset)
    adjusted_dt = naive_dt - timedelta(hours=hours_offset)
    epoch = (adjusted_dt - datetime(1970, 1, 1)).total_seconds()
    return int(epoch)


def get_secret():
    """
    Future version will handle encrypted secrets
    """
    return CLIENT_SECRET
  

# def get_decryption_key_file_path(base_name):
#     # The directory path and the known prefix
#     directory_path = "/config/filestore/files_d/Common_d/ifile_d/"
#     prefix = ":Common:"
#     search_pattern = "{}{}{}_*".format(directory_path, prefix, base_name)
#
#     # List all matching files
#     matching_files = glob(search_pattern)
#
#     # Sort the matching files to get the latest (if necessary)
#     matching_files.sort()
#
#     # Return the first match or None if no matches found
#     return matching_files[0] if matching_files else None


def request_to_get_token():
    url = "https://{}/api/oauth".format(NODE_IP)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Connection": "close"
    }

    # Prepare the request data/body
    data = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": get_secret()
    }

    # Convert the Python dictionary to a JSON string
    data_json = dumps(data)
    data_bytes = encode_to_bytes(data_json)

    # Make the request
    request = Request(url, data=data_bytes, headers=headers)

    try:
        response = urlopen(request, context=INSECURE, timeout=MON_INTERVAL - 1)
        response_data = response.read()
        response.close()
        token_data = loads(response_data)
        return token_data
    except HTTPError as e:
        LOGGER.error("{}: HTTP Error retrieving token: {} {}".format(NODE_IP, e.code, e.reason))
        exit()
    except URLError as e:
        LOGGER.error("{}: URL Error retrieving token: {}".format(NODE_IP, e.reason))
        exit()
    except timeout:
        LOGGER.error("{}:  Request timed out getting new token".format(NODE_IP))
        exit()
    except Exception as e:
        LOGGER.error("{}: Unhandled Error retrieving token: {}".format(NODE_IP, str(e)))
        exit()


def get_stored_tokens():
    """
    Retrieves stored tokens from the file. Returns an empty list if the file doesn't exist.
    """
    if path.exists(BEARER_TOKEN_FILE):
        with open(BEARER_TOKEN_FILE, 'r') as f:
            tokens = load(f)
            return tokens

    return []


def store_tokens(tokens):
    """
    Stores a list of tokens to the file.
    """
    with open(BEARER_TOKEN_FILE, 'w') as f:
        dump(tokens, f)

    LOGGER.debug("stored tokens")


def remove_expired_tokens(tokens):
    """
    Removes tokens that have already expired from the given list.
    Returns the list after removal.
    """
    tokens = [token_data for token_data in tokens if token_data['expiry_time'] > time()]
    LOGGER.debug("Filtered expired tokens")
    return tokens


def get_oldest_token(tokens):
    """
    Returns the oldest unexpired token with at least 5 seconds until expiry from a list of tokens
    If no such token exists, returns None.
    """

    LOGGER.debug("Searching for oldest valid token")
    for token_data in tokens:
        if token_data['expiry_time'] - time() > 5:
            return token_data['token']

    return None


def append_new_token(tokens):
    """
    Appends a new token to the list of tokens and stores it.
    """
    response = request_to_get_token()
    token = response['access_token']
    expiry = response['expires_in'] + int(time())  # Convert to epoch time
    tokens.append({'token': token, 'expiry_time': expiry})
    if expiry - int(time()) > BUFFER_TIME:
        LOGGER.debug("New token expires after buffer time")
    else:
        LOGGER.warning("New token expires before buffer time: {}".format(expiry)) # should be a warning

    store_tokens(tokens)


def get_token():
    tokens = get_stored_tokens()

    # Remove expired tokens first
    tokens = remove_expired_tokens(tokens)

    # Fetch the latest valid token
    token = get_oldest_token(tokens)

    # If there is no token or the latest token's expiration time is within the buffer time, append a new token
    if not token or tokens[-1]['expiry_time'] - time() <= BUFFER_TIME:
        append_new_token(tokens)
        token = get_oldest_token(tokens)  # Fetch the token again

    return token


main()
LOGGER.debug("{} monitor script execution complete".format(NODE_IP))
