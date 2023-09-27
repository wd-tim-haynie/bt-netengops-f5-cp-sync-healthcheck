#!/usr/bin/python

"""
f5-cp-sync-check.py
Version 2.0 Sept. 27, 2023
https://github.com/wd-tim-haynie/bt-netengops-f5-cp-sync-healthcheck
Author: Tim Haynie, CWNE #254, ACMX #508 https://www.linkedin.com/in/timhaynie/
"""


from json import loads, dumps
from ssl import _create_unverified_context, SSLError
from logging import getLogger, Formatter, FileHandler, INFO, DEBUG, WARNING, ERROR, CRITICAL
from os import getenv
from sys import exit
from socket import timeout
from time import time, sleep
from glob import glob
from subprocess import check_output, CalledProcessError

try:  # Python 2
    from urllib2 import Request, urlopen, HTTPError, URLError
    encode_to_bytes = lambda s: s  # returns the same value in Python 2
except ModuleNotFoundError:  # Python 3
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError
    encode_to_bytes = lambda s: s.encode('utf-8') # encode str to bytes in Python 3


# set global constants
INSECURE = _create_unverified_context()  # For insecure SSL requests
HEADERS = {"Content-Type": "application/json", "Accept": "application/json", "Connection": "close"}
LOG_LEVEL_DICT = {"DEBUG": DEBUG, "INFO": INFO, "WARNING": WARNING, "ERROR": ERROR, "CRITICAL": CRITICAL}

# retrieve environment variables
NODE_IP = getenv('NODE_IP')[7:] if '.' in getenv('NODE_IP') else getenv("NODE_IP") # converts to IPv4 if necessary
MON_TMPL_NAME = getenv("MON_TMPL_NAME")
NODE_NAME = getenv("NODE_NAME")
LOG_LEVEL = getenv("LOG_LEVEL", "CRITICAL").upper()
RUN_I = getenv("RUN_I")
CLIENT_SECRET = getenv("CLIENT_SECRET")
CLIENT_ID = getenv("CLIENT_ID")
MAX_SKEW = getenv("MAX_SKEW", 15.0)
DECRYPTION_KEYFILE = getenv("DECRYPTION_KEYFILE")
ENCRYPTED_SECRET = getenv("ENCRYPTED_SECRET")
TIMEOUT = getenv("TIMEOUT", 2.4)


def setup_logger():
    log_level = LOG_LEVEL_DICT.get(LOG_LEVEL, CRITICAL)  # default to CRITICAL logging if bad user input
    logger = getLogger('{}'.format(MON_TMPL_NAME))
    logger.setLevel(log_level)

    handler = FileHandler('/var/log/ltm')
    handler.setLevel(log_level)

    formatter = Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt='%b %d %H:%M:%S')
    handler.setFormatter(formatter)

    logger.addHandler(handler)

    return logger


LOGGER = setup_logger()
LOGGER.debug("{} {}: {} monitor script initialized, debug logging enabled".format(NODE_NAME, NODE_IP, RUN_I))


def main():
    token_req_start_time = time()
    HEADERS['Authorization'] = "Bearer " + request_to_get_token()

    # subtract the amount of time it took to get the token from the MAX_SKEW and sleep for that long
    sleep_time = float(MAX_SKEW) - (time() - token_req_start_time)

    LOGGER.debug("{} {}: Token obtained. Sleeping for {} seconds".format(NODE_NAME, NODE_IP, sleep_time))
    sleep(sleep_time)

    try:
        req = Request("https://{}/api/oauth/me".format(NODE_IP), headers=HEADERS)
        response = urlopen(req, context=INSECURE, timeout=TIMEOUT)
        content = response.read()
        response.close()

        if CLIENT_ID in loads(content)["name"]:
            LOGGER.debug("{} {}: Up".format(NODE_NAME, NODE_IP))
            print("{} {} Up".format(NODE_NAME, NODE_IP))

    except HTTPError as e:
        LOGGER.error("{} {}: HTTP Error using token: {}".format(NODE_NAME, NODE_IP, e.code))
    except URLError as e:
        LOGGER.error("{} {}: URL Error: {}".format(NODE_NAME, NODE_IP, e.reason))
    except timeout:
        LOGGER.error("{} {}: Request timed out".format(NODE_NAME, NODE_IP))
    except SSLError as e:
        LOGGER.error("{} {}: SSL Error occurred. Args: {}. Errno: {}. Strerror: {}. Full exception: {}".format(
            NODE_NAME, NODE_IP, e.args, getattr(e, 'errno', 'N/A'), getattr(e, 'strerror', 'N/A'), str(e)))
    except Exception as e:
        LOGGER.error("{} {}: Unhandled Error using token: {}. Exception type: {}"
                     .format(NODE_NAME, NODE_IP, str(e), type(e).__name__))


