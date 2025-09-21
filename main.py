import discord
from discord.ext import commands
import aiohttp
from packaging import version
import asyncio
import dotenv
import os
import datetime

dotenv.load_dotenv()

intents = discord.Intents.default()
intents.message_content = False

url = "https://master.openra.net/games?protocol=2&type=json"
mode_name = "ca"
message_id: int = 0
channel_id: int = 0
footer_icon = discord.File("./ca_icon.png", filename="ca_icon.png")

bot = commands.Bot(command_prefix="!", intents=intents)

def create_current_discord_timestamp(f: str):    # use current time zone
    now = datetime.datetime.now(datetime.timezone.utc)
    timestamp = int(now.timestamp())
    return f"<t:{timestamp}:{f}>"

async def fetch_game_data():
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                print("Failed to fetch data from openra.net.")
                return []
            data = await resp.json()
            return data

async def presence_task():
    await bot.wait_until_ready()

    import traceback
    while not bot.is_closed():
        try:
            data = await fetch_game_data()
            # Filter for Combined Arms games
            ca_games = [game for game in data if game.get("mod", "").lower() == mode_name]

            total_players = sum(game.get("players", 0) for game in ca_games)
            active_games = [game for game in ca_games if game.get("players", 0) > 0]

            player_description = "players" if total_players != 1 else "player"
            games_description = "games" if len(active_games) != 1 else "game"

            activity = discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{total_players} {player_description} in {len(active_games)} CA {games_description}"
            )
            await bot.change_presence(activity=activity)

            await asyncio.sleep(30)  # Update every 30 seconds
        except Exception as e:
            print(f"[PresenceTask] Unhandled error: {e}")
            traceback.print_exc()
            await asyncio.sleep(300)  # Wait 5 minutes before retrying

def create_games_overview_embed(games, timestamp_format="F", show_empty=False, show_outdated=False):
    embed = discord.Embed(
        title="Combined Arms Games - " + create_current_discord_timestamp(timestamp_format),
        color=discord.Color.purple(),
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )

    # Filter for Combined Arms games
    ca_games = [game for game in games if game.get("mod", "").lower() == mode_name]

    # Sort games by number of players (descending)
    ca_games.sort(key=lambda x: x.get("players", 0), reverse=True)

    # for really old version of CA, remove the initial 'v'
    for game in ca_games:
        if game.get("version", "0.0.0")[0] == 'v':
            # trim the fist character
            game.update({"version": game.get("version", "0.0.0")[1:]})

    if not show_empty:
        relevant_games = [game for game in ca_games if game.get("players", 0) > 0]
    else:
        relevant_games = ca_games

    newest_version = get_newest_version(relevant_games)
    if not show_outdated:
        relevant_games = [game for game in relevant_games if version.parse(game.get("version", "0.0.0")) >= newest_version
                         or ("dev" in game.get("version", "").lower()) or ("pre" in game.get("version", "").lower())]

    if not relevant_games:
        embed.description = "No Combined Arms games found."
        return embed

    # Group games by version
    version_groups = {}
    for game in relevant_games:
        version_str = game.get("version", "0.0.0")
        if version_str not in version_groups:
            version_groups[version_str] = []
        version_groups[version_str].append(game)

    for version_str, grouped_games in sorted(version_groups.items(), reverse=True):
        lines = []
        for game in grouped_games:
            name = game.get("name", "Unknown")
            players = game.get("players", 0)
            max_players = game.get("maxplayers", "Unknown")
            state = game.get("state", 0)
            protected = game.get("protected", False)
            if state == 1 and players == 0:
                state_emoji = "⚪"
            elif state == 1 and players > 0:
                state_emoji = "🟡"
            elif state == 2:
                state_emoji = "🟢"
            else:
                state_emoji = "❔"

            protected_emoji = "🔒" if protected else ""

            if players > 0:
                # create string of player names
                clients = game.get("clients", [])
                player_names = []
                for client in clients:
                    # skip bots
                    if client.get("isbot", True):
                        continue
                    player_names.append(client.get("name", "Unknown"))

                # make each player name cursive (add *)
                player_names = [f"*{name}*" for name in player_names]
                
                # join player names with comma
                player_list_str = ", ".join(player_names)
                
                lines.append(f"{state_emoji}{protected_emoji} {name} - **{players}/{max_players}** - {player_list_str}")

            else:
                lines.append(f"{state_emoji}{protected_emoji} {name} - **{players}/{max_players}**")


        value = "\n".join(lines)
        embed.add_field(name=f"[{version_str}]", value=value, inline=False)

    embed.set_footer(text="Data from openra.net/games", icon_url="attachment://ca_icon.png")
    return embed

