#!/usr/bin/env python3
"""Test script to verify SQLite database operations work correctly."""

import sqlite3
import json
import datetime

def test_database():
    print("Testing SQLite database operations...")
    
    conn = sqlite3.connect('games_db.sqlite')
    cursor = conn.cursor()
    
    # Test 1: Check games table
    print("\n1. Testing games table...")
    cursor.execute('SELECT COUNT(*) FROM games')
    count = cursor.fetchone()[0]
    print(f"   ✓ Found {count} game entries")
    
    # Test 2: Get a sample game entry
    print("\n2. Fetching sample game entry...")
    cursor.execute('SELECT timestamp, games_data FROM games LIMIT 1')
    result = cursor.fetchone()
    if result:
        timestamp, games_data = result
        games = json.loads(games_data)
        dt = datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc)
        print(f"   ✓ Timestamp: {dt}")
        print(f"   ✓ Number of games: {len(games)}")
        if games:
            print(f"   ✓ Sample game: {games[0].get('name', 'Unknown')}")
    
    # Test 3: Check reminders table
    print("\n3. Testing reminders table...")
    cursor.execute('SELECT COUNT(*) FROM reminders')
    count = cursor.fetchone()[0]
    print(f"   ✓ Found {count} reminder entries")
    
    # Test 4: Check avg_hourly_player_count table
    print("\n4. Testing avg_hourly_player_count table...")
    cursor.execute('SELECT COUNT(*) FROM avg_hourly_player_count')
    count = cursor.fetchone()[0]
    print(f"   ✓ Found {count} average player count entries")
    
    # Test 5: Test timestamp query (similar to what the bot does)
    print("\n5. Testing timestamp-based query...")
    now = datetime.datetime.now(datetime.timezone.utc)
    one_day_ago = now - datetime.timedelta(days=1)
    start_ts = int(one_day_ago.timestamp())
    end_ts = int(now.timestamp())
    
    cursor.execute('SELECT COUNT(*) FROM games WHERE timestamp >= ? AND timestamp <= ?', 
                   (start_ts, end_ts))
    count = cursor.fetchone()[0]
    print(f"   ✓ Found {count} game entries in the last 24 hours")
    
    conn.close()
    print("\n✅ All tests passed!")

if __name__ == '__main__':
    test_database()
