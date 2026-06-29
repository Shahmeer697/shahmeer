"""
Copyright 2022 Shahzain Masood

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""

###

print("MultiTool is starting...\nGetting discord buildNumber")
from src import (
    MultiTool,
    MPrint,
    Utility,
    scrape,
    global_variables,
    _captcha,
    DiscordSocket,
    FpScrapper,
)
import json
import threading
import random
import emoji
import asyncio
import os
from update import lookforupdates
from traceback import format_exc
from typing import Union
from colorama import Fore, Style
from tasksio import TaskPool

# VARIABLES
console = MPrint()
goodtokens = []
in_server = []
seen = {}
duplicates = 0
notjoined = 0
lockedtokens = 0
invalidTokens = 0
stopEvent = threading.Event()

# --- Discord permission bits / channel types (used by Smart Raid) -----------
PERM_ADMINISTRATOR = 1 << 3  # 8     — bypasses every other permission
PERM_VIEW_CHANNEL = 1 << 10  # 1024  — must see the channel
PERM_SEND_MESSAGES = 1 << 11  # 2048  — must be able to post in it
# Channel types we can drop a message into: 0 text, 2 voice (text chat),
# 5 announcement, 13 stage (text chat), 15 forum.
MESSAGEABLE_TYPES = {0, 2, 5, 13, 15}


def _basePermissions(guild: dict, member: dict) -> int:
    """@everyone base permissions OR'd with the base permissions of every role the
    member has. The @everyone role id always equals the guild id."""
    guildId = guild["id"]
    rolePerms = {r["id"]: int(r.get("permissions", 0)) for r in guild.get("roles", [])}
    perms = rolePerms.get(guildId, 0)
    for rid in member.get("roles", []):
        perms |= rolePerms.get(rid, 0)
    return perms


def _channelPermissions(
    channel: dict, guild: dict, member: dict, basePerms: int
) -> int:
    """Apply a channel's overwrites to the base perms following Discord's order:
    @everyone overwrite -> union of role overwrites -> the member-specific overwrite."""
    guildId = guild["id"]
    memberId = member.get("user", {}).get("id")
    memberRoles = set(member.get("roles", []))
    perms = basePerms
    overwrites = {o["id"]: o for o in channel.get("permission_overwrites", [])}

    everyone = overwrites.get(guildId)
    if everyone:
        perms &= ~int(everyone.get("deny", 0))
        perms |= int(everyone.get("allow", 0))

    roleAllow = roleDeny = 0
    for rid in memberRoles:
        ow = overwrites.get(rid)
        if ow:
            roleAllow |= int(ow.get("allow", 0))
            roleDeny |= int(ow.get("deny", 0))
    perms &= ~roleDeny
    perms |= roleAllow

    if memberId and memberId in overwrites:
        ow = overwrites[memberId]
        perms &= ~int(ow.get("deny", 0))
        perms |= int(ow.get("allow", 0))

    return perms


def channelsTokenCanWrite(guild: dict, channels: list, member: dict) -> list:
    """Return the ids of every messageable channel this member can post in.
    Guild owner and any ADMINISTRATOR role bypass channel overwrites entirely."""
    memberId = member.get("user", {}).get("id")
    base = _basePermissions(guild, member)
    bypass = (memberId and memberId == guild.get("owner_id")) or bool(
        base & PERM_ADMINISTRATOR
    )

    writable = []
    for channel in channels:
        if channel.get("type") not in MESSAGEABLE_TYPES:
            continue
        if bypass:
            writable.append(channel["id"])
            continue
        perms = _channelPermissions(channel, guild, member, base)
        if perms & PERM_ADMINISTRATOR:
            writable.append(channel["id"])
        elif (perms & PERM_VIEW_CHANNEL) and (perms & PERM_SEND_MESSAGES):
            writable.append(channel["id"])
    return writable


async def smartRaidWorker(
    token: str,
    channels: list,
    contents: list,
    massMention: bool,
    massMentionSize,
    forceProxy: bool = False,
):
    """Spam one token across every channel it can write in, cycling channels and
    picking a random content each send, until ENTER is pressed (stopEvent)."""
    m = await buildMultiTool(token, forceProxy)
    if m is None:
        return None
    try:
        with open("scraped/massmention.txt") as fs:
            scrappedMembers = fs.readlines()
    except FileNotFoundError:
        scrappedMembers = []
    while not stopEvent.is_set():
        for channelId in channels:
            if stopEvent.is_set():
                break
            await m.sendMessageInChannel(
                random.choice(contents),
                channelId,
                massMention,
                massMentionSize,
                scrappedMembers,
            )


async def _reconToken(
    token: str, guildId: str, sem: asyncio.Semaphore, forceProxy: bool = False
):
    """Recon a single token: confirm it's in the guild, pull the channel list + our
    member object, and resolve which channels it can write in. Returns
    {"token", "channels"} or None (not in server / no writable channels / error).
    The semaphore bounds how many of these run at once so we don't exhaust sockets."""
    async with sem:
        m = await buildMultiTool(token, forceProxy)
        if m is None:
            return None
        guild = await m.getGuild(guildId)
        # getGuild only returns "name" when the token is actually in the server
        if not isinstance(guild, dict) or "name" not in guild:
            return None
        channels = await m.getGuildChannels(guildId)
        member = await m.getMember(guildId)
        if not isinstance(member, dict) or "roles" not in member:
            member = {"roles": []}
        channelsToFuck = channelsTokenCanWrite(guild, channels, member)
        if not channelsToFuck:
            console.f_print(
                f"{token} is in {guild['name']} but can't write in any channel, skipping"
            )
            return None
        console.s_print(
            f"{token} -> {len(channelsToFuck)} writable channel(s) in {guild['name']}"
        )
        return {"token": token, "channels": channelsToFuck}


