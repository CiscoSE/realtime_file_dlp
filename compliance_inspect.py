#!/usr/bin/env python3
"""Real-time file DLP for Webex example.

Copyright (c) 2021 Cisco and/or its affiliates.

This software is licensed to you under the terms of the Cisco Sample
Code License, Version 1.1 (the "License"). You may obtain a copy of the
License at

               https://developer.cisco.com/docs/licenses

All use of the material herein must be in accordance with the terms of
the License. All rights not expressly granted by the License are
reserved. Unless required by applicable law or agreed to separately in
writing, software distributed under the License is distributed on an "AS
IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
or implied.

"""

__author__ = "Jaroslav Martan"
__email__ = "jmartan@cisco.com"
__version__ = "0.1.0"
__copyright__ = "Copyright (c) 2021 Cisco and/or its affiliates."
__license__ = "Cisco Sample Code License, Version 1.1"

import os
import sys
import logging
import coloredlogs
from dotenv import load_dotenv, find_dotenv
dotenv_file = os.getenv("DOT_ENV_FILE")
if dotenv_file:
    load_dotenv(find_dotenv(dotenv_file))
else:
    load_dotenv(find_dotenv())

from urllib.parse import urlparse, quote, parse_qsl, urlencode, urlunparse

from webexteamssdk import WebexTeamsAPI, ApiError, AccessToken
webex_api = WebexTeamsAPI(access_token="12345")

"""
# avoid using a proxy for DynamoDB communication
import botocore.endpoint
def _get_proxies(self, url):
    return None
botocore.endpoint.EndpointCreator._get_proxies = _get_proxies
import boto3
from ddb_single_table_obj import DDB_Single_Table
"""

import json, requests
from datetime import datetime, timedelta, timezone
import time
from flask import Flask, request, redirect, url_for, Response, make_response
from flask.logging import default_handler

