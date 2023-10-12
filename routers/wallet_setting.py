from typing import List
import jsonpickle
from aiogram import Router, types, F
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from requests import Session
from stellar_sdk import Asset

from db.requests import db_get_book_data, db_get_address_book_by_id, db_delete_address_book_by_id, \
    db_insert_into_address_book, \
    db_get_default_wallet
from keyboards.common_keyboards import get_return_button, get_kb_yesno_send_xdr, get_kb_return, get_kb_del_return
from mytypes import Balance
from routers.add_wallet import cmd_show_add_wallet_choose_pin
from routers.sign import cmd_ask_pin, PinState
from routers.start_msg import cmd_info_message
from utils.aiogram_utils import send_message, my_gettext, admin_id
from loguru import logger
from utils.stellar_utils import (stellar_get_balances, stellar_add_trust, stellar_get_user_account,
                                 stellar_is_free_wallet, public_issuer, get_good_asset_list,
                                 stellar_pay, eurmtl_asset, float2str, stellar_get_user_keypair,
                                 stellar_change_password, stellar_unfree_wallet, have_free_xlm)


class DelAssetCallbackData(CallbackData, prefix="DelAssetCallbackData"):
    answer: str


class AddAssetCallbackData(CallbackData, prefix="AddAssetCallbackData"):
    answer: str


class AddressBookCallbackData(CallbackData, prefix="AddressBookCallbackData"):
    action: str
    idx: int


class StateAddAsset(StatesGroup):
    sending_code = State()
    sending_issuer = State()


class StateAddressBook(StatesGroup):
    sending_new = State()


router = Router()


@router.callback_query(F.data == "WalletSetting")
async def cmd_wallet_setting(callback: types.CallbackQuery, state: FSMContext, session: Session):
    msg = my_gettext(callback, 'wallet_setting_msg')
    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_add_asset'), callback_data="AddAssetMenu")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_address_book'), callback_data="AddressBook")],
        # [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_buy'), callback_data="BuyAddress")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_get_key'), callback_data="GetPrivateKey")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_set_password'), callback_data="SetPassword")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_remove_password'), callback_data="RemovePassword")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'change_lang'), callback_data="ChangeLang")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_donate'), callback_data="Donate")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_set_default'), callback_data="SetDefault")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_set_limit'), callback_data="SetLimit")],
        get_return_button(callback)
    ]

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await send_message(session, callback, msg, reply_markup=keyboard)


@router.callback_query(F.data == "AddAssetMenu")
async def cmd_add_asset(callback: types.CallbackQuery, state: FSMContext, session: Session):
    msg = my_gettext(callback, 'delete_asset')
    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_delete_one'), callback_data="DeleteAsset")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_add_list'), callback_data="AddAsset")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_add_expert'), callback_data="AddAssetExpert")],
        get_return_button(callback)
    ]

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await send_message(session, callback, msg, reply_markup=keyboard)


########################################################################################################################
########################################################################################################################
########################################################################################################################

@router.callback_query(F.data == "DeleteAsset")
async def cmd_add_asset_del(callback: types.CallbackQuery, state: FSMContext, session: Session):
    asset_list = await stellar_get_balances(session, callback.from_user.id)

    kb_tmp = []
    for token in asset_list:
        kb_tmp.append([types.InlineKeyboardButton(text=f"{token.asset_code} ({float2str(token.balance)})",
                                                  callback_data=DelAssetCallbackData(
                                                      answer=token.asset_code).pack()
                                                  )])
    kb_tmp.append(get_return_button(callback))
    msg = my_gettext(callback, 'delete_asset2')
    await send_message(session, callback, msg, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb_tmp))
    await state.update_data(assets=jsonpickle.encode(asset_list))
    await callback.answer()