def request_to_get_token():
    url = "https://{}/api/oauth".format(NODE_IP)

    # Prepare the request data/body
    data = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": get_secret()
    }

    request = Request(url, data=encode_to_bytes(dumps(data)), headers=HEADERS)

    try:
        response = urlopen(request, context=INSECURE, timeout=TIMEOUT)
        response_data = response.read()
        return loads(response_data)['access_token']
    except HTTPError as e:
        LOGGER.error("{} {}: HTTP Error getting token: {} {}".format(NODE_NAME, NODE_IP, e.code, e.reason))
    except URLError as e:
        LOGGER.error("{} {}: URL Error getting token: {}".format(NODE_NAME, NODE_IP, e.reason))
    except timeout:
        LOGGER.error("{} {}: Request timed out getting new token".format(NODE_NAME, NODE_IP))
    except SSLError as e:
        LOGGER.error("{} {}: SSL Error occurred getting token. Args: {}. Errno: {}. Strerror: {}. Full exception: {}"
                     .format(NODE_NAME, NODE_IP, e.args, getattr(e, 'errno', 'N/A'), getattr(e, 'strerror', 'N/A'),
                             str(e)))
    except Exception as e:
        LOGGER.error("{} {}: Unhandled Error getting token: {}. Exception type: {}"
                     .format(NODE_NAME, NODE_IP, str(e), type(e).__name__))
    exit()  # exit if an exception occurred


def get_secret():
    if DECRYPTION_KEYFILE is not None and ENCRYPTED_SECRET is not None:
        LOGGER.debug("{} {}: DECRYPTION_KEYFILE and ENCRYPTED_SECRET are present, attempting key decryption"
                     .format(NODE_NAME, NODE_IP))
        with open (get_decryption_key_file_path(), 'r') as key_file:
            return decrypt_secret(key_file.read().strip())
    else:
        LOGGER.debug("{} {}: either DECRYPTION_KEYFILE or ENCRYPTED_SECRET is missing; will use plaintext secret"
                     .format(NODE_NAME, NODE_IP))
        return CLIENT_SECRET


def get_decryption_key_file_path():
    directory_path = "/config/filestore/files_d/Common_d/ifile_d/"
    prefix = ":Common:"
    search_pattern = "{}{}{}_*".format(directory_path, prefix, DECRYPTION_KEYFILE)
    # List all matching files
    matching_files = glob(search_pattern)

    # Sort the matching files to get the latest (if necessary)
    matching_files.sort()

    file = matching_files[0] if matching_files else None
    if file is not None:
        LOGGER.debug("{} {}: decryption key file is {}".format(NODE_NAME, NODE_IP, file))
        return file
    else:
        LOGGER.error("{} {}: could not find decryption key file".format(NODE_NAME, NODE_IP))
        exit()


def decrypt_secret(decryption_key):
    command = "echo '{}' | openssl enc -aes-256-cbc -d -a -k '{}'".format(ENCRYPTED_SECRET, decryption_key)
    try:
        with open('/dev/null', 'w') as devnull:
            return check_output(command, shell=True, stderr=devnull).decode('utf-8').strip()
    except CalledProcessError as e:
        LOGGER.error("Error in decryption: {}".format(e.output))
        exit()


main()