import concurrent.futures
import signal
import re

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)7s]  [%(module)s.%(name)s.%(funcName)s]:%(lineno)s %(message)s",
    handlers=[
        # logging.FileHandler("./log/debug.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
coloredlogs.install(
    level=os.getenv("LOG_LEVEL", "INFO"),
    fmt="%(asctime)s  [%(levelname)7s]  [%(module)s.%(name)s.%(funcName)s]:%(lineno)s %(message)s",
    logger=logger
)
# logger.addHandler(default_handler)

from logging.config import dictConfig

# dictConfig({
#     'version': 1,
#     'formatters': {'default': {
#         'format': '[%(asctime)s] %(levelname)7s in %(module)s: %(message)s',
#     }},
    # 'handlers': {'wsgi': {
    #     'class': 'logging.StreamHandler',
    #     'stream': 'ext://flask.logging.wsgi_errors_stream',
    #     'formatter': 'default'
    # }},
    # 'root': {
    #     'level': 'INFO',
    #     'handlers': ['wsgi']
    # }
# })

flask_app = Flask(__name__)
flask_app.config["DEBUG"] = True
requests.packages.urllib3.disable_warnings()

import boto3, botocore
from botocore.client import ClientError

# Webex integration scopes
ADMIN_SCOPE = ["audit:events_read"]

TEAMS_COMPLIANCE_SCOPE = ["spark-compliance:events_read",
    "spark-compliance:memberships_read", "spark-compliance:memberships_write",
    "spark-compliance:messages_read", "spark-compliance:messages_write",
    "spark-compliance:rooms_read", "spark-compliance:rooms_write",
    "spark-compliance:team_memberships_read", "spark-compliance:team_memberships_write",
    "spark-compliance:teams_read",
    "spark:people_read"] # "spark:rooms_read", "spark:kms"
    
MORE_SCOPE = ["spark:memberships_read", "spark:memberships_write",
    "spark:messages_read", "spark:messages_write",
    "spark:team_memberships_read", "spark:team_memberships_write",
    "spark:teams_read", "spark:teams_write"]
    
TEAMS_COMPLIANCE_READ_SCOPE = ["spark-compliance:events_read",
    "spark-compliance:memberships_read",
    "spark-compliance:messages_read",
    "spark-compliance:rooms_read",
    "spark-compliance:team_memberships_read",
    "spark-compliance:teams_read",
    "spark:people_read"]

MEETINGS_COMPLIANCE_SCOPE = ["spark-compliance:meetings_write"]

FILES_COMPLIANCE_SCOPE = ["spark-compliance:messages_read",
    "spark-compliance:messages_write",
    "spark-compliance:rooms_read",
    "spark-compliance:webhooks_read",
    "spark-compliance:webhooks_write"
]

# automatically added to any integration
DEFAULT_SCOPE = ["spark:kms"]

# MS Office MIME types
SUSPECT_MIME_TYPES = ["application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.template",
    "application/vnd.ms-word.document.macroEnabled.12",
    "application/vnd.ms-word.template.macroEnabled.12",
    "application/vnd.ms-word.document.macroEnabled.12",
    "application/vnd.ms-word.template.macroEnabled.12",
    "application/msexcel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.template",
    "application/vnd.ms-excel.sheet.macroEnabled.12",
    "application/vnd.ms-excel.sheet.binary.macroEnabled.12",
    "application/vnd.ms-excel.template.macroEnabled.12",
    "application/vnd.ms-excel.addin.macroEnabled.12",
    "application/mspowerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.presentationml.template",
    "application/vnd.openxmlformats-officedocument.presentationml.slideshow",
    "application/vnd.ms-powerpoint.addin.macroEnabled.12",
    "application/vnd.ms-powerpoint.presentation.macroEnabled.12",
    "application/vnd.ms-powerpoint.slideshow.macroEnabled.12",
    "application/vnd.ms-powerpoint.template.macroEnabled.12",
    "application/pdf"]
    
ALLOWED_MIME_TYPES_REGEX = [
    "image\/.*"
]

STATE_CHECK = "webex is great" # integrity test phrase

# timers
SAFE_TOKEN_DELTA = 3600 # safety seconds before access token expires - renew if smaller

AWS_REGION = os.getenv("AWS_REGION")
AWS_PROFILE = os.getenv("AWS_PROFILE")
ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL")
S3_BUCKET = os.getenv("S3_BUCKET")

def sigterm_handler(_signo, _stack_frame):
    "When sysvinit sends the TERM signal, cleanup before exiting."

    logger.info("Received signal {}, exiting...".format(_signo))
    
    thread_executor._threads.clear()
    concurrent.futures.thread._threads_queues.clear()
    sys.exit(0)

signal.signal(signal.SIGTERM, sigterm_handler)
signal.signal(signal.SIGINT, sigterm_handler)

STORAGE_PATH = "token_storage"
WEBEX_TOKEN_FILE = "webex_tokens_{}.json"

thread_executor = concurrent.futures.ThreadPoolExecutor()
wxt_token_key = "COMPLIANCE"
token_refreshed = False

class AccessTokenAbs(AccessToken):
    """
    Store Access Token with a real timestamp.
    
    Access Tokens are generated with 'expires-in' information. In order to store them
    it's better to have a real expiration date and time. Timestamps are saved in UTC.
    Note that Refresh Token expiration is not important. As long as it's being used
    to generate new Access Tokens, its validity is extended even beyond the original expiration date.
    
    Attributes:
        expires_at (float): When the access token expires
        refresh_token_expires_at (float): When the refresh token expires.
    """
    def __init__(self, access_token_json):
        super().__init__(access_token_json)
        if not "expires_at" in self._json_data.keys():
            self._json_data["expires_at"] = str((datetime.now(timezone.utc) + timedelta(seconds = self.expires_in)).timestamp())
        logger.debug("Access Token expires in: {}s, at: {}".format(self.expires_in, datetime.fromtimestamp(float(self.expires_at))))
        if not "refresh_token_expires_at" in self._json_data.keys():
            self._json_data["refresh_token_expires_at"] = str((datetime.now(timezone.utc) + timedelta(seconds = self.refresh_token_expires_in)).timestamp())
        logger.debug("Refresh Token expires in: {}s, at: {}".format(self.refresh_token_expires_in, datetime.fromtimestamp(float(self.refresh_token_expires_at))))
        
    def __str__(self):
        tr = self.token_record
        tr["expires_at"] = str(datetime.fromtimestamp(float(tr["expires_at"])))
        tr["refresh_token_expires_at"] = str(datetime.fromtimestamp(float(tr["refresh_token_expires_at"])))
        return json.dumps(tr)
        
    @property
    def expires_at(self):
        return self._json_data["expires_at"]
        
    @property
    def refresh_token_expires_at(self):
        return self._json_data["refresh_token_expires_at"]
        
    @property
    def token_record(self):
        tr = {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "refresh_token_expires_at": self.refresh_token_expires_at
        }

        return tr
        
def get_boto3_client(service):
    """
    Initialize Boto3 client.
    """
    boto3.setup_default_session(profile_name=AWS_PROFILE)
    # logger.info(f"AWS region: {AWS_REGION}, URL: {ENDPOINT_URL}, service: {service}")
    # aws_key_id = os.getenv("AWS_S3_KEY_ID")
    # aws_key = os.getenv("AWS_S3_SECRET_KEY")
    # logger.info(f"AWS keys: {aws_key_id}  {aws_key}")
    try:
        if ENDPOINT_URL:
            boto_client = boto3.client(service, region_name=AWS_REGION, endpoint_url=ENDPOINT_URL)
        else:
            # boto_resource = boto3.resource(service)
            # aws_id = os.getenv("AWS_ACCESS_KEY_ID")
            # aws_key = os.getenv("AWS_SECRET_ACCESS_KEY")
            # aws_token = os.getenv("AWS_SESSION_TOKEN")
            # logger.info(f"runtime id: {aws_id}, key: {aws_key}, token: {aws_token}")
            boto_client = boto3.client(service)
    except Exception as e:
        logger.exception(f'Error while creating Boto client: {e}')
        raise e
    else:
        return boto_client

def create_bucket(bucket_name):
    """
    Create a S3 bucket.
    """
    logger.info("create bucket")
    # session = boto3.Session()
    # # ddb = session.resource('dynamodb')
    # s3 = session.client('s3')
    try:
        s3_resource = boto3.resource('s3')
        s3_client = get_boto3_client('s3')
        try:
            s3_resource.meta.client.head_bucket(Bucket=bucket_name)
            logger.info(f"Bucket \"{bucket_name}\" already exists")
        except ClientError:
            logger.info(f"Creating bucket \"{bucket_name}\"...")
            s3_client.create_bucket(
                Bucket=bucket_name
            )
    except Exception as e:
        logger.exception(f'Error while creating s3 bucket: {e}')
        raise e

def save_tokens(token_key, tokens):
    """
    Save tokens.
    
    Parameters:
        tokens (AccessTokenAbs): Access & Refresh Token object
    """
    global token_refreshed
    
    # ddb.save_db_record(token_key, "TOKENS", str(tokens.expires_at), **token_record)
    s3_client = get_boto3_client('s3')
    logger.debug("AT timestamp: {}".format(tokens.expires_at))
    token_record = tokens.token_record
    file_destination = get_webex_token_file(token_key)
    logger.debug("Saving Webex tokens to: {}:{}".format(s3_client, file_destination))
    s3_client.put_object(Body=json.dumps(token_record), Bucket=S3_BUCKET, Key=file_destination)

    token_refreshed = True # indicate to the main loop that the Webex token has been refreshed
    
def get_webex_token_file(token_key):
    return "/".join((STORAGE_PATH, WEBEX_TOKEN_FILE.format(token_key)))
    
def get_tokens_for_key(token_key):
    """
    Load tokens.
    
    Parameters:
        token_key (str): A key to the storage of the token
        
    Returns:
        AccessTokenAbs: Access & Refresh Token object or None
    """
    try:
        file_source = get_webex_token_file(token_key)
        s3_client = get_boto3_client('s3')
        logger.debug("Loading Webex tokens from: {}:{}".format(s3_client, file_source))
        result = s3_client.get_object(Bucket=S3_BUCKET, Key=file_source)
        token_data = json.loads(result["Body"].read().decode())
        tokens = AccessTokenAbs(token_data)
        return tokens
    except Exception as e:
        logger.info("Webex token load exception: {}".format(e))
        return None

    """
    db_tokens = ddb.get_db_record(token_key, "TOKENS")
    logger.debug("Loaded tokens from db: {}".format(db_tokens))
    
    if db_tokens:
        tokens = AccessTokenAbs(db_tokens)
        logger.debug("Got tokens: {}".format(tokens))
        ## TODO: check if token is not expired, generate new using refresh token if needed
        return tokens
    else:
        logger.error("No tokens for key {}.".format(token_key))
        return None
    """

def refresh_tokens_for_key(token_key):
    """
    Run the Webex 'get new token by using refresh token' operation.
    
    Get new Access Token. Note that the expiration of the Refresh Token is automatically
    extended no matter if it's indicated. So if this operation is run regularly within
    the time limits of the Refresh Token (typically 3 months), the Refresh Token never expires.
    
    Parameters:
        token_key (str): A key to the storage of the token
        
    Returns:
        str: message indicating the result of the operation
    """
    tokens = get_tokens_for_key(token_key)
    client_id = os.getenv("WEBEX_INTEGRATION_CLIENT_ID")
    client_secret = os.getenv("WEBEX_INTEGRATION_CLIENT_SECRET")
    integration_api = WebexTeamsAPI()
    try:
        new_tokens = AccessTokenAbs(integration_api.access_tokens.refresh(client_id, client_secret, tokens.refresh_token).json_data)
        save_tokens(token_key, new_tokens)
        logger.info("Tokens refreshed for key {}".format(token_key))
    except ApiError as e:
        logger.error("Client Id and Secret loading error: {}".format(e))
        return "Error refreshing an access token. Client Id and Secret loading error: {}".format(e)
        
    return "Tokens refreshed for {}".format(token_key)
    
def get_webex_client():
    tokens = get_tokens_for_key(wxt_token_key)
    if not tokens:
        return None
        
    token_delta = datetime.fromtimestamp(float(tokens.expires_at)) - datetime.utcnow()
    if token_delta.total_seconds() < SAFE_TOKEN_DELTA:
        logger.info("Access token is about to expire, renewing...")
        refresh_tokens_for_key(wxt_token_key)
        tokens = get_tokens_for_key(wxt_token_key)
    
    try:
        client = WebexTeamsAPI(access_token = tokens.access_token)
        return client
    except ApiError as e:
        logger.error(f"Error creating Webex client: {e}")
            
def secure_scheme(scheme):
    return re.sub(r"^http$", "https", scheme)

# Flask part of the code

"""
1. initialize database table if needed
2. start event checking thread
"""
@flask_app.before_first_request
def startup():
    logger.debug("Startup...")
    logger.info(f"Creating S3 bucket \"{S3_BUCKET}\"")
    create_bucket(S3_BUCKET)

"""
OAuth proccess done
"""
@flask_app.route("/authdone", methods=["GET"])
def authdone():
    """
    Landing page for the OAuth authorization process.
    
    Used to hide the OAuth response URL parameters.
    """
    webex_client = get_webex_client()
    if webex_client:
        webhooks = webex_client.webhooks.list()
        logger.info("Existing webhooks:")
        for wh in webhooks:
            logger.info(wh)
            
        myUrlParts = urlparse(request.url)
        logger.debug(f"URL parts: {myUrlParts}")
        webhook_url = secure_scheme(myUrlParts.scheme) + "://" + myUrlParts.netloc + url_for("spark_webhook")
        logger.info("New webhook URL: {}".format(webhook_url))
        if create_webhook(webex_client, webhook_url):
            logger.info("Webhook created")
            return "Thank you for providing the authorization. You may close this browser window."
        else:
            return "Failed to create webhooks. Check the application log."
    else:
        return "Webex client creation failed. Check the application log."

def create_webhook(webex_api, target_url):
    """create a set of webhooks for the Bot
    webhooks are defined according to the resource_events dict
    
    arguments:
    target_url -- full URL to be set for the webhook
    """    
    logger.debug("Create new webhook to URL: {}".format(target_url))
    
    resource_events = {
        "messages": ["created"],
    }
    status = None
        
    try:
        check_webhook = webex_api.webhooks.list()
        for webhook in check_webhook:
            int_id = os.getenv("WEBEX_INTEGRATION_ID")
            if webhook.appId == int_id:
                logger.debug("Deleting webhook {}, '{}', target URL: {}".format(webhook.id, webhook.name, webhook.targetUrl))
                try:
                    if not flask_app.testing:
                        webex_api.webhooks.delete(webhook.id)
                except ApiError as e:
                    logger.error("Webhook {} delete failed: {}.".format(webhook.id, e))
    except ApiError as e:
        logger.error("Webhook list failed: {}.".format(e))
        
    for resource, events in resource_events.items():
        for event in events:
            try:
                if not flask_app.testing:
                    wh = webex_api.webhooks.create(name="Webhook for event \"{}\" on resource \"{}\"".format(event, resource), targetUrl=target_url, resource=resource, event=event, ownedBy="org")
                status = True
                logger.debug("Webhook for {}/{} was successfully created: {}".format(resource, event, wh.id))
            except ApiError as e:
                logger.error("Webhook create failed: {}.".format(e))
            
    return status

@flask_app.route("/authorize", methods=["GET"])
def authorize():
    """
    Start the Webex OAuth grant flow.
    
    See: https://developer.webex.com/docs/integrations
    Note that scopes and redirect URI of your integration have to match this application.
    """
    myUrlParts = urlparse(request.url)
    full_redirect_uri = os.getenv("REDIRECT_URI")
    if full_redirect_uri is None:
        full_redirect_uri = secure_scheme(myUrlParts.scheme) + "://" + myUrlParts.netloc + url_for("manager")
    logger.info("Authorize redirect URL: {}".format(full_redirect_uri))

    client_id = os.getenv("WEBEX_INTEGRATION_CLIENT_ID")
    redirect_uri = quote(full_redirect_uri, safe="")
    scope = FILES_COMPLIANCE_SCOPE + DEFAULT_SCOPE    
    scope_uri = quote(" ".join(scope), safe="")
    logger.info(f"Requested scope: {scope}")
    
    join_url = webex_api.base_url+"authorize?client_id={}&response_type=code&redirect_uri={}&scope={}&state={}".format(client_id, redirect_uri, scope_uri, STATE_CHECK)

    return redirect(join_url)
    
@flask_app.route("/manager", methods=["GET"])
def manager():
    """
    Webex OAuth grant flow redirect URL
    
    Generate access and refresh tokens using 'code' generated in OAuth grant flow
    after user successfully authenticated to Webex

    See: https://developer.webex.com/blog/real-world-walkthrough-of-building-an-oauth-webex-integration
    https://developer.webex.com/docs/integrations
    """   

    if request.args.get("error"):
        return request.args.get("error_description")
        
    input_code = request.args.get("code")
    check_phrase = request.args.get("state")
    logger.debug("Authorization request \"state\": {}, code: {}".format(check_phrase, input_code))

    myUrlParts = urlparse(request.url)
    full_redirect_uri = os.getenv("REDIRECT_URI")
    if full_redirect_uri is None:
        full_redirect_uri = secure_scheme(myUrlParts.scheme) + "://" + myUrlParts.netloc + url_for("manager")
    logger.debug("Manager redirect URI: {}".format(full_redirect_uri))
    
    try:
        client_id = os.getenv("WEBEX_INTEGRATION_CLIENT_ID")
        client_secret = os.getenv("WEBEX_INTEGRATION_CLIENT_SECRET")
        tokens = AccessTokenAbs(webex_api.access_tokens.get(client_id, client_secret, input_code, full_redirect_uri).json_data)
        logger.debug(f"Access info: {tokens}")
        save_tokens(wxt_token_key, tokens)
    except ApiError as e:
        logger.error("Client Id and Secret loading error: {}".format(e))
        return "Error issuing an access token. Client Id and Secret loading error: {}".format(e)
        
    # hide the original redirect URL and its parameters from the user's browser
    return redirect(url_for("authdone"))
    
"""
Bot setup. Used mainly for webhook creation and gathering a dynamic Bot URL.
"""

@flask_app.route("/", methods=["GET", "POST"])
def spark_webhook():
    if request.method == "POST":
        webhook = request.get_json(silent=True)
        logger.debug("Webhook received: {}".format(webhook))
        handle_webhook_event(webhook)        
    elif request.method == "GET":
        pass
    return "OK"
    
"""
Main function which handles the webhook events. It reacts both on messages and button&card events

Look at the 'msg +=' for workflow explanation
"""

# @task
def handle_webhook_event(webhook):
    action_list = []
    msg = ""
    attach = []
    target_dict = {"roomId": webhook["data"]["roomId"]}
    form_type = None
    out_messages = [] # additional messages apart of the standard response
        
# handle messages with files
    if webhook["resource"] == "messages":
        webex_api = get_webex_client()
        if not webex_api:
            logger.error("Failed to create Webex client")
            return "No action"

        # see https://developer.webex.com/docs/api/guides/webex-real-time-file-dlp-basics
        if webhook["data"].get("files") and webhook["data"]["roomType"] == "group":
            hdr = {"Authorization": "Bearer " + webex_api.access_token}
            for url in webhook["data"]["files"]:
                url += ",dlpUnchecked" # dlpRejected, dlpRejectedByDefault
                file_info = requests.head(url, headers = hdr)
                file_url_parts = urlparse(url)
                logger.debug(f"File URL parts: {file_url_parts}")
                logger.info("Message file: {}\ninfo: {}".format(url, file_info.headers))
                
                # check for disallowed MIME types
                """
                allowed_found = True
                if file_info.headers["Content-Type"] in SUSPECT_MIME_TYPES:
                    allowed_found = False
                """
                
                # check for allowed MIME types
                allowed_found = False
                content_type = file_info.headers["Content-Type"]
                for allowed_regex in ALLOWED_MIME_TYPES_REGEX:
                    if re.match(allowed_regex, content_type):
                        allowed_found = True
                        break

                result = "approve"
                if not allowed_found:
                    logger.debug(f"File type \"{content_type}\" not permitted")
                    result = "reject"
                
                res_params = [("result", result)]
                res_url = urlunparse((file_url_parts.scheme, file_url_parts.netloc, file_url_parts.path, '', urlencode(res_params), ''))
                logger.debug(f"Result URL: {res_url}")
                requests.put(res_url, headers = hdr)
                    
        
    return json.dumps(action_list)
                
"""
Startup procedure used to initiate @flask_app.before_first_request
"""

@flask_app.route("/startup")
def startup():
    return "Hello World!"
    
"""
Independent thread startup, see:
https://networklore.com/start-task-with-flask/
"""
def start_runner():
    def start_loop():
        not_started = True
        while not_started:
            logger.info('In start loop')
            try:
                r = requests.get('http://127.0.0.1:5005/startup')
                if r.status_code == 200:
                    logger.info('Server started, quiting start_loop')
                    not_started = False
                logger.debug("Status code: {}".format(r.status_code))
            except:
                logger.info('Server not yet started')
            time.sleep(2)

    logger.info('Started runner')
    thread_executor.submit(start_loop)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', action='count', help="Set logging level by number of -v's, -v=WARN, -vv=INFO, -vvv=DEBUG")
    
    args = parser.parse_args()
    if args.verbose:
        if args.verbose > 2:
            logging.basicConfig(level=logging.DEBUG)
        elif args.verbose > 1:
            logging.basicConfig(level=logging.INFO)
        if args.verbose > 0:
            logging.basicConfig(level=logging.WARN)
            
    logger.info("Logging level: {}".format(logging.getLogger(__name__).getEffectiveLevel()))
    
    start_runner()
    flask_app.run(host="0.0.0.0", port=5005)