@router.callback_query(DelAssetCallbackData.filter())
async def cq_swap_choose_token_from(callback: types.CallbackQuery, callback_data: DelAssetCallbackData,
                                    state: FSMContext, session: Session):
    answer = callback_data.answer
    data = await state.get_data()
    asset_list: List[Balance] = jsonpickle.decode(data['assets'])

    asset = list(filter(lambda x: x.asset_code == answer, asset_list))
    if asset:
        await state.update_data(send_asset_code=asset[0].asset_code,
                                send_asset_issuer=asset[0].asset_issuer)
        # todo send last coins
        xdr = await stellar_add_trust(
            (await stellar_get_user_account(session, callback.from_user.id)).account.account_id,
            Asset(asset[0].asset_code, asset[0].asset_issuer),
            delete=True)

        msg = my_gettext(callback, 'confirm_close_asset', (asset[0].asset_code, asset[0].asset_issuer))
        await state.update_data(xdr=xdr)

        await send_message(session, callback, msg, reply_markup=get_kb_yesno_send_xdr(callback))
    else:
        await callback.answer(my_gettext(callback, "bad_data"), show_alert=True)
        logger.info(f'error add asset {callback.from_user.id} {answer}')

    await callback.answer()


########################################################################################################################
########################################################################################################################
########################################################################################################################

@router.callback_query(F.data == "AddAsset")
async def cmd_add_asset_add(callback: types.CallbackQuery, state: FSMContext, session: Session):
    user_id = callback.from_user.id
    if await stellar_is_free_wallet(session, user_id) and (len(await stellar_get_balances(session, user_id)) > 5):
        await send_message(session, user_id, my_gettext(user_id, 'only_3'), reply_markup=get_kb_return(user_id))
        return False

    if not await have_free_xlm(session=session, state=state, user_id=callback.from_user.id):
        await callback.answer(my_gettext(callback, 'low_xlm'), show_alert=True)
        return

    good_asset = get_good_asset_list()
    for item in await stellar_get_balances(session, user_id):
        found = list(filter(lambda x: x.asset_code == item.asset_code, good_asset))
        if len(found) > 0:
            good_asset.remove(found[0])

    if len(good_asset) == 0:
        await send_message(session, user_id, my_gettext(user_id, 'have_all'), reply_markup=get_kb_return(user_id))
        return False

    kb_tmp = []
    for key in good_asset:
        kb_tmp.append([types.InlineKeyboardButton(text=f"{key.asset_code}",
                                                  callback_data=AddAssetCallbackData(
                                                      answer=key.asset_code).pack()
                                                  )])
    kb_tmp.append(get_return_button(callback))
    await send_message(session, callback, my_gettext(user_id, 'open_asset'),
                       reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb_tmp))

    await state.update_data(assets=jsonpickle.encode(good_asset))


@router.callback_query(AddAssetCallbackData.filter())
async def cq_add_asset(callback: types.CallbackQuery, callback_data: AddAssetCallbackData,
                       state: FSMContext, session: Session):
    answer = callback_data.answer
    data = await state.get_data()
    asset_list: List[Balance] = jsonpickle.decode(data['assets'])

    asset = list(filter(lambda x: x.asset_code == answer, asset_list))
    if asset:
        await state.update_data(send_asset_code=asset[0].asset_code,
                                send_asset_issuer=asset[0].asset_issuer)
        await cmd_add_asset_end(callback.message.chat.id, state, session, )
    else:
        await callback.answer(my_gettext(callback, "bad_data"), show_alert=True)
        logger.info(f'error add asset {callback.from_user.id} {answer}')

    await callback.answer()


########################################################################################################################
########################################################################################################################
########################################################################################################################

@router.callback_query(F.data == "AddAssetExpert")
async def cmd_add_asset_expert(callback: types.CallbackQuery, state: FSMContext, session: Session):
    user_id = callback.from_user.id
    if await stellar_is_free_wallet(session, user_id) and (len(await stellar_get_balances(session, user_id)) > 5):
        await send_message(session, user_id, my_gettext(user_id, 'only_3'), reply_markup=get_kb_return(user_id))
        return False

    if not await have_free_xlm(session=session, state=state, user_id=callback.from_user.id):
        await callback.answer(my_gettext(callback, 'low_xlm'), show_alert=True)
        return

    await state.set_state(StateAddAsset.sending_code)
    msg = my_gettext(user_id, 'send_code')
    await send_message(session, user_id, msg, reply_markup=get_kb_return(user_id))
    await callback.answer()


