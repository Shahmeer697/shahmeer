from types import NoneType
import typing
import twocaptcha
import httpx
from ._utility import Utility, MPrint, USER_AGENT

console = MPrint()


class Captcha:
    def __init__(self):
        self._client = httpx.AsyncClient()
        self._utils = Utility()
        self.api = self._utils.config["captcha"]["api"]
        self.key = self._utils.config["captcha"]["key"]

    def getBalance(self):
        if self.api == "2captcha.com":
            captcha = twocaptcha.TwoCaptcha(self.key)
            return captcha.balance()
        elif self.api == "anti-captcha.com" or self.api == "capmonster.cloud":
            resp = self._client.post(
                f"https://api.{self.api}/getBalance", json={"clientKey": self.key}
            ).json()
            if resp.get("errorId") > 0:
                console.f_print(
                    f"Error while getting captcha balance: {resp.get('errorDescription')}"
                )
                return 0.0
            return resp.get("balance")

    async def getCaptchaPrivate(
        self, captcha_data: dict, proxy: typing.Union[str, NoneType]
    ) -> str:
        try:
            resp = await self._client.post(
                f"http://localhost:3002/register-captcha",
                json={
                    "captcha_data": captcha_data,
                    "proxy": proxy,
                },
                timeout=1000,
            )
            if resp.status_code == 200:
                return resp.json()["response"], captcha_data
        except Exception as e:
            print(e)
            return await self.getCaptchaPrivate(captcha_data, proxy)

    async def getCaptcha(self, sitekey: str, rqdata: str, proxy: str):
        if self.api == "2captcha.com":
            captcha = twocaptcha.TwoCaptcha(self.key)
            return captcha.hcaptcha(
                sitekey,
                "https://discord.com",
                {"userAgent": USER_AGENT, "data": rqdata},
            )["code"]
        elif self.api == "anti-captcha.com" or self.api == "capmonster.cloud":
            taskId = await self._client.post(
                f"https://api.{self.api}/createTask",
                json={
                    "clientKey": self.key,
                    "task": {
                        "type": "HCaptchaTaskProxyless",
                        "websiteURL": "https://discord.com/",
                        "websiteKey": sitekey,
                        "userAgent": USER_AGENT,
                        "enterprisePayload": {"rqdata": rqdata, "sentry": True},
                    },
                },
                timeout=30,
            )
            taskId = taskId.json()
            if taskId.get("errorId") > 0:
                console.f_print(
                    f"Captcha(createTask) - {taskId.get('errorDescription')}"
                )
                return None
            taskId = taskId.get("taskId")
            solvedCaptcha = None
            while not solvedCaptcha:
                captchaData = await self._client.post(
                    f"https://api.{self.api}/getTaskResult",
                    json={"clientKey": self.key, "taskId": taskId},
                    timeout=30,
                )
                captchaData = captchaData.json()
                if captchaData["errorId"] > 0:
                    console.f_print(
                        f"Captcha(getTaskResult) - {captchaData['errorDescription']}"
                    )
                    return None
                if captchaData.get("status") == "ready":
                    solvedCaptcha = captchaData.get("solution").get(
                        "gRecaptchaResponse"
                    )
                    return solvedCaptcha
        elif self.api == "flanker.wtf":
            # to be realeased soon!
            return None