async def update_games_message():
    import traceback
    await bot.wait_until_ready()
    channel = bot.get_channel(int(os.getenv("GAMES_CHANNEL_ID")))
    if not channel:
        print(f"Channel with ID {os.getenv('GAMES_CHANNEL_ID')} not found.")
        return
    try:
        message = await channel.fetch_message(int(os.getenv("GAMES_MESSAGE_ID")))
    except Exception as e:
        print(f"Could not fetch message: {e}")
        return
    while not bot.is_closed():
        try:
            data = await fetch_game_data()

            embed = create_games_overview_embed(data, timestamp_format="R")
            await message.edit(content=None, embed=embed)
            await asyncio.sleep(30)
        except Exception as e:
            print(f"[GamesMessageTask] Unhandled error: {e}")
            traceback.print_exc()
            await asyncio.sleep(60)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    # Clear all guild-specific commands used for testing to avoid duplicates/dead commands
    guilds = [guild.id for guild in bot.guilds]
    for guildId in guilds:
        guild = discord.Object(id=guildId)
        print(f'Deleting commands from {guildId}.....')
        bot.tree.clear_commands(guild=guild,type=None)
        await bot.tree.sync(guild=guild)
        print(f'Deleted commands from {guildId}!')
        continue

    try:
        synced = await bot.tree.sync(guild=None)
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"Error syncing commands: {e}")



    bot.loop.create_task(presence_task())  # Start the presence loop

    global channel_id
    global message_id

    channel_id = int(os.getenv("GAMES_CHANNEL_ID"))
    message_id = int(os.getenv("GAMES_MESSAGE_ID"))


    if os.getenv("GAMES_CHANNEL_ID"):
        channel = bot.get_channel(int(os.getenv("GAMES_CHANNEL_ID")))
        if not channel:
            print(f"Channel with ID {os.getenv('GAMES_CHANNEL_ID')} not found.")
            return
        
        if message_id == 0:
            # message does not exist, create it
            message = await channel.send("Games overview...")
            print(f"Message ID (save this inside the .env): {message.id}")
        else:
            # message exists, fetch it
            message = await channel.fetch_message(message_id)


        bot.loop.create_task(update_games_message())  # Start the message update loop


"""
@bot.tree.command(name="player_count", description="Shows the current number of players in Combined Arms games.")
async def player_count(interaction: discord.Interaction):
    await interaction.response.defer()  # Optional: shows "thinking..." in Discord
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    await interaction.followup.send("Failed to fetch data from openra.net.")
                    return
                data = await resp.json()
    except Exception as e:
        await interaction.followup.send(f"Error fetching data: {e}")
        return


    # Filter for Combined Arms games
    ca_games = [game for game in data if game.get("mod", "").lower() == "ca"]

    total_players = sum(game.get("players", 0) for game in ca_games)

    # Get games with at least one player
    active_games = [game for game in ca_games if game.get("players", 0) > 0]

    await interaction.followup.send(
        f"Current Combined Arms players: **{total_players}** in **{len(active_games)}** games."
    )
"""


@bot.tree.command(name="players", description="Lists players in active Combined Arms games.")
async def players(interaction: discord.Interaction):
    # show all players in games
    await interaction.response.defer()  # Optional: shows "thinking..." in Discord
    try:
        data = await fetch_game_data()
    except Exception as e:
        await interaction.followup.send(f"Error fetching data: {e}")
        return
    
    # filter for Combined Arms games
    ca_games = [game for game in data if game.get("mod", "").lower()
                == mode_name]
    
    # count players
    total_players = sum(game.get("players", 0) for game in ca_games)

    players_string = ""


    # create one string with all player names in all games
    for game in ca_games:
        players_list_str = ""
        players = game.get("players", 0)
        if players > 0:
            clients = game.get("clients", [])
            player_names = []
            for client in clients:
                # skip bots
                if client.get("isbot", True):
                    continue
                player_names.append(client.get("name", "Unknown"))

            player_names = [f"{name}" for name in player_names]
            
            # join player names with comma
            players_string += ", ".join(player_names) + ", "

    if total_players == 0:
        await interaction.followup.send("No players found.")
        return
    
    # remove last comma and space
    players_string = players_string[:-2]

    await interaction.followup.send(f"Current players **{total_players}**:\n{players_string}")


def get_newest_version(games):
    versions = [version.parse(game.get("version", "0.0.0")) for game in games if "version" in game]
    return max(versions) if versions else version.parse("0.0.0")

@bot.tree.command(name="games", description="Lists Combined Arms games.")
async def games(interaction: discord.Interaction, show_outdated: bool = False, show_empty: bool = False):
    await interaction.response.defer()
    try:
        data = await fetch_game_data()
    except Exception as e:
        await interaction.followup.send(f"Error fetching data: {e}")
        return

    embed = create_games_overview_embed(data, timestamp_format="F", show_empty=show_empty, show_outdated=show_outdated)

    await interaction.followup.send(embed=embed)


bot.run(os.getenv("DISCORD_BOT_TOKEN"))
