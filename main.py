import discord
from discord.ext import commands, tasks
import logging
from dotenv import load_dotenv
import os
import asyncio
import re
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timezone, timedelta
import time
import webserver

# Load environment variables
load_dotenv()
token = os.getenv('DISCORD_TOKEN')

# Logging setup
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

my_chat_id = 1445557463410671878
spl_chat_id = 240776610276442113

ANNOUNCE_CHANNEL_ID = spl_chat_id  # replace with your channel ID
bypass_role_name = "SPL Host"

# ------------------ Google Sheets ------------------

scopes = ["https://www.googleapis.com/auth/spreadsheets"]
creds = Credentials.from_service_account_file("/etc/secrets/credentials.json", scopes=scopes)
client = gspread.authorize(creds)

sheet_id = "1-BlPjtE4QTgrV_wSI7ZB_eNy2g7d1L956mom-aHozEQ"
workbook = client.open_by_key(sheet_id)

verified_times = "Scheduling"
rawdata_sheet = "SchedulingRawData"

# ------------------ Commands ------------------

@bot.command()
@commands.has_any_role("SPL Host", "Raiders", "Ruiners", "Scooters", "Bigs", "Classiest", "Cryonicles", "Sharks", "Tigers", "Tyrants", "Wolfpack")
async def spladdtime(ctx, *, content: str):
    lines = [line.strip() for line in content.splitlines() if line.strip()]

    sheet = workbook.worksheet(rawdata_sheet)
    values_list = sheet.col_values(1)
    next_row = len(values_list) + 1

    added = 0
    updated = 0
    invalid_update = 0

    for line in lines:
        vschecker = re.search(r' vs\.? ', line)
        timeregex = ''
        matchupssheet = workbook.worksheet("Info")
        currentplayer1s = [v.upper() for v in workbook.worksheet(rawdata_sheet).col_values(5)]
        currentplayer2s = [v.upper() for v in workbook.worksheet(rawdata_sheet).col_values(8)]
        target_role = discord.utils.get(ctx.guild.roles, name=bypass_role_name)
        
        if vschecker is None:
            timeregex = r'(([0-9A-Za-z _\-]+)( )(\d{4}/\d{1,2}/\d{1,2}) ([0-9:]{1,5}) ?([APM]{2}) ([\-\+\.0-9]+))'
        else:
            timeregex = r'(([0-9A-Za-z _\-]+) vs\.? ([0-9A-Za-z _\-]+) (\d{4}/\d{1,2}/\d{1,2}) ([0-9:]{1,5}) ?([APM]{2}) ([\-\+\.0-9]+))'
        
        validmatch = re.search(timeregex, line)

        if not validmatch:
            continue

        weeklymatchups = [
            [cell.upper() for cell in row]
            for row in matchupssheet.get("D4:E63")
        ]

        rowcounter = 1
        for i in weeklymatchups:
            matchcounter = 0
            if validmatch.group(2).upper() in i or validmatch.group(3).upper() in i:
                isvalid = True
                matchcounter += 1
                rowcounter += 1
                break
            else:
                if len(weeklymatchups) == rowcounter and matchcounter == 0:
                    await ctx.send(f"Invalid matchup: {validmatch.group(2)} vs. {validmatch.group(3)}")
                rowcounter += 1
                continue

        if not isvalid:
            continue

        player1 = validmatch.group(2)
        player2 = validmatch.group(3)
        date_part = validmatch.group(4)
        timeofday = validmatch.group(5) + " " + validmatch.group(6)
        gmtchange = validmatch.group(7)

        try:
            date_obj = datetime.strptime(date_part, "%Y/%m/%d")
        except ValueError:
            continue

        if player1.upper() in currentplayer1s or player1.upper() in currentplayer2s:
            if target_role not in ctx.author.roles:
                await ctx.send(f"You do not have permission to update the following entry: {line}.\nPlease contact an SPL Host.")
                invalid_update += 1
                break
            else:
                next_row = currentplayer1s.index(player1.upper()) + 1 if player1.upper() in currentplayer1s else currentplayer2s.index(player1.upper()) + 1
                updated += 1
        else:
            added += 1

        sheet.update_cell(next_row, 1, date_obj.strftime("%Y-%m-%d"))
        sheet.update_cell(next_row, 2, timeofday)
        sheet.update_cell(next_row, 3, gmtchange)
        sheet.update_cell(next_row, 5, player1)
        sheet.update_cell(next_row, 6, player2)
        sheet.update_cell(next_row, 7, str(ctx.author))

        if len(values_list) + 1 == next_row:
            next_row += 1
        else:
            next_row = len(values_list) + 1

    if added or updated:
        if added and updated:
            await ctx.send(f"Added {added} scheduling entr{'y' if added == 1 else 'ies'}. \n"
                           f"Updated {updated} scheduling entr{'y' if updated == 1 else 'ies'}.")
        elif added:
            await ctx.send(f"Added {added} scheduling entr{'y' if added == 1 else 'ies'}.")
        else:
            await ctx.send(f"Updated {updated} scheduling entr{'y' if updated == 1 else 'ies'}.")
    else:
        if invalid_update > 0:
            print("No valid entries found.")
        else:
            await ctx.send(
                "No valid scheduling entries were found.\n"
                "**Example:** `Player1 vs. Player2 2024/12/31 7:00 PM +2` or `Player1 2024/12/31 7PM +2`"
        )