@router.message(StateAddAsset.sending_code)
async def cmd_swap_sum(message: types.Message, state: FSMContext, session: Session):
    user_id = message.from_user.id
    asset_code = message.text
    await state.update_data(send_asset_code=asset_code)

    await state.set_state(StateAddAsset.sending_issuer)

    msg = my_gettext(user_id, 'send_issuer', (public_issuer,))
    await send_message(session, user_id, msg, reply_markup=get_kb_return(user_id))


@router.message(StateAddAsset.sending_issuer)
async def cmd_swap_sum(message: types.Message, state: FSMContext, session: Session):
    await state.update_data(send_asset_issuer=message.text)
    await cmd_add_asset_end(message.chat.id, state, session, )


########################################################################################################################
########################################################################################################################
########################################################################################################################


async def cmd_add_asset_end(chat_id: int, state: FSMContext, session: Session):
    data = await state.get_data()
    asset_code = data.get('send_asset_code', 'XLM')
    asset_issuer = data.get('send_asset_issuer', '')

    xdr = await stellar_add_trust((await stellar_get_user_account(session, chat_id)).account.account_id,
                                  Asset(asset_code, asset_issuer))

    msg = my_gettext(chat_id, 'confirm_asset', (asset_code, asset_issuer))

    await state.update_data(xdr=xdr, operation='add_asset')
    await send_message(session, chat_id, msg, reply_markup=get_kb_yesno_send_xdr(chat_id))


########################################################################################################################
########################################################################################################################
########################################################################################################################

async def remove_password(session: Session, user_id: int, state: FSMContext):
    data = await state.get_data()
    pin = data.get('pin', '')
    stellar_change_password(session, user_id, pin, str(user_id), 0)
    await state.set_state(None)
    await cmd_info_message(session, user_id, 'Password was unset', )


@router.callback_query(F.data == "RemovePassword")
async def cmd_remove_password(callback: types.CallbackQuery, state: FSMContext, session: Session):
    pin_type = db_get_default_wallet(session, callback.from_user.id).use_pin
    if pin_type in (1, 2):
        await state.update_data(fsm_func=jsonpickle.dumps(remove_password))
        await state.set_state(PinState.sign)
        await cmd_ask_pin(session, callback.from_user.id, state)
        await callback.answer()
    elif pin_type == 10:
        await callback.answer('You have read only account', show_alert=True)
    elif pin_type == 0:
        await callback.answer('You dont have password or pin', show_alert=True)


@router.callback_query(F.data == "SetPassword")
async def cmd_set_password(callback: types.CallbackQuery, state: FSMContext, session: Session):
    pin_type = db_get_default_wallet(session, callback.from_user.id).use_pin
    if pin_type in (1, 2):
        await callback.answer('You have password. Remove it first', show_alert=True)
    elif pin_type == 10:
        await callback.answer('You have read only account', show_alert=True)
    elif pin_type == 0:
        if await stellar_is_free_wallet(session, callback.from_user.id):
            await callback.answer('You have free account. Please buy it first.', show_alert=True)
        else:
            public_key = (await stellar_get_user_account(session, callback.from_user.id)).account.account_id
            await state.update_data(public_key=public_key)
            await cmd_show_add_wallet_choose_pin(session, callback.from_user.id, state,
                                                 my_gettext(callback, 'for_address', (public_key,)))
            await callback.answer()


async def send_private_key(session: Session, user_id: int, state: FSMContext):
    data = await state.get_data()
    pin = data.get('pin', '')
    keypair = stellar_get_user_keypair(session, user_id, pin)
    await state.set_state(None)
    await send_message(session, user_id, f'Your private key is <code>{keypair.secret}</code>',
                       reply_markup=get_kb_del_return(user_id))


@router.callback_query(F.data == "GetPrivateKey")
async def cmd_get_private_key(callback: types.CallbackQuery, state: FSMContext, session: Session):
    if await stellar_is_free_wallet(session, callback.from_user.id):
        await cmd_buy_private_key(callback, state, session)
        # await callback.answer('You have free account. Please buy it first.')
    else:
        pin_type = db_get_default_wallet(session, callback.from_user.id).use_pin

        if pin_type == 10:
            await callback.answer('You have read only account', show_alert=True)
        else:
            await state.update_data(fsm_func=jsonpickle.dumps(send_private_key))
            await state.set_state(PinState.sign)
            await cmd_ask_pin(session, callback.from_user.id, state)
            await callback.answer()