async def smartRaid(tokens: list):
    """Smart Raid: figure out which tokens are actually in the guild, resolve which
    channels each one can write in (its own permission set), then raid every writable
    channel — voice text chats included — with one or many message contents."""
    console.s_print("Smart Raid...")
    guildId = input(
        f"[>] {Fore.GREEN}{Style.BRIGHT}Enter the guild Id: {Style.RESET_ALL}"
    ).strip()

    # Recon every (unique) token concurrently — bounded so thousands of tokens don't
    # open thousands of sockets at once.
    console.w_print("Scanning tokens for membership and per-channel write access...")
    uniqueTokens = list(dict.fromkeys(tokens))
    sem = asyncio.Semaphore(100)
    reconResults = await asyncio.gather(
        *[_reconToken(token, guildId, sem, forceProxy=True) for token in uniqueTokens],
        return_exceptions=True,
    )
    raiders = [r for r in reconResults if isinstance(r, dict)]

    if not raiders:
        console.f_print("No tokens are in that server with write permissions.")
        input("Press enter to return to menu")
        return

    console.s_print(f"{len(raiders)} token(s) ready to raid {guildId}")

    # --- message content: single or many (comma separated) -------------------
    multiple = (
        input(
            f"[>] {Fore.GREEN}{Style.BRIGHT}Do you want to use multiple message contents? (y/n) {Style.RESET_ALL}"
        ).lower()
        == "y"
    )
    if multiple:
        raw = input(
            f"[>] {Fore.GREEN}{Style.BRIGHT}Enter your contents separated by commas (i.e multitool is great, httpz is love, i hate you, etc...): {Style.RESET_ALL}"
        )
        contents = [c.strip() for c in raw.split(",") if c.strip()]
    else:
        contents = [
            input(
                f"[>] {Fore.GREEN}{Style.BRIGHT}Enter your message content: {Style.RESET_ALL}"
            )
        ]
    if not contents:
        console.f_print("No content provided.")
        input("Press enter to return to menu")
        return

    # --- mass mention (mirrors the normal Server Spammer) --------------------
    massMention = (
        input(
            f"{Fore.GREEN}{Style.BRIGHT}Do you want to use massmention? (y/n){Style.RESET_ALL}"
        ).lower()
        == "y"
    )
    massMentionSize = None
    if massMention:
        if (
            input(
                f"{Fore.GREEN}{Style.BRIGHT}Do you want a random massmention size? (y/n) {Style.RESET_ALL}"
            ).lower()
            == "y"
        ):
            minSize = int(
                input(
                    f"{Fore.GREEN}{Style.BRIGHT}Enter the minimum amount of people to mention: {Style.RESET_ALL}"
                )
            )
            maxSize = int(
                input(
                    f"{Fore.GREEN}{Style.BRIGHT}Enter the maximum amount of people to mention: {Style.RESET_ALL}"
                )
            )
            massMentionSize = (minSize, maxSize)
        else:
            massMentionSize = int(
                input(
                    f"{Fore.GREEN}{Style.BRIGHT}Enter the ammount of people you want to mention in one message: {Style.RESET_ALL}"
                )
            )
        if (
            input(
                f"{Fore.GREEN}{Style.BRIGHT}Do you want to use already scrapped members for massmention? (y/n) {Style.RESET_ALL}"
            ).lower()
            != "y"
        ):
            # scrape from any channel we can already see/write in
            scrapeChannel = random.choice(raiders[0]["channels"])
            await scrapeMassMention(
                raiders[0]["token"], guildId, scrapeChannel, forceProxy=True
            )

    await runTasksUntilEnter(
        [
            smartRaidWorker(
                r["token"],
                r["channels"],
                contents,
                massMention,
                massMentionSize,
                forceProxy=True,
            )
            for r in raiders
        ]
    )


# SYNC functions
def clearConsole():
    return os.system("cls" if os.name in ("nt", "dos") else "clear")


def showMenu():
    print(f"{Style.BRIGHT}{Fore.BLUE}1: Token Tools {Style.RESET_ALL}")
    print(f"{Style.BRIGHT}{Fore.BLUE}2: Server Joiner {Style.RESET_ALL}")
    print(f"{Style.BRIGHT}{Fore.BLUE}3: Scraping Menu {Style.RESET_ALL}")
    print(f"{Style.BRIGHT}{Fore.BLUE}4: Mass DM Menu {Style.RESET_ALL}")
    print(f"{Style.BRIGHT}{Fore.BLUE}5: Profile Changer {Style.RESET_ALL}")
    print(f"{Style.BRIGHT}{Fore.BLUE}6: Raiding Menu {Style.RESET_ALL}")
    print(f"{Style.BRIGHT}{Fore.BLUE}7: Adder Menu {Style.RESET_ALL}")
    print(f"{Style.BRIGHT}{Fore.RED}0: Exit {Style.RESET_ALL}")


def showSubMenu(title: str, options: list):
    """Render a category submenu: a heading, its numbered options and a 0 Back row."""
    print(f"\n{Style.BRIGHT}{Fore.CYAN}=== {title} ==={Style.RESET_ALL}")
    for key, label in options:
        print(f"{Style.BRIGHT}{Fore.BLUE}{key}: {label} {Style.RESET_ALL}")
    print(f"{Style.BRIGHT}{Fore.RED}0: Back {Style.RESET_ALL}")


def changeFormat(token: str):
    if ":" not in token or len(token.split(":")) == 2:
        token = token if ":" not in token else token.split(":")[1]
        console.f_print(f"{token} format is not [Email:Pass:Token]")
        return token
    newToken = token.split(":")[2]
    console.s_print(f"{token} -> {newToken}")
    return newToken