@bot.command()
async def splschedule(ctx):
    sheet = workbook.worksheet(verified_times)

    cooldown = datetime.now() - timedelta(hours=8) - timedelta(minutes=5)
    last_run = datetime.strptime(sheet.cell(1, 3).value, "%Y-%m-%d %H:%M:%S")

    target_role = discord.utils.get(ctx.guild.roles, name=bypass_role_name)

    if cooldown > last_run or target_role in ctx.author.roles:
        sheet.update_cell(1, 3, (datetime.now() - timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S"))

        response = sheet.cell(1, 4).value
        formatted = response.replace("\\n", "\n")

        await ctx.send(formatted)
    else:
        await ctx.send("The schedule was updated less than 5 minutes ago. Please wait until " + sheet.cell(1, 6).value + " to use this command again.")

@bot.command()
@commands.has_role(bypass_role_name)
async def splmissingtimes(ctx):
    sheet = workbook.worksheet(verified_times)
    response = sheet.cell(1, 7).value
    formatted = response.replace("\\n", "\n")

    if formatted.strip() == "":
        await ctx.send("There are no missing times!")
    else:
        await ctx.send(formatted)

@bot.command()
@commands.has_role(bypass_role_name)
async def clearsplschedule(ctx):
    sheet = workbook.worksheet(rawdata_sheet)

    await ctx.send(
        "**Are you sure you want to clear ALL scheduling data?**\n"
        "Type **Yes** to confirm. This will cancel in 30 seconds."
    )

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    try:
        msg = await bot.wait_for("message", check=check, timeout=30)
    except asyncio.TimeoutError:
        return await ctx.send("Timed out. Clear cancelled.")

    if msg.content.lower() == "yes":
        sheet.batch_clear(["A3:G"])
        await ctx.send("Scheduling data cleared!")
    else:
        await ctx.send("Cancelled.")


@bot.command()
@commands.has_role(bypass_role_name)
async def currentsplrecordsheet(ctx, *, content: str):
    sheet = workbook.worksheet(verified_times)
    sheet.update_cell(1, 2, content)
    await ctx.send("Spreadsheet link updated!")


@bot.command()
@commands.has_any_role("SPL Host", "Team Manager", "Raiders", "Ruiners", "Scooters", "Bigs", "Classiest", "Cryonicles", "Sharks", "Tigers", "Tyrants", "Wolfpack")
async def splcommands(ctx):
    await ctx.send(
        "**Available Commands:**\n"
        "`!spladdtime` - Add scheduling times and updates existing times if used by 'SPL Host'.\n Example: `Player1 vs. Player2 2024/12/31 7:00 PM +2`\n Another example: `Player1 2024/12/31 7PM +2`\n One entry per line.\n Only users with team roles or 'SPL Host' can use this command.\n"
        "`!splschedule` - Shows the current schedule. There's a 5-minute cooldown, bypassed with the 'SPL Host' role.\n"
        "`!clearsplschedule` - Clears all scheduled times. 'SPL Host' role required.\n"
        "`!currentsplrecordsheet <link>` - Updates the current records link. 'SPL Host' role required.\n" \
        "`!splmissingtimes` - Shows players with missing times. 'SPL Host' role required.\n"
    )

# ------------------ Scheduled Announcements ------------------

@tasks.loop(minutes=15)
async def announce_upcoming_games():
    now = datetime.now(timezone.utc)

    if not (45 <= now.minute < 46):
        return

    channel = bot.get_channel(my_chat_id)
    if not channel:
        return

    # Run blocking Sheets call in a thread
    response = await asyncio.to_thread(
        lambda: workbook.worksheet(verified_times).cell(1, 5).value
    )

    if not response:
        return

    await channel.send(
        f"**Upcoming Matches:**\n{response.replace('\\n', '\n')}"
    )

# ------------------ Startup ------------------

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    if not announce_upcoming_games.is_running():
        announce_upcoming_games.start()

webserver.keep_alive()
bot.run(token, log_handler=handler, log_level=logging.DEBUG)
