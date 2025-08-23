import discord
from discord.ext import tasks
import json
import re
from datetime import datetime
import pytz
import os
from flask import Flask
from threading import Thread

# --- КОНФИГУРАЦИЯ ---
try:
    TOKEN = os.environ['DISCORD_BOT_TOKEN']
    REPORT_CHANNEL_ID = int(os.environ['REPORT_CHANNEL_ID'])
    TIMEZONE = pytz.timezone('Europe/Kiev')
except KeyError as e:
    print(f"!!! КРИТИЧЕСКАЯ ОШИБКА: Секрет '{e.args[0]}' не найден в Replit.")
    exit()

# --- ВЕБ-СЕРВЕР ДЛЯ UPTIMEROBOT ---
app = Flask('')
@app.route('/')
def home():
    return "I'm alive"

def run_web_server():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_web_server)
    t.start()

# --- НАСТРОЙКА БОТА ---
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True
client = discord.Client(intents=intents)

# --- ХРАНИЛИЩЕ СТАТИСТИКИ ---
daily_stats = {}
def ensure_user_stats(user_id):
    if user_id not in daily_stats:
        daily_stats[user_id] = {
            'messages': 0, 'images': 0, 'files': 0,
            'youtube_links': 0, 'other_links': 0, 'reactions_given': 0,
            'channel_activity': {}
        }

# --- ОСНОВНЫЕ СОБЫТИЯ БОТА ---
@client.event
async def on_ready():
    print(f'Бот {client.user} успешно запущен!')
    print('------')
    generate_daily_report.start()

@client.event
async def on_message(message):
    if message.author.bot:
        return

    # [НОВОЕ] Команда для проверки статуса
    if message.content.lower().strip() == 'гарри, ты тут?':
        if message.author.guild_permissions.administrator:
            await message.channel.send('Ага! Бдю ;)')
        return # Важно, чтобы эта команда не шла в общую статистику

    if message.content.lower().strip() == 'очистить чат':
        if message.author.guild_permissions.administrator:
            try:
                target_channel = message.channel
                await target_channel.send(f'**Принято!** Начинаю полную очистку канала **#{target_channel.name}**.')
                deleted = await target_channel.purge(limit=1000, check=lambda m: not m.pinned)
                await target_channel.send(f'**Очистка завершена!** Удалено сообщений: **{len(deleted)}**.', delete_after=20)
            except discord.Forbidden:
                await message.channel.send('**Ошибка!** У меня нет права "Управлять сообщениями" в этом канале.')
            except Exception as e:
                await message.channel.send(f'**Ошибка!** Не удалось выполнить очистку: {e}')
        else:
            await message.channel.send('Эта команда доступна только администраторам.', delete_after=10)
        return

    # --- Сбор статистики ---
    user_id = message.author.id
    ensure_user_stats(user_id)
    daily_stats[user_id]['messages'] += 1
    channel_id_str = str(message.channel.id)
    if channel_id_str not in daily_stats[user_id]['channel_activity']:
        daily_stats[user_id]['channel_activity'][channel_id_str] = 0
    daily_stats[user_id]['channel_activity'][channel_id_str] += 1
    urls = re.findall(r'https?://[^\s]+', message.content)
    for url in urls:
        if 'youtube.com' in url or 'youtu.be' in url:
            daily_stats[user_id]['youtube_links'] += 1
        else:
            daily_stats[user_id]['other_links'] += 1
    if message.attachments:
        for attachment in message.attachments:
            if attachment.content_type and 'image' in attachment.content_type:
                daily_stats[user_id]['images'] += 1
            else:
                daily_stats[user_id]['files'] += 1

@client.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return
    ensure_user_stats(user.id)
    daily_stats[user_id]['reactions_given'] += 1

# --- ЗАДАЧА ПО РАСПИСАНИЮ ---
@tasks.loop(minutes=1)
async def generate_daily_report():
    now = datetime.now(TIMEZONE)
    if now.hour == 22 and now.minute == 00:
        if not hasattr(generate_daily_report, "last_run_date") or generate_daily_report.last_run_date != now.date():
            report_channel = client.get_channel(REPORT_CHANNEL_ID)
            if report_channel:
                await send_report(report_channel)
                generate_daily_report.last_run_date = now.date()

async def send_report(channel):
    global daily_stats
    embed = discord.Embed(
        title=f"📊 Суточный отчет {datetime.now(TIMEZONE).strftime('%d.%m.%Y')} | Кто вчера зажигал?",
        color=discord.Color.blue()
    )
    if not daily_stats:
        embed.description = "За последние сутки на сервере царила медитативная тишина. Все познавали дзен."
    else:
        # ... (логика отчета без изменений)
        def find_winner(metric):
            filtered_users = {uid: stats for uid, stats in daily_stats.items() if stats.get(metric, 0) > 0}
            if not filtered_users: return None, None
            winner_id = max(filtered_users, key=lambda u: filtered_users[u][metric])
            return winner_id, filtered_users[winner_id]
        main_chatter_id, main_chatter_stats = find_winner('messages')
        if not main_chatter_id:
             embed.description = "За последние сутки на сервере не было написано ни одного сообщения. Странная тишина..."
        else:
            youtube_winner_id, youtube_stats = find_winner('youtube_links')
            image_winner_id, image_stats = find_winner('images')
            link_winner_id, link_stats = find_winner('other_links')
            reaction_winner_id, reaction_stats = find_winner('reactions_given')
            file_winner_id, file_stats = find_winner('files')
            main_chatter_user = await client.fetch_user(main_chatter_id)
            active_channels = sorted(main_chatter_stats['channel_activity'].items(), key=lambda item: item[1], reverse=True)
            main_channel_name = client.get_channel(int(active_channels[0][0])).name
            other_channels_text = ""
            if len(active_channels) > 1:
                other_names = [client.get_channel(int(cid)).name for cid, count in active_channels[1:3]]
                other_channels_text = f", но не забыл также отметиться в **#{'** и **#'.join(other_names)}**!"
            embed.description = (f"Самым неутомимым за последние 24 часа признается **{main_chatter_user.mention}**! ...") # Сокращено
            async def add_field_with_fallback(winner_id, stats, metric, title, win_text, fallback_text):
                if winner_id:
                    user = await client.fetch_user(winner_id)
                    embed.add_field(name=title, value=win_text.format(user=user, count=stats[metric]), inline=False)
                else:
                    embed.add_field(name=title, value=fallback_text, inline=False)
            await add_field_with_fallback(youtube_winner_id, youtube_stats, 'youtube_links', "📺 ...", "...", "...")
            await add_field_with_fallback(image_winner_id, image_stats, 'images', "🖼️ ...", "...", "...")
            await add_field_with_fallback(link_winner_id, link_stats, 'other_links', "🔗 ...", "...", "...")
            await add_field_with_fallback(reaction_winner_id, reaction_stats, 'reactions_given', "👍 ...", "...", "...")
            await add_field_with_fallback(file_winner_id, file_stats, 'files', "📎 ...", "...", "...")
    embed.set_footer(text="Статистика собрана за последние 24 часа. Счетчик обнулен.")
    await channel.send(embed=embed)
    daily_stats = {}

# --- ЗАПУСК ВСЕГО ---
keep_alive()
try:
    client.run(TOKEN)
except Exception as e:
    print(f"!!! КРИТИЧЕСКАЯ ОШИБКА при запуске бота: {e}")