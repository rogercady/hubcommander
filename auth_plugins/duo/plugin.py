"""
.. module: hubcommander.auth_plugins.duo.plugin
    :platform: Unix
    :copyright: (c) 2017 by Netflix Inc., see AUTHORS for more
    :license: Apache, see LICENSE for more details.

.. moduleauthor:: Mike Grima <mgrima@netflix.com>
"""
import json

from duo_client.client import Client

from hubcommander.bot_components.bot_classes import BotAuthPlugin
from hubcommander.bot_components.slack_comm import send_info, send_error, send_success


class InvalidDuoResponseError(Exception):
    pass


class CantDuoUserError(Exception):
    pass


class NoSecretsProvidedError(Exception):
    pass


class DuoPlugin(BotAuthPlugin):
    def __init__(self):
        super().__init__()

        self.client = None

    def setup(self, secrets, **kwargs):
        if not secrets.get("DUO_IKEY") or not secrets.get("DUO_SKEY") or not secrets.get("DUO_HOST"):
            raise NoSecretsProvidedError("Must provide secrets to enable authentication.")

        self.client = Client(secrets["DUO_IKEY"], secrets["DUO_SKEY"], secrets["DUO_HOST"])

    def authenticate(self, data, user_data, **kwargs):
        send_info(data["channel"], "🎟 @{}: Sending a Duo notification to your device. You must approve!"
                  .format(user_data["name"]), markdown=True, ephemeral_user=user_data["id"])

        try:
            result = self._perform_auth(user_data)
        except InvalidDuoResponseError as idre:
            send_error(data["channel"], "💀 @{}: There was a problem communicating with Duo. Got this status: {}. "
                                        "Aborting..."
                       .format(user_data["name"], str(idre)), markdown=True)
            return False

        except CantDuoUserError as _:
            send_error(data["channel"], "💀 @{}: I can't Duo authenticate you. Please consult with your identity team."
                                        " Aborting..."
                       .format(user_data["name"]), markdown=True)
            return False

        except Exception as e:
            send_error(data["channel"], "💀 @{}: I encountered some issue with Duo... Here are the details: ```{}```"
                       .format(user_data["name"], str(e)), markdown=True)
            return False

        if not result:
            send_error(data["channel"], "💀 @{}: Your Duo request was rejected. Aborting..."
                       .format(user_data["name"]), markdown=True, thread=data["ts"])
            return False

        # All Good:
        send_success(data["channel"], "🎸 @{}: Duo approved! Completing request..."
                     .format(user_data["name"]), markdown=True, ephemeral_user=user_data["id"])
        return True

    def _perform_auth(self, user_data):
        # Push to devices:
        duo_params = {
            "username": user_data["profile"]["email"],
            "factor": "push",
            "device": "auto"
        }
        response, data = self.client.api_call("POST", "/auth/v2/auth", duo_params)
        result = json.loads(data.decode("utf-8"))

        if response.status != 200:
            raise InvalidDuoResponseError(response.status)

        if result["stat"] != "OK":
            raise CantDuoUserError()

        if result["response"]["result"] == "allow":
            return True

        return False
