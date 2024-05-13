import telebot
from iqoptionapi.stable_api import IQ_Option
from datetime import datetime, timedelta
from os import system
import threading
import time
import sys

bot = telebot.TeleBot('TOKEN')

QTD_MARTINGALE = 2
PAYOUTS = { 'digital': {}, 'turbo': {} }
EMAIL = 'teste@gmail.com'
SENHA = 'teste'
TIPO_CONTA = 'PRACTICE'
TIPO_PAR = 'turbo'

qtd_win = 0
entrada_base = 0.0
banca_inicio = 0.0
stop_gain = 0.0
par = ''
hora_inicio = ''
conectado = False
api = None

def iniciar_thread_checar_conexao():
	thread = threading.Thread(target=checar_conexao)
	thread.daemon = True
	thread.start()

def checar_conexao():
	global conectado

	while True:
		if api.check_connect() == False:
			printar_tentando_reconectar()

			conectado = False
			api.connect()
		else:
			conectado = True
		
		time.sleep(15)

def iniciar_thread_atualizar_payout():
	thread = threading.Thread(target=atualizar_payouts)
	thread.daemon = True
	thread.start()

def atualizar_payouts():
	while True:
		tipos = ['turbo', 'digital']
		pares = api.get_all_open_time()
		
		for tipo in tipos:
			for par in pares[tipo]:
				if pares[tipo][par]['open'] == True:
					PAYOUTS[tipo].update({ par: payout(par) })

		time.sleep(30)

def hora(): 
	return datetime.now().strftime('%H:%M:%S:%f')

def banca():
	return api.get_balance()

def payout(par):
	if TIPO_PAR == 'turbo':
		a = api.get_all_profit()

		return int(100 * a[par]['turbo'])
	elif TIPO_PAR == 'digital':
		api.subscribe_strike_list(par, 1)

		while True:
			d = api.get_digital_current_profit(par, 1)
			if d != False:
				break

			time.sleep(1)

		api.unsubscribe_strike_list(par, 1)

		return d

def entrada_base_martingale():
	lucro_esperado = (stop_gain  / qtd_win)

	return round(lucro_esperado * 100 / payout(par), 2)

def segundos_float():
	return float(datetime.now().strftime('%S.%f'))

def hora_de_entrar():
	minutos = datetime.now().strftime('%M.%S')
	minutos_float = float(minutos[1:])
	ok = minutos_float == 5.00 or minutos_float == 0.00

	return ok

def delay_aceitavel():
	segundos = int(datetime.now().strftime('%S'))
	ok = segundos >= 0 and segundos <= 3

	return ok

def cores_velas(velas):
	velas[0] = 'g' if velas[0]['open'] < velas[0]['cltose'] else 'r' if velas[0]['open'] > velas[0]['close'] else 'd'
	velas[1] = 'g' if velas[1]['open'] < velas[1]['close'] else 'r' if velas[1]['open'] > velas[1]['close'] else 'd'
	velas[2] = 'g' if velas[2]['open'] < velas[2]['close'] else 'r' if velas[2]['open'] > velas[2]['close'] else 'd'

	return velas[0] + ' ' + velas[1] + ' ' + velas[2] 

def direcao_entrada(str_cores_velas):
	direcao = False	
	if str_cores_velas.count('g') > str_cores_velas.count('r') and str_cores_velas.count('d') == 0: 
		direcao = 'put'
	if str_cores_velas.count('r') > str_cores_velas.count('g') and str_cores_velas.count('d') == 0: 
		direcao = 'call'	

	return direcao

def stop(hit, mhi_count, wins):
	if hit:
		printar_stop('************* STOP LOSS *************', mhi_count, wins)
		sys.exit()
	elif wins == qtd_win:
		printar_stop('************* STOP GAIN *************', mhi_count, wins)
		sys.exit()

def calcular_martingale(ultima_entrada):
	payout = PAYOUTS[TIPO_PAR][par]
	if payout:
		payout_decimal = payout / 100
		lucro_esperado = ultima_entrada + (ultima_entrada * payout_decimal)

		return lucro_esperado * 100 / payout
	else:
		return ultima_entrada

def check_result(id, entrada, lucro, martingale_count, mhi_count, delay_compra, wins):
	while True: 
		valor_resultante = api.check_win_v3(id)

		if valor_resultante > 0:
			wins += 1

		lucro += valor_resultante
		hit = martingale_count == QTD_MARTINGALE and valor_resultante < 0 

		printar_resultado(hit, entrada, valor_resultante, lucro, martingale_count, delay_compra)
		stop(hit, mhi_count, wins)
		
		return (valor_resultante, lucro, wins)

def operar(direcao, lucro, mhi_count, wins):
	if direcao:
		entrada = entrada_base
		martingale_count = 0

		while martingale_count <= QTD_MARTINGALE:
			if delay_aceitavel():
				inicio_compra = segundos_float()
				status, id = api.buy(entrada, par, direcao, 1)
				delay_compra = segundos_float() - inicio_compra

				if status:
					valor_resultante, lucro, wins = check_result(id, entrada, lucro, martingale_count, mhi_count, delay_compra, wins)

					if valor_resultante > 0:
						break
					elif valor_resultante < 0:
						entrada = calcular_martingale(entrada)
						martingale_count += 1
				else:
					printar_erro_operacao()

					break
			else:
				printar_delay_inaceitavel()

				break
	else:
		printar_doji_encontrado()
		time.sleep(2.5)

	return (lucro, wins)

