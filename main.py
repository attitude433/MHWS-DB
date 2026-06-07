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
from commands import info, skill, material, custom, chat, sns, scheduler, meal, steam_sale, weapon, armor, random_build, zenny, rps

CAT_DIR = '/home/ubuntu/Cat-Images-Dataset'
CAT_FILES = []
for _ext in ('jpg', 'jpeg', 'png', 'JPG', 'gif'):
    CAT_FILES.extend(glob.glob(f'{CAT_DIR}/**/*.{_ext}', recursive=True))
MEOW_LINES = ['야옹', '야~옹', '냐옹', '냐~옹', '야옹!', '갸르릉…']

VS_PATTERN = re.compile(r'^\s*(.+?)\s*(?:vs|VS|Vs|vS)\s*(.+?)\s*$')

load_dotenv()

db.monster_to_equipment = db.build_monster_to_equipment(alias.MONSTER_ALIASES)

ALERT_ROOM_ID = os.environ.get('ALERT_ROOM_ID', '')
_pending_new_user_id = None
_notified_unmapped: set = set()

import nicknames as _nicknames

bot = Bot(os.environ['IRIS_SERVER_URL'])

HELP_TEXT = """[명령어 목록]

━━━━━━━━━━━━
🐲 와일즈 DB
━━━━━━━━━━━━
.정보 (몬스터)
.스킬 (스킬명)
.스킬 (스킬명) 장비
.소재 (소재명) / .아이템 (아이템명)
.무기 (무기명)
.방어구 (방어구명)

━━━━━━━━━━━━
🛠 빌드
━━━━━━━━━━━━
.커스텀
.커스텀 (무기 종류)
.랜덤

━━━━━━━━━━━━
🎰 제니·룰렛
━━━━━━━━━━━━
.출석
.룰렛 [금액] / [%] / 올
.가위 / .바위 / .보 [금액]
.제니
.제니순위

━━━━━━━━━━━━
💬 잡담·기타
━━━━━━━━━━━━
.다이애나 (질문/잡담)
.메뉴추천 (ㅈㅁㅊ / 점메추 / 저메추)
.디스코드
.고양이
.명령어"""


