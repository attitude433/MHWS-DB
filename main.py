import os
import asyncio
from dotenv import load_dotenv
from iris import Bot
import alias
import db
from commands import info, skill, material, custom, chat, sns

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


@bot.on_event('chat')
async def on_chat(ctx):
    msg = ctx.message.content.strip()

    if msg == '.명령어':
        await ctx.reply(HELP_TEXT)
        return

    if msg.startswith('.정보 '):
        query = msg[4:].strip()
        monster = alias.find_monster(query)
        if monster:
            await ctx.reply(info.format_info(monster))
        else:
            await ctx.reply(f'몬스터를 찾을 수 없습니다: {query}')
        return

    if msg.startswith('.스킬 '):
        query = msg[4:].strip()
        if query.endswith(' 장비'):
            skill_name = query[:-3].strip()
            found = alias.find_skill(skill_name)
            equip = db.skill_to_equipment.get(found) if found else None
            if equip:
                await ctx.reply(skill.format_skill_equipment(found, equip))
            else:
                await ctx.reply(f'스킬을 찾을 수 없습니다: {skill_name}')
        else:
            found = alias.find_skill(query)
            if found:
                await ctx.reply(skill.format_skill(db.skill_index[found]))
            else:
                await ctx.reply(f'스킬을 찾을 수 없습니다: {query}')
        return

    if msg.startswith('.소재 '):
        query = msg[4:].strip()
        item_data = alias.find_item(query)
        if item_data:
            await ctx.reply(material.format_material(query, item_data))
        else:
            await ctx.reply(f'소재를 찾을 수 없습니다: {query}')
        return

    if msg == '.커스텀':
        await ctx.reply(custom.format_custom())
        return

    if msg.startswith('.커스텀 '):
        weapon = msg[5:].strip()
        await ctx.reply(custom.format_custom_weapon(weapon, db.external_guides))
        return

    if msg.startswith('.챗 '):
        query = msg[4:].strip()
        result = await chat.ask(query)
        await ctx.reply(result)
        return


async def main():
    room_name = os.environ.get('SNS_ROOM_NAME', '')
    if room_name:
        asyncio.create_task(sns.start_poller(bot, room_name))
    await bot.run()


asyncio.run(main())
