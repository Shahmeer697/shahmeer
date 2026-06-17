# Discord MultiTool V3 - WE ARE BACK!
## By Shahzain
<li>This project was inspired by DMDGO by Vanshaj https://github.com/V4NSH4J/discord-mass-DM-GO</li>

# We are SO back!

So remember when I said this project was discontinued because I didn't have time? Well guess what, the tool is back and its better then ever! Almost everything that was broken before has been fixed and a whole bunch of new stuff got added on top of that. This is no longer the old tool that gets captcha every 5 seconds, V3 is on a completely different level.

# Credits

Multitool-V3 was made possible thanks to [flank4r](https://github.com/flank4r), go give them a follow they did alot of work on this rewrite.

# About
<strong>Discord Multi Tool-PY</strong> is a multi-threaded Discord Self Bot and it is used for many features such as the token joiner, MassDM, server spammer, reaction spammer and alot more.

# Whats new in V3?

Alright so this is the part you actually care about. Here is what makes V3 better then ever:

<li><strong>httpz</strong> - The whole tool now runs on httpz which lets us impersonate a real browser properly. This means proper TLS/JA3 and HTTP2 fingerprints instead of looking like an obvious python bot.</li>
<li><strong>Anti-Tracking</strong> - Every single request now wears a fresh disguise. The tool forges believable Firefox user-agents and pairs them with matching JA3 and Akamai fingerprints, a random timezone and randomized super properties so each connection looks like a real browser and not a bot. No more all your tokens sharing the same fingerprint and getting correlated.</li>
<li><strong>Reaction Spammer</strong> - Brand new feature! Just give it a guildId, channelId and messageId, it pulls every reaction on that message and lets you pick which one you want, then all your tokens react. You can use fixed delays, random delays or no delays at all.</li>
<li><strong>Button and Emoji Verification on Join</strong> - The joiner can now bypass button and emoji verification when joining a server, just set <code>bypassButtonAndEmojiVerification</code> to true in the config.</li>
<li><strong>Way less captcha</strong> - Because of the new fingerprinting the joiner doesn't get hit with captcha all the time like it used to, good tokens actually go through now.</li>
<li><strong>Better MassDM and Spammers</strong> - The mass mention content is now randomized (random characters and randomized order) so its harder to detect, and you can set the massmention size to a random value between a min and max.</li>

If you would like to help with this project, please create a pull request it would be very appreciated. 

# Features
<li>Proxyless/HTTP Proxy Support</li>
<li>Token Joiner</li>
<li>Token Bio Changer</li>
<li>Token Username Changer</li>
<li>Token Format Changer [Email:Pass:Token] => [Token]</li>
<li>MassDM</li>
<li>Single DM Spam</li>
<li>Server Joiner(Captcha support + Button and Emoji verification bypass)</li>
<li>Server Leaver</li>
<li>Member Scrapper</li>
<li>Reaction adder</li>
<li>Reaction Spammer(NEW)</li>
<li>Anti-Tracking with httpz browser impersonation(NEW)</li>
<li>VC Spammer</li>
<li>Username Scrapper(Soon)</li>
<li>Easy to use and setup</li>
<li>Server spammer(Has MassMention with randomized content and random size)</li>
<li>Token Checker</li>
<li>This can send multiple messages and this can ping the user aswell which is pretty cool if you ask me</li>
<li>Auto Update, This will automatically install all the newest updates so you dont have to download them manually 😃</li>

## Config
| Name                                          | Type | Description                                                                                                                            |
|-----------------------------------------------|------|----------------------------------------------------------------------------------------------------------------------------------------|
| <code>proxy.protocol</code>                   | str  | Your proxy protocol, by default its http.                                                                                             |
| <code>proxy.proxyless</code>                  | bool | Set this to true if you want to use the tool without proxies.                                                                          |
| <code>captcha.api</code>                      | str  | The captcha api you are gonna use to bypass captcha on join.                                                                           |
| <code>captcha.key</code>                      | str  | Your api key for the captcha api.                                                                                                      |
| <code>joiner.useDelays</code>                 | bool | If you want to use delays on the joiner to avoid being rate limited and detected.                                                     |
| <code>joiner.delay</code>                     | int  | How long to wait between each join in seconds when useDelays is true.                                                                  |
| <code>joiner.bypassMembershipScreening</code> | bool | Set this to true if you want to bypass membership screening upon joining server. Setting this to true is recommended.                  |
| <code>joiner.bypassOnboarding</code>          | bool | Set this to true to bypass the onboarding/rules screening when joining a server.                                                       |
| <code>joiner.bypassButtonAndEmojiVerification</code> | bool | Set this to true if your target server has a button or emoji verification on join.                                             |
| <code>joiner.bypassDoubleCounter</code>       | bool | Set this to true to bypass DoubleCounter verification bots.                                                                            |
| <code>joiner.scrapperApiKey</code>            | str  | Your Scrappey api key, used for solving the harder verifications.                                                                      |
| <code>removeDeadTokens</code>                 | bool | After checking MultiTool will remove all non-working tokens from input/tokens.txt.                                                     |
| <code>preferedThreads</code>                  | int  | The amount of threads MultiTool will use for its tasks.                                                                                |
| <code>saveFailedLogs</code>                   | bool | Saves failed logs to logs/logtype.txt.                                                                                                 |
| <code>requestTimeout</code>                   | int  | Timeout for all requests in seconds. Increase if slow connection or proxies.                                                          |
| <code>traceback</code>                        | bool | Set this to true if you want to see the full error traceback when something goes wrong, useful for debugging.                          |

## Example Configuration
```json
{
    "proxy": {
        "protocol": "http",
        "proxyless": true
    },
    "captcha": {
        "api": "flanker.wtf",
        "key": "YOUR CAPTCHA KEY"
    },
    "joiner": {
        "useDelays": true,
        "delay": 15,
        "bypassMembershipScreening": true,
        "bypassOnboarding": true,
        "bypassButtonAndEmojiVerification": true,
        "bypassDoubleCounter": false,
        "scrapperApiKey": "YOUR SCRAPPEY KEY"
    },
    "removeDeadTokens": true,
    "preferedThreads": 100000,
    "saveFailedLogs": true,
    "requestTimeout": 35,
    "traceback": false
}
```
## Need Help?
Join our discord server for help: https://discord.gg/uCyFnvHED3
## How to use?
Install all the requirements
<pre><code>pip install -r requirements.txt
</code></pre>
Fill in the config.json file and message.json file<br/>
And run the main.py file
<pre><code>python main.py
</code></pre>
## Note:
Shahzain345 and flank4r will not be responsible for any damage caused by this script.<br/>
If you see anyone selling this tool report it to me asap!
## Thank You!