def iniciar_mhi():
	printar_inicio()

	lucro = 0
	wins = 0
	mhi_count = 0

	while True:
		if hora_de_entrar() and conectado:
			minuto_antes = datetime.now() - timedelta(minutes=1)
			velas = api.get_candles(par, 60, 3, datetime.timestamp(minuto_antes))

			str_cores_velas = cores_velas(velas)
			direcao = direcao_entrada(str_cores_velas)

			mhi_count += 1

			printar_inicio_mhi(str_cores_velas, direcao)
				
			lucro, wins = operar(direcao, lucro, mhi_count, wins)

	time.sleep(0.5)

def printar_inicio():
	bot.send_message(chat_id, '\n')
	bot.send_message(chat_id, 'Banca inicial: ' + str(banca()))
	bot.send_message(chat_id, 'Esperando a primeira operação...')

	printar_resumo()

def printar_inicio_mhi(str_cores_velas, direcao):
	bot.send_message(chat_id, '\n')
	bot.send_message(chat_id, '----- Iniciando MHI -----')

	if direcao:
		bot.send_message(chat_id, 'DIREÇÃO:', direcao.upper())

	bot.send_message(chat_id, 'Cores: ' + str_cores_velas)	

	printar_resumo()

def printar_doji_encontrado():
	bot.send_message(chat_id, '\n')
	bot.send_message(chat_id, 'DOJI Encontrado! MHI abortado!')

	printar_resumo()

def printar_erro_operacao():
	bot.send_message(chat_id, '\n')
	bot.send_message(chat_id, 'ERRO AO REALIZAR OPERAÇÃO!!!')

	printar_resumo()

def printar_delay_inaceitavel():
	bot.send_message(chat_id, '\n')
	bot.send_message(chat_id, 'A OPERAÇÃO FOI ABORTADA PORQUE JÁ PASSOU DA HORA DE ENTRAR!!!')

	printar_resumo()

def printar_tentando_reconectar():
	bot.send_message(chat_id, '\n')
	bot.send_message(chat_id, '************* TENTANDO RECONECTAR *************')

	printar_resumo()

def printar_resultado(hit, entrada, valor_resultante, lucro, martingale_count, delay_compra):
	payout = PAYOUTS[TIPO_PAR][par]
	if payout:
		str_gale_count = ' (' + str(martingale_count) + 'º GALE)' if martingale_count > 0 else ''
	
		if valor_resultante > 0:
			str_result = '[WIN]'  
		elif valor_resultante < 0: 
			str_result = '[LOSS]'
		else:
			str_result = '[EMPATE]'

		bot.send_message(chat_id, '\n')
		bot.send_message(chat_id, '----- Resultado Operação' + str_gale_count + ' -----')
		bot.send_message(chat_id, str_result, round(valor_resultante, 2), '/ PAYOUT:', str(round(payout, 2)) + '%', '/ LUCRO:', round(lucro, 2))
		bot.send_message(chat_id, 'DELAY DA COMPRA:', delay_compra)

		printar_resumo()

		if hit:
			bot.send_message(chat_id, '')
			bot.send_message(chat_id, '############## HIT ##############')

def printar_stop(título, mhi_count, wins):
	bot.send_message(chat_id, '\n')
	bot.send_message(chat_id, título)
	bot.send_message(chat_id, 'Tipo:', TIPO_PAR, '/ Par:', par)
	bot.send_message(chat_id, 'Entrada base:', str(entrada_base))
	bot.send_message(chat_id, 'Qtd. MHI realizado:', str(mhi_count))
	bot.send_message(chat_id, 'WINS:', wins)
	bot.send_message(chat_id, 'Banca inicial:', str(banca_inicio))
	bot.send_message(chat_id, 'Banca final:', str(banca()))
	bot.send_message(chat_id, 'Hora de início:', hora_inicio)
	bot.send_message(chat_id, 'Hora de término:', hora())

def printar_resumo():
	bot.send_message(chat_id, 'Tipo: ' + TIPO_PAR + ' / Par: ' + par)
	bot.send_message(chat_id, hora())


system('clear')

@bot.message_handler(commands=['start'])
def handle_start(message):
    bot.send_message(message.chat.id, 'Welcome to the bot menu!')
    bot.send_message(message.chat.id, 'Please select an option:')
    bot.send_message(message.chat.id, '/profile - View your profile')
    bot.send_message(message.chat.id, '/buy - Buy something')
    bot.send_message(message.chat.id, '/sell - Sell something')
    bot.send_message(message.chat.id, '/entries - View your entries')
    bot.send_message(message.chat.id, '/startbot - Start MHI strategie')
    global chat_id 
    chat_id = message.chat.id

@bot.message_handler(commands=['profile'])
def handle_profile(message):
    bot.send_message(message.chat.id, 'User: {message.from_user.username}')
    bot.send_message(message.chat.id, 'Age: 30')
    bot.send_message(message.chat.id, 'Location: New York')

@bot.message_handler(commands=['buy'])
def handle_buy(message):
    bot.send_message(message.chat.id, 'Buying something...')

@bot.message_handler(commands=['sell'])
def handle_sell(message):
    bot.send_message(message.chat.id, 'Selling something...')

@bot.message_handler(commands=['entries'])
def handle_entries(message):
    bot.send_message(message.chat.id, 'Entry 1: Lorem ipsum')
    bot.send_message(message.chat.id, 'Entry 2: Dolor sit amet')

@bot.message_handler(commands=['startbot'])
def handle_start(message):
    bot.send_message(message.chat.id, 'Starting bot...')
    mhi()


def mhi(message):
	api = IQ_Option(EMAIL, SENHA)
	api.connect()
	api.change_balance(TIPO_CONTA)
	par = 'EURUSD'
	stop_gain = 20
	qtd_win = 2
	entrada_base = entrada_base_martingale()

	hora_inicio = hora()
	banca_inicio = banca()

	iniciar_thread_checar_conexao()
	iniciar_thread_atualizar_payout()
	iniciar_mhi()
bot.polling()
