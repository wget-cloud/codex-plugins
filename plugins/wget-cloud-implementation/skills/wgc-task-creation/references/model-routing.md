# Модель чата и контекст

Все агенты наследуют model и reasoning effort текущего чата: при spawn опускай overrides, `MODEL: inherit`, `REASONING_EFFORT: inherit`, `MODEL_ROUTE: inherit`. Orchestrator остаётся main-only. После смены модели новые назначения наследуют новую модель; работающие агенты не перенастраиваются задним числом.

Не выбирай Luna/Terra/Sol/Astra автоматически, не подменяй неизвестную модель и не меняй настройки пользователя. Доступность берётся из активного инструмента. `service_tier=default` и `features.fast_mode=false` обязательны; Fast/priority/ultrafast запрещены, неподтверждённая конфигурация блокирует запуск. Если инструмент предлагает только priority, верни `WGC_FAST_MODE_FORBIDDEN`; модель сама не обеспечивает Standard.

Default `FORK_TURNS: none`. Передавай узкое assignment с role file, domain profile, task/assessment revisions, scope, acceptance и ссылками на evidence. Положительное N используй только для незаменимого контекста; all не является способом экономии. Не держи более трёх активных субагентов. Независимый reviewer получает собственный контекст.

GPT-6: явно ограничивай проверки изменённым поведением и repository requirements. После успешных проверок не расширяй их без новых изменений, failures или unresolved risk. Делегируй только роли выбранного маршрута. Эти правила применимы и к другим моделям; не добавляй API-only параметры в spawn.

Источник рекомендаций GPT-6: https://developers.openai.com/api/docs/guides/latest-model
