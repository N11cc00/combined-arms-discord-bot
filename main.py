import discord
from discord.ext import commands
import aiohttp
from packaging import version
import asyncio
import dotenv
import os
import datetime
from tinydb import TinyDB, Query
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import matplotlib.dates as mdates
from discord import app_commands
import pytz
import logging


dotenv.load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = False

url = "https://master.openra.net/games?protocol=2&type=json"
mode_name = "ca"
message_id: int = 0
channel_id: int = 0
task_iteration: int = 0

# path to main.py
# path_to_main = os.path.dirname(os.path.abspath(__file__))
# footer_icon = discord.File(f"{path_to_main}/icon.png", filename="icon.png")
icon_url = "https://cdn.discordapp.com/attachments/947159381101916183/1419453031413583902/icon-3x.png?ex=68d1d026&is=68d07ea6&hm=cfaaeb522709dfac96fa43f6edccc9ce708bc44463398b42e7bfff72c8f30992&"

bot = commands.Bot(command_prefix="!", intents=intents)

reminder_group = app_commands.Group(name="reminder", description="Commands to interact with reminders for players.")

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

    embed.set_footer(text="Data from openra.net/games", icon_url=icon_url)
    return embed
    
def save_data_to_db(data):
    # only save Combined Arms games with at least one player to reduce db size
    with TinyDB('games_db.json') as db:
        ca_games = [game for game in data if game.get("mod", "").lower() == mode_name and game.get("players", 0) > 0]

        # if there are no games, still save an entry with empty games list
        # to indicate that the bot was running at that time

        # remove some keys to save data
        for game in ca_games:
            keys_to_remove = ["modwebsite", "modtitle", "modicon32"]
            for key in keys_to_remove:
                game.pop(key, None)

            # remove all clients that are bots
            clients = game.get("clients", [])
            game["clients"] = [client for client in clients if not client.get("isbot", False)]

        timestamp_data = {"timestamp": int(datetime.datetime.now(datetime.timezone.utc).timestamp()), "games": ca_games}
        db.insert(timestamp_data) 

async def check_for_reminders(data):
    with TinyDB('games_db.json') as db:
        reminders_table = db.table('reminders')
        all_reminders = reminders_table.all()
        if not all_reminders:
            return  # No reminders set

        ca_games = [game for game in data if game.get("mod", "").lower() == mode_name and game.get("players", 0) > 0]
        active_player_names = set()
        for game in ca_games:
            clients = game.get("clients", [])
            for client in clients:
                if not client.get("isbot", False):
                    active_player_names.add(client.get("name", "").lower())

        # do a query into the table where any of the names in the reminders is in the active_player_names
        for reminder in all_reminders:
            discord_id: int = reminder.get("discord_id", 0)
            names: list[str] = reminder.get("names", [])
            matched_names = [name for name in names if name.lower() in active_player_names]
            if matched_names:
                user = bot.get_user(discord_id)
                if user is None:
                    user = await bot.fetch_user(discord_id)
                if user:
                    try:
                        logger.info(f"Sending reminder to user {discord_id} for names: {matched_names}")
                        await user.send(f"The following players you are tracking are currently online: {', '.join(matched_names)}")

                        # remove the matched names from the reminder list
                        remaining_names = [name for name in names if name.lower() not in active_player_names]
                        if remaining_names:
                            reminders_table.update({"names": remaining_names}, Query().discord_id == discord_id)
                        else:
                            reminders_table.remove(Query().discord_id == discord_id)
                    except Exception as e:
                        logging.error(f"Failed to send reminder to user {discord_id}: {e}")

async def update_presence(data):
    # update the bot's presence
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
    return
 