async def cmd_after_buy(session: Session, user_id: int, state: FSMContext):
    data = await state.get_data()
    buy_address = data.get('buy_address')
    await send_message(session, user_id=admin_id, msg=f'{user_id} buy {buy_address}', need_new_msg=True,
                       reply_markup=get_kb_return(user_id))
    await stellar_unfree_wallet(session, user_id)


@router.callback_query(F.data == "BuyAddress")
async def cmd_buy_private_key(callback: types.CallbackQuery, state: FSMContext, session: Session):
    if await stellar_is_free_wallet(session, callback.from_user.id):
        public_key = (await stellar_get_user_account(session, callback.from_user.id)).account.account_id
        father_key = (await stellar_get_user_account(session, 0)).account.account_id
        await state.update_data(buy_address=public_key, fsm_after_send=jsonpickle.dumps(cmd_after_buy))
        balances = await stellar_get_balances(session, callback.from_user.id)
        eurmtl_balance = 0
        for balance in balances:
            if balance.asset_code == 'EURMTL':
                eurmtl_balance = float(balance.balance)
                break
        if eurmtl_balance < 1:
            await callback.answer(
                "You have free account. Please buy it first. You don't have enough money. Need 1 EURMTL",
                show_alert=True)
        else:
            await callback.answer("You have free account. Please buy it first", show_alert=True)
            memo = f"{callback.from_user.id}*{public_key[len(public_key) - 4:]}"
            xdr = await stellar_pay(public_key, father_key, eurmtl_asset, 1, memo=memo)
            await state.update_data(xdr=xdr)
            msg = my_gettext(callback, 'confirm_send', (1, eurmtl_asset.code, father_key, memo))
            msg = f"For buy {public_key}\n{msg}"

            await send_message(session, callback, msg, reply_markup=get_kb_yesno_send_xdr(callback))
    else:
        await callback.answer('You can`t buy. You have you oun account. But you can donate /donate', show_alert=True)


async def cmd_edit_address_book(session: Session, user_id: int):
    data = db_get_book_data(session, user_id)

    buttons = []
    for row in data:
        buttons.append(
            [
                types.InlineKeyboardButton(text=row.address,
                                           callback_data=AddressBookCallbackData(
                                               action='Show', idx=row.id).pack()
                                           ),
                types.InlineKeyboardButton(text=row.name,
                                           callback_data=AddressBookCallbackData(
                                               action='Show', idx=row.id).pack()
                                           ),
                types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_delete'),
                                           callback_data=AddressBookCallbackData(
                                               action='Delete', idx=row.id).pack()
                                           )
            ]
        )
    buttons.append(get_return_button(user_id))

    await send_message(session, user_id, my_gettext(user_id, 'address_book'),
                       reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data == "AddressBook")
async def cb_edit_address_book(callback: types.CallbackQuery, state: FSMContext, session: Session):
    await callback.answer()
    await state.set_state(StateAddressBook.sending_new)
    await cmd_edit_address_book(session, callback.from_user.id)


@router.message(StateAddressBook.sending_new, F.text)
async def cmd_send_for(message: types.Message, state: FSMContext, session: Session):
    await message.delete()
    if len(message.text) > 5 and message.text.find(' ') != -1:
        arr = message.text.split(' ')
        db_insert_into_address_book(session, arr[0], ' '.join(arr[1:]), message.from_user.id)
    await cmd_edit_address_book(session, message.from_user.id)


@router.callback_query(AddressBookCallbackData.filter())
async def cq_setting(callback: types.CallbackQuery, callback_data: AddressBookCallbackData,
                     state: FSMContext, session: Session):
    answer = callback_data.action
    idx = callback_data.idx
    user_id = callback.from_user.id

    if answer == 'Show':
        book = db_get_address_book_by_id(session, idx, user_id)
        if book is not None:
            await callback.answer(f"{book.address}\n{book.name}"[:200], show_alert=True)

    if answer == 'Delete':
        db_delete_address_book_by_id(session, idx, user_id)
        await cmd_edit_address_book(session, user_id)

    await callback.answer()
