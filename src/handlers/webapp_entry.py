# from aiogram import Router, types
# from aiogram.fsm.context import FSMContext
# router = Router()
#
# @router.message(types.WebAppData)
# async def webapp_data(msg: types.Message, state: FSMContext):
#     # данные приходят как JSON-строка msg.web_app_data.data
#     # здесь можно отладочно залогировать, но WebApp сама всё сохранила через FastAPI
#     await msg.answer("✅ Данные получены. Если кнопка не сработала — напишите /start ещё раз.")