async def update_bot_task():
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
            # fetch game data
            data = await fetch_game_data()

            # save data to tinydb, key should be the timestamp
            global task_iteration
            if task_iteration % 2 == 0: # Save to DB every 2nd iteration (every minute)
                save_data_to_db(data)

            # check for reminders and send them
            await check_for_reminders(data)

            # update the embed
            embed = create_games_overview_embed(data, timestamp_format="R")
            await message.edit(content=None, embed=embed)

            await update_presence(data)

            task_iteration += 1

            await asyncio.sleep(30)
        except Exception as e:
            print(f"[GamesMessageTask] Unhandled error: {e}")
            traceback.print_exc()
            await asyncio.sleep(60)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    # Clear all guild-specific commands used for testing to avoid duplicates/dead commands
    """guilds = [guild.id for guild in bot.guilds]
    for guildId in guilds:
        guild = discord.Object(id=guildId)
        print(f'Deleting commands from {guildId}.....')
        bot.tree.clear_commands(guild=guild,type=None)
        await bot.tree.sync(guild=guild)
        print(f'Deleted commands from {guildId}!')
        continue """

    # Add command groups to the tree before syncing
    bot.tree.add_command(reminder_group)
    
    # Debug: Check what commands are in the group
    print(f"Reminder group has {len(reminder_group.commands)} commands:")
    for cmd in reminder_group.commands:
        print(f"  - {cmd.name}: {cmd.description}")
    
    # Debug: Check what commands are in the tree
    print(f"Bot tree has {len(bot.tree.get_commands())} total commands")

    try:
        # Sync to a specific guild for faster updates during development
        guild = discord.Object(id=947159380401483878)  # Replace with your server ID
        synced = await bot.tree.sync(guild=guild)
        print(f"Synced {len(synced)} slash commands to guild.")
        for cmd in synced:
            print(f"  - Synced: {cmd.name} ({type(cmd).__name__})")
        
        # Global sync (takes up to 1 hour to update) - uncomment for production
        # synced = await bot.tree.sync(guild=None)
        # print(f"Synced {len(synced)} slash commands globally.")
    except Exception as e:
        print(f"Error syncing commands: {e}")


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


        bot.loop.create_task(update_bot_task())  # Start the message update loop

@bot.tree.command(name="players", description="Lists players in active Combined Arms games.")
async def players(interaction: discord.Interaction):
    # show all players in games
    await interaction.response.defer()  # Optional: shows "thinking..." in Discord
    logging.info(f"Players command invoked by user {interaction.user} ({interaction.user.id}) and interaction id {interaction.id} in {interaction.guild}.")

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

    await interaction.followup.send(f"Current players: **{total_players}**\n{players_string}")

def get_newest_version(games):
    versions = [version.parse(game.get("version", "0.0.0")) for game in games if "version" in game]
    return max(versions) if versions else version.parse("0.0.0")

@bot.tree.command(name="games", description="Lists Combined Arms games.")
@app_commands.describe(outdated="Show games with outdated versions", empty="Show games with zero players")
async def games(interaction: discord.Interaction, outdated: bool = False, empty: bool = False):
    await interaction.response.defer()
    logging.info(f"Games command invoked with outdated: {outdated}, empty: {empty} by user {interaction.user} ({interaction.user.id}) and interaction id {interaction.id} in {interaction.guild}.")

    try:
        data = await fetch_game_data()
    except Exception as e:
        await interaction.followup.send(f"Error fetching data: {e}")
        return

    embed = create_games_overview_embed(data, timestamp_format="F", show_empty=empty, show_outdated=outdated)

    await interaction.followup.send(embed=embed)

def get_average_player_count_on_day(day: datetime.date) -> float:
    with TinyDB('games_db.json') as db:
        Game = Query()
        start_timestamp = int(datetime.datetime.combine(day, datetime.time.min, tzinfo=datetime.timezone.utc).timestamp())
        end_timestamp = int(datetime.datetime.combine(day, datetime.time.max, tzinfo=datetime.timezone.utc).timestamp())
        
        entries = db.search((Game.timestamp >= start_timestamp) & (Game.timestamp <= end_timestamp))
        
    # structure of an entry is {"timestamp": 1234567890, "games": [...]}
    # data is already filtered
    total_player_counts = []
    for entry in entries:
        games = entry.get("games", [])
        total_players = sum(game.get("players", 0) for game in games)
        total_player_counts.append(total_players)

    if not total_player_counts:
        return 0

    return sum(total_player_counts) / len(total_player_counts)

def get_average_player_count_on_hour(hour: datetime.datetime) -> float:
    with TinyDB('games_db.json') as db:
        Game = Query()
        start_timestamp = int(hour.replace(minute=0, second=0, microsecond=0, tzinfo=datetime.timezone.utc).timestamp())
        end_timestamp = int(hour.replace(minute=59, second=59, microsecond=999999, tzinfo=datetime.timezone.utc).timestamp())

        entries = db.search((Game.timestamp >= start_timestamp) & (Game.timestamp <= end_timestamp))

    # structure of an entry is {"timestamp": 1234567890, "games": [...]}
    # data is already filtered
    total_player_counts = []
    for entry in entries:
        games = entry.get("games", [])
        total_players = sum(game.get("players", 0) for game in games)
        total_player_counts.append(total_players)

    if not total_player_counts:
        return 0
    return sum(total_player_counts) / len(total_player_counts)