def setTitle(tokens: list):
    return os.system(
        f'title Discord MultiTool - Tokens: {len(tokens)} - Proxies: {len(open("input/proxies.txt").read().splitlines())} - By Shahzain'
        if os.name == "nt"
        else f'echo -n -e "\033]0;Discord MultiTool | Tokens {len(tokens)} | Proxies {len(open("input/proxies.txt").read().splitlines())} | Captcha Balance: $ {_captcha.Captcha().getBalance()} - By Shahzain\007"'
    )


# ASYNC FUNCTIONS
async def scrapeMassMention(token, guildId, channelId, forceProxy: bool = False):
    o = await buildMultiTool(token, forceProxy)
    res = await o.getGuild(guildId)
    if "name" not in res:
        return await scrapeMassMention(
            random.choice(open("input/tokens.txt").read().splitlines()),
            guildId,
            channelId,
            forceProxy,
        )
    open("scraped/massmention.txt", "w").write("")
    console.s_print(f"Scraping in {guildId} with {token}")
    members = scrape(token, guildId, channelId)
    for member in members:
        console.s_print(f"Scraped {member}")
        open("scraped/massmention.txt", "a").write(member + "\n")
    console.s_print(f"Total Scrapped: {len(members)}")
    return True


async def runTasksUntilEnter(coros: list):
    """Run worker coroutines concurrently until the user presses ENTER.

    The blocking input() is run in a thread so the workers keep flowing on the event
    loop while we wait. As soon as ENTER is pressed we flip stopEvent (for thread
    based workers) and cancel every task, then return so the caller can go back to
    the menu — no more pools left running in the background."""
    coros = [c for c in coros if c is not None]
    if not coros:
        return
    stopEvent.clear()
    tasks = [asyncio.create_task(c) for c in coros]
    console.w_print(
        "Tasks are running. Press ENTER to stop them and return to the menu."
    )
    await asyncio.to_thread(input)
    stopEvent.set()
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    console.s_print("All tasks stopped. Returning to menu...")


async def vcSpammer(token: str, guild: str, channelId: str):
    """Keeps a token sitting in the voice channel: join, let the short-lived gateway
    session drop, then rejoin — looping until stopEvent is set (user pressed ENTER)."""
    while not stopEvent.is_set():
        try:
            await asyncio.to_thread(DiscordSocket(token).run, channelId, guild)
            console.s_print(f"Joined vc: {token}")
        except Exception as e:
            console.f_print(f"{token} failed to join vc: {e}")
        await asyncio.sleep(5)


async def usernameChanger(token: str, username: str):
    if ":" not in token:
        console.f_print(f"{token} is not [Email:Pass:Token]")
        return None
    spllited = token.split(":")
    password = spllited[1]
    token = spllited[2]
    m = await buildMultiTool(token)
    await m.usernameChange(username, password)


async def bioChanger(token: str, bio: str):
    m = await buildMultiTool(token)
    await m.bioChange(bio)


async def globalNameChanger(token: str, globalName: str):
    m = await buildMultiTool(token)
    if m is None:
        return None
    await m.globalNameChange(globalName)


def readAvatarFile(path: str) -> list:
    try:
        return [
            line
            for line in open(path, encoding="utf-8").read().splitlines()
            if line.strip()
        ]
    except FileNotFoundError:
        return []


def loadAvatars() -> Union[list, None]:
    """Asks the user where to take avatars from (scraped/input), falling back to
    the other file when the chosen one is empty. Returns a list of avatar urls,
    or None if both files are empty."""
    source = (
        input(
            f"{Fore.GREEN}{Style.BRIGHT}Where do you want to take avatars from? (scraped/input) {Style.RESET_ALL}"
        )
        .lower()
        .strip()
    )
    if source == "input":
        primary, fallback = "input/avatars.txt", "scraped/avatars.txt"
    else:
        primary, fallback = "scraped/avatars.txt", "input/avatars.txt"
    avatars = readAvatarFile(primary)
    if avatars:
        return avatars
    console.w_print(f"{primary} is empty, taking avatars from {fallback} instead...")
    avatars = readAvatarFile(fallback)
    if avatars:
        return avatars
    console.f_print(
        "Both avatar files are empty. Add avatar URLs to input/avatars.txt or scrape avatars first."
    )
    return None


async def avatarChanger(token: str, avatarUrl: str):
    m = await buildMultiTool(token)
    if m is None:
        return None
    await m.avatarChange(avatarUrl)


async def scrapeMembers(token, guildId, channelId, emptyFirst=True):
    o = await buildMultiTool(token)
    res = await o.getGuild(guildId)
    if "name" not in res:
        return await scrapeMembers(
            random.choice(open("input/tokens.txt").read().splitlines()),
            guildId,
            channelId,
            emptyFirst,
        )
    if emptyFirst:
        open("scraped/members.txt", "w", encoding="utf-8").write("")
    console.s_print(f"Scraping in {guildId} with {token}")
    members = scrape(token, guildId, channelId)
    with open("scraped/members.txt", "a", encoding="utf-8") as f:
        for member in members:
            console.s_print(f"Scraped {member}")
            f.write(member + "\n")
    console.s_print(f"Total Scrapped: {len(members)}")
    return True


async def scrapeGlobalNames(token, guildId, channelId, emptyFirst=True):
    o = await buildMultiTool(token)
    res = await o.getGuild(guildId)
    if "name" not in res:
        return await scrapeGlobalNames(
            random.choice(open("input/tokens.txt").read().splitlines()),
            guildId,
            channelId,
            emptyFirst,
        )
    if emptyFirst:
        open("scraped/globalnames.txt", "w", encoding="utf-8").write("")
    console.s_print(f"Scraping global names in {guildId} with {token}")
    members = scrape(token, guildId, channelId, "global_name")
    with open("scraped/globalnames.txt", "a", encoding="utf-8") as f:
        for member in members:
            try:
                console.s_print(f"Scraped {member}")
            except UnicodeEncodeError:
                console.s_print(f"Scraped {member.encode('ascii', 'replace').decode()}")
            f.write(member + "\n")
    console.s_print(f"Total Scrapped: {len(members)}")
    return True


