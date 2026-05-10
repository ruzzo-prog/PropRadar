#!/bin/sh
# Preflight: TLS файлы должны существовать в контейнере до старта nginx.
# Пути внутри контейнера фиксированы; хостовые пути задаются в docker-compose через env.
set -eu

missing=0

check_one() {
	_path="$1"
	_label="$2"
	if [ ! -e "$_path" ]; then
		printf '%s\n' "reverse-proxy preflight: отсутствует файл: ${_label} (ожидался ${_path})" >&2
		missing=1
	elif [ ! -f "$_path" ]; then
		printf '%s\n' "reverse-proxy preflight: ожидался обычный файл: ${_label} (${_path}); если на хосте путь не смонтирован, Docker мог создать каталог-заглушку." >&2
		missing=1
	elif [ ! -r "$_path" ]; then
		printf '%s\n' "reverse-proxy preflight: нет прав на чтение: ${_label} (${_path})" >&2
		missing=1
	fi
}

check_one /etc/nginx/certs/n8n/fullchain.pem "N8N TLS fullchain"
check_one /etc/nginx/certs/n8n/privkey.pem "N8N TLS privkey"
check_one /etc/nginx/certs/evolution/fullchain.pem "Evolution TLS fullchain"
check_one /etc/nginx/certs/evolution/privkey.pem "Evolution TLS privkey"
check_one /etc/nginx/certs/metabase/fullchain.pem "Metabase TLS fullchain"
check_one /etc/nginx/certs/metabase/privkey.pem "Metabase TLS privkey"

if [ "$missing" -ne 0 ]; then
	printf '%s\n' "reverse-proxy preflight: задайте пути на хосте: N8N_TLS_FULLCHAIN, N8N_TLS_PRIVKEY, EVOLUTION_TLS_FULLCHAIN, EVOLUTION_TLS_PRIVKEY, METABASE_TLS_FULLCHAIN, METABASE_TLS_PRIVKEY (см. docker/reverse-proxy/README.md и docs/TLS_LETSENCRYPT.md)." >&2
	exit 1
fi
