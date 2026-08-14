# Legacy workflow exports

Экспорты Make и n8n в родительской папке используются только как справочный
материал. Python-приложение не импортирует их и не зависит от Make/n8n во время
работы.

Перед запуском Python-бота выключите Make scenario и сделайте n8n workflow
inactive/unpublished. Один Telegram token не должен одновременно использоваться
несколькими polling/webhook реализациями.