async def scrapeAvatars(token, guildId, channelId, emptyFirst=True):
    o = await buildMultiTool(token)
    res = await o.getGuild(guildId)
    if "name" not in res:
        return await scrapeAvatars(
            random.choice(open("input/tokens.txt").read().splitlines()),
            guildId,
            channelId,
            emptyFirst,
        )
    if emptyFirst:
        open("scraped/avatars.txt", "w", encoding="utf-8").write("")
    console.s_print(f"Scraping avatars in {guildId} with {token}")
    members = scrape(token, guildId, channelId, "avatar")
    with open("scraped/avatars.txt", "a", encoding="utf-8") as f:
        for member in members:
            console.s_print(f"Scraped {member}")
            f.write(member + "\n")
    console.s_print(f"Total Scrapped: {len(members)}")
    return True


async def leave(token: str, guildId: str):
    o = await buildMultiTool(token)
    await o.leave(guildId)


def formatEmojiName(emojiObj: dict) -> str:
    """Human-readable label for a reaction's emoji: <:name:id> for custom emojis,
    the raw character for unicode emojis."""
    if emojiObj.get("id"):
        return f"<:{emojiObj['name']}:{emojiObj['id']}>"
    return emojiObj["name"]


async def reactionSpammer(
    token: str,
    channelId: str,
    messageId: str,
    emojiObj: dict,
    useDelay: bool,
    delayConfig: Union[dict, None],
):
    m = await buildMultiTool(token)
    if useDelay:
        if delayConfig["random"]:
            await asyncio.sleep(random.uniform(delayConfig["min"], delayConfig["max"]))
        else:
            await asyncio.sleep(delayConfig["fixed"])
    await m.addReactionByEmoji(messageId, channelId, emojiObj)


async def buildMultiTool(token: str, forceProxy: bool = False) -> MultiTool:
    try:
        m = MultiTool()
        await m._init(token, forceProxy)
        return m
    except Exception as e:
        console.f_print(f"Error while building Multitool Coroutine: {e}")
        return await buildMultiTool(token, forceProxy)


async def checkInServer(token: str, guildId: str):
    m = await buildMultiTool(token)
    if await m.checkServer(guildId):
        in_server.append(token)


async def sendMessage(
    token: str,
    channelId: str,
    message: str,
    massMention: bool,
    massMentionSize: int,
    forceProxy: bool = False,
):
    m = await buildMultiTool(token, forceProxy)
    with open("scraped/massmention.txt") as fs:
        scrappedMembers = fs.readlines()
    while True:
        await m.sendMessageInChannel(
            message, channelId, massMention, massMentionSize, scrappedMembers
        )


async def friendRequest(token: str, username: str, discrim: str):
    m = await buildMultiTool(token)
    await m.sendFriendRequest(username, discrim)


async def spamMessages(token: str, userId: str, message: str):
    m = await buildMultiTool(token)
    if not m:
        return None
    while True:
        _, _res = await m.sendDirectMessage(userId, message)
        if _:
            console.s_print(f"{token} successfully sent dm to {userId}")
        else:
            console.f_print(f"{token} failed to send dm to {userId}")


async def sendDm(token: str, userId: str, message: str):
    m = await buildMultiTool(token)
    _, _res = await m.sendDirectMessage(userId, message)
    if "You are opening direct messages too fast" in _res.text:
        global_variables.qurantined_tokens.append(token)
        console.f_print(f"{token} got ratelimited. sleeping for 10 minutes.")
        threading.Thread(target=global_variables.removeFromQurantine, args=(token,))
    elif "Cannot send messages to this user" in _res.text:
        global_variables.blaclisted_users.append(userId)
    elif (
        "You need to verify your account in order to perform this action" in _res.text
        or "401: Unauthorized" in _res.text
    ):
        global_variables.locked_tokens.append(token)
        global_variables.qurantined_tokens.append(token)
        console.f_print(f"{token} token got locked during mass dm")
    elif _:
        console.s_print(f"{token} successfully sent dm to {userId}")


async def checkToken(token: str):
    global lockedtokens
    global invalidTokens
    m = await buildMultiTool(token)
    if m == None:
        return None
    res, typee = await m.checkToken()
    if typee == "LOCKED":
        lockedtokens += 1
        return False
    if typee == "INVALID":
        invalidTokens += 1
    if res:
        goodtokens.append(token)
        return True


async def join(
    token: str,
    rawInvite: str,
    ctx: str,
    guildId: str,
    channelId: Union[str, None] = None,
    messageId: Union[str, None] = None,
):
    global notjoined
    m = await buildMultiTool(token)
    if m == None:
        return None
    res, req = await m.join(rawInvite, ctx)
    if not res:
        notjoined += 1
        return res
    if (
        Utility().config["joiner"]["bypassMembershipScreening"]
        and "show_verification_form" in req.json()
    ):
        await m.bypassScreening(guildId, rawInvite)
    if Utility().config["joiner"].get("bypassOnboarding"):
        await m.bypassOnboarding(guildId)
    if Utility().config["joiner"].get("bypassDoubleCounter"):
        await m.bypassDoubleCounter()
    if Utility().config["joiner"].get("bypassButtonAndEmojiVerification"):
        await m.buttonAndEmojiVerification(guildId)
    return res


