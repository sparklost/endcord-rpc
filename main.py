import json
import logging
import os
import signal
import sys
import time

os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"   # fix for https://github.com/Nuitka/Nuitka/issues/3442
if sys.platform == "linux":
    cert_path = "/etc/ssl/certs/ca-certificates.crt"
    if os.path.exists(cert_path):
        os.environ["SSL_CERT_FILE"] = cert_path

from endcord_rpc import client_properties
from endcord_rpc.discord import Discord
from endcord_rpc.game_detection import GameDetection
from endcord_rpc.gateway import Gateway
from endcord_rpc.rpc import RPC

APP_NAME = "endcord-rpc"
ERROR_TEXT = "\nUnhandled exception occurred. Please report here: https://github.com/sparklost/endcord-rpc/issues"
DEFAULT_CONFIG = {
  "token": "",
  "game_detection": True,
  "game_list_download_delay": 7,
  "games_blacklist": [],
  "proxy": None,
  "custom_host": None,
  "client_properties": "default",
  "custom_user_agent": None,
}
gateway = None
run = False

# get platform specific paths
if sys.platform == "linux":
    path = os.environ.get("XDG_DATA_HOME", "")
    if path.strip():
        config_path = os.path.join(path, f"{APP_NAME}")
    else:
        config_path = f"~/.config/{APP_NAME}"
elif sys.platform == "win32":
    config_path = os.path.join(os.environ["LOCALAPPDATA"], APP_NAME)
elif sys.platform == "darwin":
    config_path = f"~/Library/Application Support/{APP_NAME}"
else:
    sys.exit(f"Unsupported platform: {sys.platform}")
config_path = os.path.expanduser(config_path)
if not os.path.exists(config_path):
    os.makedirs(config_path, exist_ok=True)

logger = logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    filename=os.path.join(config_path, "endcord-rpc.log"),
    encoding="utf-8",
    filemode="w",
    format="{asctime} - {levelname}\n  [{module}]: {message}\n",
    style="{",
    datefmt="%Y-%m-%d-%H:%M:%S",
)


