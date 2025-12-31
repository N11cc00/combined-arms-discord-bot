import sqlite3
import json
from tinydb import TinyDB
from tqdm import tqdm

def migrate_tinydb_to_sqlite(tinydb_path, sqlite_path):
    """
    Migrate TinyDB database to SQLite3.
    
    The TinyDB has three tables:
    1. Default table (_default): Game data with timestamp and games list
    2. reminders: Discord reminders with discord_id and names list
    3. avg_hourly_player_count: Average player count per hour with timestamp and average_players
    """
    
    # Connect to TinyDB
    db = TinyDB(tinydb_path)
    
    # Connect to SQLite3
    conn = sqlite3.connect(sqlite_path)
    cursor = conn.cursor()
    
    # Create games table for the default table data
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER NOT NULL,
            games_data TEXT NOT NULL
        )
    ''')
    
    # Create reminders table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_id INTEGER NOT NULL UNIQUE,
            names TEXT NOT NULL
        )
    ''')
    
    # Create avg_hourly_player_count table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS avg_hourly_player_count (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER NOT NULL UNIQUE,
            average_players REAL NOT NULL
        )
    ''')
    
    # Create indexes for better query performance
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_games_timestamp ON games(timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_reminders_discord_id ON reminders(discord_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_avg_timestamp ON avg_hourly_player_count(timestamp)')
    
    # Migrate default table (games data)
    default_table = db.table('_default')
    games_data = default_table.all()
    games_count = 0
    
    print("Migrating default table (games data)...")
    for entry in tqdm(games_data, desc="Games", unit="entry"):
        timestamp = entry.get('timestamp')
        games = entry.get('games', [])
        # Store games as JSON string
        games_json = json.dumps(games)
        
        cursor.execute('''
            INSERT INTO games (timestamp, games_data) VALUES (?, ?)
        ''', (timestamp, games_json))
        games_count += 1
    
    # Migrate reminders table
    reminders_table = db.table('reminders')
    reminders_data = reminders_table.all()
    reminders_count = 0
    
    print("\nMigrating reminders table...")
    for entry in tqdm(reminders_data, desc="Reminders", unit="entry"):
        discord_id = entry.get('discord_id')
        names = entry.get('names', [])
        # Store names as JSON string
        names_json = json.dumps(names)
        
        cursor.execute('''
            INSERT INTO reminders (discord_id, names) VALUES (?, ?)
        ''', (discord_id, names_json))
        reminders_count += 1
    
    # # Migrate avg_hourly_player_count table
    # print("Migrating avg_hourly_player_count table...")
    # avg_table = db.table('avg_hourly_player_count')
    # avg_count = 0
    # for entry in avg_table.all():
    #     timestamp = entry.get('timestamp')
    #     average_players = entry.get('average_players')
        
    #     cursor.execute('''
    #         INSERT INTO avg_hourly_player_count (timestamp, average_players) VALUES (?, ?)
    #     ''', (timestamp, average_players))
    #     avg_count += 1
    
    # print(f"Migrated {avg_count} average player count entries.")
    
    # Commit changes and close connections
    conn.commit()
    print("\nMigration completed successfully!")
    print(f"Total entries migrated:")
    print(f"  - Games: {games_count}")
    print(f"  - Reminders: {reminders_count}")
    
    conn.close()
    db.close()


if __name__ == '__main__':
    # Run the migration
    tinydb_path = 'games_db.json'
    sqlite_path = 'games_db.sqlite'
    
    print(f"Starting migration from {tinydb_path} to {sqlite_path}...")
    migrate_tinydb_to_sqlite(tinydb_path, sqlite_path)
    print(f"\nDatabase migrated to {sqlite_path}")