# sets a reminder for a nickname add command
@reminder_group.command(name="add", description="Set a reminder for when a player is in a game.")
@app_commands.describe(name="Name of the player to set a reminder for")
async def reminder(interaction: discord.Interaction, name: str):
    await interaction.response.defer()
    logging.info(f"Reminder add command invoked with name: {name} by user {interaction.user} ({interaction.user.id}) and interaction id {interaction.id} in {interaction.guild}.")

    name = name.lower().strip()
    with TinyDB('games_db.json') as db:
        reminders_table = db.table('reminders')

        User = Query()
        doc = reminders_table.get(User.discord_id == interaction.user.id)
        if doc:
            names = doc.get("names", [])
            if name not in names:
                names.append(name)
            else:
                await interaction.followup.send(f"Reminder for {name} already set!")
                return
            # Update the document
            reminders_table.update({"names": names}, User.discord_id == interaction.user.id)
        else:
            # Insert new document if not found
            reminders_table.insert({"discord_id": interaction.user.id, "names": [name]})

        # the value should be a python list
        await interaction.followup.send(f"I'll remind you when {name} is in a game!", ephemeral=True)

@reminder_group.command(name="clear", description="Clear all your reminders.")
async def reminder_clear(interaction: discord.Interaction):
    await interaction.response.defer()
    logging.info(f"Reminder clear command invoked by user {interaction.user} ({interaction.user.id}) and interaction id {interaction.id} in {interaction.guild}.")

    with TinyDB('games_db.json') as db:
        reminders_table = db.table('reminders')
        reminders_table.remove((Query().discord_id == interaction.user.id))
        await interaction.followup.send(f"All reminders cleared!", ephemeral=True)

def create_stats_embed(filename: str, image_path: str, title: str):
    embed = discord.Embed(
        title=title,
        color=discord.Color.blue(),
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    file = discord.File(image_path, filename=filename)
    embed.set_image(url=f"attachment://{filename}")
    embed.set_footer(text="Data from openra.net/games", icon_url=icon_url)
    return embed

def create_plot(x_times, y_values, title, x_label, y_label, output_path, period="day", timezone="UTC"):
    # Convert x_times to the specified timezone
    tz = pytz.timezone(timezone)
    if x_times and isinstance(x_times[0], datetime.datetime):
        x_times = [dt.astimezone(tz) for dt in x_times]

    plt.style.use('seaborn-v0_8')
    plt.figure(figsize=(12, 6), facecolor='white')
    ax = plt.gca()
    
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))

    if y_values:  # Ensure y_values is not empty
        ax.set_ylim(bottom=0, top=max(y_values) * 1.1)  # Start at 0, extend 10% above max for padding

    if x_times:  # Ensure x_times is not empty
        ax.set_xlim(left=min(x_times), right=max(x_times))
    
    if period == "day":
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=pytz.timezone(timezone)))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
    elif period == "week":
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M", tz=pytz.timezone(timezone)))
        # only show midnight and noon
        ax.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 12], interval=1))
    elif period == "month":
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d", tz=pytz.timezone(timezone)))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=2))
    elif period == "year":
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m", tz=pytz.timezone(timezone)))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))

    plt.plot(x_times, y_values, color='#1f77b4', linewidth=2.5)
    plt.title(f"{title}", fontsize=16, fontweight='bold', pad=15, color='#333333')  # Add timezone to title
    plt.xlabel(f"{x_label} ({timezone})", fontsize=12, fontweight='medium', color='#333333')
    plt.ylabel(y_label, fontsize=12, fontweight='medium', color='#333333')
    plt.xticks(rotation=45, ha='right', fontsize=10, color='#333333')
    plt.yticks(fontsize=10, color='#333333')
    plt.grid(True, which='both', linestyle='--', linewidth=0.7, alpha=0.7, color='#cccccc')
    ax.set_facecolor('#f5f5f5')
    for spine in ax.spines.values():
        spine.set_edgecolor('#cccccc')
        spine.set_linewidth(1)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

async def period_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    periods = ["day", "week", "month", "year"]
    return [
        app_commands.Choice(name=period, value=period)
        for period in periods
        if current.lower() in period.lower()
    ][:25]