@bot.on_event('message')
def on_message(ctx):
    msg = ctx.message.msg.strip()

    # 1:1 알림방에서 운영자가 답장한 텍스트 → 가장 최근 pending 신규 user 와 매핑
    global _pending_new_user_id
    if (
        ALERT_ROOM_ID
        and isinstance(getattr(ctx, 'raw', None), dict)
        and str(ctx.raw.get('chat_id', '')) == str(ALERT_ROOM_ID)
        and msg
        and not msg.startswith('.')
        and not msg.startswith('[봇]')
    ):
        # 명시적 수동 매핑: "닉 [user_id 또는 구닉] [신닉]"
        m = re.match(r'^닉\s+(\S+)\s+(.+)$', msg)
        if m:
            key = m.group(1)
            new_nick = m.group(2).strip()
            target_uid = None
            try:
                if key.isdigit():
                    target_uid = int(key)
                else:
                    all_map = _nicknames.all_mappings()
                    exact = [u for u, n in all_map.items() if n == key]
                    if len(exact) == 1:
                        target_uid = exact[0]
                    elif len(exact) > 1:
                        ctx.reply(f'"{key}" 동일 닉 {len(exact)}건 — user_id 로 지정해주세요')
                        return
                    else:
                        partial = [(u, n) for u, n in all_map.items() if key in n]
                        if len(partial) == 1:
                            target_uid = partial[0][0]
                        elif len(partial) > 1:
                            cands = ', '.join(n for _, n in partial[:10])
                            ctx.reply(f'"{key}" 후보 {len(partial)}건: {cands}')
                            return
                        else:
                            ctx.reply(f'매핑에 없음: {key!r}')
                            return
                _nicknames.update(target_uid, new_nick)
                with members._conn() as c:
                    c.execute(
                        'INSERT INTO members (user_id, nickname, last_seen, first_seen) VALUES (?, ?, ?, ?) '
                        'ON CONFLICT(user_id) DO UPDATE SET nickname = excluded.nickname',
                        (target_uid, new_nick, '', ''),
                    )
                _notified_unmapped.discard(target_uid)
                ctx.reply(f'매핑 완료: {target_uid} → {new_nick}')
            except Exception as ex:
                ctx.reply(f'매핑 실패: {ex}')
            return
        # 일반 텍스트: pending 신규 user 와 매핑
        if _pending_new_user_id:
            uid = _pending_new_user_id
            nick = msg
            try:
                _nicknames.update(uid, nick)
                with members._conn() as c:
                    c.execute(
                        'UPDATE members SET nickname = ? WHERE user_id = ?',
                        (nick, uid),
                    )
                _notified_unmapped.discard(uid)
                ctx.reply(f'매핑 완료: {uid} → {nick}')
            except Exception as ex:
                ctx.reply(f'매핑 실패: {ex}')
            _pending_new_user_id = None
            return

    if ctx.sender:
        try:
            uid = ctx.sender.id
            members.upsert(uid, ctx.sender.name)
            # 매핑 안 된 사용자 채팅 시 1:1 알림 (세션당 1회)
            if uid and ALERT_ROOM_ID and not _nicknames.get(uid):
                if uid not in _notified_unmapped:
                    _notified_unmapped.add(uid)
                    _pending_new_user_id = uid
                    try:
                        raw_nick = ctx.sender.name or '(없음)'
                        # 채팅 내용 미리보기 (200자 자름)
                        preview = msg if len(msg) <= 200 else msg[:200] + '…'
                        bot.api.reply(
                            int(ALERT_ROOM_ID),
                            f'[봇] 매핑 안 된 사용자 채팅 감지\n'
                            f'user_id: {uid}\n'
                            f'raw nick: {raw_nick}\n'
                            f'메시지: {preview}\n'
                            f'\n신규 답장: 닉만 보내면 자동 매핑\n'
                            f'닉변 매핑: "닉 [구닉 또는 user_id] [신닉]"',
                        )
                    except Exception:
                        pass
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
            # raw 토큰 대신 매핑된 평문 닉 우선 (없으면 raw, 그것도 없으면 빈값)
            uid = ctx.sender.id if ctx.sender else 0
            mapped = _nicknames.get(uid) if uid else None
            sender_nick = mapped or (ctx.sender.name if ctx.sender else '')
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

    if msg == '.랜덤' or msg == '.란듐':
        ctx.reply(random_build.random_build_text())
        return

    if msg == '.출석' or msg == '.출석체크' or msg == '.출첵':
        uid = ctx.sender.id if ctx.sender else 0
        nick = (ctx.sender.name if ctx.sender else '') or '익명 헌터'
        if uid:
            res = zenny.check_attend(uid, nick)
            if res:
                ctx.reply(res)
        return

    if msg == '.룰렛' or msg.startswith('.룰렛 '):
        uid = ctx.sender.id if ctx.sender else 0
        nick = (ctx.sender.name if ctx.sender else '') or '익명 헌터'
        if uid:
            arg = msg[4:].strip()  # '.룰렛' → ''  / '.룰렛 100' → '100' / '.룰렛 올' → '올'
            body, notice = zenny.spin_roulette(uid, nick, arg)
            if body:
                ctx.reply(body)
            if notice:
                ctx.reply(notice)
        return

    for _hand in ('가위', '바위', '보'):
        _prefix = f'.{_hand}'
        if msg == _prefix or msg.startswith(_prefix + ' '):
            uid = ctx.sender.id if ctx.sender else 0
            nick = (ctx.sender.name if ctx.sender else '') or '익명 헌터'
            if uid:
                arg = msg[len(_prefix):].strip()
                res = rps.play(uid, nick, _hand, arg)
                if res:
                    ctx.reply(res)
            return

    if msg == '.제니':
        uid = ctx.sender.id if ctx.sender else 0
        nick = (ctx.sender.name if ctx.sender else '') or '익명 헌터'
        if uid:
            ctx.reply(zenny.my_zenny(uid, nick))
        return

    if msg == '.제니순위':
        viewer = ctx.sender.id if ctx.sender else 0
        ctx.reply(zenny.leaderboard(viewer))
        return

    if msg == '.제니그래프' or msg.startswith('.제니그래프 '):
        target_uid = ctx.sender.id if ctx.sender else 0
        target_nick = (ctx.sender.name if ctx.sender else '') or '익명 헌터'
        if msg.startswith('.제니그래프 '):
            query = msg[7:].strip()
            if query:
                found_uid, found_nick, cands = zenny.find_user(query)
                if found_uid:
                    target_uid = found_uid
                    target_nick = found_nick
                elif cands:
                    names = ', '.join(n for _, n in cands[:10])
                    ctx.reply(f'"{query}" 후보 {len(cands)}건: {names}')
                    return
                else:
                    ctx.reply(f'"{query}" 닉네임을 못 찾았어요')
                    return
        if target_uid:
            path = zenny.my_graph(target_uid, target_nick or '익명')
            if path:
                threading.Thread(
                    target=lambda p=path: ctx.reply_media([p]),
                    daemon=True,
                ).start()
            else:
                who = target_nick or str(target_uid)
                ctx.reply(f'{who} 님 그래프 그릴 기록이 없어요')
        return

    if msg == '.고양이':
        if random.randint(0, 9) == 0 or not CAT_FILES:
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
    global _pending_new_user_id
    try:
        if ctx.sender and ALERT_ROOM_ID:
            uid = ctx.sender.id
            raw_nick = ctx.sender.name or '(없음)'
            mapped = _nicknames.get(uid)
            is_known = members.exists(uid) or bool(mapped)
            if not is_known:
                members.upsert(uid, raw_nick)
                _pending_new_user_id = uid
                bot.api.reply(
                    int(ALERT_ROOM_ID),
                    f'[봇] 🆕 신규 사용자 입장\n'
                    f'user_id: {uid}\n'
                    f'raw nick: {raw_nick}\n'
                    f'\n신규 답장: 닉만 보내면 자동 매핑\n'
                    f'닉변 매핑: "닉 [구닉 또는 user_id] [신닉]"',
                )
            else:
                # 재입장 (이미 알고 있는 사람)
                display = mapped or raw_nick
                bot.api.reply(
                    int(ALERT_ROOM_ID),
                    f'[봇] 🔁 재입장\n'
                    f'user_id: {uid}\n'
                    f'닉: {display}',
                )
    except Exception:
        pass
    ctx.reply('안녕하세요! 공지 읽고 닉변 부탁드려요')


@bot.on_event('del_member')
def on_del_member(ctx):
    try:
        if ctx.sender and ALERT_ROOM_ID:
            uid = ctx.sender.id
            raw_nick = ctx.sender.name or '(없음)'
            mapped = _nicknames.get(uid)
            display = mapped or raw_nick
            bot.api.reply(
                int(ALERT_ROOM_ID),
                f'[봇] 👋 퇴장\n'
                f'user_id: {uid}\n'
                f'닉: {display}',
            )
    except Exception:
        pass
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
