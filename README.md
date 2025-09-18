# Combined Arms Discord Bot (aka. *Watcher*)
Provides some useful commands and updates its presence texts. Requirements.txt provided.
## Commands
- `/games` - gives an overview over current CA games with optional parameters
- `/players` - shows the current number of players and their names

## Setup
The bot needs to be added to a discord server. Three environment variables need to be set in the .env file:
- `DISCORD_BOT_TOKEN` contains the bot's discord token, visible on creation in the developer portal
- `GAMES_CHANNEL_ID` the channel where the bot displays the games overview
- `GAMES_MESSAGE_ID` the message that is constantly updated by the bot and displays the games overview. This can only be set after starting the bot once as this MUST be a message that the bot has sent

The bot needs permissions:
- `Send Messgage` for sending the initial message, the permission can be revoked later, as editing a message no longer requires the permission
- `View Channels` for finding the games channel

So, set the `DISCORD_BOT_TOKEN` and `GAMES_CHANNEL_ID`, start the bot, then add the `GAMES_MESSAGE_ID` and perform a restart to make the script work. The bot can also be used without the live games overview by omitting the .env variables.