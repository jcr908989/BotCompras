import os
import requests
import time
import json
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from functools import wraps
import threading
import webbrowser
import pywhatkit as kit
import pyautogui
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Configuración
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot_compras.log')
    ]
)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'clave_secreta_123456')

# Configuración global
TELEGRAM_CONFIG = {'bot_token': '', 'chat_id': ''}
USUARIO_ADMIN = 'admin'
PASSWORD_ADMIN = 'admin123'

# ========== SISTEMA PRINCIPAL ==========
class SistemaBot:
    def __init__(self):
        self.config = self.ConfiguracionUsuario()
        self.preventas = []
        self.productos = []
        self.en_ejecucion = True
        self.logs = []
        self.cargar_configuracion()
        self.iniciar_monitoreo_automatico()

    class ConfiguracionUsuario:
        def __init__(self):
            self.datos_pago = {
                'nombre': '', 'apellido': '', 'direccion': '', 'ciudad': '',
                'codigo_postal': '', 'pais': 'España', 'telefono': '', 'email': ''
            }
            self.tarjeta = {'numero': '', 'mes_expiracion': '', 'anio_expiracion': '', 'cvv': '', 'titular': ''}
            self.paypal = {'email': '', 'password': ''}
            self.telegram = {'bot_token': '', 'chat_id': ''}
            self.whatsapp = {'numero': '', 'activo': False}

    def cargar_configuracion(self):
        for archivo in ['config_usuario.json', 'preventas.json', 'productos.json']:
            if os.path.exists(archivo):
                try:
                    with open(archivo, 'r') as f:
                        data = json.load(f)
                        if archivo == 'config_usuario.json':
                            self.config.datos_pago.update(data.get('datos_pago', {}))
                            self.config.tarjeta.update(data.get('tarjeta', {}))
                            self.config.paypal.update(data.get('paypal', {}))
                            self.config.telegram.update(data.get('telegram', {}))
                            self.config.whatsapp.update(data.get('whatsapp', {}))
                            if self.config.telegram.get('bot_token'):
                                TELEGRAM_CONFIG['bot_token'] = self.config.telegram['bot_token']
                            if self.config.telegram.get('chat_id'):
                                TELEGRAM_CONFIG['chat_id'] = self.config.telegram['chat_id']
                        elif archivo == 'preventas.json':
                            self.preventas = data if isinstance(data, list) else data.get('preventas', [])
                        elif archivo == 'productos.json':
                            self.productos = data if isinstance(data, list) else data.get('productos', [])
                    self.add_log(f"✓ Cargado: {archivo}")
                except Exception as e:
                    self.add_log(f"✗ Error cargando {archivo}: {e}")

    def guardar_configuracion(self):
        config = {
            'datos_pago': self.config.datos_pago,
            'tarjeta': self.config.tarjeta,
            'paypal': self.config.paypal,
            'telegram': self.config.telegram,
            'whatsapp': self.config.whatsapp
        }
        with open('config_usuario.json', 'w') as f:
            json.dump(config, f, indent=2)
        with open('preventas.json', 'w') as f:
            json.dump(self.preventas, f, indent=2)
        with open('productos.json', 'w') as f:
            json.dump(self.productos, f, indent=2)
        self.add_log("✓ Configuración guardada")

    def add_log(self, mensaje):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.logs.append(f"[{timestamp}] {mensaje}")
        if len(self.logs) > 200:
            self.logs = self.logs[-200:]
        logging.info(mensaje)

    def enviar_telegram(self, mensaje):
        try:
            token = TELEGRAM_CONFIG.get('bot_token') or self.config.telegram.get('bot_token')
            chat_id = TELEGRAM_CONFIG.get('chat_id') or self.config.telegram.get('chat_id')
            if token and chat_id:
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                requests.post(url, json={'chat_id': chat_id, 'text': mensaje, 'parse_mode': 'HTML'}, timeout=5)
                self.add_log("📱 Telegram enviado")
        except Exception as e:
            self.add_log(f"✗ Error Telegram: {e}")

    def enviar_whatsapp(self, mensaje):
        try:
            numero = self.config.whatsapp.get('numero', '')
            if numero and self.config.whatsapp.get('activo'):
                kit.sendwhatmsg_instantly(f"+{numero}", mensaje, wait_time=10, tab_close=True)
                self.add_log("📱 WhatsApp enviado")
            else:
                self.add_log("✗ WhatsApp no configurado o inactivo (revisa /configuracion)")
        except Exception as e:
            self.add_log(f"✗ Error WhatsApp: {e}")

    def notificar(self, mensaje):
        """Envía notificación SOLO por WhatsApp (Telegram desactivado)"""
        self.enviar_whatsapp(mensaje)
        self.add_log(f"📱 Notificación enviada: {mensaje[:50]}...")

    def iniciar_monitoreo_automatico(self):
        if self.productos:
            hilo = threading.Thread(target=self.monitorear_stock, daemon=True)
            hilo.start()
            self.add_log("▶️ Monitoreo automático iniciado")
        if self.preventas:
            hilo = threading.Thread(target=self.monitorear_preventas, daemon=True)
            hilo.start()
            self.add_log("▶️ Monitoreo preventas iniciado")

    def monitorear_stock(self):
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        while self.en_ejecucion:
            for p in self.productos:
                if not p.get('notificado'):
                    try:
                        response = requests.get(p['url'], headers=headers, timeout=10)
                        if response.status_code == 200:
                            text = response.text.lower()
                            disponible = False
                            tienda = p['tienda']

                            if tienda == 'topps':
                                disponible = 'add to cart' in text
                            elif tienda == 'game':
                                disponible = 'añadir a la cesta' in text or 'add to basket' in text
                            elif tienda == 'inside_box':
                                disponible = 'in den warenkorb' in text
                            elif tienda == 'amazon':
                                disponible = 'añadir al carrito' in text or 'add to cart' in text
                            elif tienda == 'ebay':
                                disponible = 'buy it now' in text or 'add to cart' in text
                            elif tienda == 'cardmarket':
                                disponible = 'add to cart' in text
                            elif tienda == 'fnac':
                                disponible = 'ajouter au panier' in text or 'añadir a la cesta' in text
                            elif tienda == 'elcorteingles':
                                disponible = 'añadir a la cesta' in text
                            elif tienda == 'aliexpress':
                                disponible = 'add to cart' in text
                            elif tienda == 'wallapop':
                                disponible = 'comprar' in text
                            elif tienda == 'carrefour':
                                disponible = 'añadir a la cesta' in text and 'sin stock' not in text
                            elif tienda == 'reinodecartas':
                                disponible = 'añadir al carrito' in text and 'agotado' not in text
                            elif tienda == 'pokestore_fr':
                                disponible = 'ajouter au panier' in text
                            elif tienda == 'checollect':
                                disponible = 'añadir al carrito' in text and 'agotado' not in text
                            elif tienda == 'outpost':
                                disponible = 'add to cart' in text
                            elif tienda == 'universetcg':
                                disponible = 'add to cart' in text
                            elif tienda == 'maximus':
                                disponible = 'in winkelwagen' in text
                            else:
                                disponible = any(w in text for w in ['add to cart', 'añadir al carrito', 'buy now', 'comprar', 'in stock', 'disponible', 'available'])

                            if disponible:
                                p['disponible'] = True
                                p['notificado'] = True
                                self.notificar(f"🔔 ¡STOCK DISPONIBLE!\n\n📦 {p['nombre']}\n🏪 {p['tienda']}\n🔗 {p['url']}")
                                self.add_log(f"🔔 Stock: {p['nombre']}")
                    except Exception as e:
                        self.add_log(f"✗ Error: {e}")
            self.guardar_configuracion()
            for _ in range(30):
                if not self.en_ejecucion:
                    break
                time.sleep(1)

    def monitorear_preventas(self):
        while self.en_ejecucion:
            for p in self.preventas:
                if p.get('estado') in ['pendiente', 'error']:
                    try:
                        response = requests.get(p['url'], timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
                        if any(w in response.text.lower() for w in ['preventa', 'reservar', 'añadir al carrito']):
                            p['estado'] = 'en_carrito'
                            self.notificar(f"✅ ¡Preventa disponible!\n\n{p['url']}")
                    except Exception as e:
                        self.add_log(f"✗ Error: {e}")
            self.guardar_configuracion()
            for _ in range(300):
                if not self.en_ejecucion:
                    break
                time.sleep(1)

sistema = SistemaBot()

# ========== DECORADOR ==========
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ========== RUTAS ==========
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('username') == USUARIO_ADMIN and request.form.get('password') == PASSWORD_ADMIN:
            session['logged_in'] = True
            return redirect(url_for('index'))
        flash('Credenciales incorrectas', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html',
                         estado=sistema.en_ejecucion,
                         preventas=len(sistema.preventas),
                         productos=len(sistema.productos),
                         whatsapp_activo=sistema.config.whatsapp.get('activo', False),
                         fecha=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

@app.route('/configuracion', methods=['GET', 'POST'])
@login_required
def configuracion():
    if request.method == 'POST':
        d = request.form
        sistema.config.datos_pago['nombre'] = d.get('nombre', '')
        sistema.config.datos_pago['apellido'] = d.get('apellido', '')
        sistema.config.datos_pago['direccion'] = d.get('direccion', '')
        sistema.config.datos_pago['ciudad'] = d.get('ciudad', '')
        sistema.config.datos_pago['codigo_postal'] = d.get('codigo_postal', '')
        sistema.config.datos_pago['telefono'] = d.get('telefono', '')
        sistema.config.datos_pago['email'] = d.get('email', '')
        sistema.config.tarjeta['numero'] = d.get('tarjeta_numero', '')
        sistema.config.tarjeta['mes_expiracion'] = d.get('tarjeta_mes', '')
        sistema.config.tarjeta['anio_expiracion'] = d.get('tarjeta_anio', '')
        sistema.config.tarjeta['cvv'] = d.get('tarjeta_cvv', '')
        sistema.config.tarjeta['titular'] = d.get('tarjeta_titular', '')
        sistema.config.telegram['bot_token'] = d.get('telegram_token', '')
        sistema.config.telegram['chat_id'] = d.get('telegram_chat_id', '')
        sistema.config.whatsapp['numero'] = d.get('whatsapp_numero', '')
        sistema.config.whatsapp['activo'] = d.get('whatsapp_activo') == 'on'

        if sistema.config.telegram['bot_token']:
            TELEGRAM_CONFIG['bot_token'] = sistema.config.telegram['bot_token']
        if sistema.config.telegram['chat_id']:
            TELEGRAM_CONFIG['chat_id'] = sistema.config.telegram['chat_id']

        sistema.guardar_configuracion()
        flash('Configuración guardada', 'success')
        return redirect(url_for('configuracion'))

    return render_template('configuracion.html', config=sistema.config, telegram_config=TELEGRAM_CONFIG)

@app.route('/preventas')
@login_required
def preventas():
    return render_template('preventas.html', preventas=sistema.preventas)

@app.route('/productos')
@login_required
def productos():
    return render_template('productos.html', productos=sistema.productos)

# ========== API ==========
@app.route('/api/estado')
@login_required
def api_estado():
    return jsonify({
        'ejecutando': sistema.en_ejecucion,
        'preventas': len(sistema.preventas),
        'productos': len(sistema.productos),
        'whatsapp': sistema.config.whatsapp.get('activo', False),
        'telegram': bool(TELEGRAM_CONFIG['bot_token'])
    })

@app.route('/api/preventas/agregar', methods=['POST'])
@login_required
def api_agregar_preventa():
    data = request.json
    url = data.get('url', '').strip()
    cantidad = int(data.get('cantidad', 1))
    if not url or 'tcgfactory.com' not in url:
        return jsonify({'success': False, 'error': 'URL no válida'})
    for p in sistema.preventas:
        if p['url'] == url:
            return jsonify({'success': False, 'error': 'Ya existe'})
    sistema.preventas.append({'url': url, 'cantidad': cantidad, 'estado': 'pendiente', 'fecha': datetime.now().isoformat()})
    sistema.guardar_configuracion()
    sistema.notificar(f"📦 Nueva preventa: {url}")
    return jsonify({'success': True})

@app.route('/api/preventas/eliminar/<int:index>', methods=['DELETE'])
@login_required
def api_eliminar_preventa(index):
    if 0 <= index < len(sistema.preventas):
        sistema.preventas.pop(index)
        sistema.guardar_configuracion()
        return jsonify({'success': True})
    return jsonify({'success': False})

@app.route('/api/preventas/verificar', methods=['POST'])
@login_required
def api_verificar_preventas():
    resultados = []
    for p in sistema.preventas:
        try:
            r = requests.get(p['url'], timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
            disponible = any(w in r.text.lower() for w in ['preventa', 'reservar', 'añadir al carrito'])
            resultados.append({'url': p['url'][:50], 'disponible': disponible})
        except:
            resultados.append({'url': p['url'][:50], 'disponible': False})
    return jsonify({'success': True, 'resultados': resultados})

@app.route('/api/productos/agregar', methods=['POST'])
@login_required
def api_agregar_producto():
    data = request.json
    nombre = data.get('nombre', '').strip()
    url = data.get('url', '').strip()
    if not nombre or not url:
        return jsonify({'success': False, 'error': 'Nombre y URL requeridos'})

    tienda = None
    if 'topps.com' in url:
        tienda = 'topps'
    elif 'game.es' in url:
        tienda = 'game'
    elif 'inside-the-box.de' in url:
        tienda = 'inside_box'
    elif 'amazon.' in url:
        tienda = 'amazon'
    elif 'ebay.' in url:
        tienda = 'ebay'
    elif 'cardmarket.com' in url:
        tienda = 'cardmarket'
    elif 'fnac.es' in url:
        tienda = 'fnac'
    elif 'elcorteingles.' in url:
        tienda = 'elcorteingles'
    elif 'aliexpress.com' in url:
        tienda = 'aliexpress'
    elif 'wallapop.com' in url:
        tienda = 'wallapop'
    elif 'carrefour.es' in url:
        tienda = 'carrefour'
    elif 'reinodecartas.com' in url:
        tienda = 'reinodecartas'
    elif 'pokestore-france.com' in url:
        tienda = 'pokestore_fr'
    elif 'checollect.es' in url:
        tienda = 'checollect'
    elif 'outpostbrussels.be' in url:
        tienda = 'outpost'
    elif 'universetcg.com' in url:
        tienda = 'universetcg'
    elif 'maximus.be' in url:
        tienda = 'maximus'
    else:
        tienda = 'otra'

    for p in sistema.productos:
        if p['url'] == url:
            return jsonify({'success': False, 'error': 'Ya existe'})

    sistema.productos.append({
        'nombre': nombre, 'url': url, 'tienda': tienda,
        'disponible': False, 'notificado': False,
        'fecha': datetime.now().isoformat()
    })
    sistema.guardar_configuracion()
    sistema.notificar(f"📦 Nuevo producto: {nombre} ({tienda})")
    return jsonify({'success': True})

@app.route('/api/productos/eliminar/<int:index>', methods=['DELETE'])
@login_required
def api_eliminar_producto(index):
    if 0 <= index < len(sistema.productos):
        sistema.productos.pop(index)
        sistema.guardar_configuracion()
        return jsonify({'success': True})
    return jsonify({'success': False})

@app.route('/api/productos/verificar', methods=['POST'])
@login_required
def api_verificar_productos():
    resultados = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    for p in sistema.productos:
        try:
            r = requests.get(p['url'], headers=headers, timeout=10)
            disponible = False
            if r.status_code == 200:
                text = r.text.lower()
                tienda = p['tienda']
                if tienda == 'topps':
                    disponible = 'add to cart' in text
                elif tienda == 'game':
                    disponible = 'añadir a la cesta' in text or 'add to basket' in text
                elif tienda == 'inside_box':
                    disponible = 'in den warenkorb' in text
                elif tienda == 'amazon':
                    disponible = 'añadir al carrito' in text
                elif tienda == 'ebay':
                    disponible = 'buy it now' in text
                elif tienda == 'cardmarket':
                    disponible = 'add to cart' in text
                elif tienda == 'fnac':
                    disponible = 'ajouter au panier' in text or 'añadir a la cesta' in text
                elif tienda == 'elcorteingles':
                    disponible = 'añadir a la cesta' in text
                elif tienda == 'aliexpress':
                    disponible = 'add to cart' in text
                elif tienda == 'wallapop':
                    disponible = 'comprar' in text
                elif tienda == 'carrefour':
                    disponible = 'añadir a la cesta' in text and 'sin stock' not in text
                elif tienda == 'reinodecartas':
                    disponible = 'añadir al carrito' in text and 'agotado' not in text
                elif tienda == 'pokestore_fr':
                    disponible = 'ajouter au panier' in text
                elif tienda == 'checollect':
                    disponible = 'añadir al carrito' in text and 'agotado' not in text
                elif tienda == 'outpost':
                    disponible = 'add to cart' in text
                elif tienda == 'universetcg':
                    disponible = 'add to cart' in text
                elif tienda == 'maximus':
                    disponible = 'in winkelwagen' in text
                else:
                    disponible = any(w in text for w in ['add to cart', 'añadir al carrito', 'buy now', 'comprar', 'in stock', 'disponible'])
            p['disponible'] = disponible
            resultados.append({'nombre': p['nombre'], 'disponible': disponible})
        except:
            resultados.append({'nombre': p['nombre'], 'disponible': False})
    sistema.guardar_configuracion()
    return jsonify({'success': True, 'resultados': resultados})

@app.route('/api/logs')
@login_required
def api_logs():
    return jsonify({'logs': sistema.logs[-50:]})

@app.route('/api/notificar', methods=['POST'])
@login_required
def api_notificar():
    sistema.notificar("🔔 Prueba desde el Bot de Compras\n✅ Todo funcionando correctamente")
    return jsonify({'success': True})

@app.route('/api/whatsapp/conectar', methods=['POST'])
@login_required
def api_whatsapp_conectar():
    webbrowser.open('https://web.whatsapp.com')
    return jsonify({'success': True, 'mensaje': 'WhatsApp Web abierto. Escanea el QR con tu móvil.'})

@app.route('/api/whatsapp/probar', methods=['POST'])
@login_required
def api_whatsapp_probar():
    sistema.enviar_whatsapp("🔔 Prueba desde Bot de Compras\n✅ WhatsApp funcionando")
    return jsonify({'success': True})

# ========== INICIO ==========
if __name__ == '__main__':
    if not os.path.exists('templates'):
        os.makedirs('templates')

    print("="*60)
    print("🤖 BOT DE COMPRAS AUTOMÁTICAS 24/7")
    print("="*60)
    print()
    print("🌐 http://localhost:5000")
    print("👤 Usuario: admin")
    print("🔑 Contraseña: admin123")
    print()
    print("📱 Notificaciones: WhatsApp")
    print()
    print("⚡ Configura en:")
    print("   http://localhost:5000/configuracion")
    print("="*60)

    app.run(host='0.0.0.0', port=5000, debug=True)
