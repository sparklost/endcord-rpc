import base64
import http.client
import logging
import os
import socket
import ssl
import time
import urllib.parse

try:
    import orjson as json
except ImportError:
    try:
        import ujson as json
    except ImportError:
        import json
import json as json_

import socks
from discord_protos import FrecencyUserSettings, PreloadedUserSettings
from google.protobuf.json_format import MessageToDict

DISCORD_HOST = "discord.com"
logger = logging.getLogger(__name__)


def json_array_objects(stream):
    """Stream a json array from a file like object. Yield one parsed object at a time without loading full json into memory"""
    # replaces ijson.items(data, "item")
    decoder = json_.JSONDecoder()
    buf = ""
    in_array = False
    for chunk in iter(lambda: stream.read(65536).decode("utf-8"), ""):
        buf += chunk
        i = 0
        length = len(buf)
        while i < length:
            ch = buf[i]
            if not in_array:
                if ch == "[":   # skip to [
                    in_array = True
                i += 1
                continue
            if ch == "]":
                return
            if ch.isspace() or ch == ",":   # skip space and comma
                i += 1
                continue
            try:   # try to get object
                obj, consumed = decoder.raw_decode(buf[i:])
            except json_.JSONDecodeError:
                break
            yield obj
            i += consumed
        buf = buf[i:]   # keep incomplete json only