def main():
    """Main app function"""
    global gateway, run

    # load config
    config_file_path = os.path.join(config_path, "config.json")
    if not os.path.exists(config_file_path):
        with open(config_file_path, "w") as file:
            json.dump(DEFAULT_CONFIG, file, indent=2)
    with open(config_file_path, "r") as f:
        config = json.load(f)
    host = config["custom_host"]
    token = config["token"]
    proxy = config["proxy"]
    enable_game_detection = config["game_detection"]
    download_delay = config.get("game_list_download_delay", 7)
    game_detection_blacklist = config["games_blacklist"]
    if not token:
        sys.exit(f"Token not specified in config: {config_file_path}")
        logger.error(f"Token not specified in config: {config_file_path}")
    print(f"Config: {config_file_path}")
    logger.info(f"Config: {config_file_path}")

    # initial values
    run = True
    my_status = {
        "status": "online",
        "custom_status": None,
        "custom_status_emoji": None,
        "activities": [],
    }
    my_activities = []

    # get client properties
    if config["client_properties"].lower() == "anonymous":
        client_prop = client_properties.get_anonymous_properties()
    else:
        client_prop = client_properties.get_default_properties()
    if config["custom_user_agent"]:
        client_prop = client_properties.add_user_agent(client_prop, config["custom_user_agent"])
    client_prop_gateway = client_properties.add_for_gateway(client_prop)
    user_agent = client_prop["browser_user_agent"]
    client_prop = client_properties.encode_properties(client_prop)
    logger.debug(f"User-Agent: {user_agent}")

    # initialize stuff
    logger.info("Connecting to gateway")
    print("Connecting to gateway")
    discord = Discord(token, host, client_prop, user_agent, proxy=proxy)
    gateway = Gateway(token, host, client_prop_gateway, user_agent, proxy=proxy)
    gateway.connect()
    while not gateway.get_ready():
        if gateway.error:
            logger.fatal(f"Gateway error: \n {gateway.error}")
            print(f"Gateway error: \n {gateway.error}")
            sys.exit(gateway.error + ERROR_TEXT)
        if not gateway.run:
            sys.exit()
        time.sleep(0.2)

    discord_settings = gateway.get_settings_proto()
    # download proto if its not in gateway
    if not discord_settings or "status" not in discord_settings:
        discord_settings = discord.get_settings_proto(1)
    custom_status_emoji = None
    custom_status = None
    if "status" in discord_settings and "status" in discord_settings["status"]:
        status = discord_settings["status"]["status"]
        if "customStatus" in discord_settings["status"]:
            custom_status_emoji = {
                "id": discord_settings["status"]["customStatus"].get("emojiID"),
                "name": discord_settings["status"]["customStatus"].get("emojiName"),
                "animated": discord_settings["status"]["customStatus"].get("animated", False),
            }
            custom_status = discord_settings["status"]["customStatus"].get("text")
        if custom_status_emoji and not (custom_status_emoji["name"] or custom_status_emoji["id"]):
            custom_status_emoji = None
    else:   # just in case
        status = "online"
        custom_status = None
        custom_status_emoji = None
    my_status.update({
        "status": status,
        "custom_status": custom_status,
        "custom_status_emoji": custom_status_emoji,
    })
    gateway.update_presence(
        my_status["status"],
        custom_status=my_status["custom_status"],
        custom_status_emoji=my_status["custom_status_emoji"],
        activities=my_activities,
    )

    my_user_data = gateway.get_my_user_data()
    rpc = RPC(discord, my_user_data, {"rpc_external": True})
    if enable_game_detection:
        game_detection = GameDetection(gateway, discord, game_detection_blacklist, config_path, download_delay=download_delay)

    # perform token update if needed
    new_token = gateway.get_token_update()
    if new_token:
        logger.info("Token has been refreshed")
        print("Token hsa been refreshed")
        config["token"] = new_token
        with open(config_file_path, "w") as file:
            json.dump(config, file, indent=2)
    del new_token

    # main loop
    while run:

        # check gateway state
        gateway_state = gateway.get_state()

        # check and update my status
        new_status = gateway.get_my_status()
        if new_status:
            my_status.update(new_status)
            my_status["activities"] = new_status["activities"]
        new_proto = gateway.get_settings_proto()
        if new_proto:
            discord_settings = new_proto
            custom_status_emoji = None
            custom_status = None
            if "status" in discord_settings and "status" in discord_settings["status"]:
                status = discord_settings["status"]["status"]
                if "customStatus" in discord_settings["status"]:
                    custom_status_emoji = {
                        "id": discord_settings["status"]["customStatus"].get("emojiID"),
                        "name": discord_settings["status"]["customStatus"].get("emojiName"),
                        "animated": discord_settings["status"]["customStatus"].get("animated", False),
                    }
                    custom_status = discord_settings["status"]["customStatus"].get("text")
                if custom_status_emoji and not (custom_status_emoji["name"] or custom_status_emoji["id"]):
                    custom_status_emoji = None
            else:   # just in case
                status = "online"
                custom_status = None
                custom_status_emoji = None
            my_status.update({
                "status": status,
                "custom_status": custom_status,
                "custom_status_emoji": custom_status_emoji,
            })
            gateway.update_presence(
                my_status["status"],
                custom_status=my_status["custom_status"],
                custom_status_emoji=my_status["custom_status_emoji"],
                activities=my_activities,
            )

        # check for user data updates
        new_user_data = gateway.get_my_user_data()
        if new_user_data:
            rpc.generate_dispatch(new_user_data)

        # send new rpc activities
        new_activities = rpc.get_activities()
        if new_activities is not None and gateway_state == 1:
            rpc_apps_ids = [d["application_id"] for d in new_activities]
            game_detection_activities = game_detection.get_activities(force=True) if enable_game_detection else []
            my_activities = new_activities + [d for d in game_detection_activities if d["application_id"] not in rpc_apps_ids]
            gateway.update_presence(
                my_status["status"],
                custom_status=my_status["custom_status"],
                custom_status_emoji=my_status["custom_status_emoji"],
                activities=my_activities,
                afk=True,   # so other clients can receive notifications
            )

        # send new detectable games activities
        if enable_game_detection:
            new_activities = game_detection.get_activities()
            if new_activities is not None and gateway_state == 1:
                # if new activities app_id not in rpc activities app_id
                rpc_activities = rpc.get_activities(force=True)
                rpc_apps_ids = [d["application_id"] for d in rpc_activities]
                my_activities = rpc_activities + [d for d in new_activities if d["application_id"] not in rpc_apps_ids]
                gateway.update_presence(
                    my_status["status"],
                    custom_status=my_status["custom_status"],
                    custom_status_emoji=my_status["custom_status_emoji"],
                    activities=my_activities,
                    afk=True,   # so other clients can receive notifications
                )

        # check gateway for errors
        if gateway.error:
            print(f"Gateway error: \n {gateway.error}")
            sys.exit(gateway.error + ERROR_TEXT)

        time.sleep(0.1)   # some reasonable delay
    run = False


def sigint_handler(_signum, _frame):
    """Handling Ctrl-C event"""
    global gateway, run
    if gateway:
        gateway.disconnect_ws()
    run = False
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, sigint_handler)
    main()