async def runAction(choice: int, tokens: list):
    """Execute a single action by its (legacy) number. The menu hierarchy maps every
    submenu selection to one of these numbers, so the action bodies stay untouched."""
    global duplicates
    global notjoined
    global lockedtokens
    global invalidTokens
    try:
        if choice == 1:
            console.s_print(f"Checking tokens...")
            async with TaskPool(10_000) as pool:
                for token in tokens:
                    if token in seen:
                        duplicates += 1
                        continue
                    seen[token] = True
                    await pool.put(checkToken(token))
            console.s_print(
                f"All tokens checked.\nDuplicates: {duplicates} | Valid: {len(goodtokens)} | Invalid: {invalidTokens} | Locked Tokens: {lockedtokens} | Total Bad Tokens(includes locked+invalid tokens): {invalidTokens + lockedtokens}"
            )
            seen.clear()
            duplicates = 0
            lockedtokens = 0
            invalidTokens = 0
            if Utility().config["removeDeadTokens"]:
                open("input/tokens.txt", "w").write("")
                for goodtoken in goodtokens:
                    open("input/tokens.txt", "a").write(f"{goodtoken}\n")
            goodtokens.clear()
            return
        if choice == 2:
            console.s_print(f"Server Joiner...")
            rawInvite = input(
                f"[>] {Fore.GREEN}{Style.BRIGHT}Enter your invite: {Style.RESET_ALL}"
            ).split("discord.gg/")[1]
            try:
                req1 = Utility().getInviteInfo(rawInvite)
                if req1 == {"message": "Unknown Invite", "code": 10006}:
                    console.f_print(f"https://discord.gg/{rawInvite} is INVALID")
                    return
            except:
                console.f_print(
                    "Failed to get invite info, You are probably ratelimited, try using a VPN"
                )
                req1 = {"guild": {"id": None}, "channel": {"id": None}}
                if Utility().config.get("proxy")[
                    "proxyless"
                ]:  # if proxyless is true, redirect back to `menu` otherwise keep joining
                    return
            console.s_print(f"https://discord.gg/{rawInvite} is VALID")
            ctx = Utility().getContextProperties(
                req1["channel"]["id"], req1["guild"]["id"]
            )
            deley = Utility().config["joiner"]["delay"]
            useDelay = Utility().config["joiner"]["useDelays"]
            randomDelay = False
            minDelay = maxDelay = 0
            if useDelay:
                if (
                    input(
                        f"[>] {Fore.GREEN}{Style.BRIGHT}Do you want to use a random delay? (y/n) {Style.RESET_ALL}"
                    ).lower()
                    == "y"
                ):
                    randomDelay = True
                    minDelay = int(
                        input(
                            f"[>] {Fore.GREEN}{Style.BRIGHT}Enter the minimum delay (seconds): {Style.RESET_ALL}"
                        )
                    )
                    maxDelay = int(
                        input(
                            f"[>] {Fore.GREEN}{Style.BRIGHT}Enter the maximum delay (seconds): {Style.RESET_ALL}"
                        )
                    )
            channelId = None
            messageId = None
            # join on a single thread (sequentially) so the delays are respected per token
            for token in tokens:
                if token in seen:
                    duplicates += 1
                    continue
                seen[token] = True
                if useDelay:
                    await join(
                        token, rawInvite, ctx, req1["guild"]["id"], channelId, messageId
                    )
                    await asyncio.sleep(
                        random.randint(minDelay, maxDelay) if randomDelay else deley
                    )
                else:
                    await pool.put(
                        join(
                            token,
                            rawInvite,
                            ctx,
                            req1["guild"]["id"],
                            channelId,
                            messageId,
                        )
                    )

            console.s_print(
                f"Tokens successfully joined https://discord.gg/{rawInvite} \nDuplicate Tokens: {duplicates} | Joined Tokens: {len(tokens) - notjoined} | Not Joined: {notjoined}"
            )
            seen.clear()
            duplicates = 0
            return
        if choice == 3:
            console.s_print(f"Server spammer...")
            massMention = (
                True
                if input(
                    f"{Fore.GREEN}{Style.BRIGHT}Do you want to use massmention? (y/n){Style.RESET_ALL}"
                ).lower()
                == "y"
                else None
            )
            massMentionSize = None
            if massMention:
                if (
                    input(
                        f"{Fore.GREEN}{Style.BRIGHT}Do you want a random massmention size? (y/n) {Style.RESET_ALL}"
                    ).lower()
                    == "y"
                ):
                    minSize = int(
                        input(
                            f"{Fore.GREEN}{Style.BRIGHT}Enter the minimum amount of people to mention: {Style.RESET_ALL}"
                        )
                    )
                    maxSize = int(
                        input(
                            f"{Fore.GREEN}{Style.BRIGHT}Enter the maximum amount of people to mention: {Style.RESET_ALL}"
                        )
                    )
                    massMentionSize = (minSize, maxSize)
                else:
                    massMentionSize = int(
                        input(
                            f"{Fore.GREEN}{Style.BRIGHT}Enter the ammount of people you want to mention in one message: {Style.RESET_ALL}"
                        )
                    )
            message = input(
                f"{Fore.GREEN}{Style.BRIGHT}Please type the message: {Style.RESET_ALL}"
            )
            channelId = input(
                f"{Fore.GREEN}{Style.BRIGHT}Enter the channel Id you want to spam: {Style.RESET_ALL}"
            )
            m = await buildMultiTool(random.choice(tokens), forceProxy=True)
            guildId = await m.getChannel(channelId)

            if (
                massMention
                and input(
                    f"{Fore.GREEN}{Style.BRIGHT}Do you want to use already scrapped members for massmention? (y/n) {Style.RESET_ALL}"
                ).lower()
                != "y"
            ):
                await scrapeMassMention(
                    random.choice(tokens), guildId, channelId, forceProxy=True
                )
            await runTasksUntilEnter(
                [
                    sendMessage(
                        token,
                        channelId,
                        message,
                        massMention,
                        massMentionSize,
                        forceProxy=True,
                    )
                    for token in tokens
                ]
            )
            return
        if choice == 4:
            console.s_print(f"Server leaver...")
            guildId = input(
                f"{Fore.GREEN}{Style.BRIGHT}Enter the server Id you want to leave: {Style.RESET_ALL}"
            )
            async with TaskPool(10_000) as pool:
                for token in tokens:
                    await pool.put(leave(token, guildId))
            return
        if choice == 5:
            console.s_print(f"Format changer...")
            open("input/tokens.txt", "w").write("")
            for token in tokens:
                token = changeFormat(token)
                open("input/tokens.txt", "a").write(token + "\n")
            return
        if choice == 6:
            console.s_print(f"Single DM Spammer...")
            message = input(
                f"{Fore.GREEN}{Style.BRIGHT}Enter your message: {Style.RESET_ALL}"
            )
            userId = input(
                f"{Fore.GREEN}{Style.BRIGHT}Enter the vitim's userId: {Style.RESET_ALL}"
            )
            await runTasksUntilEnter(
                [spamMessages(token, userId, message) for token in tokens]
            )
            return
        if choice == 7:
            console.f_print(
                f"Hey Multitool user. We are sorry but mass dm is currently disabled"
            )
            return
            console.s_print(f"Mass DM...")
            members = open("scraped/members.txt").read().splitlines()
            if len(members) == 0:
                channelId = input(
                    f"{Fore.GREEN}{Style.BRIGHT}Enter the channel Id you want to spam: {Style.RESET_ALL}"
                )
                m = await buildMultiTool(random.choice(tokens))
                guildId = await m.getChannel(channelId)
                await scrapeMembers(random.choice(tokens), guildId, channelId)
                members = open("scraped/members.txt").read().splitlines()
            msg: str = json.loads(open("messages.json").read())["content"]
            async with TaskPool(10_000) as pool:
                for member in members:
                    variableReplaced = msg.replace("<@user>", f"<@{member}>")
                    await pool.put(
                        sendDm(
                            global_variables.getGoodToken(), member, variableReplaced
                        )
                    )
            return
        if choice == 8:
            console.s_print(f"Username changer...")
            usernames = open("input/usernames.txt").read().splitlines()
            if len(usernames) == 0:
                console.f_print(
                    f"Please input some usernames before using this feature"
                )
                input("Press enter to return to menu")
                return
            async with TaskPool(10_000) as pool:
                for token in tokens:
                    await pool.put(usernameChanger(token, random.choice(usernames)))
            return
        if choice == 9:
            console.s_print(f"Bio changer...")
            bios = open("input/bios.txt").read().splitlines()
            if len(usernames) == 0:
                console.f_print(f"Please input some bios before using this feature")
                input("Press enter to return to menu")
                return
            async with TaskPool(10_000) as pool:
                for token in tokens:
                    await pool.put(bioChanger(token, random.choice(bios)))
            return
        if choice == 10:
            console.s_print(f"Friend adder...")
            spllited = input(
                f"{Fore.GREEN}{Style.BRIGHT}Enter your username and tag: {Style.RESET_ALL}"
            ).split("#")
            username = spllited[0]
            discrim = spllited[1]
            await runTasksUntilEnter(
                [friendRequest(token, username, discrim) for token in tokens]
            )
            return
        if choice == 11:
            console.s_print("Member scrapper...")
            channelId = input(
                f"{Fore.GREEN}{Style.BRIGHT}Enter your channelId you want to scrape: {Style.RESET_ALL}"
            )
            emptyFirst = (
                input(
                    f"{Fore.GREEN}{Style.BRIGHT}Do you want to empty the file before scrapping? (y/n) {Style.RESET_ALL}"
                ).lower()
                == "y"
            )
            m = await buildMultiTool(random.choice(tokens))
            guildId = await m.getChannel(channelId)
            await scrapeMembers(random.choice(tokens), guildId, channelId, emptyFirst)
            return
        if choice == 12:
            console.s_print("VC Spammer...")
            channelId = input(
                f"{Fore.GREEN}{Style.BRIGHT}Enter your Voice channelId you want to spam: {Style.RESET_ALL}"
            )
            m = await buildMultiTool(
                random.choice(tokens)
            )  # build the multitool coroutine
            guildId = await m.getChannel(channelId=channelId)
            coros = []
            for token in tokens:
                if token in seen:
                    continue
                seen[token] = True
                coros.append(vcSpammer(token, guildId, channelId))
            await runTasksUntilEnter(coros)
            seen.clear()
            return
        if choice == 13:
            console.s_print("Reaction adder...")
            guildId = input(
                f"{Fore.GREEN}{Style.BRIGHT}Enter the guild Id: {Style.RESET_ALL}"
            )
            channelId = input(
                f"{Fore.GREEN}{Style.BRIGHT}Enter the channel Id: {Style.RESET_ALL}"
            )
            messageId = input(
                f"{Fore.GREEN}{Style.BRIGHT}Enter the message Id: {Style.RESET_ALL}"
            )
            m = await buildMultiTool(random.choice(tokens))
            reactions = await m.getAllReactions(messageId, channelId)
            if not reactions:
                console.f_print("No reactions found on that message.")
                input("Press enter to return to menu")
                return
            console.s_print("Reactions on this message:")
            for index, reaction in enumerate(reactions):
                print(
                    f"{Fore.GREEN}{Style.BRIGHT}{index}: {formatEmojiName(reaction['emoji'])} (count: {reaction.get('count', '?')}){Style.RESET_ALL}"
                )
            selected = int(
                input(
                    f"{Fore.GREEN}{Style.BRIGHT}Select the reaction you want to spam (0, 1, 2 ...): {Style.RESET_ALL}"
                )
            )
            if selected < 0 or selected >= len(reactions):
                console.f_print("Invalid reaction selection.")
                input("Press enter to return to menu")
                return
            emojiObj = reactions[selected]["emoji"]
            useDelay = (
                input(
                    f"{Fore.GREEN}{Style.BRIGHT}Do you want to use delays? (y/n) {Style.RESET_ALL}"
                ).lower()
                == "y"
            )
            delayConfig = None
            if useDelay:
                if (
                    input(
                        f"{Fore.GREEN}{Style.BRIGHT}Do you want to use a random delay? (y/n) {Style.RESET_ALL}"
                    ).lower()
                    == "y"
                ):
                    minDelay = float(
                        input(
                            f"{Fore.GREEN}{Style.BRIGHT}Enter the minimum delay (seconds): {Style.RESET_ALL}"
                        )
                    )
                    maxDelay = float(
                        input(
                            f"{Fore.GREEN}{Style.BRIGHT}Enter the maximum delay (seconds): {Style.RESET_ALL}"
                        )
                    )
                    delayConfig = {"random": True, "min": minDelay, "max": maxDelay}
                else:
                    fixedDelay = float(
                        input(
                            f"{Fore.GREEN}{Style.BRIGHT}Enter the fixed delay (seconds): {Style.RESET_ALL}"
                        )
                    )
                    delayConfig = {"random": False, "fixed": fixedDelay}
            async with TaskPool(10_000) as pool:
                for token in tokens:
                    await pool.put(
                        reactionSpammer(
                            token, channelId, messageId, emojiObj, useDelay, delayConfig
                        )
                    )
            return
        if choice == 14:
            console.s_print("Global name scrapper...")
            channelId = input(
                f"{Fore.GREEN}{Style.BRIGHT}Enter your channelId you want to scrape: {Style.RESET_ALL}"
            )
            emptyFirst = (
                input(
                    f"{Fore.GREEN}{Style.BRIGHT}Do you want to empty the file before scrapping? (y/n) {Style.RESET_ALL}"
                ).lower()
                == "y"
            )
            m = await buildMultiTool(random.choice(tokens))
            guildId = await m.getChannel(channelId)
            await scrapeGlobalNames(
                random.choice(tokens), guildId, channelId, emptyFirst
            )
            return
        if choice == 15:
            console.s_print("Avatar scrapper...")
            channelId = input(
                f"{Fore.GREEN}{Style.BRIGHT}Enter your channelId you want to scrape: {Style.RESET_ALL}"
            )
            emptyFirst = (
                input(
                    f"{Fore.GREEN}{Style.BRIGHT}Do you want to empty the file before scrapping? (y/n) {Style.RESET_ALL}"
                ).lower()
                == "y"
            )
            m = await buildMultiTool(random.choice(tokens))
            guildId = await m.getChannel(channelId)
            await scrapeAvatars(random.choice(tokens), guildId, channelId, emptyFirst)
            return
        if choice == 16:
            console.s_print("Avatar adder...")
            avatars = loadAvatars()
            if not avatars:
                input("Press enter to return to menu")
                return
            async with TaskPool(10_000) as pool:
                for token in tokens:
                    await pool.put(avatarChanger(token, random.choice(avatars)))
            return
        if choice == 17:
            console.s_print("Fp scrapper...")
            scrapper = FpScrapper()
            try:
                await scrapper.generate_fps()
            except KeyboardInterrupt:
                scrapper._stop.set()
                console.w_print("Stopping fingerprint generator...")
            return
        if choice == 18:
            console.s_print("Check if token is in a server...")
            guildId = input(
                f"[>] {Fore.GREEN}{Style.BRIGHT}Enter the guild Id: {Style.RESET_ALL}"
            )
            async with TaskPool(10_000) as pool:
                for token in tokens:
                    await pool.put(checkInServer(token, guildId))
            console.s_print(f"{len(in_server)} token(s) are in {guildId}")
            if (
                in_server
                and input(
                    f"[>] {Fore.GREEN}{Style.BRIGHT}Do you want to separate the tokens that are in the server? (y/n) {Style.RESET_ALL}"
                ).lower()
                == "y"
            ):
                with open(
                    f"input/tokens_in_server_{guildId}.txt", "a", encoding="utf-8"
                ) as f:
                    for token in in_server:
                        f.write(f"{token}\n")
                console.s_print(
                    f"Saved {len(in_server)} token(s) to input/tokens_in_server_{guildId}.txt"
                )
            in_server.clear()
            return
        if choice == 19:
            console.s_print("Change global name...")
            oneForAll = (
                input(
                    f"[>] {Fore.GREEN}{Style.BRIGHT}Do you want to use one global name for all tokens? (y/n) {Style.RESET_ALL}"
                ).lower()
                == "y"
            )
            globalNames = None
            if oneForAll:
                staticName = input(
                    f"[>] {Fore.GREEN}{Style.BRIGHT}Enter the global name: {Style.RESET_ALL}"
                )
            else:
                source = (
                    input(
                        f"[>] {Fore.GREEN}{Style.BRIGHT}Where do you want to take global names from? (scraped/input) {Style.RESET_ALL}"
                    )
                    .lower()
                    .strip()
                )
                path = (
                    "input/globalnames.txt"
                    if source == "input"
                    else "scraped/globalnames.txt"
                )
                globalNames = readAvatarFile(path)
                if not globalNames:
                    console.f_print(
                        f"{path} is empty. Add global names or scrape them first."
                    )
                    input("Press enter to return to menu")
                    return
            async with TaskPool(10_000) as pool:
                for token in tokens:
                    name = staticName if oneForAll else random.choice(globalNames)
                    await pool.put(globalNameChanger(token, name))
            return
        if choice == 21:
            await smartRaid(tokens)
            return
    except Exception as e:
        console.f_print(e)
        if Utility().config["traceback"]:
            print(format_exc())