class Discord():
    """Methods for fetching and sending data to Discord using REST API"""

    def __init__(self, token, host, client_prop, user_agent, proxy=None):
        if host:
            host_obj = urllib.parse.urlsplit(host)
            if host_obj.netloc:
                self.host = host_obj.netloc
            else:
                self.host = host_obj.path
        else:
            self.host = DISCORD_HOST
        self.token = token
        self.header = {
            "Accept": "*/*",
            "Authorization": self.token,
            "Content-Type": "application/json",
            "Priority": "u=1",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
            "User-Agent": user_agent,
        }
        if client_prop:
            self.header["X-Super-Properties"] = client_prop
        if self.header["Authorization"].startswith("Bot"):
            self.header.pop("User-Agent", None)
            self.header.pop("X-Super-Properties", None)
        self.user_agent = user_agent
        self.proxy = urllib.parse.urlsplit(proxy)
        self.activity_token = None
        self.protos = [[], []]


    def get_connection(self, host, port):
        """Get connection object and handle proxying"""
        if self.proxy.scheme:
            if self.proxy.scheme.lower() == "http":
                connection = http.client.HTTPSConnection(self.proxy.hostname, self.proxy.port)
                connection.set_tunnel(host, port=port)
            elif "socks" in self.proxy.scheme.lower():
                proxy_sock = socks.socksocket()
                proxy_sock.set_proxy(socks.SOCKS5, self.proxy.hostname, self.proxy.port)
                proxy_sock.settimeout(10)
                proxy_sock.connect((host, port))
                ssl_context = ssl.create_default_context()
                ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
                proxy_sock = ssl_context.wrap_socket(proxy_sock, server_hostname=host)
                # proxy_sock.do_handshake()   # seems like its not needed
                connection = http.client.HTTPSConnection(host, port, timeout=10)
                connection.sock = proxy_sock
            else:
                connection = http.client.HTTPSConnection(host, port)
        else:
            connection = http.client.HTTPSConnection(host, port, timeout=5)
        return connection


    def get_settings_proto(self, num):
        """
        Get account settings:
        num=1 - General user settings
        num=2 - Frecency and favorites storage for various things
        """
        if self.protos[num-1]:
            return self.protos[num-1]
        message_data = None
        url = f"/api/v9/users/@me/settings-proto/{num}"
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("GET", url, message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return None
        if response.status == 200:
            data = json.loads(response.read())["settings"]
            connection.close()
            if num == 1:
                decoded = PreloadedUserSettings.FromString(base64.b64decode(data))
            elif num == 2:
                decoded = FrecencyUserSettings.FromString(base64.b64decode(data))
            else:
                return {}
            self.protos[num-1] = MessageToDict(decoded)
            return self.protos[num-1]
        logger.error(f"Failed to fetch settings. Response code: {response.status}")
        print(f"Failed to fetch settings. Response code: {response.status}")
        connection.close()
        return False


    def get_rpc_app(self, app_id):
        """Get data about Discord RPC application"""
        message_data = None
        url = f"/api/v9/oauth2/applications/{app_id}/rpc"
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("GET", url, message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return None
        if response.status == 200:
            data = json.loads(response.read())
            connection.close()
            return {
                "id": data["id"],
                "name": data["name"],
                "description": data["description"],
            }
        logger.error(f"Failed to fetch application rpc data. Response code: {response.status}")
        print(f"Failed to fetch application rpc data. Response code: {response.status}")
        connection.close()
        return False


    def get_rpc_app_assets(self, app_id):
        """Get Discord application assets list"""
        message_data = None
        url = f"/api/v9/oauth2/applications/{app_id}/assets"
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("GET", url, message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return None
        if response.status == 200:
            data = json.loads(response.read())
            connection.close()
            assets = []
            for asset in data:
                assets.append({
                    "id": asset["id"],
                    "name": asset["name"],
                })
            return assets
        logger.error(f"Failed to fetch application assets. Response code: {response.status}")
        print(f"Failed to fetch application assets. Response code: {response.status}")
        connection.close()
        return False


    def get_rpc_app_external(self, app_id, asset_url):
        """Get Discord application external assets"""
        message_data = json.dumps({"urls": [asset_url]})
        url = f"/api/v9/applications/{app_id}/external-assets"
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("POST", url, message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return None
        if response.status == 200:
            data = json.loads(response.read())
            connection.close()
            return data
        if response.status == 429:
            data = json.loads(response.read())
            connection.close()
            retry_after = float(data["retry_after"])
            logger.error("Failed to fetch application external assets. Response code: 429 - Retry after: {retry_after}")
            print(f"Failed to fetch application external assets. Response code: 429 - Retry after: {retry_after}")
            return retry_after
        logger.error(f"Failed to fetch application external assets. Response code: {response.status}")
        print(f"Failed to fetch application external assets. Response code: {response.status}")
        connection.close()
        return False


    def send_update_activity_session(self, app_id, exe_path, closed, session_id, media_session_id=None, voice_channel_id=None):
        """Send update for currently running activity session"""
        message_data = json.dumps({
            "token": self.activity_token,
            "application_id": app_id,
            "share_activity": True,
            "exePath": exe_path,
            "voice_channel_id": voice_channel_id,
            "session_id": session_id,
            "media_session_id": media_session_id,
            "closed": closed,
        })
        url = "/api/v9/activities"
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("POST", url, message_data, self.header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return None
        if response.status == 200:
            self.activity_token = json.loads(response.read())["token"]
            connection.close()
            return self.activity_token
        logger.error(f"Failed to update activity session. Response code: {response.status}")
        print(f"Failed to update activity session. Response code: {response.status}")
        connection.close()
        return False


    def get_detectable_apps(self, save_dir, etag=None):
        """
        Get and save list (as ndjson) of detectable applications, containing all detectable games.
        Use etag to skip downloading same cached resource.
        File is saved as: detectable_apps_{etag}_{current_time}.ndjson, where current_time is unix_time/1000
        """
        message_data = None
        url = "/api/v9/applications/detectable"
        if etag:
            header = self.header | {"If-None-Match": f'W/"{etag}"'}
        else:
            header = self.header
        try:
            connection = self.get_connection(self.host, 443)
            connection.request("GET", url, message_data, header)
            response = connection.getresponse()
        except (socket.gaierror, TimeoutError):
            connection.close()
            return None, etag
        if response.status == 200:
            current_time = int(time.time()/1000)
            etag = response.getheader("ETag")[3:-1]
            save_path = os.path.expanduser(os.path.join(save_dir, f"detectable_apps_{etag}_{current_time}.ndjson"))
            using_orjson = json.__name__ == "orjson"
            if using_orjson:
                nl = b"\n"
            else:
                nl = "\n"
            with open(save_path, "w" + ("b" if using_orjson else "")) as f:
                try:
                    for app in json_array_objects(response):
                        executables = []
                        for exe in app["executables"]:
                            exe_os = exe["os"]
                            exe_os = 0 if exe_os == "linux" else 1 if exe_os == "win32" else 2 if exe_os == "darwin" else None
                            if exe_os is not None:
                                path_piece = exe["name"].lower()
                                if not path_piece.startswith("/"):
                                    path_piece = "/" + path_piece
                                executables.append((exe_os, path_piece))
                        if not executables:
                            continue
                        ready_app = (app["id"], app["name"], executables)
                        f.write(json.dumps(ready_app) + nl)
                except Exception as e:
                    logger.error(f"Error decoding detectable apps json: {e}")
                    print(f"Error decoding detectable apps json: {e}")
                    return None, etag
                return save_path, etag
        elif response.status == 304:   # not modified
            save_path = os.path.expanduser(os.path.join(save_dir, f"detectable_apps_{etag}_{current_time}.ndjson"))
            return save_path, etag
        connection.close()
        return None, etag
