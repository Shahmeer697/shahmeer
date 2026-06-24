"""
Copyright 2022 Shahzain Masood

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""

print("MultiTool is starting...\nGetting discord buildNumber")
from src import (
    MultiTool,
    MPrint,
    Utility,
    scrape,
    global_variables,
    _captcha,
    DiscordSocket,
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
seen = {}
duplicates = 0
notjoined = 0
lockedtokens = 0
invalidTokens = 0
stopEvent = threading.Event()


# SYNC functions
def clearConsole():
    return os.system("cls" if os.name in ("nt", "dos") else "clear")


def showMenu():
    print(f"{Style.BRIGHT}{Fore.BLUE}1: Check Tokens {Style.RESET_ALL}")
    print(f"{Style.BRIGHT}{Fore.BLUE}2: Join Server {Style.RESET_ALL}")
    print(f"{Style.BRIGHT}{Fore.BLUE}3: Server Spammer {Style.RESET_ALL}")
    print(f"{Style.BRIGHT}{Fore.BLUE}4: Server Leaver {Style.RESET_ALL}")
    print(
        f"{Style.BRIGHT}{Fore.BLUE}5: Format changer: [Email:Pass:Token] -> [Token] {Style.RESET_ALL}"
    )
    print(f"{Style.BRIGHT}{Fore.BLUE}6: Single DM Spam {Style.RESET_ALL}")
    print(f"{Style.BRIGHT}{Fore.BLUE}7: Mass DM {Style.RESET_ALL}")
    print(
        f"{Style.BRIGHT}{Fore.BLUE}8: Username Changer [Email:Pass:Token] {Style.RESET_ALL}"
    )
    print(f"{Style.BRIGHT}{Fore.BLUE}9: Bio Changer {Style.RESET_ALL}")
    print(f"{Style.BRIGHT}{Fore.BLUE}10: Friends Spammer {Style.RESET_ALL}")
    print(f"{Style.BRIGHT}{Fore.BLUE}11: Member scrapper {Style.RESET_ALL}")
    print(f"{Style.BRIGHT}{Fore.BLUE}12: VC spammer {Style.RESET_ALL}")
    print(f"{Style.BRIGHT}{Fore.BLUE}13: Reaction Spammer {Style.RESET_ALL}")
    print(f"{Style.BRIGHT}{Fore.BLUE}14: Global name scrapper {Style.RESET_ALL}")
    print(f"{Style.BRIGHT}{Fore.BLUE}15: Avatar scrapper {Style.RESET_ALL}")
    print(f"{Style.BRIGHT}{Fore.BLUE}16: Avatar adder {Style.RESET_ALL}")
    print(f"{Style.BRIGHT}{Fore.BLUE}17: Exit {Style.RESET_ALL}")


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
async def scrapeMassMention(token, guildId, channelId):
    o = await buildMultiTool(token)
    res = await o.getGuild(guildId)
    if "name" not in res:
        return await scrapeMassMention(
            random.choice(open("input/tokens.txt").read().splitlines()),
            guildId,
            channelId,
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
    if m == None:
        return None
    if useDelay:
        if delayConfig["random"]:
            await asyncio.sleep(random.uniform(delayConfig["min"], delayConfig["max"]))
        else:
            await asyncio.sleep(delayConfig["fixed"])
    await m.addReactionByEmoji(messageId, channelId, emojiObj)


async def buildMultiTool(token: str) -> MultiTool:
    try:
        m = MultiTool()
        await m._init(token)
        return m
    except Exception as e:
        console.f_print(f"Error while building Multitool Coroutine: {e}")
        return await buildMultiTool(token)


async def sendMessage(
    token: str, channelId: str, message: str, massMention: bool, massMentionSize: int
):
    m = await buildMultiTool(token)
    if m == None:
        return None
    while True:
        await m.sendMessageInChannel(message, channelId, massMention, massMentionSize)


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


async def menu():
    global duplicates
    global notjoined
    global lockedtokens
    global invalidTokens
    try:
        tokens = open("input/tokens.txt").read().splitlines()
        setTitle(tokens)
        print("")
        showMenu()
        print("\n")
        choice = int(
            input(
                f"[>] {Fore.GREEN}{Style.BRIGHT}Enter your choice \n>> {Style.RESET_ALL}"
            )
        )
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
            return await menu()
        if choice == 2:
            console.s_print(f"Server Joiner...")
            rawInvite = input(
                f"[>] {Fore.GREEN}{Style.BRIGHT}Enter your invite: {Style.RESET_ALL}"
            ).split("discord.gg/")[1]
            try:
                req1 = Utility().getInviteInfo(rawInvite)
                if req1 == {"message": "Unknown Invite", "code": 10006}:
                    console.f_print(f"https://discord.gg/{rawInvite} is INVALID")
                    return await menu()
            except:
                console.f_print(
                    "Failed to get invite info, You are probably ratelimited, try using a VPN"
                )
                req1 = {"guild": {"id": None}, "channel": {"id": None}}
                if Utility().config.get("proxy")[
                    "proxyless"
                ]:  # if proxyless is true, redirect back to `menu` otherwise keep joining
                    return await menu()
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
            return await menu()
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
            m = await buildMultiTool(random.choice(tokens))
            guildId = await m.getChannel(channelId)

            if (
                massMention
                and input(
                    f"{Fore.GREEN}{Style.BRIGHT}Do you want to use already scrapped members for massmention? (y/n) {Style.RESET_ALL}"
                ).lower()
                != "y"
            ):
                await scrapeMassMention(random.choice(tokens), guildId, channelId)
            await runTasksUntilEnter(
                [
                    sendMessage(token, channelId, message, massMention, massMentionSize)
                    for token in tokens
                ]
            )
            return await menu()
        if choice == 4:
            console.s_print(f"Server leaver...")
            guildId = input(
                f"{Fore.GREEN}{Style.BRIGHT}Enter the server Id you want to leave: {Style.RESET_ALL}"
            )
            async with TaskPool(10_000) as pool:
                for token in tokens:
                    await pool.put(leave(token, guildId))
            return await menu()
        if choice == 5:
            console.s_print(f"Format changer...")
            open("input/tokens.txt", "w").write("")
            for token in tokens:
                token = changeFormat(token)
                open("input/tokens.txt", "a").write(token + "\n")
            return await menu()
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
            return await menu()
        if choice == 7:
            console.f_print(
                f"Hey Multitool user. We are sorry but mass dm is currently disabled"
            )
            return await menu()
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
            return await menu()
        if choice == 8:
            console.s_print(f"Username changer...")
            usernames = open("input/usernames.txt").read().splitlines()
            if len(usernames) == 0:
                console.f_print(
                    f"Please input some usernames before using this feature"
                )
                input("Press enter to return to menu")
                return await menu()
            async with TaskPool(10_000) as pool:
                for token in tokens:
                    await pool.put(usernameChanger(token, random.choice(usernames)))
            return await menu()
        if choice == 9:
            console.s_print(f"Bio changer...")
            bios = open("input/bios.txt").read().splitlines()
            if len(usernames) == 0:
                console.f_print(f"Please input some bios before using this feature")
                input("Press enter to return to menu")
                return await menu()
            async with TaskPool(10_000) as pool:
                for token in tokens:
                    await pool.put(bioChanger(token, random.choice(bios)))
            return await menu()
        if choice == 10:
            console.s_print(f"Friend spammer...")
            spllited = input(
                f"{Fore.GREEN}{Style.BRIGHT}Enter your username and tag: {Style.RESET_ALL}"
            ).split("#")
            username = spllited[0]
            discrim = spllited[1]
            await runTasksUntilEnter(
                [friendRequest(token, username, discrim) for token in tokens]
            )
            return await menu()
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
            return await menu()
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
            return await menu()
        if choice == 13:
            console.s_print("Reaction Spammer...")
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
                return await menu()
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
                return await menu()
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
            await runTasksUntilEnter(
                [
                    reactionSpammer(
                        token, channelId, messageId, emojiObj, useDelay, delayConfig
                    )
                    for token in tokens
                ]
            )
            return await menu()
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
            return await menu()
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
            return await menu()
        if choice == 16:
            console.s_print("Avatar adder...")
            avatars = loadAvatars()
            if not avatars:
                input("Press enter to return to menu")
                return await menu()
            async with TaskPool(10_000) as pool:
                for token in tokens:
                    await pool.put(avatarChanger(token, random.choice(avatars)))
            return await menu()
        if choice == 17:
            exit()
        else:
            console.f_print("Invalid Choice")
            return await menu()

    except Exception as e:
        console.f_print(e)
        if Utility().config["traceback"]:
            print(format_exc())
        return await menu()


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
