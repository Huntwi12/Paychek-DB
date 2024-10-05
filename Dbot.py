import discord
from discord.ext import commands
from datetime import datetime, timedelta
import os
import asyncio
import csv

# Set the event loop policy for Windows
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)


# Load user data from a CSV file
def load_user_data():
    user_data = {}
    if os.path.exists('user_data.csv'):
        with open('user_data.csv', 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                user_id = int(row['User ID'])
                user_data[user_id] = {
                    'name': row['Name'],
                    'bills': [],
                    'pay_frequency': row['Pay Frequency'],
                    'payday': row['Payday']
                }
                # Parse the bills if any
                if row['Bills']:
                    bills = row['Bills'].split('; ')
                    for bill in bills:
                        freq, merchant, amount, due_day = bill.split(', ')
                        user_data[user_id]['bills'].append({
                            'frequency': freq,
                            'merchant': merchant,
                            'amount': float(amount.replace('$', '')),
                            'due_day': int(due_day.split(' ')[-1])
                        })
    return user_data


# Save user data to a CSV file
def save_user_data():
    with open('user_data.csv', 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['User ID', 'Name', 'Pay Frequency', 'Payday', 'Bills'])

        for user_id, user_info in user_data.items():
            name = user_info['name']
            pay_frequency = user_info['pay_frequency']
            payday = user_info['payday']
            bills = user_info['bills']
            bills_str = '; '.join(
                [f"{bill['frequency']}, {bill['merchant']}, ${bill['amount']}, due on {bill['due_day']}" for bill in
                 bills])
            writer.writerow([user_id, name, pay_frequency, payday, bills_str])


user_data = load_user_data()


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')


@bot.command(name='start')
async def start(ctx):
    await ctx.send("Let's set up your bills! What's your name?")

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    try:
        name_msg = await bot.wait_for('message', check=check)
        name = name_msg.content.strip()

        if ctx.author.id not in user_data:
            user_data[ctx.author.id] = {'name': name, 'bills': [], 'pay_frequency': None, 'payday': None}
        else:
            user_data[ctx.author.id]['name'] = name

        if user_data[ctx.author.id]['pay_frequency'] is None or user_data[ctx.author.id]['payday'] is None:
            await ctx.send(
                f"Hi {name}! Do you get paid every week, every 2 weeks, or monthly? (type 'week', '2 weeks', or 'monthly')")
            frequency_msg = await bot.wait_for('message', check=check)

            if frequency_msg.content.lower() not in ['week', '2 weeks', 'monthly']:
                await ctx.send("Please type 'week', '2 weeks', or 'monthly' only.")
                return

            user_data[ctx.author.id]['pay_frequency'] = frequency_msg.content.lower()

            await ctx.send("What day of the week do you get paid on? (e.g., Monday, Tuesday)")
            payday_msg = await bot.wait_for('message', check=check)

            if payday_msg.content.lower() not in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday',
                                                  'sunday']:
                await ctx.send("Please enter a valid day of the week.")
                return

            user_data[ctx.author.id]['payday'] = payday_msg.content.lower()

        await ctx.send("Would you like to add any bills? (type 'yes' or 'no')")
        add_bills_msg = await bot.wait_for('message', check=check)

        if add_bills_msg.content.lower() == 'yes':
            await ctx.send(
                "Enter the bill frequency (weekly, bi-weekly, or monthly), merchant name, amount, and due date (day of the month, e.g., 15). Type 'done' when you are finished.")
            while True:
                bill_msg = await bot.wait_for('message', check=check)

                if bill_msg.content.lower() == 'done':
                    break

                try:
                    parts = bill_msg.content.split(',')
                    if len(parts) != 4:  # Ensure there are exactly 4 parts
                        await ctx.send("Please enter all four parts: 'frequency, merchant, amount, due day'.")
                        continue

                    frequency = parts[0].strip().lower()
                    merchant = parts[1].strip()
                    amount = float(parts[2].strip().replace('$', ''))  # Handle currency symbol
                    due_day = int(parts[3].strip())

                    if not (1 <= due_day <= 31):
                        await ctx.send("Please enter a valid day of the month (1-31) for the due date.")
                        continue

                    user_data[ctx.author.id]['bills'].append({
                        'frequency': frequency,
                        'merchant': merchant,
                        'amount': amount,
                        'due_day': due_day
                    })
                    save_user_data()  # Save data after adding a bill

                    await ctx.send(f"Bill added: {merchant} - ${amount} due on day {due_day} ({frequency})")

                except ValueError:
                    await ctx.send("Please ensure the amount is a valid number and the due day is a valid integer.")
                except IndexError:
                    await ctx.send(
                        "Please enter the bill in the correct format: 'frequency, merchant, amount, due day'.")

        await ctx.send("Here's a summary of your bills:")
        await display_bills(ctx)

    except Exception as e:
        await ctx.send("An error occurred while processing your request. Please try again.")
        print(f"Error in start command: {e}")


async def display_bills(ctx):
    user_bills = user_data.get(ctx.author.id, {}).get('bills', [])
    if not user_bills:
        await ctx.send("You have no bills set up.")
        return

    today = datetime.now()
    bills_upcoming = []
    bills_remaining_month = []

    for bill in user_bills:
        due_date = today.replace(day=bill['due_day'])

        if bill['frequency'] == 'monthly':
            if due_date < today:
                due_date = (due_date + timedelta(days=30)).replace(day=bill['due_day'])
        elif bill['frequency'] == 'weekly':
            while due_date < today:
                due_date += timedelta(weeks=1)
        elif bill['frequency'] == '2 weeks':
            while due_date < today:
                due_date += timedelta(weeks=2)

        if due_date <= today + timedelta(days=14):
            bills_upcoming.append(f"{bill['merchant']} - ${bill['amount']} due on {due_date.strftime('%Y-%m-%d')}")

        if due_date.month == today.month and due_date >= today:
            bills_remaining_month.append(
                f"{bill['merchant']} - ${bill['amount']} due on {due_date.strftime('%Y-%m-%d')}")

    if bills_upcoming:
        await ctx.send("You have the following bills coming up:\n" + "\n".join(bills_upcoming))
    else:
        if bills_remaining_month:
            await ctx.send(
                "You have no bills coming up in the next two weeks. Here are your remaining bills for the month:\n" + "\n".join(
                    bills_remaining_month))
        else:
            await ctx.send("You have no bills for the remaining month.")

bot.run('DISCORD BOT TOKEN GOES HERE')
