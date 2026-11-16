"""Mi Home cloud connector used to fetch device tokens automatically.

The login and signed-request logic is adapted from the micloud project
(https://github.com/squachen/micloud, MIT license) as rewritten for
XiaomiGateway3 (https://github.com/AlexxIT/XiaomiGateway3, MIT license).
Original MIT license text:

MIT License

Copyright (c) 2020 Sammy Svensson

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import base64
import hashlib
import json
import logging
import os
import random
import string
import time

from aiohttp import ClientSession, ClientTimeout

_LOGGER = logging.getLogger(__name__)

UA = "Android-7.1.1-1.0.0-ONEPLUS A3010-136-%s APP/xiaomi.smarthome APPV/62830"


class MiCloudError(Exception):
    """Generic Mi Cloud error."""


class MiCloudAuthError(MiCloudError):
    """Wrong username or password."""


class MiCloudTwoFactor(MiCloudError):
    """Two-factor verification required, user must visit the url first."""

    def __init__(self, verify_url: str) -> None:
        super().__init__(verify_url)
        self.verify_url = verify_url


class MiCloud:
    """Minimal async Mi Cloud client for login and device list."""

    def __init__(self, session: ClientSession) -> None:
        self.session = session
        self.device_id = get_random_string(16)
        self.user_id: str | None = None
        self.ssecurity: str | None = None
        self.service_token: str | None = None

    async def login(self, username: str, password: str) -> None:
        """Login with Mi account credentials.

        Raises MiCloudTwoFactor when the account needs browser verification,
        MiCloudAuthError on wrong credentials.
        """
        payload = await self._login_step1()
        data = await self._login_step2(username, password, payload)

        if not data.get("location"):
            verify = data.get("notificationUrl")
            if verify:
                raise MiCloudTwoFactor(verify)
            raise MiCloudAuthError(
                data.get("desc") or f"login rejected (code {data.get('code')})"
            )

        token = await self._login_step3(data["location"])
        self.user_id = str(data["userId"])
        self.ssecurity = data["ssecurity"]
        self.service_token = token

    async def _login_step1(self) -> dict:
        r = await self.session.get(
            "https://account.xiaomi.com/pass/serviceLogin",
            cookies={"sdkVersion": "3.8.6", "deviceId": self.device_id},
            headers={"User-Agent": UA % self.device_id},
            params={"sid": "xiaomiio", "_json": "true"},
            timeout=ClientTimeout(total=15),
        )
        raw = await r.read()
        resp: dict = json.loads(raw[11:])
        return {k: v for k, v in resp.items() if k in ("sid", "qs", "callback", "_sign")}

    async def _login_step2(self, username: str, password: str, payload: dict) -> dict:
        payload["user"] = username
        payload["hash"] = hashlib.md5(password.encode()).hexdigest().upper()

        r = await self.session.post(
            "https://account.xiaomi.com/pass/serviceLoginAuth2",
            cookies={"sdkVersion": "3.8.6", "deviceId": self.device_id},
            data=payload,
            headers={"User-Agent": UA % self.device_id},
            params={"_json": "true"},
            timeout=ClientTimeout(total=15),
        )
        raw = await r.read()
        return json.loads(raw[11:])

    async def _login_step3(self, location: str) -> str:
        r = await self.session.get(location, headers={"User-Agent": UA})
        return r.cookies["serviceToken"].value

    async def get_devices(self, server: str = "cn") -> list[dict]:
        """Fetch the device list (did/name/model/localip/mac/token...)."""
        if not self.ssecurity:
            raise MiCloudError("not logged in")

        payload = {
            "getVirtualModel": True,
            "getHuamiDevices": 1,
            "get_split_device": False,
            "support_smart_home": True,
        }
        resp = await self._request(
            server, "/v2/home/device_list_page", payload
        )
        if resp is None:
            raise MiCloudError("device list request failed")
        return resp.get("list", [])

    async def _request(self, server: str, url: str, payload: dict):
        baseurl = (
            "https://api.io.mi.com/app"
            if server == "cn"
            else f"https://{server}.api.io.mi.com/app"
        )
        data = json.dumps(payload, separators=(",", ":"))

        nonce = gen_nonce()
        signed_nonce = gen_signed_nonce(self.ssecurity, nonce)

        params = {"data": data}
        params["rc4_hash__"] = gen_signature(url, signed_nonce, params)
        params = {k: encrypt_rc4(signed_nonce, v) for (k, v) in params.items()}
        params.update(
            {
                "signature": gen_signature(url, signed_nonce, params),
                "ssecurity": self.ssecurity,
                "_nonce": nonce,
            }
        )
        r = await self.session.post(
            baseurl + url,
            cookies={
                "userId": self.user_id,
                "serviceToken": self.service_token,
                "locale": "en_US",
            },
            headers={
                "Accept-Encoding": "identity",
                "User-Agent": UA,
                "x-xiaomi-protocal-flag-cli": "PROTOCAL-HTTP2",
                "MIOT-ENCRYPT-ALGORITHM": "ENCRYPT-RC4",
            },
            data=params,
            timeout=ClientTimeout(total=15),
        )
        resp = await r.text()
        resp = json.loads(decrypt_rc4(signed_nonce, resp))
        if resp.get("code") != 0:
            raise MiCloudError(f"API {url} error: {resp}")
        return resp["result"]


def get_random_string(length: int) -> str:
    seq = string.ascii_uppercase + string.digits
    return "".join(random.choice(seq) for _ in range(length))


def gen_nonce() -> str:
    """Time based nonce."""
    nonce = os.urandom(8) + int(time.time() / 60).to_bytes(4, "big")
    return base64.b64encode(nonce).decode()


def gen_signed_nonce(ssecret: str, nonce: str) -> str:
    """Nonce signed with ssecret."""
    m = hashlib.sha256()
    m.update(base64.b64decode(ssecret))
    m.update(base64.b64decode(nonce))
    return base64.b64encode(m.digest()).decode()


def gen_signature(url: str, signed_nonce: str, data: dict) -> str:
    """Request signature based on url, signed_nonce, nonce and data."""
    sign = "&".join(
        (["POST", url] + [f"{k}={v}" for k, v in data.items()] + [signed_nonce])
    )
    return base64.b64encode(hashlib.sha1(sign.encode()).digest()).decode()


class RC4:
    _idx = 0
    _jdx = 0
    _ksa: list

    def __init__(self, pwd):
        self.init_key(pwd)

    def init_key(self, pwd):
        cnt = len(pwd)
        ksa = list(range(256))
        j = 0
        for i in range(256):
            j = (j + ksa[i] + pwd[i % cnt]) & 255
            ksa[i], ksa[j] = ksa[j], ksa[i]
        self._ksa = ksa
        self._idx = 0
        self._jdx = 0
        return self

    def crypt(self, data):
        if isinstance(data, str):
            data = data.encode()
        ksa = self._ksa
        i = self._idx
        j = self._jdx
        out = []
        for byt in data:
            i = (i + 1) & 255
            j = (j + ksa[i]) & 255
            ksa[i], ksa[j] = ksa[j], ksa[i]
            out.append(byt ^ ksa[(ksa[i] + ksa[j]) & 255])
        self._idx = i
        self._jdx = j
        self._ksa = ksa
        return bytearray(out)

    def init1024(self):
        self.crypt(bytes(1024))
        return self


def encrypt_rc4(pwd, data):
    s = RC4(base64.b64decode(pwd.encode())).init1024().crypt(data.encode())
    return base64.b64encode(s).decode()


def decrypt_rc4(pwd, data):
    return RC4(base64.b64decode(pwd.encode())).init1024().crypt(base64.b64decode(data))