async def timezone_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    common_timezones = [
        "UTC", "Europe/Berlin", "America/New_York", "America/Los_Angeles", "Europe/London",
        "Europe/Paris", "Asia/Tokyo", "Australia/Sydney", "Asia/Dubai", "America/Chicago", "Asia/Singapore"
    ]
    return [
        app_commands.Choice(name=tz, value=tz)
        for tz in common_timezones
        if current.lower() in tz.lower()
    ][:25]

@bot.tree.command(name="stats", description="Shows online player statistics for Combined Arms.")
@app_commands.describe(
    period="Time period for stats: day, week, month, year. Default: day", 
    timezone="IANA timezone for stats. Default: UTC"
)                  
@app_commands.autocomplete(period=period_autocomplete, timezone=timezone_autocomplete)
async def stats(interaction: discord.Interaction, period: str = "day", timezone: str = "UTC"):
    await interaction.response.defer()
    logging.info(f"Stats command invoked with period: {period}, timezone: {timezone} by user {interaction.user} ({interaction.user.id}) and interaction id {interaction.id} in {interaction.guild}.")

    # for testing this should send an embed with player count numbers from the database
    # for this we need to read from the tinydb and only display the player counts
    period = period.lower()
    
    # check that timezone is a valid timezone
    try:
        pytz.timezone(timezone)
    except pytz.exceptions.UnknownTimeZoneError:
        await interaction.followup.send(
            f"Invalid timezone: `{timezone}`. Please use an IANA timezone (e.g., `America/New_York`, `Europe/London`, `UTC`)."
        )
        return

    # get data for the last 24 hours
    match period:
        case "day":
            now = datetime.datetime.now(datetime.timezone.utc)
            last_24_hours = [(now - datetime.timedelta(hours=i)).replace(minute=0, second=0, microsecond=0) for i in range(24)]
            last_24_hours.reverse()  # so that the oldest hour is first
            # convert to timezone
            player_counts = [get_average_player_count_on_hour(hour) for hour in last_24_hours]

            # create a plot with matplotlib
            create_plot(last_24_hours, player_counts, "Average Player Count in the Last 24 Hours", f"Time", "Average Player Count", 
                        "last_day.png", period="day", timezone=timezone)
        case "week":
            now = datetime.datetime.now(datetime.timezone.utc)
            # split up week into hours
            last_168_hours = [(now - datetime.timedelta(hours=i)).replace(minute=0, second=0, microsecond=0) for i in range(168)]
            last_168_hours.reverse()  # so that the oldest hour is first
            player_counts = [get_average_player_count_on_hour(hour) for hour in last_168_hours]

            # create a plot with matplotlib
            create_plot(last_168_hours, player_counts, "Average Player Count in the Last Week", f"Time", "Average Player Count", 
                        "last_week.png", period="week", timezone=timezone)
        case "month":
            now = datetime.datetime.now(datetime.timezone.utc)
            last_30_days = [(now - datetime.timedelta(days=i)).date() for i in range(30)]
            last_30_days.reverse()  # so that the oldest day is first
            player_counts = [get_average_player_count_on_day(day) for day in last_30_days]

            # create a plot with matplotlib
            create_plot(last_30_days, player_counts, "Average Player Count in the Last Month", f"Time", "Average Player Count", 
                        "last_month.png", period="month", timezone=timezone)
        case "year":
            # do this for every day
            now = datetime.datetime.now(datetime.timezone.utc)
            last_365_days = [(now - datetime.timedelta(days=i)).date() for i in range(365)]
            last_365_days.reverse()  # so that the oldest day is first
            player_counts = [get_average_player_count_on_day(day) for day in last_365_days]

            # create a plot with matplotlib
            create_plot(last_365_days, player_counts, "Average Player Count in the Last Year", f"Time", "Average Player Count", 
                        "last_year.png", period="year", timezone=timezone)
        case _:
            await interaction.followup.send("Invalid period. Available: day, week, month, year.")
            return

    embed = create_stats_embed(f"last_{period}.png", f"last_{period}.png", f"Combined Arms Player Statistics - Last {period.capitalize()}")
    await interaction.followup.send(embed=embed, file=discord.File(f"last_{period}.png"))

    # embed = create_stats_embed("stats.png", "last_24_hours.png", f"Combined Arms Player Statistics - Last {period.capitalize()}")
    # await interaction.followup.send(embed=embed, file=discord.File("last_24_hours.png"))

bot.run(os.getenv("DISCORD_BOT_TOKEN"))
