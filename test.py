# do a test for the bot
import unittest
from unittest.mock import AsyncMock, patch
from main import bot, get_average_player_count_on_hour
import datetime


# test for the aggregate_average_hourly_player_counts function
class TestAggregateAverageHourlyPlayerCounts(unittest.TestCase):
    @patch('main.TinyDB')
    def test_aggregate_average_hourly_player_counts(self, mock_tinydb):
        # setup mock database
        mock_db_instance = mock_tinydb.return_value.__enter__.return_value
        mock_avg_table = mock_db_instance.table.return_value
        
        # Mock existing entries so it only processes a few hours (not hundreds)
        # Set last entry to 5 hours ago (so it processes 4 hours: -4, -3, -2, -1)
        last_timestamp = datetime.datetime.now(datetime.timezone.utc).replace(minute=0, second=0, microsecond=0) - datetime.timedelta(hours=5)
        mock_avg_table.all.return_value = [
            {"timestamp": int(last_timestamp.timestamp()), "average_players": 100}
        ]

        # mock data for get_average_player_count_on_hour
        with patch('main.get_average_player_count_on_hour', side_effect=[10, 20, -1, 30]) as mock_get_avg:
            # run the function
            from main import aggregate_average_hourly_player_counts
            aggregate_average_hourly_player_counts()

            # check that get_average_player_count_on_hour was called correct number of times
            self.assertEqual(mock_get_avg.call_count, 4)

            # check that the database insert was called correct number of times (should skip the -1 case)
            self.assertEqual(mock_avg_table.insert.call_count, 3)

            # check the values inserted into the database
            inserted_values = [call.args[0] for call in mock_avg_table.insert.call_args_list]
            # With last entry at -5 hours, function processes: -4, -3, -2 (skipped), -1
            # So inserted timestamps are: -4, -3, -1 hours
            expected_values = [
                {"timestamp": int((datetime.datetime.now(datetime.timezone.utc).replace(minute=0, second=0, microsecond=0) - datetime.timedelta(hours=4)).timestamp()), "average_players": 10},
                {"timestamp": int((datetime.datetime.now(datetime.timezone.utc).replace(minute=0, second=0, microsecond=0) - datetime.timedelta(hours=3)).timestamp()), "average_players": 20},
                {"timestamp": int((datetime.datetime.now(datetime.timezone.utc).replace(minute=0, second=0, microsecond=0) - datetime.timedelta(hours=1)).timestamp()), "average_players": 30},
            ]
            self.assertEqual(inserted_values, expected_values)