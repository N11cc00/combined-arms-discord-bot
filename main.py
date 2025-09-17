import discord
from discord.ext import commands
import aiohttp
from packaging import version
import asyncio
import dotenv
import os

dotenv.load_dotenv()

intents = discord.Intents.default()
intents.message_content = False

url = "https://master.openra.net/games?protocol=2&type=json"
mode_name = "ca"

bot = commands.Bot(command_prefix="!", intents=intents)

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

    while not bot.is_closed():
        try:
            data = await fetch_game_data()
        except Exception as e:
            print(f"Error fetching data: {e}")
            await asyncio.sleep(300)  # Wait 5 minutes before retrying
            continue

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

        await asyncio.sleep(20)  # Update every 20 seconds

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"Error syncing commands: {e}")
    bot.loop.create_task(presence_task())  # Start the presence loop


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

""" @bot.tree.command(name="players", description="Lists players in active Combined Arms games.")
async def players(interaction: discord.Interaction):
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
        return """
    

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

    # Filter for Combined Arms games
    ca_games = [game for game in data if game.get("mod", "").lower() == mode_name]

    if not ca_games:
        await interaction.followup.send("No Combined Arms games found.")
        return

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
                         or ("dev" in game.get(version, "").lower()) or ("pre" in game.get(version, "").lower())]

    if not relevant_games:
        await interaction.followup.send("No Combined Arms games found.")
        return

    # Group games by version
    version_groups = {}
    for game in relevant_games:
        version_str = game.get("version", "0.0.0")
        if version_str not in version_groups:
            version_groups[version_str] = []
        version_groups[version_str].append(game)

    embed = discord.Embed(
        title="Combined Arms Games",
        color=discord.Color.red()
    )

    for version_str, games in sorted(version_groups.items(), reverse=True):
        lines = []
        for game in games:
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

    await interaction.followup.send(embed=embed)


bot.run(os.getenv("DISCORD_BOT_TOKEN"))