async def _runSubMenu(title: str, options: list):
    """Loop a category submenu until the user picks 0 (Back).

    `options` is a list of (key, label, actionNumber). The key is what the user types,
    the label is shown, and the actionNumber routes into runAction() — so all the real
    work still lives in the original action bodies."""
    while True:
        tokens = open("input/tokens.txt").read().splitlines()
        setTitle(tokens)
        showSubMenu(title, [(key, label) for key, label, _ in options])
        choice = input(
            f"\n[>] {Fore.GREEN}{Style.BRIGHT}Enter your choice \n>> {Style.RESET_ALL}"
        ).strip()
        if choice == "0":
            return
        action = next((num for key, _, num in options if key == choice), None)
        if action is None:
            console.f_print("Invalid Choice")
            continue
        await runAction(action, tokens)


async def tokenToolsMenu():
    await _runSubMenu(
        "Token Tools",
        [
            ("1", "Check Tokens", 1),
            ("2", "Format changer: [Email:Pass:Token] -> [Token]", 5),
            ("3", "Check if token is in a server", 18),
        ],
    )


async def scrapingMenu():
    await _runSubMenu(
        "Scraping Menu",
        [
            ("1", "Member scrapper", 11),
            ("2", "Global name scrapper", 14),
            ("3", "Avatar scrapper", 15),
            ("4", "Fp scrapper", 17),
        ],
    )


