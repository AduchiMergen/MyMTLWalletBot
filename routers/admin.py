import os
from contextlib import suppress

from aiogram import Router, types, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from sqlalchemy.orm import Session

from other.config_reader import config, horizont_urls
from other.global_data import global_data
from other.stellar_tools import async_stellar_check_fee


class ExitState(StatesGroup):
    need_exit = State()


router = Router()
router.message.filter(F.chat.type == "private")
router.message.filter(F.chat.id.in_(config.admins))


@router.message(Command(commands=["exit"]))
@router.message(Command(commands=["restart"]))
async def cmd_exit(message: types.Message, state: FSMContext, session: Session):
    my_state = await state.get_state()
    if message.from_user.username == "itolstov":
        if my_state == ExitState.need_exit:
            await state.set_state(None)
            await message.reply("Chao :[[[")
            exit()
        else:
            await state.set_state(ExitState.need_exit)
            await message.reply(":'[")


@router.message(Command(commands=["horizon"]))
async def cmd_horizon(message: types.Message, state: FSMContext, session: Session):
    if message.from_user.username == "itolstov":
        if config.horizon_url in horizont_urls:
            config.horizon_url = horizont_urls[(horizont_urls.index(config.horizon_url) + 1) % len(horizont_urls)]
        else:
            horizont_urls.append(config.horizon_url)
            config.horizon_url = horizont_urls[0]
        await message.reply(f"Horizon url: {config.horizon_url}")


@router.message(Command(commands=["horizon_rw"]))
async def cmd_horizon(message: types.Message, state: FSMContext, session: Session):
    if message.from_user.username == "itolstov":
        if config.horizon_url_rw in horizont_urls:
            config.horizon_url_rw = horizont_urls[(horizont_urls.index(config.horizon_url_rw) + 1) % len(horizont_urls)]
        else:
            horizont_urls.append(config.horizon_url_rw)
            config.horizon_url_rw = horizont_urls[0]
        await message.reply(f"Horizon url: {config.horizon_url_rw}")


async def cmd_send_file(message: types.Message, filename):
    if os.path.isfile(filename):
        await global_data.bot.send_document(message.chat.id, types.FSInputFile(filename))


async def cmd_delete_file(filename):
    if os.path.isfile(filename):
        os.remove(filename)


@router.message(Command(commands=["log"]))
async def cmd_log(message: types.Message):
    if message.from_user.username == "itolstov":
        await cmd_send_file(message, 'mmwb.log')
        await cmd_send_file(message, 'mmwb_check_transaction.log')


@router.message(Command(commands=["err"]))
async def cmd_log(message: types.Message):
    if message.from_user.username == "itolstov":
        await cmd_send_file(message, 'MyMTLWallet_bot.err')


@router.message(Command(commands=["clear"]))
async def cmd_log(message: types.Message):
    if message.from_user.username == "itolstov":
        await cmd_delete_file('MMWB.err')
        await cmd_delete_file('MMWB.log')


@router.message(Command(commands=["fee"]))
async def cmd_fee(message: types.Message):
    await message.answer("Комиссия (мин и мах) " + await async_stellar_check_fee())


# @router.message(Command(commands=["update"]))
# async def cmd_update(message: types.Message):
#     if message.from_user.username == "itolstov":
#         for rec in fb.execsql('select distinct m.user_id, m.user_name from mymtlwalletbot_user m where m.user_id > 0'):
#             try:
#                 username = await bot.get_chat(rec[0])
#                 if username.username:
#                     if username.username.lower() != rec[1]:
#                         fb.execsql('update mymtlwalletbot_user m set m.user_name = ? where m.user_id = ?',
#                                    (username.username.lower(), username.id))
#                         await message.answer(f'username {username.username}')
#             except Exception:  # ChatNotFound
#                 pass
#         await message.answer('done')


# @router.message(Command(commands=["update2"]))
# async def cmd_update2(message: types.Message):
#     if message.from_user.username == "itolstov":
#         select = fb.execsql('select distinct m.user_id, m.public_key from mymtlwalletbot m '
#                             'where m.user_id > 0 and m.default_wallet = 1 and m.free_wallet = 1')
#         await message.answer(str(len(select)))
#         i = 0
#         for rec in select:
#             i += 1
#             if i > 140:
#                 await message.answer(rec[1] + ' ' + str(i))
#             await stellar_find_claim(rec[1], rec[0])
#
#         await message.answer('done')


# @router.message(Command(commands=["update3"]))
# async def cmd_update3(message: types.Message):
#     if message.from_user.username == "itolstov":
#         select = fb.execsql('select distinct m.user_id, m.public_key, m.credit from mymtlwalletbot m '
#                             'where m.user_id > 0 and m.default_wallet = 1 and m.free_wallet = 1 and m.credit = 3')
#         await message.answer(str(len(select)))
#         await stellar_update_credit(select)
#         await message.answer(f'done 90')


@router.message(Command(commands=["test"]))
async def cmd_test(message: types.Message):
    if message.from_user.username == "itolstov":
        with suppress(TelegramBadRequest):
            chat = await global_data.bot.get_chat(215155653)
            await message.answer(chat.json())
        with suppress(TelegramBadRequest):
            chat = await global_data.bot.get_chat(5687567734)
            await message.answer(chat.json())
