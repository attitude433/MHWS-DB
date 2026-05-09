import os
import threading
from dotenv import load_dotenv
from iris import Bot
import alias
import db
from commands import info, skill, material, custom, chat, sns, scheduler

load_dotenv()

bot = Bot(os.environ['IRIS_SERVER_URL'])

HELP_TEXT = """[명령어 목록]

.명령어
.정보 (몬스터)
.스킬 (스킬명)
.스킬 (스킬명) 장비
.소재 (소재명)
.커스텀
.커스텀 (무기)
.챗 (질문)"""


@bot.on_event('message')
def on_message(ctx):
    msg = ctx.message.msg.strip()

    if msg == '.명령어':
        ctx.reply(HELP_TEXT)
        return

    if msg.startswith('.정보 '):
        query = msg[4:].strip()
        monster = alias.find_monster(query)
        if monster:
            ctx.reply(info.format_info(monster))
        else:
            ctx.reply('정확히 입력해주세요')
        return

    if msg.startswith('.스킬 '):
        query = msg[4:].strip()
        if query.endswith(' 장비'):
            skill_name = query[:-3].strip()
            found = alias.find_skill(skill_name)
            equip = db.skill_to_equipment.get(found) if found else None
            if equip:
                ctx.reply(skill.format_skill_equipment(found, equip))
            else:
                ctx.reply('정확히 입력해주세요')
        else:
            found = alias.find_skill(query)
            if found:
                ctx.reply(skill.format_skill(db.skill_index[found]))
            else:
                ctx.reply('정확히 입력해주세요')
        return

    if msg.startswith('.소재 '):
        query = msg[4:].strip()
        item_data = alias.find_item(query)
        if item_data:
            ctx.reply(material.format_material(item_data['name_kr'], item_data))
        else:
            ctx.reply('정확히 입력해주세요')
        return

    if msg == '.커스텀':
        ctx.reply(custom.format_custom())
        return

    if msg.startswith('.커스텀 '):
        weapon = msg[5:].strip()
        ctx.reply(custom.format_custom_weapon(weapon, db.external_guides))
        return

    if msg.startswith('.챗 '):
        query = msg[4:].strip()
        if query:
            threading.Thread(
                target=lambda: ctx.reply(chat.ask(query)),
                daemon=True,
            ).start()
        return


@bot.on_event('new_member')
def on_new_member(ctx):
    ctx.reply('안녕하세요! 공지읽고 닉변 부탁드려요')


sns_room_id = os.environ.get('SNS_ROOM_ID', '')
youtube_key = os.environ.get('YOUTUBE_API_KEY', '')
if sns_room_id and youtube_key:
    threading.Thread(
        target=sns.start_poller,
        args=(bot, int(sns_room_id), youtube_key),
        daemon=True,
    ).start()

if sns_room_id:
    threading.Thread(
        target=scheduler.start_scheduler,
        args=(bot, int(sns_room_id)),
        daemon=True,
    ).start()

bot.run()