async def massDmMenu():
    await _runSubMenu(
        "Mass DM Menu",
        [
            ("1", "Mass DM", 7),
            ("2", "Single DM Spam", 6),
        ],
    )


async def profileMenu():
    await _runSubMenu(
        "Profile Changer",
        [
            ("1", "Change global name", 19),
            ("2", "Username Changer [Email:Pass:Token]", 8),
            ("3", "Bio Changer", 9),
            ("4", "Avatar adder", 16),
        ],
    )


async def raidingMenu():
    await _runSubMenu(
        "Raiding Menu",
        [
            ("1", "Server Spammer", 3),
            ("2", "VC spammer", 12),
            ("3", "Server Leaver", 4),
            ("4", "Smart Raid", 21),
        ],
    )


async def adderMenu():
    await _runSubMenu(
        "Adder Menu",
        [
            ("1", "Reaction adder", 13),
            ("2", "Friend adder", 10),
        ],
    )


async def menu():
    """Top-level menu: route to a category submenu, or run the joiner directly."""
    while True:
        tokens = open("input/tokens.txt").read().splitlines()
        setTitle(tokens)
        print("")
        showMenu()
        print("\n")
        choice = input(
            f"[>] {Fore.GREEN}{Style.BRIGHT}Enter your choice \n>> {Style.RESET_ALL}"
        ).strip()
        if choice == "1":
            await tokenToolsMenu()
        elif choice == "2":
            await runAction(2, open("input/tokens.txt").read().splitlines())
        elif choice == "3":
            await scrapingMenu()
        elif choice == "4":
            await massDmMenu()
        elif choice == "5":
            await profileMenu()
        elif choice == "6":
            await raidingMenu()
        elif choice == "7":
            await adderMenu()
        elif choice == "0":
            exit()
        else:
            console.f_print("Invalid Choice")


