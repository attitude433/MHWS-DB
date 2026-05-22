import glob
import os
import random
import re
import threading
from dotenv import load_dotenv
from iris import Bot
import alias
import db
import members
from commands import info, skill, material, custom, chat, sns, scheduler, meal, steam_sale, weapon, armor

CAT_DIR = '/home/ubuntu/Cat-Images-Dataset'
CAT_FILES = []
for _ext in ('jpg', 'jpeg', 'png', 'JPG', 'gif'):
    CAT_FILES.extend(glob.glob(f'{CAT_DIR}/**/*.{_ext}', recursive=True))
MEOW_LINES = ['야옹', '야~옹', '냐옹', '냐~옹', '야옹!', '갸르릉…']

VS_PATTERN = re.compile(r'^\s*(.+?)\s*(?:vs|VS|Vs|vS)\s*(.+?)\s*$')

load_dotenv()

bot = Bot(os.environ['IRIS_SERVER_URL'])

HELP_TEXT = """[명령어 목록]

.명령어
.정보 (몬스터)
.스킬 (스킬명)
.스킬 (스킬명) 장비
.소재 (소재명) / .아이템 (아이템명)
.커스텀
.커스텀 (무기 종류)
.무기 (무기명)
.방어구 (방어구명)
.다이애나 (질문/잡담)
.메뉴추천 (ㅈㅁㅊ / 점메추 / 저메추)
.디스코드
.고양이"""


@bot.on_event('message')
def on_message(ctx):
    msg = ctx.message.msg.strip()

    if ctx.sender:
        try:
            members.upsert(ctx.sender.id, ctx.sender.name)
        except Exception:
            pass

    if msg == '.명령어':
        ctx.reply(HELP_TEXT)
        return

    if msg == '.정보':
        ctx.reply('.정보 (몬스터명)\n예: .정보 도샤구마')
        return

    if msg == '.스킬':
        ctx.reply('.스킬 (스킬명) 또는 .스킬 (스킬명) 장비\n예: .스킬 만족감')
        return

    if msg == '.소재' or msg == '.아이템':
        ctx.reply('.소재 (소재명) 또는 .아이템 (아이템명)\n예: .소재 철광석 / .아이템 비약')
        return

    if msg == '.무기':
        ctx.reply('.무기 (무기명)\n예: .무기 호프보우Ⅰ')
        return

    if msg == '.방어구':
        ctx.reply('.방어구 (방어구명)\n예: .방어구 호프헬름')
        return

    if msg == '.다이애나':
        ctx.reply('.다이애나 (질문)\n예: .다이애나 오늘 뭐 먹지?')
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

    if msg.startswith('.소재 ') or msg.startswith('.아이템 '):
        prefix_len = 4 if msg.startswith('.소재 ') else 5
        query = msg[prefix_len:].strip()
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
        weapon_name = msg[5:].strip()
        ctx.reply(custom.format_custom_weapon(weapon_name, db.external_guides))
        return

    if msg.startswith('.무기 '):
        query = msg[4:].strip()
        w = alias.find_weapon(query)
        if w:
            ctx.reply(weapon.format_weapon(w))
        else:
            cands = alias.find_weapon_candidates(query)
            if cands:
                body = '\n'.join(cands)
                ctx.reply(f'정확한 이름을 입력해주세요. 후보:\n{body}')
            else:
                ctx.reply('정확히 입력해주세요')
        return

    if msg.startswith('.방어구 '):
        query = msg[5:].strip()
        p = alias.find_armor_piece(query)
        if p:
            ctx.reply(armor.format_armor(p))
        else:
            cands = alias.find_armor_candidates(query)
            if cands:
                body = '\n'.join(cands)
                ctx.reply(f'정확한 이름을 입력해주세요. 후보:\n{body}')
            else:
                ctx.reply('정확히 입력해주세요')
        return

    if msg.startswith('.다이애나 '):
        query = msg[6:].strip()
        if query:
            sender_nick = ctx.sender.name if ctx.sender else ''
            mentioned = members.get_mentioned_in(query)
            threading.Thread(
                target=lambda: ctx.reply(chat.ask_chat(query, sender_nick, mentioned)),
                daemon=True,
            ).start()
        return

    if msg in ('.메뉴추천', '.ㅈㅁㅊ', '.점메추', '.저메추', 'ㅈㅁㅊ', '점메추', '저메추'):
        ctx.reply(meal.pick_random())
        return

    if msg == '.디스코드':
        ctx.reply('디스코드 채널은 https://discord.gg/N9kRfVw 에서 만나요!')
        return

    if msg == '.고양이':
        if random.randint(0, 2) == 0 or not CAT_FILES:
            ctx.reply(random.choice(MEOW_LINES))
        else:
            path = random.choice(CAT_FILES)
            threading.Thread(
                target=lambda p=path: ctx.reply_media([p]),
                daemon=True,
            ).start()
        return

    vs = VS_PATTERN.match(msg)
    if vs:
        a, b = vs.group(1).strip(), vs.group(2).strip()
        if a and b:
            if a == '태도':
                choice = a
            elif b == '태도':
                choice = b
            else:
                choice = random.choice([a, b])
            ctx.reply(f'다이애나는 {choice} 골랐어요!')
            return


@bot.on_event('new_member')
def on_new_member(ctx):
    ctx.reply('안녕하세요! 공지 읽고 닉변 부탁드려요')


@bot.on_event('del_member')
def on_del_member(ctx):
    ctx.reply('ㅠㅠ')


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
    threading.Thread(
        target=steam_sale.start_poller,
        args=(bot, int(sns_room_id)),
        daemon=True,
    ).start()

bot.run()
