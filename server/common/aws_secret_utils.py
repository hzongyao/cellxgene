import logging
import os
import sys

import boto3
from flask import json

from server.common.data_locator import discover_s3_region_name


def handle_config_from_secret(app_config):
    """Update configuration from the secret manager"""
    secret_name = os.getenv("CXG_AWS_SECRET_NAME")
    if not secret_name:
        return

    # need to find the secret manager region.
    #  1. from CXG_AWS_SECRET_REGION_NAME
    #  2. discover from dataroot location (if on s3)
    #  3. discover from config file location (if on s3)
    secret_region_name = os.getenv("CXG_AWS_SECRET_REGION_NAME")
    if secret_region_name is None:
        secret_region_name = discover_s3_region_name(app_config.multi_dataset__dataroot)
        if not secret_region_name:
            from server.eb.app import config_file
            secret_region_name = discover_s3_region_name(config_file)
    if not secret_region_name:
        logging.error("Could not determine the AWS Secret Manager region")
        sys.exit(1)

    secrets = get_secret_key(secret_region_name, secret_name)

    if not secrets:
        return

    keyattrs = (
        ("flask_secret_key", "app__flask_secret_key"),
        ("oauth_client_secret", "authentication__params_oauth__client_secret"),
    )

    for key, attr in keyattrs:
        cur_val = getattr(app_config.server_config, attr)
        if cur_val:
            continue

        # replace the attr with the secret if it is not set
        val = secrets.get(key)
        if val:
            logging.error(f"set {attr} from secret")
            app_config.update_server_config(**{attr : val})


def get_secret_key(region_name, secret_name):
    session = boto3.session.Session()
    client = session.client(service_name="secretsmanager", region_name=region_name)

    try:
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)
        if "SecretString" in get_secret_value_response:
            var = get_secret_value_response["SecretString"]
            secret = json.loads(var)
            return secret
    except Exception:
        logging.critical("Caught exception during get_secret_key", exc_info=True)
        sys.exit(1)

    return None