if __name__ == "__main__":
    clearConsole()
    print(Fore.BLUE + Style.BRIGHT + """
██████╗ ██╗███████╗ ██████╗ ██████╗ ██████╗ ██████╗     ███╗   ███╗██╗   ██╗██╗     ████████╗██╗████████╗ ██████╗  ██████╗ ██╗     
██╔══██╗██║██╔════╝██╔════╝██╔═══██╗██╔══██╗██╔══██╗    ████╗ ████║██║   ██║██║     ╚══██╔══╝██║╚══██╔══╝██╔═══██╗██╔═══██╗██║     
██║  ██║██║███████╗██║     ██║   ██║██████╔╝██║  ██║    ██╔████╔██║██║   ██║██║        ██║   ██║   ██║   ██║   ██║██║   ██║██║     
██║  ██║██║╚════██║██║     ██║   ██║██╔══██╗██║  ██║    ██║╚██╔╝██║██║   ██║██║        ██║   ██║   ██║   ██║   ██║██║   ██║██║     
██████╔╝██║███████║╚██████╗╚██████╔╝██║  ██║██████╔╝    ██║ ╚═╝ ██║╚██████╔╝███████╗   ██║   ██║   ██║   ╚██████╔╝╚██████╔╝███████╗
╚═════╝ ╚═╝╚══════╝ ╚═════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝     ╚═╝     ╚═╝ ╚═════╝ ╚══════╝   ╚═╝   ╚═╝   ╚═╝    ╚═════╝  ╚═════╝ ╚══════╝
                                                                                                                        P Y T H O N
""" + Style.RESET_ALL)
    print(f"{Style.BRIGHT}By Shahzain\n\n")
    if len(open("input/tokens.txt").read().splitlines()) == 0:
        console.f_print("Input some tokens before restarting...")
        input("Press Enter To Exit\n")
        exit()
    console.w_print("Mass DM is disabled")
    console.w_print(
        "Before using any feature, please check your tokens, To avoid errors."
    )
    if Utility().config["proxy"]["proxyless"]:
        console.w_print("Proxyless is on. Switch to proxies for best performance")
    asyncio.run(menu())
