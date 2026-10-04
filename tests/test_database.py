import asyncio
import unittest

from database.db import Database


class DatabaseTests(unittest.TestCase):
    def test_all_tables_create_in_sqlite(self) -> None:
        database = Database("sqlite+aiosqlite:///:memory:")
        asyncio.run(database.create_tables())
        asyncio.run(database.close())
