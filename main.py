import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


async def main():
    async with bot:
        await bot.load_extension("cogs.applications")

        @bot.event
        async def on_ready():
            try:
                synced = await bot.tree.sync()
                print(f"Synced {len(synced)} command(s)")
            except Exception as e:
                print(f"Sync error: {e}")
            print(f"Logged in as {bot.user} (ID: {bot.user.id})")

        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
